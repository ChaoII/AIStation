from datetime import datetime, timedelta

from sqlalchemy import delete, desc, func, select, update

from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log

from ..dataset.model import (
    AnnotationDocumentModel,
    AnnotationImageModel,
    AnnotationVideoModel,
    DatasetModel,
)
from ..task.model import AnnotationTaskModel
from .model import AnnotationRecordModel


class AnnotationService:

    LOCK_TIMEOUT_MINUTES = 5

    @classmethod
    async def lock_image(cls, image_id: int, user_id: int) -> dict:
        async with async_db_session.begin() as db:
            img = await db.get(AnnotationImageModel, image_id)
            if not img:
                raise ValueError("图片不存在")
            # Auto-release stale locks
            if img.locked_by and img.locked_at:
                if datetime.utcnow() - img.locked_at > timedelta(minutes=cls.LOCK_TIMEOUT_MINUTES):
                    img.locked_by = None
                    img.locked_at = None
            if img.locked_by and img.locked_by != user_id:
                return {"locked": True, "locked_by": img.locked_by}
            img.locked_by = user_id
            img.locked_at = datetime.utcnow()
            return {"locked": False, "locked_by": user_id}

    @classmethod
    async def unlock_image(cls, image_id: int, user_id: int) -> None:
        async with async_db_session.begin() as db:
            img = await db.get(AnnotationImageModel, image_id)
            if img and img.locked_by == user_id:
                img.locked_by = None
                img.locked_at = None

    @classmethod
    async def _prune_versions(cls, db, task_id: int, image_id: int,
                              latest_version: int, keep: int) -> None:
        """保留首版（v1）与最近 keep 版，删除中间旧版本。"""
        if keep <= 0 or latest_version <= keep + 1:
            return
        upper = latest_version - keep  # 删除 version ∈ [2, upper]
        await db.execute(
            delete(AnnotationRecordModel).where(
                AnnotationRecordModel.task_id == task_id,
                AnnotationRecordModel.image_id == image_id,
                AnnotationRecordModel.version >= 2,
                AnnotationRecordModel.version <= upper,
            )
        )

    @classmethod
    async def save_annotations(cls, task_id: int, image_id: int, annotation_data: list[dict], auth) -> dict:
        async with async_db_session.begin() as db:
            # Verify lock
            img = await db.get(AnnotationImageModel, image_id)
            if img and img.locked_by and img.locked_by != auth.user.id:
                raise CustomException(msg="图片已被其他用户锁定，无法保存", code=409, status_code=409)

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
            await db.flush()
            await cls._prune_versions(db, task_id, image_id, version,
                                      settings.ANNOTATION_VERSION_KEEP)

            # Update image status and annotation count
            if img:
                img.status = "annotated" if annotation_data else "unannotated"
                img.annotation_count = len(annotation_data)

            # Recalculate dataset annotated_count
            if img:
                subq = select(AnnotationImageModel.id).where(
                    AnnotationImageModel.dataset_id == img.dataset_id
                )
                annotated = await db.scalar(
                    select(func.count(func.distinct(AnnotationRecordModel.image_id)))
                    .where(AnnotationRecordModel.image_id.in_(subq))
                )
                await db.execute(
                    update(DatasetModel)
                    .where(DatasetModel.id == img.dataset_id)
                    .values(annotated_count=annotated or 0)
                )

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
    async def rollback_annotation(cls, task_id: int, image_id: int, version: int, auth) -> dict:
        """把所选历史版本内容作为新的最新版本写回（append-only 回滚）。"""
        async with async_db_session.begin() as db:
            img = await db.get(AnnotationImageModel, image_id)
            if img and img.locked_by and img.locked_by != auth.user.id:
                raise CustomException(msg="图片已被其他用户锁定，无法回滚", code=409, status_code=409)

            target = (
                await db.execute(
                    select(AnnotationRecordModel).where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.image_id == image_id,
                        AnnotationRecordModel.version == version,
                    )
                )
            ).scalar_one_or_none()
            if not target:
                raise CustomException(msg="目标版本不存在", code=404, status_code=404)

            latest = (
                await db.execute(
                    select(AnnotationRecordModel)
                    .where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.image_id == image_id,
                    )
                    .order_by(desc(AnnotationRecordModel.version))
                    .limit(1)
                )
            ).scalar_one_or_none()
            new_version = (latest.version + 1) if latest else 1

            data = target.annotation_data or []
            db.add(
                AnnotationRecordModel(
                    task_id=task_id,
                    image_id=image_id,
                    annotation_data=data,
                    version=new_version,
                    created_id=auth.user.id,
                )
            )
            if img:
                img.status = "annotated" if data else "unannotated"
                img.annotation_count = len(data)
                subq = select(AnnotationImageModel.id).where(
                    AnnotationImageModel.dataset_id == img.dataset_id
                )
                annotated = await db.scalar(
                    select(func.count(func.distinct(AnnotationRecordModel.image_id))).where(
                        AnnotationRecordModel.image_id.in_(subq)
                    )
                )
                await db.execute(
                    update(DatasetModel)
                    .where(DatasetModel.id == img.dataset_id)
                    .values(annotated_count=annotated or 0)
                )
        return {"version": new_version, "annotation_count": len(data)}

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

    @classmethod
    async def _verify_video_task_relation(cls, db, task_id: int, video_id: int) -> AnnotationVideoModel:
        """校验视频确实归属于指定任务（同为数据集下的 video_detection 任务），返回视频对象。"""
        video = await db.get(AnnotationVideoModel, video_id)
        if not video or video.is_deleted:
            raise CustomException(msg=f"视频不存在: {video_id}", code=404, status_code=404)
        task = await db.get(AnnotationTaskModel, task_id)
        if (
            not task
            or task.is_deleted
            or task.dataset_id != video.dataset_id
            or task.task_type != "video_detection"
        ):
            raise CustomException(
                msg="任务与视频不存在有效归属关系，无法保存/读取标注",
                code=400,
                status_code=400,
            )
        return video

    @classmethod
    async def _prune_video_versions(cls, db, task_id: int, video_id: int,
                                    frame_index: int, latest_version: int, keep: int) -> None:
        """保留首版（v1）与最近 keep 版，删除中间旧版本（按视频帧粒度）。"""
        if keep <= 0 or latest_version <= keep + 1:
            return
        upper = latest_version - keep
        await db.execute(
            delete(AnnotationRecordModel).where(
                AnnotationRecordModel.task_id == task_id,
                AnnotationRecordModel.video_id == video_id,
                AnnotationRecordModel.frame_index == frame_index,
                AnnotationRecordModel.version >= 2,
                AnnotationRecordModel.version <= upper,
            )
        )

    @classmethod
    async def save_video_annotations(
        cls, task_id: int, video_id: int, frame_index: int, annotation_data: list[dict], auth
    ) -> dict:
        """按 (task_id, video_id, frame_index) 持久化一帧的视频标注；空列表时清除该帧记录。"""
        async with async_db_session.begin() as db:
            video = await cls._verify_video_task_relation(db, task_id, video_id)
            if video.locked_by and video.locked_by != auth.user.id:
                raise CustomException(
                    msg="视频已被其他用户锁定，无法保存", code=409, status_code=409
                )

            existing = (
                await db.execute(
                    select(AnnotationRecordModel)
                    .where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.video_id == video_id,
                        AnnotationRecordModel.frame_index == frame_index,
                    )
                    .order_by(desc(AnnotationRecordModel.version))
                    .limit(1)
                )
            ).scalar_one_or_none()
            version = existing.version + 1 if existing else 1

            if annotation_data:
                db.add(AnnotationRecordModel(
                    task_id=task_id, video_id=video_id, frame_index=frame_index,
                    annotation_data=annotation_data, version=version,
                    created_id=auth.user.id,
                ))
                await db.flush()
                await cls._prune_video_versions(
                    db, task_id, video_id, frame_index, version,
                    settings.ANNOTATION_VERSION_KEEP,
                )
            else:
                # 空列表：清除该帧已有的标注记录
                await db.execute(
                    delete(AnnotationRecordModel).where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.video_id == video_id,
                        AnnotationRecordModel.frame_index == frame_index,
                    )
                )

            if video:
                video.status = "annotated" if annotation_data else "unannotated"
                video.annotation_count = len(annotation_data)

        log.info(f"save_video_annotations video={video_id} frame={frame_index} v={version}")
        return {"version": version, "annotation_count": len(annotation_data)}

    @classmethod
    async def load_video_annotations(cls, task_id: int, video_id: int, frame_index: int) -> list[dict] | None:
        """读取某视频帧的最新标注；无记录返回 None。"""
        async with async_db_session.begin() as db:
            await cls._verify_video_task_relation(db, task_id, video_id)
            record = (
                await db.execute(
                    select(AnnotationRecordModel)
                    .where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.video_id == video_id,
                        AnnotationRecordModel.frame_index == frame_index,
                    )
                    .order_by(desc(AnnotationRecordModel.version))
                    .limit(1)
                )
            ).scalar_one_or_none()
            return record.annotation_data if record else None

    # ------------------------------------------------------------------
    # 文本 NER 文档标注（按 document_id 读写）
    # ------------------------------------------------------------------

    @classmethod
    async def _verify_document_task_relation(
        cls, db, task_id: int, document_id: int
    ) -> AnnotationDocumentModel:
        """校验文档确实归属于指定任务（同为数据集下的 text_ner 任务），返回文档对象。"""
        doc = await db.get(AnnotationDocumentModel, document_id)
        if not doc or doc.is_deleted:
            raise CustomException(msg=f"文档不存在: {document_id}", code=404, status_code=404)
        task = await db.get(AnnotationTaskModel, task_id)
        if (
            not task
            or task.is_deleted
            or task.dataset_id != doc.dataset_id
            or task.task_type != "text_ner"
        ):
            raise CustomException(
                msg="任务与文档不存在有效归属关系，无法保存/读取标注",
                code=400,
                status_code=400,
            )
        return doc

    @classmethod
    def _validate_text_annotations(
        cls, annotations: list[dict], classes: dict, character_count: int
    ) -> None:
        """校验 text_ner 标注：实体/关系字段合法性、类型归属、重叠检测。

        非法项一律抛 ``CustomException``（400）。``character_count`` 为文档
        UTF-16 code unit 数，实体 ``[start, end)`` 必须落在 ``[0, character_count]``。
        """
        if not isinstance(classes, dict):
            raise CustomException(msg="text_ner 任务 classes 必须为字典", code=400, status_code=400)
        entity_label_ids = {e.get("id") for e in classes.get("entities", [])}
        relation_type_ids = {r.get("id") for r in classes.get("relations", [])}

        entity_ids: set[str] = set()
        spans: list[tuple[int, int]] = []
        for item in annotations:
            if not isinstance(item, dict):
                raise CustomException(msg="标注项必须为字典对象", code=400, status_code=400)
            itype = item.get("type")
            if itype == "EntitySpan":
                start, end = item.get("start"), item.get("end")
                if not isinstance(start, int) or not isinstance(end, int):
                    raise CustomException(
                        msg="实体 span 的 start/end 必须为整数", code=400, status_code=400
                    )
                if end <= start:
                    raise CustomException(
                        msg="实体 span 的 end 必须大于 start", code=400, status_code=400
                    )
                if start < 0 or end > character_count:
                    raise CustomException(
                        msg=f"实体 span 超出文档范围 [0, {character_count}]",
                        code=400,
                        status_code=400,
                    )
                if item.get("label_id") not in entity_label_ids:
                    raise CustomException(
                        msg=f"实体 label_id 非法: {item.get('label_id')}",
                        code=400,
                        status_code=400,
                    )
                eid = item.get("id")
                if eid is None:
                    raise CustomException(msg="实体缺少 id", code=400, status_code=400)
                if eid in entity_ids:
                    raise CustomException(msg=f"实体 id 重复: {eid}", code=400, status_code=400)
                entity_ids.add(eid)
                spans.append((start, end))
            elif itype == "Relation":
                if item.get("relation_type") not in relation_type_ids:
                    raise CustomException(
                        msg=f"关系 relation_type 非法: {item.get('relation_type')}",
                        code=400,
                        status_code=400,
                    )
                from_id, to_id = item.get("from"), item.get("to")
                if from_id not in entity_ids or to_id not in entity_ids:
                    raise CustomException(
                        msg="关系 from/to 必须引用同集合中的实体", code=400, status_code=400
                    )
                if from_id == to_id:
                    raise CustomException(
                        msg="关系 from/to 不能指向同一实体", code=400, status_code=400
                    )
            else:
                raise CustomException(
                    msg=f"未知标注类型: {itype}", code=400, status_code=400
                )

        # 重叠校验：任意两个 [start, end) 区间不得相交（相邻不视为重叠）
        spans.sort()
        for i in range(1, len(spans)):
            if spans[i][0] < spans[i - 1][1]:
                raise CustomException(msg="实体 span 存在重叠", code=400, status_code=400)

    @classmethod
    async def _prune_document_versions(
        cls, db, task_id: int, document_id: int, latest_version: int, keep: int
    ) -> None:
        """保留首版（v1）与最近 keep 版，删除中间旧版本（按文档粒度）。"""
        if keep <= 0 or latest_version <= keep + 1:
            return
        upper = latest_version - keep
        await db.execute(
            delete(AnnotationRecordModel).where(
                AnnotationRecordModel.task_id == task_id,
                AnnotationRecordModel.document_id == document_id,
                AnnotationRecordModel.version >= 2,
                AnnotationRecordModel.version <= upper,
            )
        )

    @classmethod
    async def save_text_annotations(
        cls, task_id: int, document_id: int, annotations: list[dict], auth
    ) -> dict:
        """按 (task_id, document_id) 持久化文本标注；校验实体/关系/重叠后 upsert。"""
        async with async_db_session.begin() as db:
            doc = await cls._verify_document_task_relation(db, task_id, document_id)
            if doc.locked_by and doc.locked_by != auth.user.id:
                raise CustomException(
                    msg="文档已被其他用户锁定，无法保存", code=409, status_code=409
                )
            task = await db.get(AnnotationTaskModel, task_id)
            cls._validate_text_annotations(annotations, task.classes, doc.character_count)

            existing = (
                await db.execute(
                    select(AnnotationRecordModel)
                    .where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.document_id == document_id,
                    )
                    .order_by(desc(AnnotationRecordModel.version))
                    .limit(1)
                )
            ).scalar_one_or_none()
            version = existing.version + 1 if existing else 1

            db.add(AnnotationRecordModel(
                task_id=task_id,
                document_id=document_id,
                annotation_data=annotations,
                version=version,
                created_id=auth.user.id,
            ))
            await db.flush()
            await cls._prune_document_versions(
                db, task_id, document_id, version, settings.ANNOTATION_VERSION_KEEP
            )

            if doc:
                doc.status = "annotated" if annotations else "unannotated"
                doc.annotation_count = len(annotations)

        log.info(f"save_text_annotations task={task_id} document={document_id} v={version}")
        return {"version": version, "annotation_count": len(annotations)}

    @classmethod
    async def load_text_annotations(cls, task_id: int, document_id: int) -> dict:
        """读取某文档的最新标注；无记录返回空列表与 version 0。"""
        async with async_db_session.begin() as db:
            await cls._verify_document_task_relation(db, task_id, document_id)
            record = (
                await db.execute(
                    select(AnnotationRecordModel)
                    .where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.document_id == document_id,
                    )
                    .order_by(desc(AnnotationRecordModel.version))
                    .limit(1)
                )
            ).scalar_one_or_none()
            return {
                "annotation_data": record.annotation_data if record else [],
                "version": record.version if record else 0,
            }
