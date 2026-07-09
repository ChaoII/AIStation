from datetime import datetime, timedelta

from sqlalchemy import Date, cast, func, select, text

from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.dataset.model import AnnotationImageModel, DatasetModel
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.core.database import async_db_session


class StatsService:

    @classmethod
    async def get_overview(cls) -> dict:
        async with async_db_session() as db:
            dataset_count = await db.scalar(select(func.count(DatasetModel.id)))
            task_count = await db.scalar(select(func.count(AnnotationTaskModel.id)))
            image_count = await db.scalar(select(func.count(AnnotationImageModel.id))) or 0
            annotated_count = await db.scalar(
                select(func.count(func.distinct(AnnotationRecordModel.image_id)))
            ) or 0

            # Task count by type
            type_rows = await db.execute(
                select(AnnotationTaskModel.task_type, func.count(AnnotationTaskModel.id))
                .group_by(AnnotationTaskModel.task_type)
            )
            tasks_by_type = {str(r[0]): r[1] for r in type_rows}

            # Task count by status
            status_rows = await db.execute(
                select(AnnotationTaskModel.status, func.count(AnnotationTaskModel.id))
                .group_by(AnnotationTaskModel.status)
            )
            tasks_by_status = {str(r[0]): r[1] for r in status_rows}

            # Image count by status
            img_status_rows = await db.execute(
                select(AnnotationImageModel.status, func.count(AnnotationImageModel.id))
                .group_by(AnnotationImageModel.status)
            )
            images_by_status = {str(r[0]): r[1] for r in img_status_rows}

            # Daily annotated images (last 30 days)
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            daily_rows = await db.execute(
                select(
                    cast(AnnotationRecordModel.created_time, Date).label("day"),
                    func.count(func.distinct(AnnotationRecordModel.image_id)),
                )
                .where(AnnotationRecordModel.created_time >= thirty_days_ago)
                .group_by(text("day"))
                .order_by(text("day"))
            )
            daily_trend = [{"date": str(r[0]), "count": r[1]} for r in daily_rows]

            return {
                "dataset_count": dataset_count or 0,
                "task_count": task_count or 0,
                "image_count": image_count,
                "annotated_image_count": annotated_count,
                "tasks_by_type": tasks_by_type,
                "tasks_by_status": tasks_by_status,
                "images_by_status": images_by_status,
                "daily_trend": daily_trend,
            }

    @classmethod
    async def get_dataset_stats(cls, dataset_id: int) -> dict | None:
        async with async_db_session() as db:
            ds = await db.get(DatasetModel, dataset_id)
            if not ds:
                return None

            # Image counts
            unannotated = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(
                    AnnotationImageModel.dataset_id == dataset_id,
                    AnnotationImageModel.status == "unannotated",
                )
            ) or 0
            in_progress = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(
                    AnnotationImageModel.dataset_id == dataset_id,
                    AnnotationImageModel.status == "in_progress",
                )
            ) or 0
            annotated = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(
                    AnnotationImageModel.dataset_id == dataset_id,
                    AnnotationImageModel.status == "annotated",
                )
            ) or 0

            # Resolution distribution
            res_rows = await db.execute(
                select(
                    AnnotationImageModel.width,
                    AnnotationImageModel.height,
                    func.count(AnnotationImageModel.id),
                )
                .where(AnnotationImageModel.dataset_id == dataset_id)
                .group_by(AnnotationImageModel.width, AnnotationImageModel.height)
                .order_by(func.count(AnnotationImageModel.id).desc())
                .limit(10)
            )
            resolution_dist = [
                {"width": r[0], "height": r[1], "count": r[2]} for r in res_rows
            ]

            # Tasks for this dataset
            tasks = await db.execute(
                select(AnnotationTaskModel).where(
                    AnnotationTaskModel.dataset_id == dataset_id
                )
            )
            tasks_list = tasks.scalars().all()

            # Class distribution and user contributions across all tasks
            class_counter: dict[int, int] = {}
            user_counter: dict[int, int] = {}
            total_annotations = 0

            for task in tasks_list:
                # class name lookup from task.classes
                if task.classes:
                    for cls_def in task.classes if isinstance(task.classes, list) else task.classes.get("classes", []):
                        cid = cls_def.get("id") if isinstance(cls_def, dict) else None
                        if cid is not None and cid not in class_counter:
                            class_counter[cid] = 0  # ensure all defined classes appear

                # Query annotation records for this task
                ann_rows = await db.execute(
                    select(AnnotationRecordModel.annotation_data, AnnotationRecordModel.created_id)
                    .where(AnnotationRecordModel.task_id == task.id)
                )
                for row in ann_rows:
                    ann_data = row[0]
                    created_id = row[1]
                    if isinstance(ann_data, list):
                        for item in ann_data:
                            cid = item.get("class_id") if isinstance(item, dict) else None
                            if cid is not None:
                                class_counter[cid] = class_counter.get(cid, 0) + 1
                                total_annotations += 1
                    if created_id:
                        user_counter[created_id] = user_counter.get(created_id, 0) + 1

            # Build class name map from all tasks
            class_name_map: dict[int, str] = {}
            for task in tasks_list:
                if task.classes:
                    if isinstance(task.classes, list):
                        for cls_def in task.classes:
                            cid = cls_def.get("id")
                            if cid is not None:
                                class_name_map.setdefault(cid, cls_def.get("name", f"class_{cid}"))
                    elif isinstance(task.classes, dict):
                        for cid_str, cls_def in task.classes.items():
                            try:
                                cid = int(cid_str)
                                class_name_map.setdefault(cid, cls_def.get("name", f"class_{cid}") if isinstance(cls_def, dict) else str(cls_def))
                            except ValueError:
                                pass

            class_distribution = [
                {"class_id": cid, "class_name": class_name_map.get(cid, f"class_{cid}"), "count": cnt}
                for cid, cnt in sorted(class_counter.items(), key=lambda x: -x[1])
            ]

            # Avg annotations per image
            total_images = unannotated + in_progress + annotated
            avg_density = round(total_annotations / total_images, 2) if total_images > 0 else 0
            annotated_images = annotated
            annot_avg = round(total_annotations / annotated_images, 2) if annotated_images > 0 else 0

            return {
                "dataset_id": dataset_id,
                "name": ds.name,
                "image_count": total_images,
                "annotated_count": annotated,
                "unannotated_count": unannotated,
                "in_progress_count": in_progress,
                "total_annotations": total_annotations,
                "annotations_per_image_avg": avg_density,
                "annotations_per_annotated_image_avg": annot_avg,
                "class_distribution": class_distribution,
                "resolution_distribution": resolution_dist,
                "user_contributions": [
                    {"user_id": uid, "annotation_count": cnt}
                    for uid, cnt in sorted(user_counter.items(), key=lambda x: -x[1])
                ],
            }
