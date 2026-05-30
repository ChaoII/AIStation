import asyncio
import os
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, update as sa_update

from app.api.v1.module_system.auth.schema import AuthSchema
from app.api.v1.module_video.camera.model import CameraModel
from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.media_server import media_server

from .crud import RecordExecutionLogCRUD, RecordFileCRUD, RecordPlanCRUD
from .model import RecordExecutionLog, RecordFileModel, RecordPlanModel
from .schema import (
    RecordExecutionLogOutSchema,
    RecordFileOutSchema,
    RecordPlanCreateSchema,
    RecordPlanOutSchema,
    RecordPlanUpdateSchema,
)

RECORDINGS_DIR = Path("data/recordings").resolve()
RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

_SEGMENT_SEC = 300  # 5 min per segment

# stream_id -> {"proc": subprocess.Popen, "known_segments": set[str], "start_time": datetime, "camera_id": int}
_running_recordings: dict[str, dict] = {}


def _ensure_dir(stream_id: str) -> Path:
    d = RECORDINGS_DIR / stream_id
    d.mkdir(parents=True, exist_ok=True)
    return d


class RecordService:

    # ── internal FFmpeg helpers (used by scheduler & manual) ──

    @classmethod
    async def _start_ffmpeg_recording(cls, camera_id: int, stream_id: str, trigger: str = "MANUAL"):
        flv_url = f"{settings.ZLM_BASE_URL}/live/{stream_id}.live.flv"
        outdir = _ensure_dir(stream_id)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        pattern = str(outdir / f"{ts}_%03d.mp4")

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", flv_url,
            "-c", "copy",
            "-f", "segment", "-segment_time", str(_SEGMENT_SEC),
            "-reset_timestamps", "1",
            pattern,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        known = set(f.name for f in outdir.glob("*.mp4") if f.stat().st_size > 10000)
        _running_recordings[stream_id] = {
            "proc": proc,
            "known_segments": known,
            "start_time": datetime.now(),
            "camera_id": camera_id,
        }

    @classmethod
    async def _stop_ffmpeg_recording(cls, stream_id: str):
        info = _running_recordings.pop(stream_id, None)
        if info:
            proc = info["proc"]
            proc.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        await cls._complete_running_logs(stream_id)
        # Persist any remaining new segments (including final partial)
        outdir = RECORDINGS_DIR / stream_id
        if outdir.exists():
            for fp in sorted(outdir.glob("*.mp4")):
                fsize = fp.stat().st_size
                if fsize < 1000:
                    fp.unlink(missing_ok=True)
                    continue
                await cls._persist_segment(stream_id, str(fp))

    @classmethod
    async def _persist_segment(cls, stream_id: str, file_path: str):
        """Create a RecordFileModel for a completed segment, skipping duplicates."""
        fp = Path(file_path)
        # Find camera_id by stream_id
        camera_id = None
        async with async_db_session() as session:
            result = await session.execute(
                select(CameraModel.id).where(
                    CameraModel.stream_id == stream_id,
                    CameraModel.is_deleted.is_(False),
                )
            )
            cam = result.scalar_one_or_none()
            if cam:
                camera_id = cam
        if not camera_id:
            return
        # Skip if already recorded
        async with async_db_session() as session:
            existing = await session.execute(
                select(RecordFileModel.id).where(
                    RecordFileModel.file_path == str(fp),
                    RecordFileModel.stream_id == stream_id,
                )
            )
            if existing.scalar_one_or_none():
                return
            fsize = fp.stat().st_size
            record_file = RecordFileModel(
                camera_id=camera_id,
                stream_id=stream_id,
                file_path=str(fp),
                file_size=fsize,
                duration=0,
                start_time=datetime.fromtimestamp(fp.stat().st_ctime),
                end_time=datetime.now(),
                record_type="MANUAL",
                format="mp4",
                status="COMPLETED",
            )
            session.add(record_file)
            await session.commit()

    # ── Manual recording API (called by frontend) ──

    @classmethod
    async def start_recording_service(cls, camera_id: int, stream_id: str, auth: AuthSchema) -> dict:
        try:
            await cls._start_ffmpeg_recording(camera_id, stream_id, "MANUAL")
            plan_ids = await cls._get_plan_ids_for_camera(camera_id)
            if plan_ids:
                for pid in plan_ids:
                    log_entry = RecordExecutionLog(
                        plan_id=pid, camera_id=camera_id, stream_id=stream_id,
                        trigger_type="MANUAL", status="RECORDING", start_time=datetime.now(),
                    )
                    async with async_db_session() as session:
                        session.add(log_entry)
                        await session.commit()
            return {"camera_id": camera_id, "stream_id": stream_id}
        except Exception as e:
            raise CustomException(msg=f"启动录制失败: {e}")

    @classmethod
    async def stop_recording_service(cls, stream_id: str, auth: AuthSchema) -> dict:
        try:
            await cls._stop_ffmpeg_recording(stream_id)
            return {"stream_id": stream_id}
        except Exception as e:
            raise CustomException(msg=f"停止录制失败: {e}")

    # ── Plan CRUD ──

    @classmethod
    async def get_plan_list_service(
        cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None
    ) -> list[dict]:
        plans = await RecordPlanCRUD(auth).get_list_crud(search=search.__dict__ if search else None, order_by=order_by)
        return [RecordPlanOutSchema.model_validate(p).model_dump() for p in plans]

    @classmethod
    async def create_plan_service(cls, data: RecordPlanCreateSchema, auth: AuthSchema) -> dict:
        new_plan = await RecordPlanCRUD(auth).create(data=data)
        return RecordPlanOutSchema.model_validate(new_plan).model_dump()

    @classmethod
    async def update_plan_service(cls, id: int, data: RecordPlanUpdateSchema, auth: AuthSchema) -> dict:
        plan = await RecordPlanCRUD(auth).get_by_id_crud(id=id)
        if not plan:
            raise CustomException(msg="录制计划不存在")
        updated = await RecordPlanCRUD(auth).update(id=id, data=data)
        return RecordPlanOutSchema.model_validate(updated).model_dump()

    @classmethod
    async def delete_plan_service(cls, ids: list[int], auth: AuthSchema) -> None:
        await RecordPlanCRUD(auth).delete(ids=ids)

    @classmethod
    async def _get_plan_ids_for_camera(cls, camera_id: int) -> list[int]:
        async with async_db_session() as session:
            result = await session.execute(
                select(RecordPlanModel.id).where(
                    RecordPlanModel.camera_id == camera_id,
                    RecordPlanModel.status.is_(True),
                    RecordPlanModel.is_deleted.is_(False),
                )
            )
            return [r[0] for r in result.all()]

    @classmethod
    async def _complete_running_logs(cls, stream_id: str):
        async with async_db_session() as session:
            result = await session.execute(
                select(RecordExecutionLog).where(
                    RecordExecutionLog.stream_id == stream_id,
                    RecordExecutionLog.status == "RECORDING",
                )
            )
            now = datetime.now()
            for log_entry in result.scalars().all():
                if log_entry.start_time:
                    log_entry.duration = int((now - log_entry.start_time).total_seconds())
                log_entry.end_time = now
                log_entry.status = "COMPLETED"
                log_entry.updated_at = now
            await session.commit()

    # ── File / Playback ──

    @classmethod
    async def get_record_files_service(cls, camera_id: int, auth: AuthSchema) -> list[dict]:
        search = {"camera_id": camera_id}
        files = await RecordFileCRUD(auth).get_list_crud(search=search, order_by=[{"start_time": "desc"}])
        return [RecordFileOutSchema.model_validate(f).model_dump() for f in files]

    @classmethod
    async def get_file_list_service(
        cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None
    ) -> list[dict]:
        files = await RecordFileCRUD(auth).get_list_crud(search=search.__dict__ if search else None, order_by=order_by)
        return [RecordFileOutSchema.model_validate(f).model_dump() for f in files]

    @classmethod
    async def get_file_detail_service(cls, id: int, auth: AuthSchema) -> dict:
        file_obj = await RecordFileCRUD(auth).get(id=id)
        if not file_obj:
            raise CustomException(msg="录制文件不存在")
        return RecordFileOutSchema.model_validate(file_obj).model_dump()

    @classmethod
    async def delete_file_service(cls, ids: list[int], auth: AuthSchema) -> None:
        await RecordFileCRUD(auth).delete(ids=ids)

    @classmethod
    async def get_file_play_url_service(cls, id: int, auth: AuthSchema) -> dict:
        file_obj = await RecordFileCRUD(auth).get(id=id)
        if not file_obj:
            raise CustomException(msg="录制文件不存在")
        fp = Path(str(file_obj.file_path))
        play_url = f"/recordings/{file_obj.stream_id}/{fp.name}" if file_obj.stream_id else ""
        return {
            "id": file_obj.id,
            "camera_id": file_obj.camera_id,
            "stream_id": file_obj.stream_id,
            "file_path": file_obj.file_path,
            "play_url": play_url,
        }

    @classmethod
    async def get_execution_log_list_service(
        cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None
    ) -> list[dict]:
        logs = await RecordExecutionLogCRUD(auth).get_list_crud(search=search.__dict__ if search else None, order_by=order_by or [{"start_time": "desc"}])
        return [RecordExecutionLogOutSchema.model_validate(log).model_dump() for log in logs]

    @classmethod
    async def get_execution_log_detail_service(cls, id: int, auth: AuthSchema) -> dict:
        log_entry = await RecordExecutionLogCRUD(auth).get_by_id_crud(id=id)
        if not log_entry:
            raise CustomException(msg="执行日志不存在")
        return RecordExecutionLogOutSchema.model_validate(log_entry).model_dump()

    @classmethod
    async def handle_record_webhook(cls, data: dict) -> dict:
        stream_id = data.get("stream_id", "")
        file_path = data.get("file_path", "")
        file_name = data.get("file_name", "")
        file_size = data.get("file_size", 0)
        duration = data.get("duration", 0)
        start_time_str = data.get("start_time", "")
        end_time_str = data.get("time", "")
        camera_id = None
        if stream_id:
            async with async_db_session() as session:
                result = await session.execute(
                    select(CameraModel.id).where(
                        CameraModel.stream_id == stream_id,
                        CameraModel.is_deleted.is_(False),
                    )
                )
                cam = result.scalar_one_or_none()
                if cam:
                    camera_id = cam
        if not camera_id:
            return {"code": 1, "msg": "camera not found"}
        record_file = RecordFileModel(
            camera_id=camera_id, stream_id=stream_id,
            file_path=file_path or file_name, file_size=file_size, duration=duration,
            start_time=datetime.fromisoformat(start_time_str) if start_time_str else datetime.now(),
            end_time=datetime.fromisoformat(end_time_str) if end_time_str else datetime.now(),
            record_type="CONTINUOUS", format="mp4", status="COMPLETED",
        )
        async with async_db_session() as session:
            session.add(record_file)
            await session.commit()
            await session.execute(
                sa_update(RecordExecutionLog)
                .where(RecordExecutionLog.stream_id == stream_id, RecordExecutionLog.status == "RECORDING")
                .values(file_count=RecordExecutionLog.file_count + 1, updated_at=datetime.now())
            )
            await session.commit()
        return {"code": 0, "msg": "ok"}
