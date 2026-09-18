from datetime import datetime, timedelta

from sqlalchemy import bindparam, func, select, text

from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.dataset.model import AnnotationImageModel, DatasetModel
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.config.setting import settings
from app.core.database import async_db_session


class StatsService:

    @classmethod
    async def get_overview(cls) -> dict:
        async with async_db_session() as db:
            # 所有计数均排除软删数据
            dataset_count = await db.scalar(
                select(func.count(DatasetModel.id)).where(DatasetModel.is_deleted == False)  # noqa: E712
            )
            task_count = await db.scalar(
                select(func.count(AnnotationTaskModel.id)).where(AnnotationTaskModel.is_deleted == False)  # noqa: E712
            )
            image_count = await db.scalar(
                select(func.count(AnnotationImageModel.id)).where(AnnotationImageModel.is_deleted == False)  # noqa: E712
            ) or 0
            annotated_count = await db.scalar(
                select(func.count(func.distinct(AnnotationRecordModel.image_id)))
                .where(AnnotationRecordModel.is_deleted == False)  # noqa: E712
            ) or 0

            # Task count by type（枚举键取值，而非 "AnnotationType.X"）
            type_rows = await db.execute(
                select(AnnotationTaskModel.task_type, func.count(AnnotationTaskModel.id))
                .where(AnnotationTaskModel.is_deleted == False)  # noqa: E712
                .group_by(AnnotationTaskModel.task_type)
            )
            tasks_by_type = {getattr(r[0], "value", r[0]): r[1] for r in type_rows}

            # Task count by status
            status_rows = await db.execute(
                select(AnnotationTaskModel.status, func.count(AnnotationTaskModel.id))
                .where(AnnotationTaskModel.is_deleted == False)  # noqa: E712
                .group_by(AnnotationTaskModel.status)
            )
            tasks_by_status = {str(r[0]): r[1] for r in status_rows}

            # Image count by status（枚举键取值）
            img_status_rows = await db.execute(
                select(AnnotationImageModel.status, func.count(AnnotationImageModel.id))
                .where(AnnotationImageModel.is_deleted == False)  # noqa: E712
                .group_by(AnnotationImageModel.status)
            )
            images_by_status = {getattr(r[0], "value", r[0]): r[1] for r in img_status_rows}

            # Daily annotated images (last 30 days)
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            daily_rows = await db.execute(
                select(
                    func.date(AnnotationRecordModel.created_time).label("day"),
                    func.count(func.distinct(AnnotationRecordModel.image_id)),
                )
                .where(
                    AnnotationRecordModel.created_time >= thirty_days_ago,
                    AnnotationRecordModel.is_deleted == False,  # noqa: E712
                )
                .group_by(text("day"))
                .order_by(text("day"))
            )
            daily_trend = [{"date": str(r[0]), "count": r[1]} for r in daily_rows]

            # 数据集图片数 Top10（供首页图表；聚合查询，避免前端拉 100 行列表）
            top_ds_rows = await db.execute(
                select(DatasetModel.name, DatasetModel.image_count)
                .where(DatasetModel.is_deleted == False)  # noqa: E712
                .order_by(DatasetModel.image_count.desc())
                .limit(10)
            )
            top_datasets = [{"name": r[0], "image_count": r[1] or 0} for r in top_ds_rows]

            return {
                "dataset_count": dataset_count or 0,
                "task_count": task_count or 0,
                "image_count": image_count,
                "annotated_image_count": annotated_count,
                "tasks_by_type": tasks_by_type,
                "tasks_by_status": tasks_by_status,
                "images_by_status": images_by_status,
                "daily_trend": daily_trend,
                "top_datasets": top_datasets,
            }

    @classmethod
    async def get_dataset_stats(cls, dataset_id: int) -> dict | None:
        async with async_db_session() as db:
            ds = await db.get(DatasetModel, dataset_id)
            if not ds:
                return None

            # Image counts（排除软删图片）
            unannotated = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(
                    AnnotationImageModel.dataset_id == dataset_id,
                    AnnotationImageModel.status == "unannotated",
                    AnnotationImageModel.is_deleted == False,  # noqa: E712
                )
            ) or 0
            in_progress = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(
                    AnnotationImageModel.dataset_id == dataset_id,
                    AnnotationImageModel.status == "in_progress",
                    AnnotationImageModel.is_deleted == False,  # noqa: E712
                )
            ) or 0
            annotated = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(
                    AnnotationImageModel.dataset_id == dataset_id,
                    AnnotationImageModel.status == "annotated",
                    AnnotationImageModel.is_deleted == False,  # noqa: E712
                )
            ) or 0

            # Resolution distribution
            res_rows = await db.execute(
                select(
                    AnnotationImageModel.width,
                    AnnotationImageModel.height,
                    func.count(AnnotationImageModel.id),
                )
                .where(
                    AnnotationImageModel.dataset_id == dataset_id,
                    AnnotationImageModel.is_deleted == False,  # noqa: E712
                )
                .group_by(AnnotationImageModel.width, AnnotationImageModel.height)
                .order_by(func.count(AnnotationImageModel.id).desc())
                .limit(10)
            )
            resolution_dist = [
                {"width": r[0], "height": r[1], "count": r[2]} for r in res_rows
            ]

            # Tasks for this dataset（排除软删任务）
            tasks = await db.execute(
                select(AnnotationTaskModel).where(
                    AnnotationTaskModel.dataset_id == dataset_id,
                    AnnotationTaskModel.is_deleted == False,  # noqa: E712
                )
            )
            tasks_list = tasks.scalars().all()
            task_ids = [t.id for t in tasks_list]

            # Class distribution and user contributions：SQL 聚合（跨方言 json 展开），
            # 避免对每个任务拉全部 annotation_data 再在 Python 逐条展开大 JSON。
            # 仅统计带 class_id 的条目（与旧口径一致）。
            class_counter: dict[int, int] = {}
            user_counter: dict[int, int] = {}
            total_annotations = 0

            if task_ids:
                if settings.DATABASE_TYPE == "sqlite":
                    agg_sql = text(
                        """
                        SELECT json_extract(elem.value, '$.class_id') AS class_id,
                               ar.created_id AS created_id,
                               COUNT(*) AS cnt
                        FROM annotation_record ar, json_each(ar.annotation_data) AS elem
                        WHERE ar.task_id IN :task_ids AND ar.is_deleted = 0
                          AND json_extract(elem.value, '$.class_id') IS NOT NULL
                        GROUP BY class_id, ar.created_id
                        """
                    )
                else:
                    agg_sql = text(
                        """
                        SELECT elem.value ->> 'class_id' AS class_id,
                               ar.created_id AS created_id,
                               COUNT(*) AS cnt
                        FROM annotation_record ar, jsonb_array_elements(ar.annotation_data) AS elem
                        WHERE ar.task_id IN :task_ids AND ar.is_deleted = false
                          AND (elem.value ->> 'class_id') IS NOT NULL
                        GROUP BY class_id, ar.created_id
                        """
                    )
                agg_sql = agg_sql.bindparams(bindparam("task_ids", expanding=True))
                rows = (await db.execute(agg_sql, {"task_ids": task_ids})).fetchall()
                for class_id, created_id, cnt in rows:
                    total_annotations += cnt
                    try:
                        cid = int(class_id)
                    except (TypeError, ValueError):
                        cid = class_id
                    class_counter[cid] = class_counter.get(cid, 0) + cnt
                    if created_id:
                        user_counter[created_id] = user_counter.get(created_id, 0) + cnt

            # Build class name map from all tasks（同时把已定义但未出现的类补 0）
            class_name_map: dict[int, str] = {}
            for task in tasks_list:
                if task.classes:
                    if isinstance(task.classes, list):
                        for cls_def in task.classes:
                            cid = cls_def.get("id")
                            if cid is not None:
                                class_name_map.setdefault(cid, cls_def.get("name", f"class_{cid}"))
                                class_counter.setdefault(cid, 0)
                    elif isinstance(task.classes, dict):
                        for cid_str, cls_def in task.classes.items():
                            try:
                                cid = int(cid_str)
                            except ValueError:
                                continue
                            class_name_map.setdefault(
                                cid,
                                cls_def.get("name", f"class_{cid}")
                                if isinstance(cls_def, dict) else str(cls_def),
                            )
                            class_counter.setdefault(cid, 0)

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
