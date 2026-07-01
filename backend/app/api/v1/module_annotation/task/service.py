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
                log.warning(f"update_progress: task {task_id} not found")
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
            if progress >= 100:
                task.status = "COMPLETED"
                task.progress = 100
            elif progress > 0:
                task.status = "IN_PROGRESS"
                task.progress = progress
            else:
                task.status = "PENDING"
                task.progress = 0
            await db.commit()

    @classmethod
    async def get_task_progress(cls, task_id: int, auth) -> dict:
        async with async_db_session() as db:
            task = await db.get(AnnotationTaskModel, task_id)
            if not task:
                raise ValueError("任务不存在")
            total = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(AnnotationImageModel.dataset_id == task.dataset_id)
            )
            annotated = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(
                    AnnotationImageModel.dataset_id == task.dataset_id,
                    AnnotationImageModel.status != "UNANNOTATED",
                )
            ) or 0
            pct = int(annotated / total * 100) if total else 0
            status = "COMPLETED" if pct >= 100 else "IN_PROGRESS" if pct > 0 else "PENDING"
            return {
                "total_images": total or 0,
                "annotated_images": annotated,
                "progress": pct,
                "status": status.lower(),
            }