import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import and_, func, select

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
    async def get_images(cls, dataset_id: int, task_id: int | None = None,
                         page_no: int = 1, page_size: int = 100) -> dict:
        offset = (page_no - 1) * page_size
        async with async_db_session() as db:
            # Count
            count_sql = select(func.count()).select_from(
                select(AnnotationImageModel).where(AnnotationImageModel.dataset_id == dataset_id).subquery()
            )
            total = (await db.execute(count_sql)).scalar() or 0

            # Get paginated images
            sql = (select(AnnotationImageModel)
                   .where(AnnotationImageModel.dataset_id == dataset_id)
                   .order_by(AnnotationImageModel.filename)
                   .limit(page_size).offset(offset))
            result = await db.execute(sql)
            images = result.scalars().all()

            if not task_id or not images:
                return {"items": [_img_minimal(i) for i in images], "total": total, "page": page_no}

            # Bulk-load annotation statuses — one query instead of N
            from ..annotation.model import AnnotationRecordModel
            img_ids = [i.id for i in images]
            recs = await db.execute(
                select(AnnotationRecordModel.task_id, AnnotationRecordModel.image_id,
                       AnnotationRecordModel.annotation_data, AnnotationRecordModel.version,
                       AnnotationRecordModel.created_id, AnnotationRecordModel.created_time)
                .where(and_(
                    AnnotationRecordModel.task_id == task_id,
                    AnnotationRecordModel.image_id.in_(img_ids),
                ))
                .order_by(AnnotationRecordModel.version.desc())
            )
            rec_rows = recs.fetchall()

            # Build image_id → latest annotation record map
            from app.api.v1.module_system.user.model import UserModel
            ann_map: dict[int, dict] = {}
            user_cache: dict[int, str] = {}
            for r in rec_rows:
                iid = r[1]
                if iid not in ann_map:
                    ann_map[iid] = {
                        "has_data": bool(r[2] and isinstance(r[2], list) and len(r[2]) > 0),
                        "created_id": r[4],
                        "created_time": r[5],
                    }
            for uid in {a["created_id"] for a in ann_map.values() if a["created_id"]}:
                u = await db.get(UserModel, uid)
                if u:
                    user_cache[uid] = u.name

            items = []
            for img in images:
                info = ann_map.get(img.id)
                has_data = info and info["has_data"]
                status = "annotated" if has_data else "unannotated"
                updater_name = user_cache.get(info["created_id"]) if info and info["created_id"] else None
                update_time = info["created_time"] if info else None
                items.append({
                    "id": img.id,
                    "dataset_id": img.dataset_id,
                    "filename": img.filename,
                    "object_key": img.object_key,
                    "width": img.width,
                    "height": img.height,
                    "status": status,
                    "locked_by": img.locked_by,
                    "updated_by": {"id": (info or {}).get("created_id"), "name": updater_name} if info and has_data else None,
                    "updated_time": update_time.isoformat() if update_time else None,
                })
            return {"items": items, "total": total, "page": page_no}

    @classmethod
    async def get_presigned_url(cls, image_id: int) -> str:
        async with async_db_session() as db:
            result = await db.execute(select(AnnotationImageModel).where(AnnotationImageModel.id == image_id))
            img = result.scalar_one_or_none()
            if not img:
                raise ValueError("图片不存在")
            return s3_client.presigned_url(img.object_key)


def _img_minimal(img) -> dict:
    return {
        "id": img.id,
        "dataset_id": img.dataset_id,
        "filename": img.filename,
        "object_key": img.object_key,
        "width": img.width,
        "height": img.height,
        "status": img.status.value if hasattr(img.status, "value") else img.status,
        "locked_by": img.locked_by,
    }
