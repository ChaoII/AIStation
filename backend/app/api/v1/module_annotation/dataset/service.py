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
from app.core.logger import log
from app.utils.s3_client import s3_client

from .crud import DatasetCRUD
from .export_model import DatasetExportModel
from .import_jobs import get_latest_job, job_snapshot
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
    async def purge_datasets(cls, ids: list[int], progress_cb=None) -> dict:
        """彻底删除数据集：先按 DB 记录的 key 删对象，再物理删 DB 行（不可逆）。

        ``progress_cb(processed, total, phase)`` 可空；``total`` 为待删对象数，
        ``phase`` 取 ``delete`` / ``db`` / ``done``。
        """
        # 0) 从 DB 收集所有待删对象的 key（用于进度总数；不列举前缀以避免超时）
        keys_by_ds: dict[int, list[str]] = {}
        all_keys: list[str] = []
        async with async_db_session() as db:
            for dataset_id in ids:
                rows = (
                    await db.execute(
                        select(
                            AnnotationImageModel.object_key,
                            AnnotationImageModel.thumbnail_key,
                        ).where(AnnotationImageModel.dataset_id == dataset_id)
                    )
                ).fetchall()
                ks = [k for pair in rows for k in pair if k]
                keys_by_ds[dataset_id] = ks
                all_keys += ks

        total = len(all_keys)
        if total and progress_cb:
            progress_cb(0, total, "delete")
        if total:
            s3_client.delete_objects(
                all_keys,
                progress_cb=(
                    (lambda done, _t: progress_cb(done, total, "delete"))
                    if progress_cb
                    else None
                ),
            )

        purged = 0
        for dataset_id in ids:
            # 导出产物数量少，尽力而为；失败不影响 DB 清理
            try:
                s3_client.delete_prefix(f"train/exports/dataset_{dataset_id}_")
            except Exception as e:  # noqa: BLE001
                log.warning(f"[数据集彻底删除] 导出产物清理失败 dataset={dataset_id}: {e}")

            # 物理删除 DB（含软删行）
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
        if progress_cb:
            progress_cb(total or 1, total or 1, "done")
        return {"purged": purged}

    @classmethod
    async def delete_images(
        cls,
        dataset_id: int,
        image_ids: list[int] | None = None,
        status: str | None = None,
    ) -> dict:
        """硬删除数据集图片（对象存储 + DB），锁定中的图片跳过。

        - ``image_ids``：删除指定图片
        - ``status``：删除该数据集下该状态的图片（unannotated/in_progress/annotated）
        - 两者至少提供一个
        """
        if not image_ids and not status:
            raise CustomException(msg="请指定要删除的图片或筛选条件", code=400, status_code=400)

        import asyncio

        keys: list[str] = []
        async with async_db_session.begin() as db:
            stmt = select(AnnotationImageModel).where(
                AnnotationImageModel.dataset_id == dataset_id,
                AnnotationImageModel.is_deleted == False,  # noqa: E712
            )
            if image_ids:
                stmt = stmt.where(AnnotationImageModel.id.in_(image_ids))
            elif status and status != "all":
                stmt = stmt.where(AnnotationImageModel.status == status)
            rows = (await db.execute(stmt)).scalars().all()

            locked = [r for r in rows if r.locked_by]
            targets = [r for r in rows if not r.locked_by]
            if not targets:
                return {"deleted": 0, "skipped_locked": len(locked)}

            ids = [r.id for r in targets]
            # 先收集待删对象 key 并在 DB 事务内删除行（对象与 DB 非同源事务，先 DB 后对象）
            keys = [k for r in targets for k in (r.object_key, r.thumbnail_key) if k]

            await db.execute(
                delete(AnnotationRecordModel).where(AnnotationRecordModel.image_id.in_(ids))
            )
            await db.execute(delete(AnnotationImageModel).where(AnnotationImageModel.id.in_(ids)))

            # 重算数据集计数
            ds = await db.get(DatasetModel, dataset_id)
            if ds:
                ds.image_count = await db.scalar(
                    select(func.count(AnnotationImageModel.id)).where(
                        AnnotationImageModel.dataset_id == dataset_id,
                        AnnotationImageModel.is_deleted == False,  # noqa: E712
                    )
                ) or 0
                ds.annotated_count = await db.scalar(
                    select(func.count(func.distinct(AnnotationRecordModel.image_id)))
                    .select_from(AnnotationRecordModel)
                    .join(
                        AnnotationImageModel,
                        AnnotationImageModel.id == AnnotationRecordModel.image_id,
                    )
                    .where(
                        AnnotationImageModel.dataset_id == dataset_id,
                        AnnotationImageModel.is_deleted == False,  # noqa: E712
                        AnnotationRecordModel.is_deleted == False,  # noqa: E712
                    )
                ) or 0

        # DB 已提交，再删对象存储；失败仅告警，不阻断删除结果
        if keys:
            try:
                await asyncio.to_thread(s3_client.delete_objects, keys)
            except Exception as e:  # noqa: BLE001
                log.warning(f"[删除图片] 对象删除失败 dataset={dataset_id}: {e}")

        # 重算该数据集下所有任务的进度（图片总数变化）
        from app.api.v1.module_annotation.task.service import TaskService

        async with async_db_session() as db:
            task_ids = (
                await db.execute(
                    select(AnnotationTaskModel.id).where(
                        AnnotationTaskModel.dataset_id == dataset_id
                    )
                )
            ).scalars().all()
        for tid in task_ids:
            try:
                await TaskService.update_progress(tid)
            except Exception as e:  # noqa: BLE001
                log.warning(f"[删除图片] 重算任务进度失败 task={tid}: {e}")

        return {"deleted": len(targets), "skipped_locked": len(locked)}

    @classmethod
    async def upload_images(cls, dataset_id: int, files: list, auth) -> dict:
        import asyncio
        import io

        from .media import (
            ALLOWED_IMAGE_EXTENSIONS,
            content_hash,
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
            # 已存在的内容哈希（用于去重）
            seen: set[str] = set(
                (
                    await db.execute(
                        select(AnnotationImageModel.content_hash).where(
                            AnnotationImageModel.dataset_id == dataset_id,
                            AnnotationImageModel.is_deleted == False,  # noqa: E712
                            AnnotationImageModel.content_hash.isnot(None),
                        )
                    )
                ).scalars().all()
            )

        sem = asyncio.Semaphore(max(1, settings.ANNOTATION_UPLOAD_CONCURRENCY))

        async def _process(file) -> dict:
            filename = file.filename or "unnamed"
            async with sem:
                try:
                    content = await file.read()
                    digest = content_hash(content)
                    if digest in seen:
                        return {"ok": False, "duplicate": True, "filename": filename}
                    seen.add(digest)
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
                            "thumbnail_key": thumb_key, "width": width, "height": height,
                            "content_hash": digest}
                except Exception as e:
                    return {"ok": False, "filename": filename, "reason": str(e)}

        results = await asyncio.gather(*[_process(f) for f in files])

        uploaded: list[dict] = []
        failed: list[dict] = []
        duplicates: list[str] = []
        # 本次成功上传到对象存储的所有 key（用于 DB 失败时补偿删除，避免孤儿）
        uploaded_keys = [
            k for r in results if r.get("ok")
            for k in (r.get("object_key"), r.get("thumbnail_key")) if k
        ]
        try:
            async with async_db_session.begin() as db:
                for r in results:
                    if not r["ok"]:
                        if r.get("duplicate"):
                            duplicates.append(r["filename"])
                        else:
                            failed.append({"filename": r["filename"], "reason": r["reason"]})
                        continue
                    img = AnnotationImageModel(
                        dataset_id=dataset_id,
                        filename=r["filename"],
                        object_key=r["object_key"],
                        thumbnail_key=r["thumbnail_key"],
                        content_hash=r["content_hash"],
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
        except Exception:
            # DB 事务失败：尽力删除本次已上传的对象，避免留孤儿
            if uploaded_keys:
                try:
                    await asyncio.to_thread(s3_client.delete_objects, uploaded_keys)
                except Exception as e2:  # noqa: BLE001
                    log.warning(f"[上传] 补偿删除孤儿对象失败: {e2}")
            raise
        return {"uploaded": uploaded, "failed": failed, "skipped_duplicate": duplicates,
                "uploaded_count": len(uploaded), "failed_count": len(failed),
                "skipped_duplicate_count": len(duplicates)}

    @classmethod
    async def get_images(cls, dataset_id: int, task_id: int | None = None,
                         page_no: int = 1, page_size: int = 100) -> dict:
        # 服务端限制 page_size 上限，避免一次全表拉取
        page_size = max(1, min(page_size, 200))
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
            for r in rec_rows:
                iid = r[1]
                if iid not in ann_map:
                    ann_map[iid] = {
                        "has_data": bool(r[2] and isinstance(r[2], list) and len(r[2]) > 0),
                        "created_id": r[4],
                        "created_time": r[5],
                    }
            # 一次查询所有创建人 → id→name 映射，避免逐条 db.get(UserModel)
            user_cache: dict[int, str] = {}
            creator_ids = {a["created_id"] for a in ann_map.values() if a["created_id"]}
            if creator_ids:
                users = await db.execute(
                    select(UserModel.id, UserModel.name).where(UserModel.id.in_(creator_ids))
                )
                user_cache = dict(users.fetchall())

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
                    "thumbnail_key": img.thumbnail_key,
                    "thumbnail_url": (
                        s3_client.presigned_url(img.thumbnail_key)
                        if img.thumbnail_key else None
                    ),
                    "updated_by": {"id": (info or {}).get("created_id"), "name": updater_name} if info and has_data else None,
                    "updated_time": update_time.isoformat() if update_time else None,
                })
            return {"items": items, "total": total, "page": page_no}

    @classmethod
    async def enrich_dataset_list(cls, db, items: list[dict]) -> None:
        """为本页数据集就地填充任务列表与进度（单次聚合、只读不写）。"""
        if not items:
            return
        ids = [i["id"] for i in items]

        total_rows = await db.execute(
            select(AnnotationImageModel.dataset_id, func.count(AnnotationImageModel.id))
            .where(
                AnnotationImageModel.dataset_id.in_(ids),
                AnnotationImageModel.is_deleted == False,  # noqa: E712
            )
            .group_by(AnnotationImageModel.dataset_id)
        )
        totals = dict(total_rows.fetchall())

        task_rows = (
            await db.execute(
                select(AnnotationTaskModel).where(
                    AnnotationTaskModel.dataset_id.in_(ids),
                    AnnotationTaskModel.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
        task_ids = [t.id for t in task_rows]

        ann: dict[int, int] = {}
        if task_ids:
            max_v = (
                select(
                    AnnotationRecordModel.task_id.label("task_id"),
                    AnnotationRecordModel.image_id.label("image_id"),
                    func.max(AnnotationRecordModel.version).label("mv"),
                )
                .where(AnnotationRecordModel.task_id.in_(task_ids))
                .group_by(AnnotationRecordModel.task_id, AnnotationRecordModel.image_id)
                .subquery()
            )
            json_length = (
                func.json_array_length
                if settings.DATABASE_TYPE == "sqlite"
                else func.jsonb_array_length
            )
            ann_rows = await db.execute(
                select(AnnotationRecordModel.task_id, func.count())
                .select_from(AnnotationRecordModel)
                .join(
                    max_v,
                    and_(
                        AnnotationRecordModel.task_id == max_v.c.task_id,
                        AnnotationRecordModel.image_id == max_v.c.image_id,
                        AnnotationRecordModel.version == max_v.c.mv,
                    ),
                )
                .where(
                    AnnotationRecordModel.annotation_data.isnot(None),
                    json_length(AnnotationRecordModel.annotation_data) > 0,
                )
                .group_by(AnnotationRecordModel.task_id)
            )
            ann = dict(ann_rows.fetchall())

        by_ds: dict[int, list] = {}
        for t in task_rows:
            by_ds.setdefault(t.dataset_id, []).append(t)

        for item in items:
            ds_tasks = by_ds.get(item["id"], [])
            total = totals.get(item["id"], 0)
            out_tasks = []
            for t in ds_tasks:
                pct = int(ann.get(t.id, 0) / total * 100) if total > 0 else 0
                out_tasks.append({
                    "id": t.id,
                    "name": t.name,
                    "task_type": t.task_type,
                    "status": "completed" if pct >= 100 else "in_progress" if pct > 0 else "pending",
                    "progress": pct,
                })
            item["task_count"] = len(ds_tasks)
            item["tasks"] = out_tasks
            # 附带最近一次导入任务快照（进程内），供列表展示导入状态
            item["import"] = job_snapshot(get_latest_job(item["id"]))

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
        "thumbnail_key": img.thumbnail_key,
        "thumbnail_url": (
            s3_client.presigned_url(img.thumbnail_key) if img.thumbnail_key else None
        ),
    }
