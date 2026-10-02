"""数据落地（抽帧/清洗）编排服务：后台任务执行 + 图片/帧入库。

复用既有媒体链路：``media.process_image``（缩略图/尺寸）、``s3_client``（对象存储）、
``AnnotationImageModel``（入库），与 ``DatasetService.upload_images`` 保持一致。
"""
import asyncio
import io
import uuid

from sqlalchemy import func, select, update

from app.core.audit import set_create_audit
from app.core.database import async_db_session
from app.core.logger import log
from app.utils.s3_client import s3_client

from ..media import content_hash, process_image
from ..model import AnnotationImageModel, DatasetModel, ImageStatus
from . import jobs
from .config import CleaningConfig, ExtractConfig
from .frames import decide_reason, extract_video_frames, frame_from_image


class PreprocessService:

    # ── 对外：后台任务入口 ───────────────────────────────────────────────
    @classmethod
    async def run_video_job(
        cls,
        job_id: str,
        dataset_id: int,
        user_id: int,
        video_path: str,
        filename: str,
        extract_cfg: ExtractConfig,
        clean_cfg: CleaningConfig,
        auth,
    ) -> None:
        """视频抽帧 + 清洗 + 入库，全程更新 job 进度。"""
        job = jobs.get_job(job_id)
        if not job:
            return
        try:
            job.status, job.phase = "running", "extract"
            frames = await asyncio.to_thread(extract_video_frames, video_path, extract_cfg)
            job.total = len(frames)
            job.phase = "clean"
            await cls._ingest_candidates(job, dataset_id, clean_cfg, auth, frames, _prefix="frame")
            job.status, job.phase = "done", "done"
        except Exception as e:  # noqa: BLE001
            log.warning(f"[数据落地-视频] 失败 job={job_id}: {e}")
            job.status, job.error = "failed", str(e)
        finally:
            job.touch()

    @classmethod
    async def run_images_job(
        cls,
        job_id: str,
        dataset_id: int,
        user_id: int,
        items: list[tuple[str, bytes]],
        clean_cfg: CleaningConfig,
        auth,
    ) -> None:
        """批量图片清洗 + 入库（items 为 [(filename, content_bytes), ...]）。"""
        job = jobs.get_job(job_id)
        if not job:
            return
        try:
            job.status, job.phase = "running", "clean"
            job.total = len(items)
            # 先解码为 FrameInfo；解码失败单独计数
            infos: list[tuple[str, object]] = []
            for name, content in items:
                info = await asyncio.to_thread(frame_from_image, content)
                if info is None:
                    job.dropped_unreadable += 1
                    job.processed += 1
                else:
                    infos.append((name, info))
            await cls._ingest_candidates(job, dataset_id, clean_cfg, auth, infos, _prefix="img")
            job.status, job.phase = "done", "done"
        except Exception as e:  # noqa: BLE001
            log.warning(f"[数据落地-图片] 失败 job={job_id}: {e}")
            job.status, job.error = "failed", str(e)
        finally:
            job.touch()

    # ── 内部：过滤 + 入库 ───────────────────────────────────────────────
    @classmethod
    async def _ingest_candidates(cls, job, dataset_id, clean_cfg, auth, infos, _prefix):
        """对候选帧/图逐个清洗判定，通过的写入对象存储 + 数据库。

        ``infos`` 元素为 ``FrameInfo`` 或 ``(filename, FrameInfo)``。
        """
        seen = await cls._load_existing_hashes(dataset_id)
        phash_list: list[int] = []
        uploaded_keys: list[str] = []

        try:
            async with async_db_session.begin() as db:
                dataset = await db.get(DatasetModel, dataset_id)
                if not dataset or dataset.is_deleted:
                    raise ValueError(f"数据集不存在: {dataset_id}")

                for item in infos:
                    if isinstance(item, tuple):
                        filename, info = item
                    else:
                        filename, info = None, item
                    if filename is None:
                        # 视频帧：按帧号生成文件名
                        filename = f"{_prefix}_{info.idx:06d}"
                    reason = decide_reason(info, clean_cfg, seen, phash_list)
                    if reason:
                        cls._count_drop(job, reason)
                    else:
                        keys = await cls._ingest_image(db, dataset_id, info, auth, filename)
                        uploaded_keys.extend(keys)
                        job.ingested += 1
                    job.processed += 1
                    if job.processed % 10 == 0:
                        job.touch()

                total = await db.scalar(
                    select(func.count(AnnotationImageModel.id)).where(
                        AnnotationImageModel.dataset_id == dataset_id,
                        AnnotationImageModel.is_deleted == False,  # noqa: E712
                    )
                )
                await db.execute(
                    update(DatasetModel)
                    .where(DatasetModel.id == dataset_id)
                    .values(image_count=total or 0)
                )
        except Exception:
            # DB 事务/上传失败：尽力补偿删除已上传对象，避免留孤儿
            if uploaded_keys:
                try:
                    await asyncio.to_thread(s3_client.delete_objects, uploaded_keys)
                except Exception as e2:  # noqa: BLE001
                    log.warning(f"[数据落地] 补偿删除孤儿对象失败: {e2}")
            raise

    @classmethod
    async def _ingest_image(cls, db, dataset_id, info, auth, filename: str | None = None):
        """单帧/单图入库：对象存储上传 + ``AnnotationImageModel`` 写入。"""
        name = filename or f"img_{uuid.uuid4().hex[:12]}.jpg"
        if not name.lower().endswith((".jpg", ".jpeg")):
            name = f"{name}.jpg"
        content = info.jpeg
        token = uuid.uuid4().hex
        object_key = f"datasets/{dataset_id}/images/{token}.jpg"
        thumb_key = f"datasets/{dataset_id}/thumbnails/{token}.jpg"

        width, height, thumb = await asyncio.to_thread(process_image, content)
        await asyncio.to_thread(
            s3_client.upload_fileobj, io.BytesIO(content), object_key, None, "image/jpeg"
        )
        if thumb:
            await asyncio.to_thread(
                s3_client.upload_fileobj, io.BytesIO(thumb), thumb_key, None, "image/jpeg"
            )
            thumb_key_ok = thumb_key
        else:
            thumb_key_ok = None

        img = AnnotationImageModel(
            dataset_id=dataset_id,
            filename=name,
            object_key=object_key,
            thumbnail_key=thumb_key_ok,
            content_hash=content_hash(content),
            width=width or info.width,
            height=height or info.height,
            status=ImageStatus.UNANNOTATED,
        )
        set_create_audit(img, auth)
        db.add(img)
        await db.flush()
        return [object_key] + ([thumb_key] if thumb else [])

    @classmethod
    async def _load_existing_hashes(cls, dataset_id: int) -> set[str]:
        """载入该数据集现有图片内容哈希，用于跨批次精确去重。"""
        async with async_db_session() as db:
            rows = await db.execute(
                select(AnnotationImageModel.content_hash).where(
                    AnnotationImageModel.dataset_id == dataset_id,
                    AnnotationImageModel.is_deleted == False,  # noqa: E712
                    AnnotationImageModel.content_hash.isnot(None),
                )
            )
            return set(rows.scalars().all())

    @staticmethod
    def _count_drop(job, reason: str) -> None:
        if reason == "blur":
            job.dropped_blur += 1
        elif reason == "dark":
            job.dropped_dark += 1
        elif reason == "bright":
            job.dropped_bright += 1
        elif reason == "too_small":
            job.dropped_small += 1
        elif reason == "duplicate":
            job.dropped_duplicate += 1
        else:
            job.dropped_unreadable += 1
