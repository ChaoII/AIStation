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
"""

import json
import os
import tempfile
import zipfile
from datetime import datetime

from sqlalchemy import select

from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.dataset.model import (
    AnnotationImageModel,
    AnnotationType,
    DatasetModel,
    ImageStatus,
)
from app.api.v1.module_annotation.task.model import AnnotationTaskModel, TaskStatus
from app.core.database import async_db_session
from app.core.logger import log
from app.utils.s3_client import s3_client


async def import_x_anylabeling_zip(zip_file, dataset_id: int, user_id: int) -> dict:
    """Parse x-anylabeling ZIP, import images + annotations into dataset."""
    extract_dir = tempfile.mkdtemp(prefix="xal_")
    try:
        with zipfile.ZipFile(zip_file, "r") as zf:
            zf.extractall(extract_dir)
        return await _import_from_dir(extract_dir, dataset_id, user_id)
    finally:
        import shutil
        shutil.rmtree(extract_dir, ignore_errors=True)


async def _import_from_dir(src_dir: str, dataset_id: int, user_id: int) -> dict:
    """Import x-anylabeling data from an extracted directory."""
    # Collect image files and their JSON sidecars
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
    json_files: dict[str, str] = {}  # stem → json_path
    image_files: dict[str, str] = {}  # stem → img_path

    for root, _, files in os.walk(src_dir):
        for f in files:
            stem, ext = os.path.splitext(f)
            ext_lower = ext.lower()
            path = os.path.join(root, f)
            if ext_lower == ".json":
                json_files[stem] = path
            elif ext_lower in image_extensions:
                image_files[stem] = path

    if not image_files:
        return {"imported": 0, "total_images": 0, "total_annotations": 0, "class_mapping": {}, "error": "ZIP 中未找到图片文件"}

    # Scan all JSON files to build class mapping (label → sequential class_id)
    all_labels: set[str] = set()
    for stem, jp in json_files.items():
        try:
            with open(jp, encoding="utf-8") as f:
                data = json.load(f)
            for shape in data.get("shapes", []):
                label = shape.get("label", "").strip()
                if label:
                    all_labels.add(label)
        except Exception:
            continue

    sorted_labels = sorted(all_labels)
    class_mapping = {label: idx for idx, label in enumerate(sorted_labels)}

    now = datetime.now()
    imported_count = 0
    total_annotations = 0

    # Determine annotation type from labels (heuristic: if class_mapping has entries, use detection)
    task_type = AnnotationType.DETECTION

    async with async_db_session.begin() as db:
        # Create an annotation task for the imported data
        ds = await db.get(DatasetModel, dataset_id)
        task_name = f"[导入] {ds.name if ds else 'dataset_' + str(dataset_id)} - x-anylabeling"
        ann_task = AnnotationTaskModel(
            dataset_id=dataset_id,
            name=task_name,
            task_type=task_type,
            status=TaskStatus.COMPLETED,
            classes=[{"id": cid, "name": label} for label, cid in sorted(class_mapping.items(), key=lambda x: x[1])],
            progress=100,
            completed_at=now,
            created_id=user_id,
        )
        db.add(ann_task)
        await db.flush()
        task_id = ann_task.id

        for stem, img_path in image_files.items():
            # Upload image to RustFS
            ext = os.path.splitext(img_path)[1]
            object_key = f"annotations/dataset_{dataset_id}/{stem}{ext}"
            with open(img_path, "rb") as f:
                s3_client.upload_fileobj(f, object_key)
            img_url = s3_client.presigned_url(object_key)

            # Determine image dimensions from JSON sidecar if available
            img_height = 0
            img_width = 0
            if stem in json_files:
                try:
                    with open(json_files[stem], encoding="utf-8") as f:
                        meta = json.load(f)
                    img_height = meta.get("imageHeight", 0) or 0
                    img_width = meta.get("imageWidth", 0) or 0
                except Exception:
                    pass
            if not img_height or not img_width:
                img_height, img_width = _get_image_size(img_path)

            # Create image record
            img_rec = AnnotationImageModel(
                dataset_id=dataset_id,
                filename=f"{stem}{ext}",
                object_key=object_key,
                url=img_url,
                status=ImageStatus.ANNOTATED,
                width=img_width,
                height=img_height,
                created_id=user_id,
            )
            db.add(img_rec)
            await db.flush()

            # Parse annotations
            annotations = []
            if stem in json_files:
                try:
                    with open(json_files[stem], encoding="utf-8") as f:
                        data = json.load(f)
                    for shape in data.get("shapes", []):
                        ann = _shape_to_annotation(shape, class_mapping, img_width, img_height)
                        if ann:
                            annotations.append(ann)
                except Exception as e:
                    log.warning(f"skip annotation for {stem}: {e}")

            # Create annotation record
            if annotations:
                total_annotations += len(annotations)
                ann_rec = AnnotationRecordModel(
                    task_id=task_id,
                    image_id=img_rec.id,
                    annotation_data=annotations,
                    version=1,
                )
                db.add(ann_rec)

            imported_count += 1

        # Update dataset counts
        await db.execute(
            select(DatasetModel).where(DatasetModel.id == dataset_id)
        )
        ds = await db.get(DatasetModel, dataset_id)
        if ds:
            ds.image_count = (ds.image_count or 0) + imported_count
            ds.annotated_count = (ds.annotated_count or 0) + imported_count

    # Update task progress after transaction commits
    if task_id:
        from app.api.v1.module_annotation.task.service import TaskService
        try:
            await TaskService.update_progress(task_id)
        except Exception as e:
            log.warning(f"update_progress failed: {e}")

    return {
        "imported": imported_count,
        "total_images": len(image_files),
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
            "type": "AxisAlignedBox",
            "class_id": class_id,
            "label": label,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
        }
    elif shape_type == "polygon" and len(points) >= 3:
        return {
            "type": "polygon",
            "class_id": class_id,
            "label": label,
            "points": points,
        }
    elif shape_type == "point" and len(points) >= 1:
        return {
            "type": "point",
            "class_id": class_id,
            "label": label,
            "x": points[0][0],
            "y": points[0][1],
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
