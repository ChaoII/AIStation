import asyncio
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_db_session
from app.core.logger import logger
from app.api.v1.module_video.camera.model import CameraModel
from app.api.v1.module_video.record.model import RecordExecutionLog, RecordPlanModel
from app.api.v1.module_video.record.service import RECORDINGS_DIR, RecordService, _running_recordings

_WARMUP_DELAY = 15
_CHECK_INTERVAL = 60
_SEGMENT_DURATION = 300  # 5 minutes


def _should_record_now(plan: RecordPlanModel) -> bool:
    if not plan.schedule_json or plan.plan_type != "SCHEDULE":
        return plan.plan_type == "CONTINUOUS"
    schedule = plan.schedule_json
    if schedule.get("type") != "weekly":
        return True
    now = datetime.now()
    weekday = now.weekday()
    current_minutes = now.hour * 60 + now.minute
    for slot in schedule.get("slots", []):
        if slot.get("day") == weekday:
            start_mins = int(slot["start"]) * 60 if isinstance(slot["start"], int) else slot["start"]
            end_mins = int(slot["end"]) * 60 if isinstance(slot["end"], int) else slot["end"]
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


async def _check_new_segments(stream_id: str):
    """Detect completed FFmpeg segment files and persist them."""
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
        await RecordService._persist_segment(stream_id, str(fp))


async def _check_and_execute_plans():
    async with async_db_session() as session:
        try:
            plans = await _get_active_plans(session)
            for plan in plans:
                camera = await _get_camera(session, plan.camera_id)
                if not camera or not camera.stream_id:
                    continue
                stream_id = camera.stream_id
                should_record = _should_record_now(plan)
                is_running = stream_id in _running_recordings

                if should_record and not is_running:
                    try:
                        await RecordService._start_ffmpeg_recording(plan.camera_id, stream_id, "SCHEDULED")
                        await _create_execution_log(session, plan, camera)
                        logger.info(f"[录制定时器] 启动录制: camera={camera.name} plan={plan.id}")
                    except Exception as e:
                        logger.error(f"[录制定时器] 启动失败: {e}")
                elif not should_record and is_running:
                    try:
                        await RecordService._stop_ffmpeg_recording(stream_id)
                        logger.info(f"[录制定时器] 停止录制: camera={camera.name} plan={plan.id}")
                    except Exception as e:
                        logger.error(f"[录制定时器] 停止失败: {e}")

            # Check for new segments & clean dead processes
            for sid in list(_running_recordings.keys()):
                await _check_new_segments(sid)
                info = _running_recordings.get(sid)
                if info and info["proc"].poll() is not None:
                    # Process exited unexpectedly — clean up
                    logger.warning(f"[录制定时器] FFmpeg 进程意外退出: {sid}")
                    _running_recordings.pop(sid, None)
        except Exception as e:
            logger.error(f"[录制定时器] 检查计划异常: {e}")


async def _create_execution_log(session: AsyncSession, plan: RecordPlanModel, camera: CameraModel):
    log_entry = RecordExecutionLog(
        plan_id=plan.id, camera_id=plan.camera_id, stream_id=camera.stream_id,
        trigger_type="SCHEDULED", status="RECORDING", start_time=datetime.now(),
    )
    session.add(log_entry)
    await session.commit()


_record_task: asyncio.Task | None = None


async def start_record_scheduler():
    global _record_task
    _record_task = asyncio.current_task()
    await asyncio.sleep(_WARMUP_DELAY)
    logger.info("[录制定时器] 启动，检查间隔 %ds", _CHECK_INTERVAL)
    while True:
        await _check_and_execute_plans()
        await asyncio.sleep(_CHECK_INTERVAL)


async def stop_record_scheduler():
    global _record_task
    if _record_task:
        _record_task.cancel()
        _record_task = None
        logger.info("[录制定时器] 已停止")
