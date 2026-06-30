import asyncio
import re
import signal
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy import update as sa_update

from app.api.v1.module_system.auth.schema import AuthSchema
from app.api.v1.module_video.camera.model import CameraModel
from app.config.setting import settings
from app.core.database import async_db_session
from app.core.exceptions import CustomException

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
    async def _start_ffmpeg_recording(cls, camera_id: int, stream_id: str, trigger: str = "MANUAL",
                                       known_segments: set[str] | None = None):
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
        # Pre-populate from both filesystem and caller (DB-backed) to prevent re-persist
        fs_files = set(f.name for f in outdir.glob("*.mp4") if f.stat().st_size > 10000)
        known = fs_files | (known_segments or set())
        _running_recordings[stream_id] = {
            "proc": proc,
            "known_segments": known,
            "start_time": datetime.now(),
            "camera_id": camera_id,
            "trigger": trigger,
        }

    @classmethod
    async def _update_execution_log(cls, stream_id: str, status: str = "COMPLETED"):
        """Mark all RECORDING execution logs for this stream as done."""
        async with async_db_session() as session:
            result = await session.execute(
                select(RecordExecutionLog).where(
                    RecordExecutionLog.stream_id == stream_id,
                    RecordExecutionLog.status == "RECORDING",
                )
            )
            now = datetime.now()
            for log in result.scalars().all():
                if log.start_time:
                    log.duration = int((now - log.start_time).total_seconds())
                log.end_time = now
                log.status = status
            await session.commit()

    @classmethod
    async def _stop_ffmpeg_recording(cls, stream_id: str):
        info = _running_recordings.pop(stream_id, None)
        trigger = info.get("trigger", "MANUAL") if info else "MANUAL"
        if info:
            proc = info["proc"]
            proc.send_signal(signal.SIGTERM)
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            # Persist any remaining new segments (including final partial)
            outdir = RECORDINGS_DIR / stream_id
            if outdir.exists():
                for fp in sorted(outdir.glob("*.mp4")):
                    fsize = fp.stat().st_size
                    if fsize < 1000:
                        fp.unlink(missing_ok=True)
                        continue
                    name = fp.name
                    if name not in info.get("known_segments", set()):
                        info["known_segments"].add(name)
                        await cls._persist_segment(stream_id, str(fp), trigger=trigger)
        await cls._update_execution_log(stream_id, status="COMPLETED")

    _SEGMENT_FILENAME_RE = re.compile(r"^(\d{8}_\d{6})_(\d{3})\.mp4$")

    @classmethod
    def _probe_segment(cls, file_path: str) -> tuple[float, float] | None:
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-hide_banner", "-loglevel", "error",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    str(file_path),
                ],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0 or not result.stdout.strip():
                return None
            duration = float(result.stdout.strip().split(",")[-1])
        except Exception:
            return None
        try:
            mtime = Path(file_path).stat().st_mtime
        except OSError:
            return None
        end = datetime.fromtimestamp(mtime)
        start = end - timedelta(seconds=duration)
        return start, duration

    @classmethod
    def _parse_segment_times(cls, file_path: str) -> tuple[datetime, datetime, int] | None:
        fp = Path(file_path)
        # Prefer ffprobe for accurate duration, combined with file mtime for end time
        probe = cls._probe_segment(str(fp))
        if probe:
            start, duration = probe
            end = start + timedelta(seconds=duration)
            return start, end, int(duration)
        # Fallback: parse from filename (less accurate for multi-session)
        m = cls._SEGMENT_FILENAME_RE.match(fp.name)
        if not m:
            return None
        base_ts_str, seq_str = m.group(1), m.group(2)
        try:
            base_dt = datetime.strptime(base_ts_str, "%Y%m%d_%H%M%S")
        except ValueError:
            return None
        seq = int(seq_str)
        start = base_dt + timedelta(seconds=seq * _SEGMENT_SEC)
        end = start + timedelta(seconds=_SEGMENT_SEC)
        duration = _SEGMENT_SEC
        return start, end, duration

    @classmethod
    async def _persist_segment(cls, stream_id: str, file_path: str, trigger: str = "MANUAL"):
        fp = Path(file_path)
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
            parsed = cls._parse_segment_times(str(fp))
            if parsed:
                start_time, end_time, duration = parsed
            else:
                start_time = datetime.fromtimestamp(fp.stat().st_ctime)
                end_time = datetime.now()
                duration = 0
            record_file = RecordFileModel(
                camera_id=camera_id,
                stream_id=stream_id,
                file_path=str(fp),
                file_size=fsize,
                duration=duration,
                start_time=start_time,
                end_time=end_time,
                record_type=trigger,
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
        result = []
        for p in plans:
            item = RecordPlanOutSchema.model_validate(p).model_dump()
            # Add running state
            camera_id = item.get("camera_id")
            if camera_id:
                async with async_db_session() as session:
                    from sqlalchemy import select as sa_select
                    r = await session.execute(
                        sa_select(CameraModel.stream_id).where(
                            CameraModel.id == camera_id,
                            CameraModel.is_deleted.is_(False),
                        )
                    )
                    stream_id = r.scalar_one_or_none()
                item["is_running"] = stream_id in _running_recordings if stream_id else False
            else:
                item["is_running"] = False
            result.append(item)
        return result

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
    async def toggle_plan_service(cls, id: int, auth: AuthSchema) -> dict:
        plan = await RecordPlanCRUD(auth).get_by_id_crud(id=id)
        if not plan:
            raise CustomException(msg="录制计划不存在")
        new_status = not plan.status
        updated = await RecordPlanCRUD(auth).update(id=id, data={"status": new_status})
        return {"id": id, "status": new_status}

    @classmethod
    async def execute_plan_service(cls, id: int, auth: AuthSchema) -> dict:
        plan = await RecordPlanCRUD(auth).get_by_id_crud(id=id)
        if not plan:
            raise CustomException(msg="录制计划不存在")
        async with async_db_session() as session:
            from sqlalchemy import select as sa_select
            result = await session.execute(
                sa_select(CameraModel).where(
                    CameraModel.id == plan.camera_id,
                    CameraModel.is_deleted.is_(False),
                )
            )
            camera = result.scalar_one_or_none()
            if not camera or not camera.stream_id:
                raise CustomException(msg="摄像机未配置或流未启动")
        stream_id = camera.stream_id
        if stream_id in _running_recordings:
            raise CustomException(msg="该计划已在执行中")
        await cls._start_ffmpeg_recording(plan.camera_id, stream_id, "SCHEDULED")
        async with async_db_session() as session:
            log_entry = RecordExecutionLog(
                plan_id=plan.id, camera_id=plan.camera_id, stream_id=stream_id,
                trigger_type="MANUAL", status="RECORDING", start_time=datetime.now(),
            )
            session.add(log_entry)
            await session.commit()
        return {"id": id, "stream_id": stream_id, "status": "running"}

    @classmethod
    async def stop_plan_service(cls, id: int, auth: AuthSchema) -> dict:
        plan = await RecordPlanCRUD(auth).get_by_id_crud(id=id)
        if not plan:
            raise CustomException(msg="录制计划不存在")
        async with async_db_session() as session:
            from sqlalchemy import select as sa_select
            result = await session.execute(
                sa_select(CameraModel).where(
                    CameraModel.id == plan.camera_id,
                    CameraModel.is_deleted.is_(False),
                )
            )
            camera = result.scalar_one_or_none()
            if not camera or not camera.stream_id:
                raise CustomException(msg="摄像机未配置")
        stream_id = camera.stream_id
        if stream_id not in _running_recordings:
            raise CustomException(msg="该计划未在执行中")
        await cls._stop_ffmpeg_recording(stream_id)
        return {"id": id, "stream_id": stream_id, "status": "stopped"}

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
    def _fix_file_times(cls, item: dict) -> dict:
        fp = Path(item.get("file_path", ""))
        # Try ffprobe first for accurate times
        probe = cls._probe_segment(str(fp))
        if probe:
            start, duration = probe
            end = start + timedelta(seconds=duration)
            item["start_time"] = start.strftime("%Y-%m-%d %H:%M:%S")
            item["end_time"] = end.strftime("%Y-%m-%d %H:%M:%S")
            item["duration"] = int(duration)
            return item
        # Fallback: filename parsing
        parsed = cls._parse_segment_times(str(fp))
        if parsed:
            start, end, dur = parsed
            if not item.get("start_time") or item.get("duration") in (0, None):
                item["start_time"] = start.strftime("%Y-%m-%d %H:%M:%S")
                item["end_time"] = end.strftime("%Y-%m-%d %H:%M:%S")
                item["duration"] = dur
        if item.get("start_time") and item.get("end_time"):
            st = item["start_time"]
            et = item["end_time"]
            if isinstance(st, str):
                st = datetime.strptime(st, "%Y-%m-%d %H:%M:%S")
            if isinstance(et, str):
                et = datetime.strptime(et, "%Y-%m-%d %H:%M:%S")
            if not item.get("duration") or item["duration"] == 0:
                item["duration"] = max(0, int((et - st).total_seconds()))
        return item

    @classmethod
    async def get_record_files_service(cls, camera_id: int, auth: AuthSchema) -> list[dict]:
        search = {"camera_id": camera_id}
        files = await RecordFileCRUD(auth).get_list_crud(search=search, order_by=[{"start_time": "desc"}])
        return [cls._fix_file_times(RecordFileOutSchema.model_validate(f).model_dump()) for f in files]

    @classmethod
    async def get_file_list_service(
        cls, auth: AuthSchema, search: Any | None = None, order_by: list[dict[str, str]] | None = None
    ) -> list[dict]:
        files = await RecordFileCRUD(auth).get_list_crud(search=search.__dict__ if search else None, order_by=order_by)
        return [cls._fix_file_times(RecordFileOutSchema.model_validate(f).model_dump()) for f in files]

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
    async def get_file_thumbnail_service(cls, id: int, auth: AuthSchema) -> Path:
        file_obj = await RecordFileCRUD(auth).get(id=id)
        if not file_obj:
            raise CustomException(msg="录制文件不存在")
        fp = Path(str(file_obj.file_path))
        if not fp.exists():
            fp = RECORDINGS_DIR / file_obj.stream_id / fp.name if file_obj.stream_id else fp
        if not fp.exists():
            raise CustomException(msg="文件不存在")
        thumb_dir = RECORDINGS_DIR / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"{file_obj.id}.jpg"
        if thumb_path.exists() and thumb_path.stat().st_size > 0:
            return thumb_path
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-ss", "0.5", "-i", str(fp),
            "-vframes", "1", "-q:v", "4",
            "-vf", "scale=192:-1",
            "-y", str(thumb_path),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        await proc.wait()
        if not thumb_path.exists() or thumb_path.stat().st_size == 0:
            raise CustomException(msg="缩略图生成失败")
        return thumb_path

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

    @classmethod
    async def fix_file_times_service(cls) -> dict:
        fixed = 0
        async with async_db_session() as session:
            result = await session.execute(
                select(RecordFileModel).where(RecordFileModel.duration.in_([0, None]) | RecordFileModel.start_time.is_(None))
            )
            for row in result.scalars().all():
                fp = Path(row.file_path)
                if not fp.exists():
                    fp = RECORDINGS_DIR / row.stream_id / fp.name if row.stream_id else fp
                if not fp.exists():
                    continue
                probe = cls._probe_segment(str(fp))
                if probe:
                    start, duration = probe
                    end = start + timedelta(seconds=duration)
                    row.start_time = start
                    row.end_time = end
                    row.duration = int(duration)
                    fixed += 1
                else:
                    parsed = cls._parse_segment_times(str(fp))
                    if parsed:
                        start, end, dur = parsed
                        row.start_time = start
                        row.end_time = end
                        row.duration = dur
                        fixed += 1
            await session.commit()
        return {"fixed": fixed}
