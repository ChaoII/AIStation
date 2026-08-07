import json
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
        await _export_x_anylabeling(dataset_id, task_id, images, output_dir, annotation_task_id)
    elif framework == "pytorch-ocr-det":
        await _export_pytorch_ocr(dataset_id, task_id, images, output_dir, annotation_task_id)
    elif framework == "pytorch-ocr-rec":
        await _export_pytorch_ocr(dataset_id, task_id, images, output_dir, annotation_task_id, export_rec=True)
    elif framework == "paddlex":
        # PaddleX OCR：ocr_rec 区分 det(false) / rec(true)
        await _export_paddle_ocr(dataset_id, task_id, images, output_dir, annotation_task_id,
                                 export_rec=ocr_rec)
    else:
        raise ValueError(f"不支持的导出框架: {framework}")

    log.info(f"export {framework} to {output_dir}")


async def _export_yolo(dataset_id: int, task_id: int, images: list, output_dir: str, task_type: str = "detection", annotation_task_id: int | None = None, train_ratio: float = 0.8, class_names: dict | None = None, for_training: bool = False) -> None:
    """Export to YOLO format with train/val split. for_training controls YAML path."""
    import random

    from app.utils.s3_client import s3_client

    random.shuffle(images)
    split_idx = max(1, int(len(images) * train_ratio))
    train_imgs = images[:split_idx]
    val_imgs = images[split_idx:]
    classes: set[int] = set()

    for split_name, split_imgs in [("train", train_imgs), ("val", val_imgs)]:
        img_split = os.path.join(output_dir, "images", split_name)
        label_split = os.path.join(output_dir, "labels", split_name)
        os.makedirs(img_split, exist_ok=True)
        os.makedirs(label_split, exist_ok=True)

        async with async_db_session() as db:
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

                query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
                if annotation_task_id:
                    query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
                query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
                rec = await db.execute(query)
                record = rec.scalar_one_or_none()
                anns = record.annotation_data if record and record.annotation_data else []

                label_path = os.path.join(label_split, img.filename.rsplit(".", 1)[0] + ".txt")
                lines = _format_yolo_lines(anns, task_type)
                if lines:
                    with open(label_path, "w") as f:
                        f.write("\n".join(lines))
                    for ann in anns:
                        classes.add(ann.get("class_id", 0))

    base_path = "/data" if for_training else "."
    sorted_classes = sorted(classes)
    _write_yaml(os.path.join(output_dir, "dataset.yaml"), base_path, sorted_classes, class_names or {})
    log.info(f"yolo: train={len(train_imgs)} val={len(val_imgs)} classes={len(sorted_classes)} → {output_dir}")


def _format_yolo_lines(anns: list, task_type: str) -> list[str]:
    """Convert annotations to YOLO label lines based on task_type."""
    lines = []
    for ann in anns:
        cls_id = ann.get("class_id", 0)
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
            lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    return lines


def _write_yaml(path: str, base_path: str, sorted_classes: list, class_names: dict) -> None:
    """Write dataset.yaml."""
    names_dict = {str(c): class_names.get(c, str(c)) for c in sorted_classes}
    with open(path, "w") as f:
        f.write(f"path: {base_path}\n")
        f.write("train: images/train\n")
        f.write("val: images/val\n")
        f.write(f"nc: {len(sorted_classes)}\n")
        if any(k != v for k, v in names_dict.items()):
            f.write(f"names: {json.dumps(names_dict, ensure_ascii=False)}\n")
        else:
            f.write(f"names: {json.dumps(sorted_classes)}\n")


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
                if cid is not None:
                    ids.append(cid)
            if ids:
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


async def _export_x_anylabeling(dataset_id: int, task_id: int, images: list, output_dir: str, annotation_task_id: int | None = None) -> None:
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

            # Convert to x-anylabeling format
            shapes = []
            for ann in anns:
                cls_id = ann.get("class_id", 0)
                label = ann.get("label", f"class_{cls_id}")
                if ann.get("type") in ("AxisAlignedBox", "box"):
                    if "x1" in ann:
                        x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
                    else:
                        xc, yc, w, h = ann["x"], ann["y"], ann["width"], ann["height"]
                        x1, y1, x2, y2 = xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2
                    shapes.append({
                        "label": label,
                        "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
                        "group_id": None,
                        "shape_type": "rectangle",
                        "flags": {},
                    })
                elif ann.get("type") == "polygon":
                    pts = ann.get("points", [])
                    if len(pts) >= 3:
                        shapes.append({
                            "label": label,
                            "points": pts,
                            "group_id": None,
                            "shape_type": "polygon",
                            "flags": {},
                        })

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


async def _export_pytorch_ocr(dataset_id: int, task_id: int, images: list,
                              output_dir: str, annotation_task_id: int | None = None,
                              export_rec: bool = False) -> None:
    """导出 PyTorch OCR 数据。

    det: images/ + det_gt.txt（四边形像素坐标）
    rec: images/ + train_list.txt（image_path\\tlabel，文本行透视矫正裁剪图）
    """
    from app.utils.s3_client import s3_client

    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    det_lines = []
    rec_lines = []

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

            quads = []
            texts = []
            w = img.width or 1
            h = img.height or 1
            for ann in anns:
                if ann.get("type") not in ("polygon", "Polygon", "ocr", "Ocr"):
                    continue
                pts = ann.get("points", [])
                if len(pts) < 4:
                    continue
                # 转像素坐标四角点
                quad = [[float(p["x"] * w), float(p["y"] * h)]
                        if isinstance(p, dict) else [float(p[0] * w), float(p[1] * h)]
                        for p in pts[:4]]
                quads.append(quad)
                texts.append(ann.get("text", "") or "")
            if quads and not export_rec:
                det_lines.append(f"{img.filename}\t{json.dumps(quads)}")
            if export_rec:
                import cv2
                for i, (quad, text) in enumerate(zip(quads, texts, strict=False)):
                    if not text.strip():
                        continue
                    crop_name = f"{os.path.splitext(img.filename)[0]}_{i}.jpg"
                    crop = _crop_text_region(img_path, quad, w, h)
                    if crop is not None:
                        cv2.imwrite(os.path.join(img_dir, crop_name), crop)
                        # RecDataset 以 data_dir 为根读取，裁剪图在 images/ 下，需带前缀
                        rec_lines.append(f"images/{crop_name}\t{text}")

    if not export_rec:
        with open(os.path.join(output_dir, "det_gt.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(det_lines))
    else:
        with open(os.path.join(output_dir, "train_list.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(rec_lines))
    log.info(f"pytorch-ocr: exported {len(det_lines)} det, {len(rec_lines)} rec to {output_dir}")


async def export_model(task_id: int, framework: str, export_dir: str, best_metrics: dict | None = None) -> dict:
    from .model import TrainModel, TrainTask

    # 1. 优先从 YOLO/PaddleX 标准输出目录找模型文件
    best_path = None
    if framework == "paddlex":
        # PaddleX OCR train.py 保存 best_accuracy.pdparams 到 save_model_dir(=/output/det 或 /output/rec)
        candidates = [
            os.path.join(export_dir, "det", "best_accuracy.pdparams"),
            os.path.join(export_dir, "rec", "best_accuracy.pdparams"),
            os.path.join(export_dir, "best_accuracy.pdparams"),
            os.path.join(export_dir, "det", "best_model", "model.pdparams"),
            os.path.join(export_dir, "rec", "best_model", "model.pdparams"),
        ]
        for p in candidates:
            if os.path.isfile(p):
                best_path = p
                break
    else:
        extensions = [".pt"] if framework in ("ultralytics", "pytorch-ocr-det", "pytorch-ocr-rec") else [".pdparams"]
        for ext in extensions:
            candidates = [
                os.path.join(export_dir, "exp", "weights", f"best{ext}"),
                os.path.join(export_dir, "runs", "train", "exp", "weights", f"best{ext}"),
            ]
            if framework in ("pytorch-ocr-det", "pytorch-ocr-rec"):
                candidates.insert(0, os.path.join(export_dir, f"best{ext}"))
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
                if framework in ("ultralytics", "pytorch-ocr-det", "pytorch-ocr-rec") and f == "best.pt":
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
                             export_rec: bool = False) -> None:
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
    split_idx = max(1, int(len(records) * 0.8)) if len(records) > 1 else len(records)
    train_set, val_set = records[:split_idx], records[split_idx:]

    def write_label(path, rows):
        lines = []
        for fname, entries, _rec in rows:
            if entries:
                lines.append(f"{fname}\t{json.dumps(entries, ensure_ascii=False)}")
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
