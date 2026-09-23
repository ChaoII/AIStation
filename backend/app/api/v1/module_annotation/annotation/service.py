from datetime import datetime, timedelta

from sqlalchemy import delete, desc, func, select, update

from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log

from ..dataset.model import (
    AnnotationAudioModel,
    AnnotationDocumentModel,
    AnnotationImageModel,
    AnnotationTimeSeriesModel,
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
    def _validate_video_track_annotations(cls, annotations: list[dict]) -> None:
        """校验一帧内的框 track_id：同一帧内同一 track_id 至多一框（一帧一框一目标）。

        ``track_id`` 允许缺失（旧数据/独立目标，行为与现状一致）；仅对非空
        ``track_id`` 去重。非法项抛 ``CustomException``（400）。
        """
        seen: set[str] = set()
        for item in annotations:
            track_id = item.get("track_id")
            if track_id is None:
                continue
            if track_id in seen:
                raise CustomException(
                    msg=f"同一帧内 track_id 重复: {track_id}（一帧一框一目标）",
                    code=400,
                    status_code=400,
                )
            seen.add(track_id)

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
            cls._validate_video_track_annotations(annotation_data)

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
                # 已标注帧数 = count(distinct frame_index)，限定当前 task_id 与该视频，
                # 与 save_video_interpolation 语义一致（清空该帧后其记录被删除，计数随之回落）。
                annotated_frames = await db.scalar(
                    select(func.count(func.distinct(AnnotationRecordModel.frame_index)))
                    .where(AnnotationRecordModel.task_id == task_id)
                    .where(AnnotationRecordModel.video_id == video_id)
                )
                annotated = annotated_frames or 0
                video.status = "annotated" if annotated else "unannotated"
                video.annotation_count = annotated

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

    @classmethod
    async def _ensure_video_track_keyframe(
        cls, db, task_id: int, video_id: int, frame_index: int, track_id: str
    ) -> None:
        """校验关键帧 ``frame_index`` 的最新标注确实含该 ``track_id`` 的框，否则拒绝（400）。

        关键帧是插值的锚点，两个关键帧都必须实际存在对应轨迹的框，插值才有意义。
        """
        record = (
            await db.execute(
                select(AnnotationRecordModel).where(
                    AnnotationRecordModel.task_id == task_id,
                    AnnotationRecordModel.video_id == video_id,
                    AnnotationRecordModel.frame_index == frame_index,
                )
                .order_by(desc(AnnotationRecordModel.version))
                .limit(1)
            )
        ).scalar_one_or_none()
        if not record:
            raise CustomException(
                msg=f"关键帧 {frame_index} 不存在标注，无法插值",
                code=400,
                status_code=400,
            )
        has_track = any(
            item.get("track_id") == track_id for item in (record.annotation_data or [])
        )
        if not has_track:
            raise CustomException(
                msg=f"关键帧 {frame_index} 不存在 track_id={track_id} 的框，无法插值",
                code=400,
                status_code=400,
            )

    @classmethod
    async def save_video_interpolation(
        cls,
        task_id: int,
        video_id: int,
        track_id: str,
        frame_a: int,
        frame_b: int,
        frames: list[dict],
        auth,
    ) -> dict:
        """在同一个 ``track_id`` 的两个关键帧之间批量保存插值中间帧。

        ``frames`` 为 ``[{"frame_index", "annotations"}]`` 列表，每个中间帧的框均
        须携带顶层 ``track_id``。逐帧 upsert 新版本并 ``_prune_video_versions``；
        任一帧非法则整批回滚（事务化）。关键帧（frame_a/frame_b）保持不动。
        """
        async with async_db_session.begin() as db:
            video = await cls._verify_video_task_relation(db, task_id, video_id)
            if video.locked_by and video.locked_by != auth.user.id:
                raise CustomException(
                    msg="视频已被其他用户锁定，无法保存",
                    code=409,
                    status_code=409,
                )
            if not isinstance(track_id, str) or not track_id.strip():
                raise CustomException(
                    msg="track_id 不能为空", code=400, status_code=400
                )
            # int 校验需排除 bool（bool 是 int 的子类）
            if (not isinstance(frame_a, int) or isinstance(frame_a, bool)) or \
               (not isinstance(frame_b, int) or isinstance(frame_b, bool)) or frame_a >= frame_b:
                raise CustomException(
                    msg="frame_a 必须小于 frame_b", code=400, status_code=400
                )
            if frame_a < 0 or frame_b < 0 or frame_b >= video.frame_count:
                raise CustomException(
                    msg=f"frame_a/frame_b 超出视频帧范围 [0, {video.frame_count})",
                    code=400,
                    status_code=400,
                )
            # 两个关键帧都必须实际存在该 track 的框
            await cls._ensure_video_track_keyframe(db, task_id, video_id, frame_a, track_id)
            await cls._ensure_video_track_keyframe(db, task_id, video_id, frame_b, track_id)

            saved: list[dict] = []
            seen_indices: set[int] = set()
            for frame in frames:
                frame_index = frame["frame_index"]
                annotations = frame["annotations"]
                # 中间帧必须严格落在 (frame_a, frame_b)，不含关键帧
                if (not isinstance(frame_index, int) or isinstance(frame_index, bool)) or \
                   not (frame_a < frame_index < frame_b):
                    raise CustomException(
                        msg=f"中间帧 {frame_index} 必须严格落在 ({frame_a}, {frame_b}) 内",
                        code=400,
                        status_code=400,
                    )
                if frame_index in seen_indices:
                    raise CustomException(
                        msg=f"中间帧 {frame_index} 重复提交",
                        code=400,
                        status_code=400,
                    )
                seen_indices.add(frame_index)
                # 复用同帧 track_id 去重校验
                cls._validate_video_track_annotations(annotations)
                # 每帧框必须归属顶层 track_id
                for item in annotations:
                    if item.get("track_id") != track_id:
                        raise CustomException(
                            msg=f"第 {frame_index} 帧存在非目标 track_id 的框",
                            code=400,
                            status_code=400,
                        )

                # 本帧无插值框：跳过，不写空版本（避免覆盖/清空该帧既存标注）
                if not annotations:
                    continue

                # 读取该帧既存标注，仅替换本 track 的框，保留其它 track 的框
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
                existing_data = existing.annotation_data if existing else []
                # 保留既存框中与本 track 无关的部分（含无 track_id 的旧数据/独立目标）
                merged = [
                    item for item in existing_data if item.get("track_id") != track_id
                ]
                merged.extend(annotations)
                db.add(AnnotationRecordModel(
                    task_id=task_id,
                    video_id=video_id,
                    frame_index=frame_index,
                    annotation_data=merged,
                    version=version,
                    created_id=auth.user.id,
                ))
                await db.flush()
                await cls._prune_video_versions(
                    db, task_id, video_id, frame_index, version,
                    settings.ANNOTATION_VERSION_KEEP,
                )
                saved.append({"frame_index": frame_index, "version": version})

            # 更新视频状态与已标注帧数（annotation_count 语义为「已标注帧数」），
            # 限定 task_id，避免同一数据集下多任务共享视频时重复计入。
            annotated_frames = await db.scalar(
                select(func.count(func.distinct(AnnotationRecordModel.frame_index)))
                .where(AnnotationRecordModel.task_id == task_id)
                .where(AnnotationRecordModel.video_id == video_id)
            )
            video.status = "annotated" if annotated_frames else "unannotated"
            video.annotation_count = annotated_frames or 0

        log.info(f"save_video_interpolation video={video_id} track={track_id} frames={len(saved)}")
        return {"saved": saved, "count": len(saved)}

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
        relations: list[dict] = []
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
                relations.append(item)
            else:
                raise CustomException(
                    msg=f"未知标注类型: {itype}", code=400, status_code=400
                )

        # 关系校验与输入顺序无关：先收集完整实体集合，再对每个关系的 from/to 校验
        for item in relations:
            from_id, to_id = item.get("from"), item.get("to")
            if from_id not in entity_ids or to_id not in entity_ids:
                raise CustomException(
                    msg="关系 from/to 必须引用同集合中的实体", code=400, status_code=400
                )
            if from_id == to_id:
                raise CustomException(
                    msg="关系 from/to 不能指向同一实体", code=400, status_code=400
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

    # ------------------------------------------------------------------
    # 音频事件标注（按 audio_id 读写）
    # ------------------------------------------------------------------

    @classmethod
    async def _verify_audio_task_relation(
        cls, db, task_id: int, audio_id: int
    ) -> AnnotationAudioModel:
        """校验音频确实归属于指定任务（同为数据集下的 audio_event 任务），返回音频对象。"""
        audio = await db.get(AnnotationAudioModel, audio_id)
        if not audio or audio.is_deleted:
            raise CustomException(msg=f"音频不存在: {audio_id}", code=404, status_code=404)
        task = await db.get(AnnotationTaskModel, task_id)
        if (
            not task
            or task.is_deleted
            or task.dataset_id != audio.dataset_id
            or task.task_type != "audio_event"
        ):
            raise CustomException(
                msg="任务与音频不存在有效归属关系，无法保存/读取标注",
                code=400,
                status_code=400,
            )
        return audio

    @classmethod
    def _validate_audio_annotations(
        cls, annotations: list[dict], classes: list, duration: float
    ) -> None:
        """校验 audio_event 标注：AudioSegment 字段合法性、区间边界、类别归属与重叠检测。

        非法项一律抛 ``CustomException``（400）。``duration`` 为音频时长，区间
        ``[start, end)`` 必须落在 ``[0, duration]``；label_id 必须属于任务 classes 列表。
        """
        if not isinstance(classes, list):
            raise CustomException(msg="audio_event 任务 classes 必须为列表", code=400, status_code=400)
        label_ids = {c.get("id") for c in classes}

        intervals: list[tuple[float, float]] = []
        for item in annotations:
            if not isinstance(item, dict):
                raise CustomException(msg="标注项必须为字典对象", code=400, status_code=400)
            if item.get("type") != "AudioSegment":
                raise CustomException(
                    msg=f"未知标注类型: {item.get('type')}", code=400, status_code=400
                )
            start, end = item.get("start"), item.get("end")
            # 接受 int/float 数字（排除 bool）；JSON 中整数值会解析为 int
            if isinstance(start, bool) or not isinstance(start, (int, float)) or \
               isinstance(end, bool) or not isinstance(end, (int, float)):
                raise CustomException(
                    msg="AudioSegment 的 start/end 必须为数字", code=400, status_code=400
                )
            start, end = float(start), float(end)
            if end <= start:
                raise CustomException(
                    msg="AudioSegment 的 end 必须大于 start", code=400, status_code=400
                )
            if start < 0 or end > duration:
                raise CustomException(
                    msg=f"AudioSegment 超出音频范围 [0, {duration}]",
                    code=400,
                    status_code=400,
                )
            if item.get("label_id") not in label_ids:
                raise CustomException(
                    msg=f"AudioSegment label_id 非法: {item.get('label_id')}",
                    code=400,
                    status_code=400,
                )
            intervals.append((start, end))

        # 重叠校验与输入顺序无关：先收集全部区间再排序两两检测（相邻 [0,2)/[2,4) 不视为重叠）
        intervals.sort()
        for i in range(1, len(intervals)):
            if intervals[i][0] < intervals[i - 1][1]:
                raise CustomException(
                    msg="AudioSegment 区间存在重叠", code=400, status_code=400
                )

    @classmethod
    async def _prune_audio_versions(
        cls, db, task_id: int, audio_id: int, latest_version: int, keep: int
    ) -> None:
        """保留首版（v1）与最近 keep 版，删除中间旧版本（按音频粒度）。"""
        if keep <= 0 or latest_version <= keep + 1:
            return
        upper = latest_version - keep
        await db.execute(
            delete(AnnotationRecordModel).where(
                AnnotationRecordModel.task_id == task_id,
                AnnotationRecordModel.audio_id == audio_id,
                AnnotationRecordModel.version >= 2,
                AnnotationRecordModel.version <= upper,
            )
        )

    @classmethod
    async def save_audio_annotations(
        cls, task_id: int, audio_id: int, annotations: list[dict], auth
    ) -> dict:
        """按 (task_id, audio_id) 持久化音频事件标注；校验 AudioSegment 后 upsert。"""
        async with async_db_session.begin() as db:
            audio = await cls._verify_audio_task_relation(db, task_id, audio_id)
            if audio.locked_by and audio.locked_by != auth.user.id:
                raise CustomException(
                    msg="音频已被其他用户锁定，无法保存", code=409, status_code=409
                )
            task = await db.get(AnnotationTaskModel, task_id)
            cls._validate_audio_annotations(annotations, task.classes, audio.duration)

            existing = (
                await db.execute(
                    select(AnnotationRecordModel)
                    .where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.audio_id == audio_id,
                    )
                    .order_by(desc(AnnotationRecordModel.version))
                    .limit(1)
                )
            ).scalar_one_or_none()
            version = existing.version + 1 if existing else 1

            db.add(AnnotationRecordModel(
                task_id=task_id,
                audio_id=audio_id,
                annotation_data=annotations,
                version=version,
                created_id=auth.user.id,
            ))
            await db.flush()
            await cls._prune_audio_versions(
                db, task_id, audio_id, version, settings.ANNOTATION_VERSION_KEEP
            )

            if audio:
                audio.status = "annotated" if annotations else "unannotated"
                audio.annotation_count = len(annotations)

        log.info(f"save_audio_annotations task={task_id} audio={audio_id} v={version}")
        return {"version": version, "annotation_count": len(annotations)}

    @classmethod
    async def load_audio_annotations(cls, task_id: int, audio_id: int) -> dict:
        """读取某音频的最新标注；无记录返回空列表与 version 0。"""
        async with async_db_session.begin() as db:
            await cls._verify_audio_task_relation(db, task_id, audio_id)
            record = (
                await db.execute(
                    select(AnnotationRecordModel)
                    .where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.audio_id == audio_id,
                    )
                    .order_by(desc(AnnotationRecordModel.version))
                    .limit(1)
                )
            ).scalar_one_or_none()
            return {
                "annotation_data": record.annotation_data if record else [],
                "version": record.version if record else 0,
            }

    # ------------------------------------------------------------------
    # 时间序列事件标注（按 time_series_id 读写）
    # ------------------------------------------------------------------

    @classmethod
    async def _verify_time_series_task_relation(
        cls, db, task_id: int, time_series_id: int
    ) -> AnnotationTimeSeriesModel:
        """校验序列确实归属于指定任务（同为数据集下的 time_series_event 任务），返回序列对象。"""
        series = await db.get(AnnotationTimeSeriesModel, time_series_id)
        if not series or series.is_deleted:
            raise CustomException(msg=f"时间序列不存在: {time_series_id}", code=404, status_code=404)
        task = await db.get(AnnotationTaskModel, task_id)
        if (
            not task
            or task.is_deleted
            or task.dataset_id != series.dataset_id
            or task.task_type != "time_series_event"
        ):
            raise CustomException(
                msg="任务与时间序列不存在有效归属关系，无法保存/读取标注",
                code=400,
                status_code=400,
            )
        return series

    @classmethod
    def _validate_time_series_annotations(
        cls, annotations: list[dict], classes: list, series: AnnotationTimeSeriesModel
    ) -> None:
        """校验 time_series_event 标注：TimeSeriesSegment 字段合法性、区间边界、类别归属与重叠检测。

        非法项一律抛 ``CustomException``（400）。区间 ``[start, end)`` 必须落在
        ``[series.start_time, series.end_time]``；label_id 必须属于任务 classes 列表。
        """
        if not isinstance(classes, list):
            raise CustomException(
                msg="time_series_event 任务 classes 必须为列表", code=400, status_code=400
            )
        label_ids = {c.get("id") for c in classes}
        start_bound = float(series.start_time)
        end_bound = float(series.end_time)

        intervals: list[tuple[float, float]] = []
        for item in annotations:
            if not isinstance(item, dict):
                raise CustomException(msg="标注项必须为字典对象", code=400, status_code=400)
            if item.get("type") != "TimeSeriesSegment":
                raise CustomException(
                    msg=f"未知标注类型: {item.get('type')}", code=400, status_code=400
                )
            start, end = item.get("start"), item.get("end")
            # 接受 int/float 数字（排除 bool）；JSON 中整数值会解析为 int
            if isinstance(start, bool) or not isinstance(start, (int, float)) or \
               isinstance(end, bool) or not isinstance(end, (int, float)):
                raise CustomException(
                    msg="TimeSeriesSegment 的 start/end 必须为数字", code=400, status_code=400
                )
            start, end = float(start), float(end)
            if end <= start:
                raise CustomException(
                    msg="TimeSeriesSegment 的 end 必须大于 start", code=400, status_code=400
                )
            if start < start_bound or end > end_bound:
                raise CustomException(
                    msg=f"TimeSeriesSegment 超出序列时间范围 [{start_bound}, {end_bound}]",
                    code=400,
                    status_code=400,
                )
            if item.get("label_id") not in label_ids:
                raise CustomException(
                    msg=f"TimeSeriesSegment label_id 非法: {item.get('label_id')}",
                    code=400,
                    status_code=400,
                )
            intervals.append((start, end))

        # 重叠校验与输入顺序无关：先收集全部区间再排序两两检测（相邻 [0,2)/[2,4) 不视为重叠）
        intervals.sort()
        for i in range(1, len(intervals)):
            if intervals[i][0] < intervals[i - 1][1]:
                raise CustomException(
                    msg="TimeSeriesSegment 区间存在重叠", code=400, status_code=400
                )

    @classmethod
    async def _prune_time_series_versions(
        cls, db, task_id: int, time_series_id: int, latest_version: int, keep: int
    ) -> None:
        """保留首版（v1）与最近 keep 版，删除中间旧版本（按序列粒度）。"""
        if keep <= 0 or latest_version <= keep + 1:
            return
        upper = latest_version - keep
        await db.execute(
            delete(AnnotationRecordModel).where(
                AnnotationRecordModel.task_id == task_id,
                AnnotationRecordModel.time_series_id == time_series_id,
                AnnotationRecordModel.version >= 2,
                AnnotationRecordModel.version <= upper,
            )
        )

    @classmethod
    async def save_time_series_annotations(
        cls, task_id: int, time_series_id: int, annotations: list[dict], user_id: int
    ) -> dict:
        """按 (task_id, time_series_id) 持久化时间序列事件标注；校验 TimeSeriesSegment 后 upsert。"""
        async with async_db_session.begin() as db:
            series = await cls._verify_time_series_task_relation(db, task_id, time_series_id)
            if series.locked_by and series.locked_by != user_id:
                raise CustomException(
                    msg="时间序列已被其他用户锁定，无法保存", code=409, status_code=409
                )
            task = await db.get(AnnotationTaskModel, task_id)
            cls._validate_time_series_annotations(annotations, task.classes, series)

            existing = (
                await db.execute(
                    select(AnnotationRecordModel)
                    .where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.time_series_id == time_series_id,
                    )
                    .order_by(desc(AnnotationRecordModel.version))
                    .limit(1)
                )
            ).scalar_one_or_none()
            version = existing.version + 1 if existing else 1

            db.add(AnnotationRecordModel(
                task_id=task_id,
                time_series_id=time_series_id,
                annotation_data=annotations,
                version=version,
                created_id=user_id,
            ))
            await db.flush()
            await cls._prune_time_series_versions(
                db, task_id, time_series_id, version, settings.ANNOTATION_VERSION_KEEP
            )

            if series:
                series.status = "annotated" if annotations else "unannotated"
                series.annotation_count = len(annotations)

        log.info(f"save_time_series_annotations task={task_id} series={time_series_id} v={version}")
        return {"version": version, "annotation_count": len(annotations)}

    @classmethod
    async def load_time_series_annotations(cls, task_id: int, time_series_id: int) -> dict:
        """读取某时间序列的最新标注；无记录返回空列表与 version 0。"""
        async with async_db_session.begin() as db:
            await cls._verify_time_series_task_relation(db, task_id, time_series_id)
            record = (
                await db.execute(
                    select(AnnotationRecordModel)
                    .where(
                        AnnotationRecordModel.task_id == task_id,
                        AnnotationRecordModel.time_series_id == time_series_id,
                    )
                    .order_by(desc(AnnotationRecordModel.version))
                    .limit(1)
                )
            ).scalar_one_or_none()
            return {
                "annotation_data": record.annotation_data if record else [],
                "version": record.version if record else 0,
            }
