"""x-anylabeling (LabelMe JSON) format importer.

x-anylabeling saves one .json sidecar file per image:
  frame_00000.jpg  →  frame_00000.json

JSON structure:
  {
    "version": "3.2.1",
    "shapes": [{
      "label": "person",
      "points": [[x1,y1], [x2,y2], [x3,y3], [x4,y4]],
      "shape_type": "rectangle" | "polygon" | "point" | "line" | "circle",
      ...
    }],
    "imagePath": "frame_00000.jpg",
    "imageHeight": 1440,
    "imageWidth": 2560
  }

分类标注以图像级 ``flags.classification`` 承载（逗号分隔的类名），
导入时还原为内部 ``Classification`` 标注。
"""

import asyncio
import io
import json
import math
import os
import posixpath
import tempfile
import uuid
import zipfile
from collections import Counter
from datetime import datetime

from sqlalchemy import delete, func, select

from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.dataset.media import (
    content_hash,
    content_type_for,
    process_image,
)
from app.api.v1.module_annotation.dataset.model import (
    AnnotationImageModel,
    AnnotationType,
    DatasetModel,
    ImageStatus,
)
from app.api.v1.module_annotation.task.model import AnnotationTaskModel, TaskStatus
from app.config.setting import settings
from app.core.database import async_db_session
from app.core.logger import log
from app.utils.s3_client import s3_client

# 类别颜色调色板，按序循环分配
_CLASS_COLORS = [
    "#FF3838", "#FF9D97", "#FF701F", "#FFB21D", "#CFD231",
    "#48F90A", "#92CC17", "#3DDB86", "#1A9334", "#00D4BB",
    "#2C99A8", "#00C2FF", "#344593", "#6473FF", "#0018EC",
    "#8438FF", "#520085", "#CB38FF", "#FF95C8", "#FF37C7",
]


async def import_x_anylabeling_zip(zip_file, dataset_id: int, user_id: int) -> dict:
    """Parse x-anylabeling ZIP, import images + annotations into dataset."""
    extract_dir = tempfile.mkdtemp(prefix="xal_")
    try:
        with zipfile.ZipFile(zip_file, "r") as zf:
            _safe_extract(zf, extract_dir)
        return await _import_from_dir(extract_dir, dataset_id, user_id)
    finally:
        import shutil
        shutil.rmtree(extract_dir, ignore_errors=True)


def _safe_extract(zf: zipfile.ZipFile, dest: str) -> None:
    """解压并拒绝任何越界的 zip 成员（zip-slip）。"""
    dest_abs = os.path.abspath(dest)
    for member in zf.namelist():
        target = os.path.abspath(os.path.join(dest, member))
        if not (target == dest_abs or target.startswith(dest_abs + os.sep)):
            raise ValueError(f"非法的压缩包路径: {member}")
    zf.extractall(dest)


def _infer_task_type(shapes_all: list[dict]) -> str:
    """按形状推断任务类型。"""
    types = {s.get("shape_type") for s in shapes_all}
    if "rotation" in types:
        return "rotated_detection"
    if types == {"point"}:
        return "keypoint"
    if types == {"polygon"}:
        return "segmentation"
    return "detection"


def _classification_names(flags: dict | None) -> list[str]:
    """解析 sidecar 的图像级分类 flags（``classification`` 逗号分隔）。"""
    if not isinstance(flags, dict):
        return []
    raw = flags.get("classification")
    if not raw or not isinstance(raw, str):
        return []
    return [name.strip() for name in raw.split(",") if name.strip()]


def _class_color(index: int) -> str:
    """按调色板循环取颜色。"""
    return _CLASS_COLORS[index % len(_CLASS_COLORS)]


async def _import_from_dir(src_dir: str, dataset_id: int, user_id: int) -> dict:
    """Import x-anylabeling data from an extracted directory."""
    # Collect image files and their JSON sidecars.
    # 图片以「相对目录 + stem + 小写扩展名」为键，避免同目录同 stem 不同扩展名
    # （img.jpg / img.png）互相覆盖；sidecar 仍以「相对目录 + stem」配对，
    # 保证 JSON 与任意扩展名的图片都能匹配。
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    json_files: dict[tuple[str, str], str] = {}  # (reldir, stem) → json_path
    image_entries: list[dict] = []  # 每张图片一条，保留 reldir/stem/ext/文件名

    for root, _, files in os.walk(src_dir):
        for f in files:
            path = os.path.join(root, f)
            relpath = os.path.relpath(path, src_dir)
            reldir, base = os.path.split(relpath)
            stem, ext = os.path.splitext(base)
            ext_lower = ext.lower()
            if ext_lower == ".json":
                json_files[(reldir, stem)] = path
            elif ext_lower in image_extensions:
                image_entries.append(
                    {"path": path, "reldir": reldir, "stem": stem, "ext": ext, "basename": base}
                )

    if not image_entries:
        return {"imported": 0, "total_images": 0, "total_annotations": 0, "class_mapping": {}, "error": "ZIP 中未找到图片文件"}

    # 派生唯一显示 filename：basename 唯一时保持原样；否则用相对目录前缀消歧
    # （如 d2/img.png → d2__img.png），避免导出时按 filename 写入互相覆盖。
    basename_counts = Counter(e["basename"] for e in image_entries)
    used_filenames: set[str] = set()
    for e in image_entries:
        if basename_counts[e["basename"]] == 1:
            candidate = e["basename"]
        else:
            prefix = e["reldir"].replace("\\", "__").replace("/", "__")
            candidate = f"{prefix}__{e['basename']}" if prefix else e["basename"]
        final = candidate
        idx = 1
        while final in used_filenames:
            candidate_stem, candidate_ext = os.path.splitext(candidate)
            idx += 1
            final = f"{candidate_stem}_{idx}{candidate_ext}"
        used_filenames.add(final)
        e["filename"] = final

    # Scan all JSON files to build class mapping (label → sequential class_id)
    all_labels: set[str] = set()
    all_shapes: list[dict] = []
    for jp in json_files.values():
        try:
            with open(jp, encoding="utf-8") as f:
                data = json.load(f)
            shapes = data.get("shapes", []) or []
            all_shapes.extend(shapes)
            for shape in shapes:
                label = (shape.get("label") or "").strip()
                if label:
                    all_labels.add(label)
            for name in _classification_names(data.get("flags")):
                all_labels.add(name)
        except Exception:
            continue

    sorted_labels = sorted(all_labels)
    class_mapping = {label: idx for idx, label in enumerate(sorted_labels)}

    now = datetime.now()
    imported_count = 0
    total_annotations = 0

    # 按实际形状推断任务类型
    task_type = AnnotationType(_infer_task_type(all_shapes))

    async with async_db_session.begin() as db:
        # Create an annotation task for the imported data
        ds = await db.get(DatasetModel, dataset_id)
        task_name = f"[导入] {ds.name if ds else 'dataset_' + str(dataset_id)} - x-anylabeling"
        ann_task = AnnotationTaskModel(
            dataset_id=dataset_id,
            name=task_name,
            task_type=task_type,
            status=TaskStatus.COMPLETED,
            classes=[
                {"id": cid, "name": label, "color": _class_color(cid)}
                for label, cid in sorted(class_mapping.items(), key=lambda x: x[1])
            ],
            progress=100,
            completed_at=now,
            created_id=user_id,
        )
        db.add(ann_task)
        await db.flush()
        task_id = ann_task.id

        for entry in image_entries:
            img_path = entry["path"]
            # Upload image to RustFS（object_key 加 uuid 前缀，重复导入不覆盖）
            ext = entry["ext"]
            object_key = f"annotations/dataset_{dataset_id}/{uuid.uuid4().hex}{ext}"
            with open(img_path, "rb") as f:
                s3_client.upload_fileobj(f, object_key)

            # Load sidecar once: dimensions + shapes + classification flags
            img_height = 0
            img_width = 0
            shapes: list[dict] = []
            classification_names: list[str] = []
            json_path = json_files.get((entry["reldir"], entry["stem"]))
            if json_path:
                try:
                    with open(json_path, encoding="utf-8") as f:
                        meta = json.load(f)
                    img_height = meta.get("imageHeight", 0) or 0
                    img_width = meta.get("imageWidth", 0) or 0
                    shapes = meta.get("shapes", []) or []
                    classification_names = _classification_names(meta.get("flags"))
                except Exception:
                    pass
            if not img_height or not img_width:
                img_height, img_width = _get_image_size(img_path)

            # Create image record（filename 唯一，重复 basename 用相对目录前缀消歧）
            filename = entry["filename"]
            img_rec = AnnotationImageModel(
                dataset_id=dataset_id,
                filename=filename,
                object_key=object_key,
                status=ImageStatus.ANNOTATED,
                width=img_width,
                height=img_height,
                created_id=user_id,
            )
            db.add(img_rec)
            await db.flush()

            # Parse annotations
            annotations = []
            for shape in shapes:
                ann = _shape_to_annotation(shape, class_mapping, img_width, img_height)
                if ann:
                    annotations.append(ann)

            # 分类 flags → Classification 标注
            class_ids = [class_mapping[n] for n in classification_names if n in class_mapping]
            if class_ids:
                annotations.append(
                    {
                        "id": uuid.uuid4().hex,
                        "type": "Classification",
                        "class_id": class_ids[0],
                        "class_ids": class_ids,
                        "label": classification_names[0],
                    }
                )

            # Create annotation record
            if annotations:
                total_annotations += len(annotations)
                ann_rec = AnnotationRecordModel(
                    task_id=task_id,
                    image_id=img_rec.id,
                    annotation_data=annotations,
                    version=1,
                    created_id=user_id,
                )
                db.add(ann_rec)

            imported_count += 1

        # 重算数据集计数（避免重复导入累加导致 double count）
        await db.flush()
        ds = await db.get(DatasetModel, dataset_id)
        if ds:
            ds.image_count = await db.scalar(
                select(func.count(AnnotationImageModel.id)).where(
                    AnnotationImageModel.dataset_id == dataset_id,
                    AnnotationImageModel.is_deleted == False,  # noqa: E712
                )
            ) or 0
            ds.annotated_count = await db.scalar(
                select(func.count(func.distinct(AnnotationRecordModel.image_id)))
                .select_from(AnnotationRecordModel)
                .join(AnnotationImageModel, AnnotationImageModel.id == AnnotationRecordModel.image_id)
                .where(
                    AnnotationImageModel.dataset_id == dataset_id,
                    AnnotationImageModel.is_deleted == False,  # noqa: E712
                    AnnotationRecordModel.is_deleted == False,  # noqa: E712
                )
            ) or 0

    # Update task progress after transaction commits
    if task_id:
        from app.api.v1.module_annotation.task.service import TaskService
        try:
            await TaskService.update_progress(task_id)
        except Exception as e:
            log.warning(f"update_progress failed: {e}")

    return {
        "imported": imported_count,
        "total_images": len(image_entries),
        "total_annotations": total_annotations,
        "class_mapping": class_mapping,
        "task_id": task_id,
        "task_name": task_name,
    }


def _shape_to_annotation(shape: dict, class_mapping: dict, img_w: int, img_h: int) -> dict | None:
    """Convert an x-anylabeling shape to internal annotation format."""
    label = shape.get("label", "").strip()
    if not label or label not in class_mapping:
        return None
    class_id = class_mapping[label]
    shape_type = shape.get("shape_type", "rectangle")
    points = shape.get("points", [])

    if not points:
        return None

    if shape_type == "rectangle" and len(points) >= 2:
        xs = [p[0] for p in points[:4]]
        ys = [p[1] for p in points[:4]]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        return {
            "id": uuid.uuid4().hex,
            "type": "AxisAlignedBox",
            "class_id": class_id,
            "label": label,
            "x1": x1 / img_w if img_w else 0,
            "y1": y1 / img_h if img_h else 0,
            "x2": x2 / img_w if img_w else 0,
            "y2": y2 / img_h if img_h else 0,
        }
    elif shape_type == "rotation" and len(points) >= 4:
        # 内部约定：angle 在像素空间定义，width 按图像宽归一化、height 按图像高
        # 归一化（与 exporter.xany_shapes / rotated_box_to_obb_corners 对齐）。
        # 若先在归一化空间计算 hypot/atan2，非方形图像上会得到错误的角度与宽高。
        dx = points[1][0] - points[0][0]
        dy = points[1][1] - points[0][1]
        width = math.hypot(dx, dy) / img_w if img_w else 0
        angle = math.atan2(dy, dx)
        ex = points[2][0] - points[1][0]
        ey = points[2][1] - points[1][1]
        height = math.hypot(ex, ey) / img_h if img_h else 0
        cx = sum(p[0] for p in points[:4]) / 4 / img_w if img_w else 0
        cy = sum(p[1] for p in points[:4]) / 4 / img_h if img_h else 0
        return {
            "id": uuid.uuid4().hex,
            "type": "RotatedBox",
            "class_id": class_id,
            "label": label,
            "cx": cx,
            "cy": cy,
            "width": width,
            "height": height,
            "angle": angle,
        }
    elif shape_type == "polygon" and len(points) >= 3:
        return {
            "id": uuid.uuid4().hex,
            "type": "Polygon",
            "class_id": class_id,
            "label": label,
            "points": [
                {"x": p[0] / img_w if img_w else 0, "y": p[1] / img_h if img_h else 0}
                for p in points
            ],
        }
    elif shape_type == "point" and len(points) >= 1:
        x = points[0][0] / img_w if img_w else 0
        y = points[0][1] / img_h if img_h else 0
        size = min(1.0 / img_w if img_w else 0.01, 0.01)
        return {
            "id": uuid.uuid4().hex,
            "type": "AxisAlignedBox",
            "class_id": class_id,
            "label": label,
            "x1": max(0, x - size),
            "y1": max(0, y - size),
            "x2": min(1, x + size),
            "y2": min(1, y + size),
        }
    return None


def _get_image_size(img_path: str) -> tuple[int, int]:
    """Get image dimensions without loading the full image."""
    try:
        from PIL import Image
        with Image.open(img_path) as img:
            return img.height, img.width
    except Exception:
        return 0, 0


async def import_x_anylabeling_bytes(
    data: bytes,
    dataset_id: int,
    user_id: int,
    progress_cb=None,
    clear_existing: bool = False,
) -> dict:
    """从 ZIP 字节导入：流式读成员、分批并发上传（含缩略图）、分事务落库。

    ``progress_cb(processed, total, phase)`` 可为 None；不写盘，故无 zip-slip 风险。
    ``clear_existing=True`` 时先清空该数据集现有图片/标注/任务（避免重复叠加）。
    """
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        json_files: dict[tuple[str, str], str] = {}
        entries: list[dict] = []
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            reldir, base = posixpath.split(name)
            stem, ext = posixpath.splitext(base)
            el = ext.lower()
            if el == ".json":
                json_files[(reldir, stem)] = name
            elif el in image_extensions:
                entries.append({"zip_name": name, "reldir": reldir, "stem": stem,
                                "ext": ext, "basename": base})

        if not entries:
            return {"imported": 0, "total_images": 0, "total_annotations": 0,
                    "class_mapping": {}, "task_id": None,
                    "error": "ZIP 中未找到图片文件"}

        # filename 消歧（重复 basename 用相对目录前缀）
        basename_counts = Counter(e["basename"] for e in entries)
        used: set[str] = set()
        for e in entries:
            if basename_counts[e["basename"]] == 1:
                cand = e["basename"]
            else:
                prefix = e["reldir"].replace("/", "__")
                cand = f"{prefix}__{e['basename']}" if prefix else e["basename"]
            final, idx = cand, 1
            while final in used:
                s, x = os.path.splitext(cand)
                idx += 1
                final = f"{s}_{idx}{x}"
            used.add(final)
            e["filename"] = final

        # 扫描 JSON：类映射 + 形状集合
        all_labels: set[str] = set()
        all_shapes: list[dict] = []
        jsons_cache: dict[str, dict] = {}
        for _key, zname in json_files.items():
            try:
                meta = json.loads(zf.read(zname).decode("utf-8"))
            except Exception:
                continue
            jsons_cache[zname] = meta
            shapes = meta.get("shapes") or []
            all_shapes.extend(shapes)
            for s in shapes:
                lb = (s.get("label") or "").strip()
                if lb:
                    all_labels.add(lb)
            for nm in _classification_names(meta.get("flags")):
                all_labels.add(nm)

        class_mapping = {lb: i for i, lb in enumerate(sorted(all_labels))}
        task_type = AnnotationType(_infer_task_type(all_shapes))
        total = len(entries)
        if progress_cb:
            progress_cb(0, total, "scan")

        # 可选：导入前清空该数据集现有图片/标注/任务（避免重复导入叠加）
        if clear_existing:
            async with async_db_session() as db:
                old_rows = (
                    await db.execute(
                        select(
                            AnnotationImageModel.object_key,
                            AnnotationImageModel.thumbnail_key,
                        ).where(AnnotationImageModel.dataset_id == dataset_id)
                    )
                ).fetchall()
            old_keys = [k for pair in old_rows for k in pair if k]
            if old_keys:
                s3_client.delete_objects(old_keys)
            async with async_db_session.begin() as db:
                old_img_ids = (
                    await db.execute(
                        select(AnnotationImageModel.id).where(
                            AnnotationImageModel.dataset_id == dataset_id
                        )
                    )
                ).scalars().all()
                if old_img_ids:
                    await db.execute(
                        delete(AnnotationRecordModel).where(
                            AnnotationRecordModel.image_id.in_(old_img_ids)
                        )
                    )
                await db.execute(
                    delete(AnnotationImageModel).where(
                        AnnotationImageModel.dataset_id == dataset_id
                    )
                )
                await db.execute(
                    delete(AnnotationTaskModel).where(
                        AnnotationTaskModel.dataset_id == dataset_id
                    )
                )

        async with async_db_session.begin() as db:
            ds = await db.get(DatasetModel, dataset_id)
            ann_task = AnnotationTaskModel(
                dataset_id=dataset_id,
                name=f"[导入] {ds.name if ds else 'dataset_' + str(dataset_id)} - x-anylabeling",
                task_type=task_type,
                status=TaskStatus.COMPLETED,
                classes=[{"id": cid, "name": lb, "color": _class_color(cid)}
                         for lb, cid in sorted(class_mapping.items(), key=lambda x: x[1])],
                progress=100,
                completed_at=datetime.now(),
                created_id=user_id,
            )
            db.add(ann_task)
            await db.flush()
            task_id = ann_task.id
            task_name = ann_task.name

        # 已存在的内容哈希（用于去重）
        async with async_db_session() as db:
            seen: set[str] = set(
                (
                    await db.execute(
                        select(AnnotationImageModel.content_hash).where(
                            AnnotationImageModel.dataset_id == dataset_id,
                            AnnotationImageModel.is_deleted == False,  # noqa: E712
                            AnnotationImageModel.content_hash.isnot(None),
                        )
                    )
                ).scalars().all()
            )

        sem = asyncio.Semaphore(max(1, settings.ANNOTATION_IMPORT_CONCURRENCY))
        batch_size = max(1, settings.ANNOTATION_IMPORT_BATCH_SIZE)
        imported = 0
        processed = 0
        skipped_duplicate = 0
        total_annotations = 0

        for start in range(0, total, batch_size):
            batch = entries[start:start + batch_size]
            prepared: list[tuple[dict, bytes, dict | None]] = []
            for e in batch:
                img_bytes = zf.read(e["zip_name"])
                jname = json_files.get((e["reldir"], e["stem"]))
                prepared.append((e, img_bytes, jsons_cache.get(jname) if jname else None))

            async def _proc(e: dict, img_bytes: bytes) -> dict:
                async with sem:
                    digest = content_hash(img_bytes)
                    if digest in seen:
                        return {"duplicate": True}
                    seen.add(digest)
                    w, h, thumb = await asyncio.to_thread(process_image, img_bytes)
                    token = uuid.uuid4().hex
                    key = f"annotations/dataset_{dataset_id}/{token}{e['ext']}"
                    await asyncio.to_thread(
                        s3_client.upload_fileobj, io.BytesIO(img_bytes), key,
                        None, content_type_for(e["ext"]),
                    )
                    tkey = None
                    if thumb:
                        tkey = f"datasets/{dataset_id}/thumbnails/{token}.jpg"
                        await asyncio.to_thread(
                            s3_client.upload_fileobj, io.BytesIO(thumb), tkey,
                            None, "image/jpeg",
                        )
                    return {"key": key, "tkey": tkey, "w": w, "h": h, "hash": digest}

            results = await asyncio.gather(*[_proc(e, b) for e, b, _ in prepared])

            async with async_db_session.begin() as db:
                for (e, _b, meta), r in zip(prepared, results, strict=True):
                    processed += 1
                    if r.get("duplicate"):
                        skipped_duplicate += 1
                        if progress_cb:
                            progress_cb(processed, total, "import")
                        continue
                    mw = (meta or {}).get("imageWidth") or 0
                    mh = (meta or {}).get("imageHeight") or 0
                    img_rec = AnnotationImageModel(
                        dataset_id=dataset_id,
                        filename=e["filename"],
                        object_key=r["key"],
                        thumbnail_key=r["tkey"],
                        content_hash=r.get("hash"),
                        status=ImageStatus.ANNOTATED,
                        width=mw or r["w"],
                        height=mh or r["h"],
                        created_id=user_id,
                    )
                    db.add(img_rec)
                    await db.flush()

                    anns = []
                    for shape in ((meta or {}).get("shapes") or []):
                        ann = _shape_to_annotation(
                            shape, class_mapping, mw or r["w"], mh or r["h"]
                        )
                        if ann:
                            anns.append(ann)
                    names = _classification_names((meta or {}).get("flags"))
                    class_ids = [class_mapping[n] for n in names if n in class_mapping]
                    if class_ids:
                        anns.append({"id": uuid.uuid4().hex, "type": "Classification",
                                     "class_id": class_ids[0], "class_ids": class_ids,
                                     "label": names[0]})
                    if anns:
                        total_annotations += len(anns)
                        db.add(AnnotationRecordModel(
                            task_id=task_id, image_id=img_rec.id,
                            annotation_data=anns, version=1, created_id=user_id,
                        ))
                    imported += 1
                    # 每张图片回调一次，前端 1s 轮询即可看到数字持续增长
                    if progress_cb:
                        progress_cb(processed, total, "import")

        # 收尾：重算数据集计数
        async with async_db_session.begin() as db:
            ds = await db.get(DatasetModel, dataset_id)
            if ds:
                ds.image_count = await db.scalar(
                    select(func.count(AnnotationImageModel.id)).where(
                        AnnotationImageModel.dataset_id == dataset_id,
                        AnnotationImageModel.is_deleted == False,  # noqa: E712
                    )
                ) or 0
                ds.annotated_count = await db.scalar(
                    select(func.count(func.distinct(AnnotationRecordModel.image_id)))
                    .select_from(AnnotationRecordModel)
                    .join(AnnotationImageModel,
                          AnnotationImageModel.id == AnnotationRecordModel.image_id)
                    .where(
                        AnnotationImageModel.dataset_id == dataset_id,
                        AnnotationImageModel.is_deleted == False,  # noqa: E712
                        AnnotationRecordModel.is_deleted == False,  # noqa: E712
                    )
                ) or 0

    if task_id:
        from app.api.v1.module_annotation.task.service import TaskService
        try:
            await TaskService.update_progress(task_id)
        except Exception as e:
            log.warning(f"update_progress failed: {e}")

    return {
        "imported": imported,
        "skipped_duplicate": skipped_duplicate,
        "total_images": total,
        "total_annotations": total_annotations,
        "class_mapping": class_mapping,
        "task_id": task_id,
        "task_name": task_name,
    }
