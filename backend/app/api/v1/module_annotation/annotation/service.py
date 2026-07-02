from sqlalchemy import select, desc

from app.core.database import async_db_session
from app.core.logger import log

from .model import AnnotationRecordModel


class AnnotationService:

    @classmethod
    async def save_annotations(cls, task_id: int, image_id: int, annotation_data: list[dict], auth) -> dict:
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
            version = existing.version + 1 if existing else 1

            db.add(AnnotationRecordModel(
                task_id=task_id, image_id=image_id, annotation_data=annotation_data,
                version=version, created_id=auth.user.id,
            ))

        log.info(f"save_annotations task={task_id} image={image_id} v={version}")
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
