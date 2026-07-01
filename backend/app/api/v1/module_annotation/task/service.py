from sqlalchemy import select, func

from app.core.database import async_db_session
from app.core.logger import log

from ..dataset.model import AnnotationImageModel
from .model import AnnotationTaskModel


class TaskService:

    @classmethod
    async def update_progress(cls, task_id: int, auth=None) -> None:
        async with async_db_session() as db:
            task = await db.get(AnnotationTaskModel, task_id)
            if not task:
                return
            total = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(AnnotationImageModel.dataset_id == task.dataset_id)
            )
            if not total or total == 0:
                return
            annotated = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(
                    AnnotationImageModel.dataset_id == task.dataset_id,
                    AnnotationImageModel.status != "unannotated",
                )
            )
            progress = int(annotated / total * 100)
            status = "completed" if progress >= 100 else "in_progress" if progress > 0 else "pending"
            task.progress = progress
            task.status = status

    @classmethod
    async def get_task_progress(cls, task_id: int, auth) -> dict:
        async with async_db_session() as db:
            task = await db.get(AnnotationTaskModel, task_id)
            if not task:
                raise ValueError("任务不存在")
            images = await db.execute(
                select(AnnotationImageModel)
                .where(AnnotationImageModel.dataset_id == task.dataset_id)
            )
            rows = images.scalars().all()
            total = len(rows)
            annotated = sum(1 for img in rows if img.status != "unannotated")
            return {
                "total_images": total,
                "annotated_images": annotated,
                "progress": task.progress,
                "status": task.status,
            }