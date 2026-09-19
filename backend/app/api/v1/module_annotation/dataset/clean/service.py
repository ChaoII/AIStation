from collections import Counter

from sqlalchemy import func, select

from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.dataset.model import AnnotationImageModel, DatasetModel
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.core.database import async_db_session


class CleanService:

    @classmethod
    async def check_dataset(cls, dataset_id: int) -> dict | None:
        async with async_db_session() as db:
            ds = await db.get(DatasetModel, dataset_id)
            if not ds:
                return None

            # Get all images
            img_rows = await db.execute(
                select(AnnotationImageModel).where(
                    AnnotationImageModel.dataset_id == dataset_id
                )
            )
            images = img_rows.scalars().all()

            # Get all tasks for this dataset
            task_rows = await db.execute(
                select(AnnotationTaskModel).where(
                    AnnotationTaskModel.dataset_id == dataset_id
                )
            )
            tasks = task_rows.scalars().all()

            issues = []

            # Check duplicate filenames
            filenames = [img.filename for img in images]
            dup_files = [name for name, cnt in Counter(filenames).items() if cnt > 1]
            if dup_files:
                issues.append({
                    "type": "duplicate_filename",
                    "severity": "warning",
                    "message": f"发现 {len(dup_files)} 个文件名重复",
                    "details": dup_files[:10],
                })

            # Check duplicate dimensions + filesize
            dim_size = Counter(
                f"{img.width}x{img.height}" for img in images
            )
            dup_dim = [(k, v) for k, v in dim_size.items() if v > 5]
            if dup_dim:
                issues.append({
                    "type": "similar_images",
                    "severity": "info",
                    "message": f"发现 {len(dup_dim)} 组图片尺寸高度重复（疑似重复图片）",
                    "details": [f"{k}: {v}张" for k, v in dup_dim[:10]],
                })

            # Check tasks without any annotations
            for task in tasks:
                cnt = await db.scalar(
                    select(func.count(AnnotationRecordModel.id))
                    .where(AnnotationRecordModel.task_id == task.id)
                )
                if cnt == 0:
                    issues.append({
                        "type": "empty_task",
                        "severity": "warning",
                        "message": f"任务「{task.name}」没有任何标注记录",
                    })

            # Check images without annotations
            unannotated = [img for img in images if img.status == "unannotated"]
            if unannotated:
                issues.append({
                    "type": "unannotated_images",
                    "severity": "info",
                    "message": f"有 {len(unannotated)} 张图片未标注（共 {len(images)} 张）",
                })

            return {
                "dataset_id": dataset_id,
                "name": ds.name,
                "image_count": len(images),
                "task_count": len(tasks),
                "issues": issues,
                "health": "good" if not [i for i in issues if i["severity"] == "warning"] else "warning",
            }

    @classmethod
    async def detect_duplicate_images(cls, dataset_id: int) -> list[dict]:
        async with async_db_session() as db:
            img_rows = await db.execute(
                select(AnnotationImageModel).where(
                    AnnotationImageModel.dataset_id == dataset_id
                ).order_by(AnnotationImageModel.filename)
            )
            images = img_rows.scalars().all()

            # Group by filename
            groups: dict[str, list[dict]] = {}
            for img in images:
                groups.setdefault(img.filename, []).append({
                    "id": img.id,
                    "filename": img.filename,
                    "width": img.width,
                    "height": img.height,
                    "status": img.status,
                })

            duplicates = [g for g in groups.values() if len(g) > 1]
            return duplicates

    @classmethod
    async def detect_anomalous_annotations(cls, dataset_id: int) -> list[dict]:
        async with async_db_session() as db:
            # Get tasks for this dataset
            task_rows = await db.execute(
                select(AnnotationTaskModel).where(
                    AnnotationTaskModel.dataset_id == dataset_id
                )
            )
            tasks = task_rows.scalars().all()

            anomalies = []
            for task in tasks:
                ann_rows = await db.execute(
                    select(
                        AnnotationRecordModel,
                        AnnotationImageModel.width,
                        AnnotationImageModel.height,
                    )
                    .join(
                        AnnotationImageModel,
                        AnnotationRecordModel.image_id == AnnotationImageModel.id,
                    )
                    .where(AnnotationRecordModel.task_id == task.id)
                )

                for row in ann_rows:
                    record = row[0]
                    img_w = row[1] or 0
                    img_h = row[2] or 0
                    ann_data = record.annotation_data or []

                    if not isinstance(ann_data, list) or len(ann_data) == 0:
                        continue

                    for item in ann_data:
                        if not isinstance(item, dict):
                            continue
                        issues = []
                        ann_id = item.get("id", "")
                        ann_type = item.get("type", "")

                        # 旧格式（box + 像素 points）兼容检测
                        if ann_type == "box" and isinstance(item.get("points"), list) and len(item["points"]) == 2:
                            pts = item["points"]
                            x1, y1 = pts[0]
                            x2, y2 = pts[1]
                            if x2 <= x1 or y2 <= y1:
                                issues.append("零面积框")
                            if img_w > 0 and (x1 < 0 or x2 > img_w or y1 < 0 or y2 > img_h):
                                issues.append("越界框")

                        # 工作台格式（归一化 0~1）检测
                        if ann_type in ("AxisAlignedBox", "RotatedBox"):
                            if ann_type == "AxisAlignedBox":
                                x1, y1 = item.get("x1", 0), item.get("y1", 0)
                                x2, y2 = item.get("x2", 0), item.get("y2", 0)
                                if x2 <= x1 or y2 <= y1:
                                    issues.append("零面积框")
                                if x1 < 0 or y1 < 0 or x2 > 1 or y2 > 1:
                                    issues.append("越界框")
                            else:  # RotatedBox（cx,cy,width,height 归一化）
                                w = item.get("width", 0)
                                h = item.get("height", 0)
                                if w <= 0 or h <= 0:
                                    issues.append("零面积框")
                                cx, cy = item.get("cx", 0.5), item.get("cy", 0.5)
                                half = (w * w + h * h) ** 0.5 / 2
                                if cx - half < 0 or cx + half > 1 or cy - half < 0 or cy + half > 1:
                                    issues.append("越界框")
                        elif ann_type == "Polygon":
                            pts = item.get("points") or []
                            if len(pts) < 3:
                                issues.append("空多边形")
                            elif any(
                                not (0 <= p.get("x", 0) <= 1 and 0 <= p.get("y", 0) <= 1)
                                for p in pts
                            ):
                                issues.append("越界框")
                        elif ann_type == "Ocr":
                            pts = item.get("points") or []
                            if len(pts) < 4:
                                issues.append("点不足(需≥4)")
                            elif any(
                                not (0 <= p.get("x", 0) <= 1 and 0 <= p.get("y", 0) <= 1)
                                for p in pts
                            ):
                                issues.append("越界框")
                        elif ann_type == "Keypoint":
                            kps = item.get("keypoints") or []
                            if not kps:
                                issues.append("空关键点")
                            elif any(
                                not (0 <= k.get("x", 0) <= 1 and 0 <= k.get("y", 0) <= 1)
                                for k in kps
                            ):
                                issues.append("越界框")

                        if issues:
                            anomalies.append({
                                "task_id": task.id,
                                "task_name": task.name,
                                "image_id": record.image_id,
                                "annotation_id": ann_id,
                                "issues": issues,
                                "type": ann_type,
                            })

            return anomalies
