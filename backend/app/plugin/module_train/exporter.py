import json
import os
from sqlalchemy import select, desc
from app.api.v1.module_annotation.dataset.model import AnnotationImageModel
from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.core.database import async_db_session
from app.core.logger import log


async def export_dataset(dataset_id: int, task_id: int, framework: str, output_dir: str, annotation_task_id: int | None = None, ocr_rec: bool = True, train_ratio: float = 0.8) -> str:
    """Export dataset and return the path to dataset.yaml for the YOLO command."""
    data_dir = output_dir
    os.makedirs(data_dir, exist_ok=True)
    async with async_db_session() as db:
        result = await db.execute(
            select(AnnotationImageModel).where(AnnotationImageModel.dataset_id == dataset_id)
        )
        images = result.scalars().all()

    if not images:
        log.warning(f"export_dataset: dataset {dataset_id} has no images")
        return

    # Determine task_type from annotation task (affects YOLO label format)
    task_type = "detection"
    class_names: dict[int, str] = {}
    if annotation_task_id:
        from app.api.v1.module_annotation.task.model import AnnotationTaskModel
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task:
                task_type = ann_task.task_type
                if ann_task.classes:
                    for c in (ann_task.classes if isinstance(ann_task.classes, list) else []):
                        class_names[c["id"]] = c.get("name", f"class_{c['id']}")

    if framework == "ultralytics" or framework.startswith("yolo-"):
        if framework.startswith("yolo-"):
            task_type = framework.replace("yolo-", "")
        if task_type == "cls":
            await _export_yolo_cls(dataset_id, task_id, images, output_dir, annotation_task_id, train_ratio=train_ratio, class_names=class_names)
        else:
            await _export_yolo(dataset_id, task_id, images, output_dir, task_type, annotation_task_id, train_ratio=train_ratio, class_names=class_names)
    elif framework == "paddle-mlcls":
        await _export_paddle_mlcls(dataset_id, task_id, images, output_dir, annotation_task_id)
    elif framework == "paddle-ocr" or framework.startswith("paddle-ocr-"):
        export_rec = ocr_rec if framework == "paddle-ocr" else (framework == "paddle-ocr-det-rec" or framework == "paddle-ocr-rec")
        await _export_paddle_ocr(dataset_id, task_id, images, output_dir, export_rec, annotation_task_id)
    elif framework == "x-anylabeling":
        await _export_x_anylabeling(dataset_id, task_id, images, output_dir, annotation_task_id)
    else:
        _export_paddlex(images, output_dir)


async def _export_yolo(dataset_id: int, task_id: int, images: list, output_dir: str, task_type: str = "detection", annotation_task_id: int | None = None, train_ratio: float = 0.8, class_names: dict | None = None) -> None:
    """Export to YOLO format with train/val split."""
    import random, shutil
    random.shuffle(images)
    split_idx = max(1, int(len(images) * train_ratio))
    train_imgs = images[:split_idx]
    val_imgs = images[split_idx:]

    for split_name, split_imgs in [("train", train_imgs), ("val", val_imgs)]:
        img_split = os.path.join(output_dir, "images", split_name)
        label_split = os.path.join(output_dir, "labels", split_name)
        os.makedirs(img_split, exist_ok=True)
        os.makedirs(label_split, exist_ok=True)

        from app.utils.s3_client import s3_client
        classes: set[int] = set()
        saved = 0

        async with async_db_session() as db:
            for img in split_imgs:
                # Download image
                img_path = os.path.join(img_split, img.filename)
                if not os.path.exists(img_path):
                    try:
                        data = s3_client.download_fileobj(img.object_key)
                        with open(img_path, "wb") as f:
                            f.write(data.read())
                        saved += 1
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
                lines = []
                for ann in anns:
                    cls_id = ann.get("class_id", 0)
                    classes.add(cls_id)
                    ann_type = ann.get("type", "")
                    if ann_type in ("AxisAlignedBox", "box"):
                        if "x1" in ann:
                            x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
                        else:
                            xc_a, yc_a, w_a, h_a = ann["x"], ann["y"], ann["width"], ann["height"]
                            x1, y1, x2, y2 = xc_a - w_a/2, yc_a - h_a/2, xc_a + w_a/2, yc_a + h_a/2
                        if task_type == "rotated_detection":
                            lines.append(f"{cls_id} {x1:.6f} {y1:.6f} {x2:.6f} {y1:.6f} {x2:.6f} {y2:.6f} {x1:.6f} {y2:.6f}")
                        else:
                            lines.append(f"{cls_id} {(x1+x2)/2:.6f} {(y1+y2)/2:.6f} {x2-x1:.6f} {y2-y1:.6f}")
                    elif ann_type in ("RotatedBox", "rotated_box"):
                        cx, cy = ann["cx"], ann["cy"]
                        w, h = ann["width"], ann["height"]
                        lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
                if lines:
                    with open(label_path, "w") as f:
                        f.write("\n".join(lines))

            log.info(f"yolo {split_name}: {saved} images, {len(classes)} classes")

    # Generate dataset.yaml
    sorted_classes = sorted(classes)
    names_dict = {}
    for cid in sorted_classes:
        names_dict[str(cid)] = class_names.get(cid, str(cid)) if class_names else str(cid)

    yaml_path = os.path.join(output_dir, "dataset.yaml")
    with open(yaml_path, "w") as f:
        f.write("path: .\n")
        f.write("train: images/train\n")
        f.write("val: images/val\n")
        f.write(f"nc: {len(sorted_classes)}\n")
        f.write(f"names: {json.dumps(names_dict, ensure_ascii=False)}\n")
    img_dir = os.path.join(output_dir, "images")
def _export_paddlex(images: list, output_dir: str) -> None:
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    log.info(f"PaddleX export to {output_dir} — {len(images)} images")


async def _export_yolo_cls(dataset_id: int, task_id: int, images: list, output_dir: str, annotation_task_id: int | None = None, train_ratio: float = 0.8, class_names: dict | None = None) -> None:
    """Export single-label classification to YOLO CLS format with train/val split."""
    import random
    from app.utils.s3_client import s3_client
    from collections import defaultdict

    # Get class mapping
    task_cn: dict[int, str] = class_names or {}
    if not task_cn and annotation_task_id:
        from app.api.v1.module_annotation.task.model import AnnotationTaskModel
        async with async_db_session() as db:
            ann_task = await db.get(AnnotationTaskModel, annotation_task_id)
            if ann_task and ann_task.classes:
                for c in (ann_task.classes if isinstance(ann_task.classes, list) else []):
                    task_cn[c["id"]] = c.get("name", f"class_{c['id']}")

    # Collect per image class_id
    img_class: dict[int, int] = {}
    async with async_db_session() as db:
        for img in images:
            query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
            if annotation_task_id:
                query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
            query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
            rec = await db.execute(query)
            record = rec.scalar_one_or_none()
            for ann in (record.annotation_data if record and record.annotation_data else []):
                cid = ann.get("class_id")
                if cid is not None:
                    img_class[img.id] = cid
                    break

    # Group by class
    class_imgs: dict[int, list] = defaultdict(list)
    for img in images:
        if img.id in img_class:
            class_imgs[img_class[img.id]].append(img)

    # Split per class
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

    log.info(f"yolo-cls: exported to {output_dir}")


async def _export_paddle_mlcls(dataset_id: int, task_id: int, images: list, output_dir: str, annotation_task_id: int | None = None) -> None:
    """Export multi-label classification to Paddle MLCLS format (txt with class_ids per image)."""
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    lines = []
    from app.utils.s3_client import s3_client

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
                if cid is not None:
                    class_ids.append(str(cid))
            if class_ids:
                lines.append(f"{img.filename} {' '.join(class_ids)}")

    label_file = os.path.join(img_dir, "train_list.txt")
    with open(label_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log.info(f"paddle-mlcls: exported {len(lines)} labeled images to {output_dir}")


async def _export_paddle_ocr(dataset_id: int, task_id: int, images: list, output_dir: str, export_rec: bool = True, annotation_task_id: int | None = None) -> None:
    """Export OCR to PaddleOCR format.
    - det: det/dataset/  detection ground truth (det_gt.txt)
    - rec: rec/dataset/  cropped text regions (perspective transform) + rec_gt.txt
    """
    from app.utils.s3_client import s3_client

    det_dir = os.path.join(output_dir, "det", "dataset")
    rec_dir = os.path.join(output_dir, "rec", "dataset") if export_rec else None
    os.makedirs(det_dir, exist_ok=True)
    if rec_dir:
        os.makedirs(os.path.join(rec_dir, "images"), exist_ok=True)

    det_lines = []
    rec_lines = []

    async with async_db_session() as db:
        for img_idx, img in enumerate(images):
            img_path = os.path.join(output_dir, img.filename)
            try:
                if not os.path.exists(img_path):
                    data = s3_client.download_fileobj(img.object_key)
                    with open(img_path, "wb") as f:
                        f.write(data.read())
            except Exception:
                continue

            # Copy image to det/dataset/
            det_img_path = os.path.join(det_dir, img.filename)
            if os.path.exists(img_path) and not os.path.exists(det_img_path):
                import shutil
                shutil.copy2(img_path, det_img_path)

            query = select(AnnotationRecordModel).where(AnnotationRecordModel.image_id == img.id)
            if annotation_task_id:
                query = query.where(AnnotationRecordModel.task_id == annotation_task_id)
            query = query.order_by(desc(AnnotationRecordModel.version)).limit(1)
            rec = await db.execute(query)
            record = rec.scalar_one_or_none()
            anns = record.annotation_data if record and record.annotation_data else []

            polygons = []
            for ann in anns:
                ann_type = ann.get("type", "")
                if ann_type not in ("ocr", "Ocr", "polygon", "Polygon"):
                    continue
                pts = ann.get("points", [])
                if not pts and "x1" in ann:
                    pts = [[ann["x1"], ann["y1"]], [ann["x2"], ann["y1"]], [ann["x2"], ann["y2"]], [ann["x1"], ann["y2"]]]
                if pts:
                    flat = [[p["x"], p["y"]] if isinstance(p, dict) else p for p in pts]
                    polygons.append({"points": flat, "text": ann.get("text", "") or ""})

            if polygons:
                entries = [{"transcription": p["text"], "points": p["points"]} for p in polygons]
                det_lines.append(f"{img.filename}\t{json.dumps(entries, ensure_ascii=False)}")

            if rec_dir and polygons:
                try:
                    import cv2
                    import numpy as np
                    pil_img = cv2.imread(img_path)
                    if pil_img is None:
                        continue
                    h, w = pil_img.shape[:2]
                    for pi, poly in enumerate(polygons):
                        pts = np.array(poly["points"], dtype=np.float32)
                        if len(pts) < 4:
                            continue
                        # Perspective transform to get a straight text region
                        rect = cv2.minAreaRect(pts)
                        box = cv2.boxPoints(rect)
                        box = np.array(box, dtype=np.float32)
                        width = int(rect[1][0])
                        height = int(rect[1][1])
                        if width < 1 or height < 1:
                            continue
                        dst_pts = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype=np.float32)
                        M = cv2.getPerspectiveTransform(box, dst_pts)
                        warped = cv2.warpPerspective(pil_img, M, (width, height))
                        rec_name = f"{os.path.splitext(img.filename)[0]}_{pi}.jpg"
                        cv2.imwrite(os.path.join(rec_dir, "images", rec_name), warped)
                        rec_lines.append(f"images/{rec_name}\t{poly['text']}")
                except ImportError:
                    # Fallback to simple crop if OpenCV not available
                    for pi, poly in enumerate(polygons):
                        pts = poly["points"]
                        xs = [p[0] for p in pts]
                        ys = [p[1] for p in pts]
                        x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
                        if x2 - x1 < 1 or y2 - y1 < 1:
                            continue
                        rec_name = f"{os.path.splitext(img.filename)[0]}_{pi}.jpg"
                        try:
                            from PIL import Image
                            pil = Image.open(img_path)
                            crop = pil.crop((x1, y1, x2, y2))
                            crop.save(os.path.join(rec_dir, "images", rec_name))
                        except Exception:
                            continue
                        rec_lines.append(f"images/{rec_name}\t{poly['text']}")

    with open(os.path.join(det_dir, "det_gt.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(det_lines))

    if rec_lines:
        with open(os.path.join(rec_dir, "rec_gt.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(rec_lines))

    log.info(f"paddle-ocr: {len(det_lines)} det, {len(rec_lines)} rec → {output_dir}")


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
                        x1, y1, x2, y2 = xc - w/2, yc - h/2, xc + w/2, yc + h/2
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


async def export_model(task_id: int, framework: str, export_dir: str) -> dict:
    from .model import TrainModel, TrainTask

    best_path = None
    for root, _, files in os.walk(export_dir):
        for f in files:
            if framework == "ultralytics" and f.endswith(".pt"):
                best_path = os.path.join(root, f)
            elif framework == "paddlex" and f.endswith(".pdparams"):
                best_path = os.path.join(root, f)

    storage_path = ""
    if best_path:
        rustfs_path = f"train/models/task_{task_id}/{os.path.basename(best_path)}"
        try:
            from app.utils.s3_client import s3_client
            with open(best_path, "rb") as f:
                s3_client.upload_fileobj(f, rustfs_path)
            storage_path = rustfs_path
        except Exception as e:
            log.error(f"upload model failed: {e}")

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
            try:
                next_ver = int(last.version.replace("v", "")) + 1
            except ValueError:
                next_ver = 1

        model_rec = TrainModel(
            name=task.name, framework=task.framework,
            version=f"v{next_ver}", storage_path=storage_path,
            annotation_dataset_id=task.dataset_id, created_id=task.created_id,
        )
        db.add(model_rec)
        await db.flush()
        task.model_repo_id = model_rec.id

    return {"repo_id": model_rec.id, "storage_path": storage_path}
