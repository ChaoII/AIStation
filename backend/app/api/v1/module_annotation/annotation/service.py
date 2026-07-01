from sqlalchemy import select, desc

from app.core.database import async_db_session
from app.core.logger import log

from ..dataset.crud import image_crud
from ..dataset.model import ImageStatus
from .crud import AnnotationCRUD
from .model import AnnotationRecordModel


annotation_crud = AnnotationCRUD()


class AnnotationService:

    @classmethod
    async def save_annotations(cls, task_id: int, image_id: int, annotation_data: list[dict], auth) -> dict:
        from ..task.service import TaskService
        from ..dataset.crud import ImageCRUD
        img_crud = ImageCRUD(auth=auth)
        async with async_db_session.begin() as db:
            result = await db.execute(
                select(AnnotationRecordModel)
                .where(
                    AnnotationRecordModel.task_id == task_id,
                    AnnotationRecordModel.image_id == image_id,
                )
                .order_by(desc(AnnotationRecordModel.version))
                .limit(1)
            )
            existing = result.scalar_one_or_none()

            if existing:
                version = existing.version + 1
            else:
                version = 1

            record = AnnotationRecordModel(
                task_id=task_id,
                image_id=image_id,
                annotation_data=annotation_data,
                version=version,
                created_id=auth.user.id,
            )
            db.add(record)

        await img_crud.update(
            id=image_id,
            data={
                "status": ImageStatus.ANNOTATED,
                "annotation_count": len(annotation_data),
            },
        )

        from ..task.service import TaskService
        await TaskService.update_progress(task_id)

        return {"version": version, "annotation_count": len(annotation_data)}

    @classmethod
    async def get_annotations(cls, task_id: int, image_id: int) -> list[dict] | None:
        async with async_db_session.begin() as db:
            result = await db.execute(
                select(AnnotationRecordModel)
                .where(
                    AnnotationRecordModel.task_id == task_id,
                    AnnotationRecordModel.image_id == image_id,
                )
                .order_by(desc(AnnotationRecordModel.version))
                .limit(1)
            )
            record = result.scalar_one_or_none()
            return record.annotation_data if record else None

    @classmethod
    async def get_annotation_history(cls, task_id: int, image_id: int) -> list[dict]:
        async with async_db_session.begin() as db:
            result = await db.execute(
                select(AnnotationRecordModel)
                .where(
                    AnnotationRecordModel.task_id == task_id,
                    AnnotationRecordModel.image_id == image_id,
                )
                .order_by(desc(AnnotationRecordModel.version))
            )
            records = result.scalars().all()
            return [
                {
                    "version": r.version,
                    "annotation_data": r.annotation_data,
                    "created_id": r.created_id,
                    "created_time": r.created_time.isoformat() if r.created_time else None,
                }
                for r in records
            ]