import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import and_, delete, func, select, update

from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel
from app.api.v1.module_annotation.task.model import AnnotationTaskModel
from app.config.setting import settings
from app.core.audit import set_create_audit
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.utils.s3_client import s3_client

from .crud import DatasetCRUD
from .export_model import DatasetExportModel
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
    async def delete_datasets(cls, ids: list[int], auth) -> None:
        """软删数据集，并级联软删其图片与标注记录。"""
        from datetime import datetime

        actor_id = getattr(getattr(auth, "user", None), "id", None)
        async with async_db_session.begin() as db:
            for dataset_id in ids:
                img_ids = (
                    await db.execute(
                        select(AnnotationImageModel.id).where(
                            AnnotationImageModel.dataset_id == dataset_id
                        )
                    )
                ).scalars().all()
                soft = {"is_deleted": True, "deleted_time": datetime.now(), "deleted_id": actor_id}
                if img_ids:
                    await db.execute(
                        update(AnnotationRecordModel)
                        .where(AnnotationRecordModel.image_id.in_(img_ids))
                        .values(**soft)
                    )
                await db.execute(
                    update(AnnotationImageModel)
                    .where(AnnotationImageModel.dataset_id == dataset_id)
                    .values(**soft)
                )
                # 级联软删该数据集下的任务，避免数据集删除后任务仍计入统计
                await db.execute(
                    update(AnnotationTaskModel)
                    .where(AnnotationTaskModel.dataset_id == dataset_id)
                    .values(**soft)
                )
        from .crud import DatasetCRUD
        await DatasetCRUD(auth=auth).delete(ids=ids)

    @classmethod
    async def purge_datasets(cls, ids: list[int]) -> dict:
        """彻底删除数据集：先删 S3 对象，再物理删 DB 行（不可逆）。"""
        purged = 0
        for dataset_id in ids:
            # 1) 先删对象存储，失败则抛出，DB 不提交，避免留下不可恢复态
            s3_client.delete_prefix(f"datasets/{dataset_id}/")
            s3_client.delete_prefix(f"annotations/dataset_{dataset_id}/")
            s3_client.delete_prefix(f"train/exports/dataset_{dataset_id}_")

            # 2) 物理删除 DB（含软删行）
            async with async_db_session.begin() as db:
                img_ids = (
                    await db.execute(
                        select(AnnotationImageModel.id).where(
                            AnnotationImageModel.dataset_id == dataset_id
                        )
                    )
                ).scalars().all()
                if img_ids:
                    await db.execute(
                        delete(AnnotationRecordModel).where(
                            AnnotationRecordModel.image_id.in_(img_ids)
                        )
                    )
                await db.execute(
                    delete(DatasetExportModel).where(
                        DatasetExportModel.dataset_id == dataset_id
                    )
                )
                await db.execute(
                    delete(AnnotationImageModel).where(
                        AnnotationImageModel.dataset_id == dataset_id
                    )
                )
                await db.execute(
                    delete(AnnotationTaskModel).where(
                        AnnotationTaskModel.dataset_id == dataset_id
                    )
                )
                await db.execute(
                    delete(DatasetModel).where(DatasetModel.id == dataset_id)
                )
            purged += 1
        return {"purged": purged}

    @classmethod
    async def upload_images(cls, dataset_id: int, files: list, auth) -> dict:
        import asyncio
        import io

        from .media import (
            ALLOWED_IMAGE_EXTENSIONS,
            content_type_for,
            process_image,
        )

        # 1) 整批校验（不写任何对象/行）
        if len(files) > settings.ANNOTATION_UPLOAD_MAX_FILES:
            raise CustomException(
                msg=f"单次最多上传 {settings.ANNOTATION_UPLOAD_MAX_FILES} 张图片",
                code=400, status_code=400,
            )
        max_bytes = settings.ANNOTATION_UPLOAD_MAX_MB * 1024 * 1024
        for file in files:
            ext = Path(file.filename or "").suffix.lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                raise CustomException(
                    msg=f"不支持的图片格式: {file.filename}", code=400, status_code=400
                )
            size = getattr(file, "size", None)
            if size is not None and size > max_bytes:
                raise CustomException(
                    msg=f"文件过大（>{settings.ANNOTATION_UPLOAD_MAX_MB}MB）: {file.filename}",
                    code=400, status_code=400,
                )

        async with async_db_session() as db:
            dataset = await db.get(DatasetModel, dataset_id)
            if not dataset:
                raise ValueError("数据集不存在")

        sem = asyncio.Semaphore(max(1, settings.ANNOTATION_UPLOAD_CONCURRENCY))

        async def _process(file) -> dict:
            filename = file.filename or "unnamed"
            async with sem:
                try:
                    content = await file.read()
                    ext = Path(filename).suffix.lower()
                    token = uuid.uuid4().hex
                    object_key = f"datasets/{dataset_id}/images/{token}{ext}"
                    thumb_key = f"datasets/{dataset_id}/thumbnails/{token}.jpg"
                    width, height, thumb = await asyncio.to_thread(process_image, content)
                    await asyncio.to_thread(
                        s3_client.upload_fileobj, io.BytesIO(content), object_key,
                        None, content_type_for(ext),
                    )
                    if thumb:
                        await asyncio.to_thread(
                            s3_client.upload_fileobj, io.BytesIO(thumb), thumb_key,
                            None, "image/jpeg",
                        )
                    else:
                        thumb_key = None
                    return {"ok": True, "filename": filename, "object_key": object_key,
                            "thumbnail_key": thumb_key, "width": width, "height": height}
                except Exception as e:
                    return {"ok": False, "filename": filename, "reason": str(e)}

        results = await asyncio.gather(*[_process(f) for f in files])

        uploaded: list[dict] = []
        failed: list[dict] = []
        async with async_db_session.begin() as db:
            for r in results:
                if not r["ok"]:
                    failed.append({"filename": r["filename"], "reason": r["reason"]})
                    continue
                img = AnnotationImageModel(
                    dataset_id=dataset_id,
                    filename=r["filename"],
                    object_key=r["object_key"],
                    thumbnail_key=r["thumbnail_key"],
                    width=r["width"],
                    height=r["height"],
                    status=ImageStatus.UNANNOTATED,
                )
                set_create_audit(img, auth)
                db.add(img)
                await db.flush()
                uploaded.append({"id": img.id, "filename": r["filename"],
                                 "object_key": r["object_key"],
                                 "thumbnail_key": r["thumbnail_key"]})
            total = await db.scalar(
                select(func.count(AnnotationImageModel.id))
                .where(AnnotationImageModel.dataset_id == dataset_id)
            )
            await db.execute(
                update(DatasetModel)
                .where(DatasetModel.id == dataset_id)
                .values(image_count=total or 0)
            )
        return {"uploaded": uploaded, "failed": failed,
                "uploaded_count": len(uploaded), "failed_count": len(failed)}

    @classmethod
    async def get_images(cls, dataset_id: int, task_id: int | None = None,
                         page_no: int = 1, page_size: int = 100) -> dict:
        offset = (page_no - 1) * page_size
        async with async_db_session() as db:
            # Count
            count_sql = select(func.count()).select_from(
                select(AnnotationImageModel)
                .where(
                    AnnotationImageModel.dataset_id == dataset_id,
                    AnnotationImageModel.is_deleted == False,  # noqa: E712
                )
                .subquery()
            )
            total = (await db.execute(count_sql)).scalar() or 0

            # Get paginated images
            sql = (select(AnnotationImageModel)
                   .where(
                       AnnotationImageModel.dataset_id == dataset_id,
                       AnnotationImageModel.is_deleted == False,  # noqa: E712
                   )
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
