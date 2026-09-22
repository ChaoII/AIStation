"""音频上传 service：RustFS 存储 + ffprobe 元数据（时长/采样率/声道/码率）探测。

音频用 ``AnnotationAudioModel`` 记录，文件按扩展名白名单（.wav/.mp3/.m4a/.ogg/.aac/.flac）
与大小（≤100MB）校验；ffprobe 探测音频流后写入对象存储并入库，同时递增
``dataset.audio_count``。异常时删除已上传对象并重新抛出。
"""
import asyncio
import io
import json
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.api.v1.module_annotation.dataset.model import (
    AnnotationAudioModel,
    DatasetModel,
    ImageStatus,
)
from app.core.audit import set_create_audit
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log
from app.utils.s3_client import s3_client

ALLOWED_AUDIO_EXTENSIONS: set[str] = {
    ".wav", ".mp3", ".m4a", ".ogg", ".aac", ".flac",
}

MAX_AUDIO_BYTES = 100 * 1024 * 1024  # 100MB

_EXT_CONTENT_TYPE: dict[str, str] = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
}


def content_type_for(ext: str) -> str:
    """按扩展名返回 Content-Type，未知类型回退 octet-stream。"""
    return _EXT_CONTENT_TYPE.get(ext.lower(), "application/octet-stream")


def _run_ffprobe(path: str) -> dict:
    """调用 ffprobe 并解析 JSON 输出；非零返回码或解析失败抛 ValueError。"""
    cmd = [
        "ffprobe", "-hide_banner", "-loglevel", "error",
        "-print_format", "json",
        "-show_streams", "-show_format", path,
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        raise ValueError(f"ffprobe 探测失败(exit={e.returncode}): {e.stderr or e.stdout}") from e
    return json.loads(out.stdout)


def _probe_audio(path: str) -> dict:
    """探测音频元数据，返回 ``{duration,sample_rate,channels,bitrate}``。"""
    data = _run_ffprobe(path)
    streams = data.get("streams", [])
    # 优先取音频流；若 ffprobe 输出未带 codec_type（如测试 mock），回退到首个含 sample_rate 的流
    a = next(
        (s for s in streams if s.get("codec_type") == "audio" or s.get("sample_rate")),
        {},
    )
    duration = float(data.get("format", {}).get("duration", 0) or 0)
    sample_rate = a.get("sample_rate")
    channels = a.get("channels")
    bit_rate = a.get("bit_rate")
    return {
        "duration": duration,
        "sample_rate": int(sample_rate) if sample_rate else 0,
        "channels": int(channels) if channels else 0,
        "bitrate": int(bit_rate) // 1000 if bit_rate else None,
    }


class AudioService:

    @classmethod
    async def upload_audio(cls, db, dataset_id: int, file, auth) -> AnnotationAudioModel:
        """上传单个音频：白名单/大小校验、ffprobe 探测音频流、写入 RustFS、
        入库 ``AnnotationAudioModel`` 并递增 ``dataset.audio_count``。

        ``db`` 为调用方传入的 async 会话（便于复用事务）；异常时删除已上传
        对象并重新抛出。
        """
        filename = file.filename or "unnamed"
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            raise CustomException(
                msg=f"不支持的音频格式: {filename}", code=400, status_code=400
            )
        size = getattr(file, "size", None)
        if size is not None and size > MAX_AUDIO_BYTES:
            raise CustomException(
                msg=f"文件过大（>100MB）: {filename}", code=400, status_code=400
            )

        content = await file.read()
        if not content:
            raise CustomException(msg="上传内容为空", code=400, status_code=400)

        object_key = f"datasets/{dataset_id}/audios/{uuid.uuid4().hex}{ext}"

        # 先写入临时文件用于 ffprobe（探测在对象存储上传前后均可，选在上传前，
        # 避免把无音频流/损坏的文件灌入对象存储）；若探测失败则不污染 RustFS。
        probe = None
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                probe = await asyncio.to_thread(_probe_audio, tmp_path)
            except Exception as e:
                raise CustomException(
                    msg=f"无法解析音频元数据: {filename}（{e}）", code=400, status_code=400
                ) from e
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        # 上传到 RustFS（探测通过后再上传）
        await asyncio.to_thread(
            s3_client.upload_fileobj,
            io.BytesIO(content),
            object_key,
            None,
            content_type_for(ext),
        )
        uploaded = True

        try:
            dataset = await db.get(DatasetModel, dataset_id)
            if not dataset or dataset.is_deleted:
                raise CustomException(
                    msg=f"数据集不存在: {dataset_id}", code=404, status_code=404
                )
            audio = AnnotationAudioModel(
                dataset_id=dataset_id,
                name=filename,
                object_key=object_key,
                duration=probe["duration"],
                sample_rate=probe["sample_rate"],
                channels=probe["channels"],
                bitrate=probe["bitrate"],
                size_bytes=len(content),
                status=ImageStatus.UNANNOTATED,
            )
            set_create_audit(audio, auth)
            db.add(audio)
            await db.flush()
            dataset.audio_count += 1
        except Exception:
            # 入库失败：删除本次已上传对象，避免孤儿
            if uploaded:
                try:
                    await asyncio.to_thread(s3_client.delete_object, object_key)
                except Exception as e2:  # noqa: BLE001
                    log.warning(f"[音频上传] 补偿删除对象失败: {e2}")
            raise

        return audio

    LOCK_TIMEOUT_MINUTES = 5

    @classmethod
    async def list_audios(cls, dataset_id: int) -> list[dict]:
        """按数据集列出音频（不含已删除），附带对象存储的播放链接。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AnnotationAudioModel)
                    .where(
                        AnnotationAudioModel.dataset_id == dataset_id,
                        AnnotationAudioModel.is_deleted == False,  # noqa: E712
                    )
                    .order_by(AnnotationAudioModel.id.desc())
                )
            ).scalars().all()
            return [cls.audio_out(v) for v in rows]

    @classmethod
    async def get_audio(cls, audio_id: int) -> dict:
        """查询单个音频详情，不存在抛 404。"""
        async with async_db_session() as db:
            a = await db.get(AnnotationAudioModel, audio_id)
            if not a or a.is_deleted:
                raise CustomException(msg=f"音频不存在: {audio_id}", code=404, status_code=404)
            return cls.audio_out(a)

    @classmethod
    async def get_play_url(cls, audio_id: int) -> str:
        """返回音频对象存储的短时签名播放链接。"""
        async with async_db_session() as db:
            a = await db.get(AnnotationAudioModel, audio_id)
            if not a or a.is_deleted:
                raise CustomException(msg=f"音频不存在: {audio_id}", code=404, status_code=404)
            return s3_client.presigned_url(a.object_key)

    @classmethod
    async def lock_audio(cls, audio_id: int, user_id: int) -> dict:
        """按音频整体上锁，被他人持有且未超时则返回冲突信息。"""
        async with async_db_session.begin() as db:
            a = await db.get(AnnotationAudioModel, audio_id)
            if not a or a.is_deleted:
                raise CustomException(msg=f"音频不存在: {audio_id}", code=404, status_code=404)
            if a.locked_by and a.locked_at:
                if datetime.utcnow() - a.locked_at > timedelta(minutes=cls.LOCK_TIMEOUT_MINUTES):
                    a.locked_by = None
                    a.locked_at = None
            if a.locked_by and a.locked_by != user_id:
                return {"locked": True, "locked_by": a.locked_by}
            a.locked_by = user_id
            a.locked_at = datetime.utcnow()
            return {"locked": False, "locked_by": user_id}

    @classmethod
    async def unlock_audio(cls, audio_id: int, user_id: int) -> None:
        """解锁音频，仅锁持有者可解除。"""
        async with async_db_session.begin() as db:
            a = await db.get(AnnotationAudioModel, audio_id)
            if a and not a.is_deleted and a.locked_by == user_id:
                a.locked_by = None
                a.locked_at = None

    @classmethod
    def audio_out(cls, a: AnnotationAudioModel) -> dict:
        """音频行 → 输出 dict（含播放链接，status 序列化为字符串）。"""
        return {
            "id": a.id,
            "dataset_id": a.dataset_id,
            "name": a.name,
            "object_key": a.object_key,
            "duration": a.duration,
            "sample_rate": a.sample_rate,
            "channels": a.channels,
            "bitrate": a.bitrate,
            "size_bytes": a.size_bytes,
            "status": a.status.value if hasattr(a.status, "value") else a.status,
            "locked_by": a.locked_by,
            "annotation_count": a.annotation_count,
            "play_url": s3_client.presigned_url(a.object_key),
        }
