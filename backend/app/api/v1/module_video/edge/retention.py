"""边缘事件 TTL 清理：删除超过保留期的历史事件，避免表无限膨胀。

- ``purge_old_events``：按 ``created_time < now - retention_days`` 物理删除，返回删除行数；
- ``start_edge_event_retention``：启动即清一次，之后每 3600s 一轮的后台 asyncio 任务；
- 任何异常仅告警，绝不向上抛（不得影响应用启动/运行）；
- ``TESTING`` 下不启动后台任务（避免污染测试库、悬挂协程）。
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete

from app.api.v1.module_video.edge.model import EdgeEventModel
from app.config.setting import settings

log = logging.getLogger(__name__)

# 清理轮询间隔（秒）
_PURGE_INTERVAL_SEC = 3600

_retention_task: asyncio.Task | None = None


async def purge_old_events(retention_days: int = 30) -> int:
    """删除 ``created_time`` 早于保留期的事件，返回被删除的行数。

    参数:
    - retention_days (int): 保留天数；``<= 0`` 视为无效配置，直接返回 0（不删除）。

    返回:
    - int: 实际删除的行数；失败仅告警并返回 0。
    """
    if retention_days is None or retention_days <= 0:
        return 0
    cutoff = datetime.now() - timedelta(days=retention_days)
    try:
        # 延迟导入：便于测试 monkeypatch app.core.database.async_db_session
        from app.core.database import async_db_session

        stmt = delete(EdgeEventModel).where(EdgeEventModel.created_time < cutoff)
        async with async_db_session.begin() as session:
            result = await session.execute(stmt)
        return int(result.rowcount or 0)
    except Exception as e:
        log.warning(f"[边缘事件清理] 删除失败: {e}")
        return 0


async def _retention_loop(interval_sec: int = _PURGE_INTERVAL_SEC) -> None:
    """清理循环：启动即跑一次，之后每 ``interval_sec`` 秒一次；异常隔离。"""
    while True:
        try:
            removed = await purge_old_events(settings.EDGE_EVENT_RETENTION_DAYS)
            if removed:
                log.info(
                    f"[边缘事件清理] 已清理 {removed} 条超过 "
                    f"{settings.EDGE_EVENT_RETENTION_DAYS} 天的事件"
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # 兜底：任何异常都不得终止循环/影响应用
            log.warning(f"[边缘事件清理] 循环异常: {e}")
        await asyncio.sleep(interval_sec)


def start_edge_event_retention() -> asyncio.Task | None:
    """挂起 TTL 清理任务；``TESTING`` 下不启动（安全空操作）。

    返回:
    - asyncio.Task | None: 已启动的任务；测试模式或已启动时返回当前任务/None。
    """
    global _retention_task
    if settings.TESTING:
        return None
    if _retention_task is not None and not _retention_task.done():
        return _retention_task
    _retention_task = asyncio.create_task(_retention_loop())
    log.info(
        f"[边缘事件清理] 已启动，保留 {settings.EDGE_EVENT_RETENTION_DAYS} 天，"
        f"间隔 {_PURGE_INTERVAL_SEC}s"
    )
    return _retention_task


async def stop_edge_event_retention() -> None:
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
        log.warning(f"[边缘事件清理] 停止异常: {e}")
    log.info("[边缘事件清理] 已停止")
