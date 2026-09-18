"""过期软删数据集彻底清理：超过保留期后删除 DB 行与对象存储。

与 ``alarm/retention.py`` 同模式：启动即跑一次，之后按间隔循环；异常隔离；
``TESTING`` 下不启动后台任务。
"""
import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.config.setting import settings

log = logging.getLogger(__name__)

_retention_task: asyncio.Task | None = None


async def purge_expired_datasets(retention_days: int) -> int:
    """彻底删除软删时间早于保留期的数据集，返回删除数量。

    ``retention_days <= 0`` 视为无效配置，返回 0（不删除）。
    """
    if retention_days is None or retention_days <= 0:
        return 0
    from app.api.v1.module_annotation.dataset.model import DatasetModel
    from app.api.v1.module_annotation.dataset.service import DatasetService
    from app.core.database import async_db_session

    cutoff = datetime.now() - timedelta(days=retention_days)
    try:
        async with async_db_session() as db:
            ids = (
                await db.execute(
                    select(DatasetModel.id).where(
                        DatasetModel.is_deleted == True,  # noqa: E712
                        DatasetModel.deleted_time.isnot(None),
                        DatasetModel.deleted_time < cutoff,
                    )
                )
            ).scalars().all()
        if not ids:
            return 0
        result = await DatasetService.purge_datasets(list(ids))
        return int(result.get("purged", 0))
    except Exception as e:
        log.warning(f"[标注数据集清理] 删除失败: {e}")
        return 0


async def _retention_loop(interval_sec: int) -> None:
    while True:
        try:
            removed = await purge_expired_datasets(settings.ANNOTATION_PURGE_RETENTION_DAYS)
            if removed:
                log.info(
                    f"[标注数据集清理] 已彻底删除 {removed} 个超过 "
                    f"{settings.ANNOTATION_PURGE_RETENTION_DAYS} 天的数据集"
                )
        except asyncio.CancelledError:
            raise
        except Exception as e:  # pragma: no cover - 防御
            log.warning(f"[标注数据集清理] 循环异常: {e}")
        await asyncio.sleep(interval_sec)


def start_annotation_purge_retention() -> asyncio.Task | None:
    """挂起清理任务；``TESTING`` 下不启动。"""
    global _retention_task
    if settings.TESTING:
        return None
    if _retention_task is not None and not _retention_task.done():
        return _retention_task
    _retention_task = asyncio.create_task(
        _retention_loop(settings.ANNOTATION_PURGE_INTERVAL_SEC)
    )
    log.info(
        f"[标注数据集清理] 已启动，保留 {settings.ANNOTATION_PURGE_RETENTION_DAYS} 天，"
        f"间隔 {settings.ANNOTATION_PURGE_INTERVAL_SEC}s"
    )
    return _retention_task
