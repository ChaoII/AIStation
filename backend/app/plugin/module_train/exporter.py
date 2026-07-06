import json
import os
from sqlalchemy import select, desc
from app.api.v1.module_annotation.dataset.model import AnnotationImageModel
from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.core.database import async_db_session
from app.core.logger import log


async def export_dataset(dataset_id: int, task_id: int, framework: str, output_dir: str) -> str:
    """Export dataset and return the path to dataset.yaml for the YOLO command."""
    data_dir = output_dir  # /data mount point in container
    img_dir = os.path.join(data_dir, "images")
    label_dir = os.path.join(data_dir, "labels")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(label_dir, exist_ok=True)
    async with async_db_session() as db:
        result = await db.execute(
            select(AnnotationImageModel).where(AnnotationImageModel.dataset_id == dataset_id)
        )
        images = result.scalars().all()

    if not images:
        log.warning(f"export_dataset: dataset {dataset_id} has no images")
        return

    if framework == "ultralytics":
        await _export_yolo(dataset_id, task_id, images, output_dir)
    else:
        _export_paddlex(images, output_dir)


async def _export_yolo(dataset_id: int, task_id: int, images: list, output_dir: str) -> None:
    img_dir = os.path.join(output_dir, "images")
    label_dir = os.path.join(output_dir, "labels")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(label_dir, exist_ok=True)
    classes = set()
    downloaded = 0

    from app.utils.s3_client import s3_client

    async with async_db_session() as db:
        for img in images:
            # Download image from RustFS
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

            rec = await db.execute(
                select(AnnotationRecordModel)
                .where(AnnotationRecordModel.image_id == img.id)
                .order_by(desc(AnnotationRecordModel.version))
                .limit(1)
            )
            record = rec.scalar_one_or_none()
            anns = record.annotation_data if record and record.annotation_data else []

            label_path = os.path.join(label_dir, img.filename.rsplit(".", 1)[0] + ".txt")
            lines = []
            for ann in anns:
                cls_id = ann.get("class_id", 0)
                classes.add(cls_id)
                if ann.get("type") in ("AxisAlignedBox", "box"):
                    if "x1" in ann:
                        x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
                        xc = (x1 + x2) / 2
                        yc = (y1 + y2) / 2
                        w = x2 - x1
                        h = y2 - y1
                    else:
                        xc = ann["x"]
                        yc = ann["y"]
                        w = ann["width"]
                        h = ann["height"]
                    lines.append(f"{cls_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}")
                elif ann.get("type") in ("RotatedBox", "rotated_box"):
                    cx, cy = ann["cx"], ann["cy"]
                    w, h = ann["width"], ann["height"]
                    lines.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            if lines:
                with open(label_path, "w") as f:
                    f.write("\n".join(lines))

    log.info(f"exported {downloaded} images, {len(classes)} classes to {output_dir}")

    yaml_path = os.path.join(output_dir, "dataset.yaml")
    with open(yaml_path, "w") as f:
        f.write("path: /data\n")
        f.write("train: .\n")
        f.write("val: .\n")
        f.write(f"nc: {len(classes)}\n")
        f.write(f"names: {json.dumps(sorted(classes))}\n")


def _export_paddlex(images: list, output_dir: str) -> None:
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    log.info(f"PaddleX export to {output_dir} — {len(images)} images")


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
