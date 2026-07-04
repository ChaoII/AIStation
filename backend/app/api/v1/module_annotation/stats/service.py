from sqlalchemy import func, select

from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.dataset.model import DatasetModel
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.core.database import async_db_session


class StatsService:

    @classmethod
    async def get_overview(cls) -> dict:
        async with async_db_session() as db:
            dataset_count = await db.scalar(select(func.count(DatasetModel.id)))
            task_count = await db.scalar(select(func.count(AnnotationTaskModel.id)))
            annotated_count = await db.scalar(
                select(func.count(func.distinct(AnnotationRecordModel.image_id)))
            )
            return {
                "dataset_count": dataset_count or 0,
                "task_count": task_count or 0,
                "annotated_image_count": annotated_count or 0,
            }
