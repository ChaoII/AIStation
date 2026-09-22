"""视频上传 service：RustFS 存储 + ffprobe 元数据（时长/宽高/帧率/帧数）探测。"""
import io
import json
import subprocess
import tempfile
import uuid
from pathlib import Path

from sqlalchemy import func, select, update

from app.api.v1.module_annotation.dataset.model import (
    AnnotationVideoModel,
    DatasetModel,
    ImageStatus,
)
from app.core.audit import set_create_audit
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.utils.s3_client import s3_client

ALLOWED_VIDEO_EXTENSIONS: set[str] = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".flv", ".wmv", ".ts", ".m4v",
}

_EXT_CONTENT_TYPE: dict[str, str] = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".webm": "video/webm",
    ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
    ".ts": "video/mp2t",
    ".m4v": "video/x-m4v",
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


def _probe_video(path: str) -> dict:
    """探测视频元数据，返回 ``{width,height,fps,duration,frame_count}``。"""
    data = _run_ffprobe(path)
    streams = data.get("streams", [])
    # 优先取视频流；若 ffprobe 输出未带 codec_type（如测试 mock），回退到首个带宽高的流
    v = next(
        (s for s in streams if s.get("codec_type") == "video" or s.get("width")),
        {},
    )
    w, h = v.get("width", 0), v.get("height", 0)
    rate = v.get("r_frame_rate", "0/1")
    num, _, den = rate.partition("/")
    fps = float(num) / float(den) if den and float(den) else 0.0
    duration = float(data.get("format", {}).get("duration", 0) or 0)
    return {
        "width": w,
        "height": h,
        "fps": fps,
        "duration": duration,
        "frame_count": round(duration * fps),
    }


class VideoService:

    @classmethod
    async def upload_video(cls, dataset_id: int, file, auth) -> dict:
        """上传单个视频：存 RustFS、ffprobe 探测、写入 ``AnnotationVideoModel`` 并更新
        ``dataset.video_count``。异常时删除已上传对象并抛出可读错误。"""
        import asyncio
        import os

        filename = file.filename or "unnamed"
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_VIDEO_EXTENSIONS:
            raise CustomException(
                msg=f"不支持的视频格式: {filename}", code=400, status_code=400
            )
        size = getattr(file, "size", None)
        max_bytes = 1024 * 1024 * 1024  # 视频允许较大，用 1GB 兜底
        if size is not None and size > max_bytes:
            raise CustomException(
                msg=f"文件过大: {filename}", code=400, status_code=400
            )

        content = await file.read()
        if not content:
            raise CustomException(msg="上传内容为空", code=400, status_code=400)

        object_key = f"datasets/{dataset_id}/videos/{uuid.uuid4().hex}{ext}"

        # 先写入临时文件用于 ffprobe（探测在对象存储上传前后均可，选在上传前，
        # 避免把无视频流/损坏的文件灌入对象存储）；若探测失败则不污染 RustFS。
        probe = None
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                probe = await asyncio.to_thread(_probe_video, tmp_path)
            except Exception as e:
                raise CustomException(
                    msg=f"无法解析视频元数据: {filename}（{e}）", code=400, status_code=400
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
            async with async_db_session.begin() as db:
                dataset = await db.get(DatasetModel, dataset_id)
                if not dataset or dataset.is_deleted:
                    raise CustomException(
                        msg=f"数据集不存在: {dataset_id}", code=404, status_code=404
                    )
                video = AnnotationVideoModel(
                    dataset_id=dataset_id,
                    name=filename,
                    object_key=object_key,
                    width=probe["width"],
                    height=probe["height"],
                    duration=probe["duration"],
                    fps=probe["fps"],
                    frame_count=probe["frame_count"],
                    status=ImageStatus.UNANNOTATED,
                )
                set_create_audit(video, auth)
                db.add(video)
                await db.flush()
                total = await db.scalar(
                    select(func.count(AnnotationVideoModel.id)).where(
                        AnnotationVideoModel.dataset_id == dataset_id,
                        AnnotationVideoModel.is_deleted == False,  # noqa: E712
                    )
                )
                await db.execute(
                    update(DatasetModel)
                    .where(DatasetModel.id == dataset_id)
                    .values(video_count=total or 0)
                )
                video_id = video.id
        except Exception:
            # DB 事务失败：删除本次已上传对象，避免孤儿
            if uploaded:
                try:
                    await asyncio.to_thread(s3_client.delete_object, object_key)
                except Exception as e2:  # noqa: BLE001
                    from app.core.logger import log
                    log.warning(f"[视频上传] 补偿删除对象失败: {e2}")
            raise

        return {
            "id": video_id,
            "dataset_id": dataset_id,
            "name": filename,
            "object_key": object_key,
            "width": probe["width"],
            "height": probe["height"],
            "duration": probe["duration"],
            "fps": probe["fps"],
            "frame_count": probe["frame_count"],
            "play_url": s3_client.presigned_url(object_key),
        }
