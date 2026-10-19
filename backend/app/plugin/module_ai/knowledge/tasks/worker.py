"""RAG 后台任务 worker：单并发拉取 → 执行 handler → 落状态。

与项目既有调度器同款模式（``while True + asyncio.sleep``），由 ``init_app``
的启动钩子挂载；``TESTING=1`` 时不启动，避免测试里出现后台竞争。
"""
from __future__ import annotations

import asyncio

from app.core.logger import log

from ..config import rag_config
from . import (
    TERMINAL_STATUSES,
    TaskCanceled,
    claim_next,
    get_task,
    reset_stale_running,
    update_task,
)
from .jobs import get_handler


async def run_worker(*, max_iterations: int | None = None) -> None:
    """执行任务循环。

    ``max_iterations``：最多尝试抢占多少次（None = 常驻）；为 None 时队列空则
    按 ``task_poll_seconds`` 休眠，测试传入有限次数以便同步驱动。
    """
    await reset_stale_running()
    attempts = 0
    while max_iterations is None or attempts < max_iterations:
        attempts += 1
        task = await claim_next()
        if task is None:
            if max_iterations is not None:
                return
            await asyncio.sleep(rag_config.task_poll_seconds)
            continue

        handler = get_handler(task["kind"])
        if handler is None:
            await update_task(
                task["id"], status="failed", error=f"未知任务类型：{task['kind']}"
            )
            continue
        if task.get("cancel_requested"):
            await update_task(task["id"], status="canceled")
            continue
        try:
            await handler(task)
        except TaskCanceled:
            await update_task(task["id"], status="canceled")
        except Exception as e:  # noqa: BLE001
            log.exception(f"[RAG] 任务 {task['id']}（{task['kind']}）失败：{e}")
            await update_task(task["id"], status="failed", error=str(e)[:2000])
        else:
            fresh = await get_task(task["id"])
            if fresh and fresh["status"] not in TERMINAL_STATUSES:
                if fresh.get("cancel_requested"):
                    await update_task(task["id"], status="canceled")
                else:
                    await update_task(task["id"], status="succeeded")
