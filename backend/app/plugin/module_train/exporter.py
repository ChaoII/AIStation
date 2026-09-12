import json
import math
import os

from sqlalchemy import desc, select

from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.dataset.model import AnnotationImageModel
from app.core.database import async_db_session
from app.core.logger import log

from .model import TrainModelRepo


async def prepare_training_data_for_task(dataset_id: int, task_id: int, framework: str, output_dir: str, annotation_task_id: int | None = None, train_ratio: float = 0.8, ocr_rec: bool = False) -> str:
    """Export dataset for training — unified with download, just different YAML path."""
    return await _export_core(dataset_id, task_id, framework, output_dir, annotation_task_id=annotation_task_id, train_ratio=train_ratio, for_training=True, ocr_rec=ocr_rec)


async def export_dataset_for_download(
    dataset_id: int, task_id: int, format: str, output_dir: str,
    annotation_task_id: int | None = None, ocr_rec: bool = True, train_ratio: float = 0.8
) -> str:
    """Export dataset for user download — train/val split, user-friendly YAML."""
    return await _export_core(dataset_id, task_id, format, output_dir, annotation_task_id=annotation_task_id, ocr_rec=ocr_rec, train_ratio=train_ratio, for_training=False)


async def _export_core(
    dataset_id: int, task_id: int, framework: str, output_dir: str,
    annotation_task_id: int | None = None, ocr_rec: bool = True,
    train_ratio: float = 0.8, for_training: bool = False
) -> str:
    """Core export logic shared by training and download."""
    os.makedirs(output_dir, exist_ok=True)
    async with async_db_session() as db:
        result = await db.execute(
            select(AnnotationImageModel).where(AnnotationImageModel.dataset_id == dataset_id)
        )
        images = result.scalars().all()

    if not images:
        log.warning(f"export: dataset {dataset_id} has no images")
        return

    # Determine task_type and class names
    task_type = "detection"
    class_names: dict[int, str] = {}
    classification_mode: str | None = None
    if annotation_task_id:
        from app.api.v1.module_annotation.task.model import AnnotationTaskModel
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task:
                task_type = ann_task.task_type
                classification_mode = ann_task.classification_mode
                if ann_task.classes:
                    for c in (ann_task.classes if isinstance(ann_task.classes, list) else []):
                        class_names[c["id"]] = c.get("name", f"class_{c['id']}")

    if framework == "ultralytics" or framework.startswith("yolo-"):
        if framework.startswith("yolo-"):
            task_type = framework.replace("yolo-", "")
        if task_type in ("cls", "classification"):
            await _export_yolo_cls(
                dataset_id, task_id, images, output_dir, annotation_task_id,
                train_ratio=train_ratio, class_names=class_names, for_training=for_training,
                multi_label=(classification_mode == "multi"),
            )
        else:
            await _export_yolo(dataset_id, task_id, images, output_dir, task_type, annotation_task_id, train_ratio=train_ratio, class_names=class_names, for_training=for_training)
    elif framework == "x-anylabeling":
        await _export_x_anylabeling(dataset_id, task_id, images, output_dir, annotation_task_id, class_names=class_names)
    elif framework == "paddle-ocr":
        # 数据集下载导出 PaddleOCR 格式（det/rec 由 ocr_rec 控制）
        await _export_paddle_ocr(dataset_id, task_id, images, output_dir, annotation_task_id,
                                 export_rec=ocr_rec, train_ratio=train_ratio)
    elif framework == "paddle-mlcls":
        await _export_paddle_mlcls(dataset_id, task_id, images, output_dir, annotation_task_id,
                                   class_names=class_names)
    elif framework == "paddlex":
        # PaddleX OCR：ocr_rec 区分 det(false) / rec(true)
        await _export_paddle_ocr(dataset_id, task_id, images, output_dir, annotation_task_id,
                                 export_rec=ocr_rec, train_ratio=train_ratio)
    else:
        raise ValueError(f"不支持的导出框架: {framework}")

    log.info(f"export {framework} to {output_dir}")


async def _export_yolo(dataset_id: int, task_id: int, images: list, output_dir: str, task_type: str = "detection", annotation_task_id: int | None = None, train_ratio: float = 0.8, class_names: dict | None = None, for_training: bool = False) -> None:
    """Export to YOLO format with train/val split. for_training controls YAML path.

    两遍式：先收集所有图片的最新标注与全局类 id 集合，构建连续映射后再下载图片、
    按映射写标签，避免稀疏类 id（类别删除后）导致 nc/names 越界。
    """
    import random

    from app.utils.s3_client import s3_client

    anns_by_img: dict[int, list] = {}
    used_ids: set[int] = set()
    async with async_db_session() as db:
        for img in images:
            query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
            if annotation_task_id:
                query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
            query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
            record = (await db.execute(query)).scalar_one_or_none()
            anns = record.annotation_data if record and record.annotation_data else []
            anns_by_img[img.id] = anns
            for ann in anns:
                cid = ann.get("class_id")
                if cid is not None and cid != -1:
                    used_ids.add(int(cid))

    class_id_map = build_class_mapping(used_ids)

    random.shuffle(images)
    split_idx = max(1, int(len(images) * train_ratio))
    train_imgs = images[:split_idx]
    val_imgs = images[split_idx:]

    for split_name, split_imgs in [("train", train_imgs), ("val", val_imgs)]:
        img_split = os.path.join(output_dir, "images", split_name)
        label_split = os.path.join(output_dir, "labels", split_name)
        os.makedirs(img_split, exist_ok=True)
        os.makedirs(label_split, exist_ok=True)
        for img in split_imgs:
            img_path = os.path.join(img_split, img.filename)
            if not os.path.exists(img_path):
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
                except Exception as e:
                    log.warning(f"skip {img.filename}: {e}")
                    continue
            anns = anns_by_img.get(img.id, [])
            lines = _format_yolo_lines(anns, task_type, class_id_map=class_id_map,
                                       img_w=img.width or 1, img_h=img.height or 1)
            if lines:
                label_path = os.path.join(label_split,
                                          img.filename.rsplit(".", 1)[0] + ".txt")
                with open(label_path, "w") as f:
                    f.write("\n".join(lines))

    base_path = "/data" if for_training else "."
    sorted_out = list(range(len(class_id_map)))
    extra = pose_extra_yaml(anns_by_img) if task_type in ("keypoint", "pose") else None
    _write_yaml(os.path.join(output_dir, "dataset.yaml"), base_path, sorted_out,
                class_names or {}, class_id_map=class_id_map, extra_yaml=extra)
    log.info(f"yolo: train={len(train_imgs)} val={len(val_imgs)} classes={len(sorted_out)} → {output_dir}")


def build_class_mapping(class_ids: set[int]) -> dict[int, int]:
    """把稀疏的原始类 id 映射为连续 0..n-1（按原始 id 升序）。"""
    return {raw: idx for idx, raw in enumerate(sorted(class_ids))}


def rotated_box_to_obb_corners(cx: float, cy: float, w: float, h: float,
                               angle_rad: float) -> list[float]:
    """归一化旋转框 → YOLO OBB 8 点（左上→右上→右下→左下）。

    先在框自身坐标系取四角，再绕中心按 angle_rad（弧度）旋转；最后从页面左上
    （x+y 最小）起按顺时针重排，保证任意角度下顺序都是 左上→右上→右下→左下。
    """
    hw, hh = w / 2.0, h / 2.0
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    corners: list[tuple[float, float]] = []
    for dx, dy in local:
        corners.append((
            cx + dx * cos_a - dy * sin_a,
            cy + dx * sin_a + dy * cos_a,
        ))
    start = min(range(len(corners)), key=lambda i: corners[i][0] + corners[i][1])
    ordered = corners[start:] + corners[:start]
    out: list[float] = []
    for x, y in ordered:
        out.extend([x, y])
    return out


def _px(v: float, scale: int) -> float:
    return round(float(v) * scale, 4)


def xany_shapes(anns: list, img_w: int, img_h: int, class_names: dict[int, str]) -> list[dict]:
    """工作台归一化标注 → LabelMe/x-anylabeling shapes（像素坐标）。"""
    shapes: list[dict] = []
    for ann in anns:
        cid = ann.get("class_id", 0)
        label = class_names.get(cid, f"class_{cid}")
        base = {"label": label, "group_id": None, "flags": {}}
        t = ann.get("type", "")
        if t in ("AxisAlignedBox", "box"):
            if "x1" in ann:
                x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
            else:
                xc, yc, w, h = ann["x"], ann["y"], ann["width"], ann["height"]
                x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
            pts = [[_px(x1, img_w), _px(y1, img_h)], [_px(x2, img_w), _px(y1, img_h)],
                   [_px(x2, img_w), _px(y2, img_h)], [_px(x1, img_w), _px(y2, img_h)]]
            shapes.append({**base, "points": pts, "shape_type": "rectangle"})
        elif t in ("RotatedBox", "rotated_box"):
            # 旋转必须按像素空间计算（x/y 缩放不同），结果本身就是像素坐标
            px = rotated_box_to_obb_corners(ann["cx"] * img_w, ann["cy"] * img_h,
                                            ann["width"] * img_w, ann["height"] * img_h,
                                            float(ann.get("angle", 0) or 0))
            pts = [[px[i], px[i + 1]] for i in range(0, 8, 2)]
            shapes.append({**base, "points": pts, "shape_type": "rotation"})
        elif t in ("Polygon", "polygon"):
            pts = [[_px(p["x"] if isinstance(p, dict) else p[0], img_w),
                    _px(p["y"] if isinstance(p, dict) else p[1], img_h)] for p in ann.get("points", [])]
            if len(pts) >= 3:
                shapes.append({**base, "points": pts, "shape_type": "polygon"})
        elif t in ("Keypoint", "keypoint"):
            for kp in ann.get("keypoints", []):
                shapes.append({**base,
                               "points": [[_px(kp.get("x", 0), img_w), _px(kp.get("y", 0), img_h)]],
                               "shape_type": "point"})
        elif t in ("Ocr", "ocr"):
            pts = [[_px(p["x"] if isinstance(p, dict) else p[0], img_w),
                    _px(p["y"] if isinstance(p, dict) else p[1], img_h)] for p in ann.get("points", [])]
            if len(pts) >= 3:
                shapes.append({**base, "points": pts, "shape_type": "polygon",
                               "description": ann.get("text", "")})
    return shapes


def _format_yolo_lines(anns: list, task_type: str, class_id_map: dict[int, int] | None = None, img_w: int = 1, img_h: int = 1) -> list[str]:
    """Convert annotations to YOLO label lines based on task_type.

    class_id_map 把原始类 id 映射为连续下标；img_w/img_h 预留给像素坐标标注的归一化。
    坐标约定：本工作台标注为归一化 [0,1]，YOLO 也需归一化，故此处不做缩放。
    """
    lines = []
    for ann in anns:
        raw_cls = ann.get("class_id", 0)
        cls_id = (class_id_map or {}).get(raw_cls, raw_cls)
        ann_type = ann.get("type", "")
        if ann_type in ("AxisAlignedBox", "box"):
            if "x1" in ann:
                x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
            else:
                xc_a, yc_a, w_a, h_a = ann["x"], ann["y"], ann["width"], ann["height"]
                x1, y1, x2, y2 = xc_a - w_a / 2, yc_a - h_a / 2, xc_a + w_a / 2, yc_a + h_a / 2
            if task_type == "rotated_detection":
                lines.append(f"{cls_id} {x1:.6f} {y1:.6f} {x2:.6f} {y1:.6f} {x2:.6f} {y2:.6f} {x1:.6f} {y2:.6f}")
            else:
                lines.append(f"{cls_id} {(x1 + x2) / 2:.6f} {(y1 + y2) / 2:.6f} {x2 - x1:.6f} {y2 - y1:.6f}")
        elif ann_type in ("RotatedBox", "rotated_box"):
            cx, cy = ann["cx"], ann["cy"]
            w, h = ann["width"], ann["height"]
            ang = float(ann.get("angle", 0) or 0)
            if task_type in ("rotated_detection", "obb"):
                # 旋转必须按像素空间计算（x/y 缩放不同），再归一化回 [0,1] 写入标签
                px = rotated_box_to_obb_corners(cx * img_w, cy * img_h, w * img_w, h * img_h, ang)
                pts = [px[i] / (img_w if i % 2 == 0 else img_h) for i in range(8)]
                lines.append(f"{cls_id} " + " ".join(f"{v:.6f}" for v in pts))
            else:
                lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f} {math.degrees(ang):.6f}")
        elif ann_type in ("Polygon", "polygon") and task_type in ("segmentation", "seg"):
            # YOLO Seg: cls_id x1 y1 x2 y2 ... (归一化多边形顶点)
            pts = []
            for p in ann.get("points", []):
                px = p.get("x") if isinstance(p, dict) else p[0]
                py = p.get("y") if isinstance(p, dict) else p[1]
                pts.append(f"{px:.6f} {py:.6f}")
            if len(pts) >= 3:
                lines.append(f"{cls_id} {' '.join(pts)}")
        elif ann_type in ("Keypoint", "keypoint") and task_type in ("keypoint", "pose"):
            # YOLO Pose: cls_id cx cy w h kpx kpy kpv ...（bbox + 关键点，visibility 0/1/2）
            bb = ann.get("bounding_box", {})
            cx, cy = bb.get("cx", 0), bb.get("cy", 0)
            w, h = bb.get("width", 0), bb.get("height", 0)
            parts = [f"{cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"]
            vis_map = {"Visible": 2, "Occluded": 1, "Hidden": 0}
            for kp in ann.get("keypoints", []):
                kx = kp.get("x", 0)
                ky = kp.get("y", 0)
                kv = vis_map.get(kp.get("visibility", ""), 0)
                parts.append(f"{kx:.6f} {ky:.6f} {kv}")
            if len(parts) > 4:
                lines.append(f"{cls_id} {' '.join(parts)}")
    return lines


def pose_extra_yaml(anns_by_img: dict[int, list]) -> dict:
    """当存在关键点标注时，返回 pose 训练所需的 kpt_shape / flip_idx。"""
    k = 0
    for anns in anns_by_img.values():
        for ann in anns:
            if ann.get("type") in ("Keypoint", "keypoint"):
                k = max(k, len(ann.get("keypoints", [])))
    if k <= 0:
        return {}
    return {"kpt_shape": f"[{k}, 3]", "flip_idx": "[" + ", ".join(str(i) for i in range(k)) + "]"}


def _write_yaml(
    path: str,
    base_path: str,
    sorted_classes: list,
    class_names: dict,
    class_id_map: dict[int, int] | None = None,
    extra_yaml: dict | None = None,
) -> None:
    """Write dataset.yaml.

    sorted_classes 为**映射后**的连续下标列表；class_id_map 用于把下标回指原始
    id 以取真实名称（不传时按下标直接取）。
    """
    names_dict: dict[str, str] = {}
    for out_id in sorted_classes:
        raw_id = out_id
        if class_id_map:
            for raw, mapped in class_id_map.items():
                if mapped == out_id:
                    raw_id = raw
                    break
        names_dict[str(out_id)] = class_names.get(raw_id, str(out_id))
    with open(path, "w") as f:
        f.write(f"path: {base_path}\n")
        f.write("train: images/train\n")
        f.write("val: images/val\n")
        f.write(f"nc: {len(sorted_classes)}\n")
        f.write(f"names: {json.dumps(names_dict, ensure_ascii=False)}\n")
        for k, v in (extra_yaml or {}).items():
            f.write(f"{k}: {v}\n")


def _write_yolo_cls_yaml(output_dir: str, for_training: bool) -> None:
    """Write minimal dataset.yaml for classification.

    YOLO cls reads class names from the directory structure (single-label) or
    per-image label files (multi-label), so only path/train/val are required.
    """
    base_path = "/data" if for_training else "."
    with open(os.path.join(output_dir, "dataset.yaml"), "w") as f:
        f.write(f"path: {base_path}\n")
        f.write("train: train\n")
        f.write("val: val\n")


async def _export_yolo_cls(dataset_id: int, task_id: int, images: list, output_dir: str, annotation_task_id: int | None = None, train_ratio: float = 0.8, class_names: dict | None = None, for_training: bool = False, multi_label: bool = False) -> None:
    """Export classification to YOLO CLS format with train/val split.

    single_label: train/<cls>/<img>.jpg (目录结构)
    multi_label:  train/<img>.jpg + train/labels/<img>.txt (每行一个 class id)
    """
    import random

    from app.utils.s3_client import s3_client

    task_cn: dict[int, str] = class_names or {}
    if not task_cn and annotation_task_id:
        from app.api.v1.module_annotation.task.model import AnnotationTaskModel
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task and ann_task.classes:
                for c in (ann_task.classes if isinstance(ann_task.classes, list) else []):
                    task_cn[c["id"]] = c.get("name", f"class_{c['id']}")

    # Collect per-image labels: {img_id: [class_id, ...]} (multi) or {img_id: class_id} (single)
    img_labels: dict[int, list[int]] = {}
    async with async_db_session() as db:
        for img in images:
            query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
            if annotation_task_id:
                query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
            query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
            rec = await db.execute(query)
            record = rec.scalar_one_or_none()
            ids: list[int] = []
            for ann in (record.annotation_data if record and record.annotation_data else []):
                cid = ann.get("class_id")
                if cid is not None and cid != -1:
                    ids.append(cid)
                if isinstance(ann.get("class_ids"), list):
                    for c in ann["class_ids"]:
                        if c is not None and c != -1:
                            ids.append(c)
            if ids:
                # 去重保持顺序
                seen = set()
                ids = [c for c in ids if not (c in seen or seen.add(c))]
                img_labels[img.id] = ids

    if multi_label:
        # Multi-label: flat train/val dirs + labels/*.txt (one class id per line)
        random.shuffle(images)
        split_idx = max(1, int(len(images) * train_ratio)) if images else 0
        for split_name, sub in [("train", images[:split_idx]), ("val", images[split_idx:])]:
            img_dir = os.path.join(output_dir, split_name)
            lbl_dir = os.path.join(output_dir, split_name, "labels")
            os.makedirs(img_dir, exist_ok=True)
            os.makedirs(lbl_dir, exist_ok=True)
            for img in sub:
                ids = img_labels.get(img.id, [])
                if not ids:
                    continue
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(os.path.join(img_dir, img.filename), "wb") as f:
                        f.write(data.read())
                except Exception:
                    continue
                stem = os.path.splitext(img.filename)[0]
                with open(os.path.join(lbl_dir, stem + ".txt"), "w") as f:
                    f.write("\n".join(str(cid) for cid in sorted(set(ids))))
        _write_yolo_cls_yaml(output_dir, for_training)
        log.info(f"yolo-cls (multi): exported to {output_dir}")
        return

    # Single-label: existing directory structure
    class_imgs: dict[int, list] = {}
    for img in images:
        ids = img_labels.get(img.id, [])
        if ids:
            class_imgs.setdefault(ids[0], []).append(img)
    for cid, imgs in class_imgs.items():
        random.shuffle(imgs)
        split = max(0, int(len(imgs) * train_ratio))
        for split_name, sub in [("train", imgs[:split]), ("val", imgs[split:])]:
            cls_name = task_cn.get(cid, f"class_{cid}")
            dst_dir = os.path.join(output_dir, split_name, cls_name)
            os.makedirs(dst_dir, exist_ok=True)
            for img in sub:
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(os.path.join(dst_dir, img.filename), "wb") as f:
                        f.write(data.read())
                except Exception:
                    continue
    _write_yolo_cls_yaml(output_dir, for_training)
    log.info(f"yolo-cls: exported to {output_dir}")


async def _export_x_anylabeling(dataset_id: int, task_id: int, images: list, output_dir: str, annotation_task_id: int | None = None, class_names: dict | None = None) -> None:
    """Export dataset to x-anylabeling (LabelMe JSON) format: images + .json sidecar files."""
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    downloaded = 0

    from app.utils.s3_client import s3_client

    async with async_db_session() as db:
        for img in images:
            img_path = os.path.join(img_dir, img.filename)
            if not os.path.exists(img_path):
                try:
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
                    downloaded += 1
                except Exception as e:
                    log.warning(f"skip image {img.filename}: {e}")
                    continue

            # Get annotation record
            query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
            if annotation_task_id:
                query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
            query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
            rec = await db.execute(query)
            record = rec.scalar_one_or_none()
            anns = record.annotation_data if record and record.annotation_data else []

            # Convert to x-anylabeling format（归一化 → 像素；支持全部形状；使用真实类名）
            shapes = xany_shapes(anns, img.width or 0, img.height or 0, class_names or {})

            # Write JSON sidecar
            js = {
                "version": "3.2.1",
                "flags": {},
                "shapes": shapes,
                "imagePath": img.filename,
                "imageData": None,
                "imageHeight": img.height or 0,
                "imageWidth": img.width or 0,
            }
            json_path = os.path.join(img_dir, img.filename.rsplit(".", 1)[0] + ".json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(js, f, ensure_ascii=False, indent=2)

    log.info(f"exported {downloaded} images to x-anylabeling format in {output_dir}")


def _crop_text_region(img_path: str, quad: list, img_w: int = 1, img_h: int = 1):
    """透视矫正裁剪文本区域（复用 paddle-ocr 的裁剪逻辑）。

    quad 为像素坐标 4 角点。返回 BGR numpy 数组（可直接 cv2.imwrite），失败返回 None。
    """
    try:
        import cv2
        import numpy as np
        src = cv2.imread(img_path)
        if src is None:
            return None
        pts = np.array(quad, dtype=np.float32)
        if len(pts) < 4:
            return None
        rect = cv2.minAreaRect(pts)
        box = np.array(cv2.boxPoints(rect), dtype=np.float32)
        width, height = int(rect[1][0]), int(rect[1][1])
        if width < 1 or height < 1:
            return None
        dst_pts = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
        M = cv2.getPerspectiveTransform(box, dst_pts)
        return cv2.warpPerspective(src, M, (width, height))
    except ImportError:
        # Fallback to simple axis-aligned crop if OpenCV not available
        try:
            import numpy as np
            from PIL import Image
            xs = [p[0] for p in quad]
            ys = [p[1] for p in quad]
            x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
            if x2 - x1 < 1 or y2 - y1 < 1:
                return None
            pil = Image.open(img_path).convert("RGB").crop((x1, y1, x2, y2))
            return np.array(pil)[:, :, ::-1]  # RGB → BGR
        except Exception:
            return None


async def export_model(task_id: int, framework: str, export_dir: str, best_metrics: dict | None = None) -> dict:
    from .model import TrainModel, TrainTask

    # 1. 优先从 YOLO/PaddleX 标准输出目录找模型文件
    best_path = None
    if framework == "paddlex":
        # PaddleX OCR train.py 保存 best_accuracy/latest .pdparams 到 save_model_dir(=/output/det 或 /output/rec)
        candidates = [
            os.path.join(export_dir, "det", "best_accuracy.pdparams"),
            os.path.join(export_dir, "rec", "best_accuracy.pdparams"),
            os.path.join(export_dir, "best_accuracy.pdparams"),
            os.path.join(export_dir, "det", "latest.pdparams"),
            os.path.join(export_dir, "rec", "latest.pdparams"),
            os.path.join(export_dir, "det", "best_model", "model.pdparams"),
            os.path.join(export_dir, "rec", "best_model", "model.pdparams"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                best_path = p
                break
    else:
        extensions = [".pt"] if framework == "ultralytics" else [".pdparams"]
        for ext in extensions:
            candidates = [
                os.path.join(export_dir, "exp", "weights", f"best{ext}"),
                os.path.join(export_dir, "runs", "train", "exp", "weights", f"best{ext}"),
            ]
            for p in candidates:
                if os.path.isfile(p):
                    best_path = p
                    break
            if best_path:
                break
    # 2. 降级：递归搜索，但排除 .models_cache 目录
    if not best_path:
        for root, dirs, files in os.walk(export_dir):
            dirs[:] = [d for d in dirs if d != ".models_cache"]
            for f in files:
                if framework == "paddlex" and f.endswith(".pdparams"):
                    best_path = os.path.join(root, f)
                    break
                if framework == "ultralytics" and f == "best.pt":
                    best_path = os.path.join(root, f)
                    break
            if best_path:
                break

    storage_path = None
    if best_path:
        rustfs_path = f"train/models/task_{task_id}/{os.path.basename(best_path)}"
        try:
            from app.utils.s3_client import s3_client
            with open(best_path, "rb") as f:
                s3_client.upload_fileobj(f, rustfs_path)
            storage_path = rustfs_path
        except Exception as e:
            log.error(f"upload model to RustFS failed: {e}，模型将创建为无存储文件状态")

    async with async_db_session.begin() as db:
        task = await db.get(TrainTask, task_id)
        if not task:
            return {"repo_id": None, "storage_path": storage_path}

        existing = await db.execute(
            select(TrainModel).where(TrainModel.name == task.name).order_by(TrainModel.id.desc()).limit(1)
        )
        last = existing.scalar_one_or_none()
        next_ver = 1
        if last and last.version:
            from .service import TrainService
            next_ver = TrainService._parse_version(last.version) + 1

        repo = (await db.execute(
            select(TrainModelRepo).where(TrainModelRepo.name == task.name)
        )).scalar_one_or_none()
        if not repo:
            repo = TrainModelRepo(name=task.name, framework=task.framework, created_id=task.created_id)
            db.add(repo)
            await db.flush()

        model_rec = TrainModel(
            repo_id=repo.id, name=task.name, framework=task.framework,
            version=f"v{next_ver}", storage_path=storage_path,
            format="pytorch",  # Original format is PyTorch
            annotation_dataset_id=task.dataset_id, created_id=task.created_id,
            metrics=best_metrics if best_metrics is not None else task.best_metrics,
        )
        db.add(model_rec)
        await db.flush()
        repo.latest_version_id = model_rec.id
        task.model_repo_id = model_rec.id

    return {"repo_id": model_rec.id, "storage_path": storage_path}


async def _export_paddle_ocr(dataset_id: int, task_id: int, images: list,
                             output_dir: str, annotation_task_id: int | None = None,
                             export_rec: bool = False, train_ratio: float = 0.8) -> None:
    """导出 PaddleX OCR（PP-OCRv6）数据格式。

    det:  <output>/det/dataset/  (train.txt + val.txt + images/)  PaddleX JSON 标注
    rec:  <output>/rec/dataset/  (train.txt + val.txt + images/ + dict.txt)
    """
    import random

    from app.utils.s3_client import s3_client

    mode = "rec" if export_rec else "det"
    dataset_dir = os.path.join(output_dir, mode, "dataset")
    img_dir = os.path.join(dataset_dir, "images")
    os.makedirs(img_dir, exist_ok=True)

    # 收集所有图像 + 标注（train/val 切分）
    records = []  # (img_name, det_json_lines, rec_entries)
    async with async_db_session() as db:
        for img in images:
            img_path = os.path.join(img_dir, img.filename)
            try:
                if not os.path.exists(img_path):
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
            except Exception:
                continue

            query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
            if annotation_task_id:
                query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
            query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
            rec = await db.execute(query)
            record = rec.scalar_one_or_none()
            anns = record.annotation_data if record and record.annotation_data else []

            entries = []
            rec_entries = []
            w = img.width or 1
            h = img.height or 1
            for ann in anns:
                if ann.get("type") not in ("polygon", "Polygon", "ocr", "Ocr"):
                    continue
                pts = ann.get("points", [])
                if len(pts) < 4:
                    continue
                points = [[float(p["x"] * w), float(p["y"] * h)]
                          if isinstance(p, dict) else [float(p[0] * w), float(p[1] * h)]
                          for p in pts[:4]]
                text = ann.get("text", "") or ""
                entries.append({"transcription": text, "points": points})
                rec_entries.append((points, text))
            records.append((img.filename, entries, rec_entries))

    random.shuffle(records)
    split_idx = max(1, int(len(records) * train_ratio)) if len(records) > 1 else len(records)
    train_set, val_set = records[:split_idx], records[split_idx:]

    def write_label(path, rows):
        lines = []
        for fname, entries, _rec in rows:
            if entries:
                lines.append(f"images/{fname}\t{json.dumps(entries, ensure_ascii=False)}")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    if not export_rec:
        write_label(os.path.join(dataset_dir, "train.txt"), train_set)
        write_label(os.path.join(dataset_dir, "val.txt"), val_set)
        log.info(f"paddlex det: exported {len(train_set)} train / {len(val_set)} val to {dataset_dir}")
    else:
        # rec：透视矫正裁剪文字区域
        import cv2
        rec_train, rec_val = [], []
        for fname, _entries, rec_entries in train_set:
            for i, (quad, text) in enumerate(rec_entries):
                if not text.strip():
                    continue
                crop_name = f"{os.path.splitext(fname)[0]}_{i}.jpg"
                crop = _crop_text_region(os.path.join(img_dir, fname), quad, 1, 1)
                if crop is not None:
                    cv2.imwrite(os.path.join(img_dir, crop_name), crop)
                    rec_train.append(f"images/{crop_name}\t{text}")
        for fname, _entries, rec_entries in val_set:
            for i, (quad, text) in enumerate(rec_entries):
                if not text.strip():
                    continue
                crop_name = f"{os.path.splitext(fname)[0]}_{i}.jpg"
                crop = _crop_text_region(os.path.join(img_dir, fname), quad, 1, 1)
                if crop is not None:
                    cv2.imwrite(os.path.join(img_dir, crop_name), crop)
                    rec_val.append(f"images/{crop_name}\t{text}")
        with open(os.path.join(dataset_dir, "train.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(rec_train))
        with open(os.path.join(dataset_dir, "val.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(rec_val))
        # dict.txt：从所有 rec 文本提取字符集
        chars = []
        seen = set()
        for _fname, _e, rec_entries in records:
            for _quad, text in rec_entries:
                for ch in text:
                    if ch not in seen:
                        seen.add(ch)
                        chars.append(ch)
        with open(os.path.join(dataset_dir, "..", "dict.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(chars))
        log.info(f"paddlex rec: exported {len(rec_train)} train / {len(rec_val)} val to {dataset_dir}")


async def _export_paddle_mlcls(dataset_id: int, task_id: int, images: list, output_dir: str,
                               annotation_task_id: int | None = None,
                               class_names: dict | None = None) -> None:
    """导出多标签分类到 Paddle MLCLS 格式（train_list.txt：每行 image_path + 多个 class_id）。"""
    import random

    from app.utils.s3_client import s3_client

    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    lines = []

    async with async_db_session() as db:
        for img in images:
            img_path = os.path.join(img_dir, img.filename)
            try:
                if not os.path.exists(img_path):
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
            except Exception:
                continue

            query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
            if annotation_task_id:
                query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
            query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
            rec = await db.execute(query)
            record = rec.scalar_one_or_none()
            anns = record.annotation_data if record and record.annotation_data else []

            class_ids = []
            for ann in anns:
                cid = ann.get("class_id")
                if cid is not None and cid != -1:
                    class_ids.append(str(cid))
                if isinstance(ann.get("class_ids"), list):
                    for c in ann["class_ids"]:
                        if c is not None and c != -1:
                            class_ids.append(str(c))
            if class_ids:
                # 去重保持顺序
                seen = set()
                uniq = [c for c in class_ids if not (c in seen or seen.add(c))]
                lines.append(f"{img.filename} {' '.join(uniq)}")

    random.shuffle(lines)
    label_file = os.path.join(img_dir, "train_list.txt")
    with open(label_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log.info(f"paddle-mlcls: exported {len(lines)} labeled images to {output_dir}")
