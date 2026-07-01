import os
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.logger import log
from app.utils.s3_client import s3_client

from .crud import DatasetCRUD, ImageCRUD
from .model import DatasetModel, AnnotationImageModel, ImageStatus
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
        from PIL import Image
        import io
        from sqlalchemy import func
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
    async def get_images(cls, dataset_id: int, status_filter: str | None = None) -> list:
        async with async_db_session() as db:
            sql = select(AnnotationImageModel).where(AnnotationImageModel.dataset_id == dataset_id)
            if status_filter:
                sql = sql.where(AnnotationImageModel.status == status_filter)
            result = await db.execute(sql)
            return result.scalars().all()

    @classmethod
    async def get_presigned_url(cls, image_id: int) -> str:
        async with async_db_session() as db:
            result = await db.execute(select(AnnotationImageModel).where(AnnotationImageModel.id == image_id))
            img = result.scalar_one_or_none()
            if not img:
                raise ValueError("图片不存在")
            return s3_client.presigned_url(img.object_key)