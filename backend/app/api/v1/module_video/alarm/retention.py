"""告警记录 TTL 清理：删除超过保留期的历史告警，避免表无限膨胀。

与 ``edge/retention.py`` 同模式：
- ``purge_old_alarm_records``：分批物理删除，返回删除行数；
- ``start_alarm_record_retention``：启动即清一次，之后每 3600s 一轮；
- 任何异常仅告警，绝不影响应用启动/运行；``TESTING`` 下不启动后台任务。
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, delete, or_, select

from app.api.v1.module_video.alarm.model import AlarmRecordModel
from app.config.setting import settings

log = logging.getLogger(__name__)

# 清理轮询间隔（秒）
_PURGE_INTERVAL_SEC = 3600
# 单批删除上限，避免一次性长事务持锁/放大 autovacuum
_PURGE_BATCH_SIZE = 5000

_retention_task: asyncio.Task | None = None


def _cutoff(retention_days: int) -> datetime:
    return datetime.now() - timedelta(days=retention_days)


async def purge_old_alarm_records(retention_days: int = 90) -> int:
    """分批删除超过保留期的告警记录，返回被删除行数。

    参数:
    - retention_days (int): 保留天数；``<= 0`` 视为无效配置，返回 0（不删除）。

    返回:
    - int: 实际删除的行数；失败仅告警并返回 0。
    """
    if retention_days is None or retention_days <= 0:
        return 0
    cutoff = _cutoff(retention_days)
    # 以 alarm_time 为主；历史行 alarm_time 可能为空，则回退 created_at
    condition = or_(
        AlarmRecordModel.alarm_time < cutoff,
        and_(
            AlarmRecordModel.alarm_time.is_(None),
            AlarmRecordModel.created_at < cutoff,
        ),
    )
    removed = 0
    try:
        from app.core.database import async_db_session

        while True:
            async with async_db_session.begin() as session:
                batch_ids = (
                    await session.execute(
                        select(AlarmRecordModel.id).where(condition).limit(_PURGE_BATCH_SIZE)
                    )
                ).scalars().all()
                if not batch_ids:
                    break
                result = await session.execute(
                    delete(AlarmRecordModel).where(AlarmRecordModel.id.in_(batch_ids))
                )
            rowcount = int(result.rowcount or 0)
            removed += rowcount
            if rowcount < _PURGE_BATCH_SIZE:
                break
        return removed
    except Exception as e:
        log.warning(f"[告警记录清理] 删除失败: {e}")
        return removed


async def _retention_loop(interval_sec: int = _PURGE_INTERVAL_SEC) -> None:
    """清理循环：启动即跑一次，之后每 ``interval_sec`` 秒一次；异常隔离。"""
    while True:
        try:
            removed = await purge_old_alarm_records(settings.ALARM_RECORD_RETENTION_DAYS)
            if removed:
                log.info(
                    f"[告警记录清理] 已清理 {removed} 条超过 "
                    f"{settings.ALARM_RECORD_RETENTION_DAYS} 天的告警"
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning(f"[告警记录清理] 循环异常: {e}")
        await asyncio.sleep(interval_sec)


def start_alarm_record_retention() -> asyncio.Task | None:
    """挂起 TTL 清理任务；``TESTING`` 下不启动（安全空操作）。"""
    global _retention_task
    if settings.TESTING:
        return None
    if _retention_task is not None and not _retention_task.done():
        return _retention_task
    _retention_task = asyncio.create_task(_retention_loop())
    log.info(
        f"[告警记录清理] 已启动，保留 {settings.ALARM_RECORD_RETENTION_DAYS} 天，"
        f"间隔 {_PURGE_INTERVAL_SEC}s"
    )
    return _retention_task


async def stop_alarm_record_retention() -> None:
    """取消并等待清理任务结束（随应用生命周期关闭）。"""
    global _retention_task
    if _retention_task is None:
        return
    task, _retention_task = _retention_task, None
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log.warning(f"[告警记录清理] 停止异常: {e}")
    log.info("[告警记录清理] 已停止")
