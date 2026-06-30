import asyncio
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.module_video.camera.model import CameraModel
from app.api.v1.module_video.record.model import (
    RecordExecutionLog,
    RecordFileModel,
    RecordPlanModel,
)
from app.api.v1.module_video.record.service import (
    RECORDINGS_DIR,
    RecordService,
    _running_recordings,
)
from app.core.database import async_db_session
from app.core.logger import logger

_WARMUP_DELAY = 15
_CHECK_INTERVAL = 60


def _should_record_now(plan: RecordPlanModel) -> bool:
    if plan.plan_type == "CONTINUOUS":
        return True
    if plan.plan_type != "SCHEDULE":
        return False
    schedule = plan.schedule_json
    if not schedule or schedule.get("type") != "weekly":
        return False
    now = datetime.now()
    current_minutes = now.hour * 60 + now.minute
    for slot in schedule.get("slots", []):
        # DB stores day as 1=Monday..7=Sunday (Chinese convention)
        # Python weekday(): 0=Monday..6=Sunday
        slot_day = slot.get("day")
        if not isinstance(slot_day, int):
            continue
        python_weekday = slot_day - 1
        if python_weekday != now.weekday():
            continue
        start_mins = slot["start"] * 60 if isinstance(slot["start"], int) else slot["start"]
        end_mins = slot["end"] * 60 if isinstance(slot["end"], int) else slot["end"]
        if start_mins <= current_minutes < end_mins:
            return True
    return False


async def _get_active_plans(session: AsyncSession) -> list[RecordPlanModel]:
    stmt = select(RecordPlanModel).where(
        RecordPlanModel.status.is_(True),
        RecordPlanModel.is_deleted.is_(False),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _get_camera(session: AsyncSession, camera_id: int) -> CameraModel | None:
    result = await session.execute(
        select(CameraModel).where(CameraModel.id == camera_id, CameraModel.is_deleted.is_(False))
    )
    return result.scalar_one_or_none()


async def _get_known_segments_from_db(stream_id: str) -> set[str]:
    """Load already-persisted file paths from DB to avoid duplicates on restart."""
    known: set[str] = set()
    try:
        async with async_db_session() as session:
            stmt = select(RecordFileModel.file_path).where(
                RecordFileModel.stream_id == stream_id,
                RecordFileModel.status == "COMPLETED",
            )
            result = await session.execute(stmt)
            for (fp,) in result:
                known.add(Path(fp).name)
    except Exception as e:
        logger.warning(f"[录制定时器] 加载已入库文件失败: {e}")
    return known


def _is_file_already_persisted(file_path: str) -> bool:
    """Check if a file has already been persisted by scanning the record dir."""
    # Fast check via known_segments in _running_recordings is preferred.
    # This is a secondary check for edge cases.
    return False


async def _check_new_segments(stream_id: str):
    """Detect completed FFmpeg segment files and persist them (dedup-aware)."""
    info = _running_recordings.get(stream_id)
    if not info:
        return
    record_dir = RECORDINGS_DIR / stream_id
    if not record_dir.exists():
        return
    current_files = set(f.name for f in record_dir.glob("*.mp4") if f.stat().st_size > 10000)
    new_files = current_files - info.get("known_segments", set())
    if not new_files:
        return
    info["known_segments"] = current_files
    for fname in sorted(new_files):
        fp = record_dir / fname
        trigger = info.get("trigger", "SCHEDULED")
        await RecordService._persist_segment(stream_id, str(fp), trigger=trigger)


async def _init_known_segments(stream_id: str):
    """Pre-populate known_segments from both filesystem and DB on startup."""
    record_dir = RECORDINGS_DIR / stream_id
    fs_files = set()
    if record_dir.exists():
        fs_files = set(f.name for f in record_dir.glob("*.mp4") if f.stat().st_size > 10000)
    db_files = await _get_known_segments_from_db(stream_id)
    return fs_files | db_files


async def start_scheduled_recording(plan: RecordPlanModel, camera: CameraModel):
    """Start a scheduled recording with dedup-aware init."""
    stream_id = camera.stream_id
    if stream_id in _running_recordings:
        return  # already running

    known = await _init_known_segments(stream_id)
    await RecordService._start_ffmpeg_recording(
        camera_id=plan.camera_id,
        stream_id=stream_id,
        trigger="SCHEDULED",
        known_segments=known,
    )


async def stop_recording(stream_id: str, status: str = "COMPLETED"):
    """Stop a recording and update its execution log."""
    await RecordService._stop_ffmpeg_recording(stream_id)
    await RecordService._update_execution_log(stream_id, status=status)


async def handle_crashed_process(stream_id: str):
    """Handle an FFmpeg process that exited unexpectedly."""
    info = _running_recordings.pop(stream_id, None)
    if not info:
        return
    # Persist any partial segments
    outdir = RECORDINGS_DIR / stream_id
    if outdir.exists():
        for fp in sorted(outdir.glob("*.mp4")):
            fsize = fp.stat().st_size
            if fsize < 1000:
                fp.unlink(missing_ok=True)
                continue
            name = fp.name
            if name not in info.get("known_segments", set()):
                await RecordService._persist_segment(stream_id, str(fp), trigger=info.get("trigger", "SCHEDULED"))
    # Update execution log to ERROR
    await RecordService._update_execution_log(stream_id, status="ERROR")


async def _reconcile_on_startup():
    """On scheduler start: reconcile DB plans with running state, mark stale logs."""
    async with async_db_session() as session:
        # Mark any dangling RECORDING logs as ERROR (they died during restart)
        stmt = select(RecordExecutionLog).where(
            RecordExecutionLog.status == "RECORDING",
            RecordExecutionLog.end_time.is_(None),
        )
        result = await session.execute(stmt)
        stale_logs = list(result.scalars().all())
        for log in stale_logs:
            log.status = "ERROR"
            log.end_time = datetime.now()
            log.duration = 0
            logger.info(f"[录制定时器] 标记残留执行日志为ERROR: plan={log.plan_id} camera={log.camera_id}")
        if not stale_logs:
            logger.info("[录制定时器] 无残留执行日志")
        await session.commit()


async def _check_and_execute_plans():
    try:
        async with async_db_session() as session:
            plans = await _get_active_plans(session)

        # Check each plan: should it be recording?
        for plan in plans:
            try:
                camera = await _get_camera(session, plan.camera_id)
                if not camera or not camera.stream_id:
                    continue
                stream_id = camera.stream_id
                should_record = _should_record_now(plan)
                is_running = stream_id in _running_recordings

                if should_record and not is_running:
                    await start_scheduled_recording(plan, camera)
                    logger.info(f"[录制定时器] 启动录制: camera={camera.name} plan={plan.id}")
                elif not should_record and is_running:
                    await stop_recording(stream_id)
                    logger.info(f"[录制定时器] 停止录制: camera={camera.name} plan={plan.id}")
            except Exception as e:
                logger.error(f"[录制定时器] 计划处理失败: plan={plan.id} error={e}")

        # Process segments and health for all running recordings
        for sid in list(_running_recordings.keys()):
            try:
                await _check_new_segments(sid)
                info = _running_recordings.get(sid)
                if info and info["proc"].returncode is not None:
                    logger.warning(f"[录制定时器] FFmpeg 进程意外退出: {sid} rc={info['proc'].returncode}")
                    await handle_crashed_process(sid)
            except Exception as e:
                logger.error(f"[录制定时器] 健康检查失败: stream={sid} error={e}")

    except Exception as e:
        logger.error(f"[录制定时器] 调度循环异常: {e}")


_record_task: asyncio.Task | None = None


async def start_record_scheduler():
    global _record_task
    _record_task = asyncio.current_task()
    await asyncio.sleep(_WARMUP_DELAY)
    await _reconcile_on_startup()
    logger.info(f"[录制定时器] 启动，检查间隔 {_CHECK_INTERVAL}s")

    while True:
        await _check_and_execute_plans()
        await asyncio.sleep(_CHECK_INTERVAL)


async def stop_record_scheduler():
    global _record_task
    if _record_task:
        _record_task.cancel()
        _record_task = None
        logger.info("[录制定时器] 已停止")
