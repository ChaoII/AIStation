import asyncio
from datetime import datetime, time, timedelta

from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_db_session
from app.core.logger import logger
from app.core.media_server import media_server
from app.api.v1.module_video.camera.model import CameraModel
from app.api.v1.module_video.record.model import RecordExecutionLog, RecordPlanModel

_WARMUP_DELAY = 15
_CHECK_INTERVAL = 60


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
            start_h, start_m = divmod(slot.get("start", 0), 1)
            end_h, end_m = divmod(slot.get("end", 24), 1)
            start_mins = int(slot["start"]) * 60 if isinstance(slot["start"], int) else slot["start"]
            end_mins = int(slot["end"]) * 60 if isinstance(slot["end"], int) else slot["end"]
            if start_mins <= current_minutes < end_mins:
                return True
    return False


async def _get_session() -> AsyncSession:
    factory = async_db_session
    async with factory() as session:
        return session


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


async def _has_running_log(session: AsyncSession, plan_id: int) -> bool:
    result = await session.execute(
        select(RecordExecutionLog).where(
            RecordExecutionLog.plan_id == plan_id,
            RecordExecutionLog.status == "RECORDING",
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _create_execution_log(session: AsyncSession, plan: RecordPlanModel, camera: CameraModel):
    log_entry = RecordExecutionLog(
        plan_id=plan.id,
        camera_id=plan.camera_id,
        stream_id=camera.stream_id,
        trigger_type="SCHEDULED",
        status="RECORDING",
        start_time=datetime.now(),
    )
    session.add(log_entry)
    await session.commit()
    return log_entry


async def _complete_execution_log(session: AsyncSession, log_entry: RecordExecutionLog):
    now = datetime.now()
    if log_entry.start_time:
        log_entry.duration = int((now - log_entry.start_time).total_seconds())
    log_entry.end_time = now
    log_entry.status = "COMPLETED"
    await session.commit()


async def _fail_execution_log(session: AsyncSession, log_entry: RecordExecutionLog, error: str):
    log_entry.status = "FAILED"
    log_entry.error_msg = error
    log_entry.end_time = datetime.now()
    await session.commit()


async def _check_and_execute_plans():
    async with async_db_session() as session:
        try:
            plans = await _get_active_plans(session)
            for plan in plans:
                camera = await _get_camera(session, plan.camera_id)
                if not camera or not camera.stream_id:
                    continue
                should_record = _should_record_now(plan)
                has_running = await _has_running_log(session, plan.id)
                try:
                    status_data = await media_server.get_record_status(stream_id=camera.stream_id)
                    is_recording = status_data.get("status", False)
                except Exception:
                    is_recording = False
                if should_record and not is_recording:
                    try:
                        await media_server.start_record(stream_id=camera.stream_id)
                        await _create_execution_log(session, plan, camera)
                        logger.info(f"[录制定时器] 启动录制: camera={camera.name} plan={plan.id}")
                    except Exception as e:
                        logger.error(f"[录制定时器] 启动失败: {e}")
                        if not has_running:
                            log_entry = await _create_execution_log(session, plan, camera)
                            await _fail_execution_log(session, log_entry, str(e))
                elif should_record and is_recording and not has_running:
                    await _create_execution_log(session, plan, camera)
                    logger.info(f"[录制定时器] 补录执行日志: camera={camera.name} plan={plan.id}")
                elif not should_record and is_recording:
                    try:
                        await media_server.stop_record(stream_id=camera.stream_id)
                        logger.info(f"[录制定时器] 停止录制: camera={camera.name} plan={plan.id}")
                    except Exception as e:
                        logger.error(f"[录制定时器] 停止失败: {e}")
                if not should_record and has_running and not is_recording:
                    running_logs = await session.execute(
                        select(RecordExecutionLog).where(
                            RecordExecutionLog.plan_id == plan.id,
                            RecordExecutionLog.status == "RECORDING",
                        )
                    )
                    for log_entry in running_logs.scalars().all():
                        await _complete_execution_log(session, log_entry)
        except Exception as e:
            logger.error(f"[录制定时器] 检查计划异常: {e}")


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
