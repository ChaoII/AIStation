import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import and_, desc, func, select

from app.core.database import async_db_session
from app.utils.s3_client import s3_client

from .crud import DatasetCRUD
from .model import AnnotationImageModel, DatasetModel, ImageStatus
from .schema import DatasetCreateSchema


class DatasetService:

    @classmethod
    async def create_dataset(cls, data: DatasetCreateSchema, auth) -> Any:
        crud = DatasetCRUD(auth=auth)
        dataset = await crud.create(data=data)
        s3_client.ensure_bucket()
        return dataset

    @classmethod
    async def upload_images(cls, dataset_id: int, files: list, auth) -> list[dict]:
        import io

        from PIL import Image

        from .model import AnnotationImageModel

        async with async_db_session.begin() as db:
            result = await db.execute(select(DatasetModel).where(DatasetModel.id == dataset_id))
            dataset = result.scalar_one_or_none()
            if not dataset:
                raise ValueError("数据集不存在")

            results = []
            for file in files:
                content = await file.read()
                ext = Path(file.filename).suffix.lower()
                object_key = f"datasets/{dataset_id}/images/{uuid.uuid4().hex}{ext}"

                s3_client.upload_fileobj(io.BytesIO(content), object_key)

                try:
                    img = Image.open(io.BytesIO(content))
                    width, height = img.size
                except Exception:
                    width, height = 0, 0

                img_record = AnnotationImageModel(
                    dataset_id=dataset_id,
                    filename=file.filename,
                    object_key=object_key,
                    width=width,
                    height=height,
                    status=ImageStatus.UNANNOTATED,
                )
                db.add(img_record)
                await db.flush()
                results.append({"id": img_record.id, "filename": file.filename, "object_key": object_key})

            total = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(AnnotationImageModel.dataset_id == dataset_id)
            )
            dataset.image_count = total or 0
            return results

    @classmethod
    async def get_images(cls, dataset_id: int, task_id: int | None = None) -> list:
        async with async_db_session() as db:
            sql = select(AnnotationImageModel).where(AnnotationImageModel.dataset_id == dataset_id).order_by(AnnotationImageModel.filename)
            result = await db.execute(sql)
            images = result.scalars().all()

            if not task_id:
                return images

            # For each image, check if it has annotations for this task
            from app.api.v1.module_system.user.model import UserModel

            from ..annotation.model import AnnotationRecordModel

            items = []
            for img in images:
                latest = await db.execute(
                    select(AnnotationRecordModel)
                    .where(and_(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.image_id == img.id,
                    ))
                    .order_by(desc(AnnotationRecordModel.version))
                    .limit(1)
                )
                rec = latest.scalar_one_or_none()

                has_data = rec and rec.annotation_data and (
                    isinstance(rec.annotation_data, list) and len(rec.annotation_data) > 0
                )
                status = "annotated" if has_data else "unannotated"

                # Get who annotated and when
                updater_name = None
                update_time = None
                if rec and has_data:
                    user = await db.get(UserModel, rec.created_id)
                    updater_name = user.name if user else None
                    update_time = rec.created_time

                items.append({
                    "id": img.id,
                    "dataset_id": img.dataset_id,
                    "filename": img.filename,
                    "object_key": img.object_key,
                    "width": img.width,
                    "height": img.height,
                    "status": status,
                    "locked_by": img.locked_by,
                    "updated_by": {"id": rec.created_id, "name": updater_name} if rec and has_data else None,
                    "updated_time": update_time.isoformat() if update_time else None,
                })
            return items

    @classmethod
    async def get_presigned_url(cls, image_id: int) -> str:
        async with async_db_session() as db:
            result = await db.execute(select(AnnotationImageModel).where(AnnotationImageModel.id == image_id))
            img = result.scalar_one_or_none()
            if not img:
                raise ValueError("图片不存在")
            return s3_client.presigned_url(img.object_key)
