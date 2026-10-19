"""RAG 后台任务：任务表读写（创建 / 抢占 / 进度 / 取消 / 查询）。

设计要点：
- 单 worker 单并发（``RAG_TASK_CONCURRENCY=1``），抢占用
  ``FOR UPDATE SKIP LOCKED``（PG）保证多实例下也不会重复消费；
- 取消是协作式的：``cancel_requested`` 置位后由 handler 在检查点退出；
- 进程重启后的 ``running`` 僵尸任务由 :func:`reset_stale_running` 重置。

说明：该领域的状态机是扁平三态（pending/running/终态），取消只是一个
布尔请求标记，因此用普通函数 + 显式条件更新即可，无需引入状态机库。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.core.database import async_db_session
from app.core.logger import log

from ..model import AiRagTaskModel

#: 终态集合
TERMINAL_STATUSES = ("succeeded", "failed", "canceled")


def _to_dict(task: AiRagTaskModel) -> dict:
    return {
        "id": task.id,
        "kind": task.kind,
        "status": task.status,
        "kb_id": task.kb_id,
        "document_id": task.document_id,
        "payload": task.payload or {},
        "progress": int(task.progress or 0),
        "step": task.step,
        "message": task.message,
        "error": task.error,
        "cancel_requested": bool(task.cancel_requested),
        "created_time": task.created_time,
        "started_time": task.started_time,
        "finished_time": task.finished_time,
    }


async def create_task(
    kind: str,
    *,
    kb_id: int | None = None,
    document_id: int | None = None,
    payload: dict | None = None,
    auth=None,
) -> dict:
    """新建任务（``pending``）。"""
    async with async_db_session.begin() as db:
        task = AiRagTaskModel(
            kind=kind,
            status="pending",
            kb_id=kb_id,
            document_id=document_id,
            payload=payload or {},
            progress=0,
        )
        if auth is not None:
            task.created_id = getattr(getattr(auth, "user", None), "id", None)
        db.add(task)
        await db.flush()
        await db.refresh(task)
        return _to_dict(task)


async def get_task(task_id: int) -> dict | None:
    async with async_db_session() as db:
        task = await db.get(AiRagTaskModel, task_id)
        if not task or task.is_deleted:
            return None
        return _to_dict(task)


async def list_tasks(
    *,
    kb_id: int | None = None,
    status: str | None = None,
    page_no: int = 1,
    page_size: int = 20,
) -> dict:
    """分页查询任务（按 id 倒序，最新在前）。"""
    page_no = max(1, int(page_no))
    page_size = max(1, min(200, int(page_size)))
    conds = [AiRagTaskModel.is_deleted.is_(False)]
    if kb_id is not None:
        conds.append(AiRagTaskModel.kb_id == kb_id)
    if status:
        conds.append(AiRagTaskModel.status == status)
    async with async_db_session() as db:
        total = (
            await db.execute(select(func.count()).select_from(AiRagTaskModel).where(*conds))
        ).scalar() or 0
        rows = (
            (
                await db.execute(
                    select(AiRagTaskModel)
                    .where(*conds)
                    .order_by(AiRagTaskModel.id.desc())
                    .offset((page_no - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )
    items = [_to_dict(r) for r in rows]
    return {
        "page_no": page_no,
        "page_size": page_size,
        "total": int(total),
        "has_next": page_no * page_size < int(total),
        "items": items,
    }


async def cancel_task(task_id: int) -> dict:
    """请求取消：``pending`` 直接置 ``canceled``，``running`` 置标记等 handler 退出。"""
    async with async_db_session.begin() as db:
        task = await db.get(AiRagTaskModel, task_id)
        if not task or task.is_deleted:
            raise ValueError("任务不存在")
        if task.status in TERMINAL_STATUSES:
            return _to_dict(task)
        task.cancel_requested = True
        if task.status == "pending":
            task.status = "canceled"
            task.finished_time = datetime.now()
        await db.flush()
        await db.refresh(task)
        return _to_dict(task)


async def claim_next() -> dict | None:
    """抢占一个待执行任务（PG 用 SKIP LOCKED，SQLite 退化为普通查询）。"""
    async with async_db_session.begin() as db:
        stmt = (
            select(AiRagTaskModel)
            .where(
                AiRagTaskModel.status == "pending",
                AiRagTaskModel.is_deleted.is_(False),
            )
            .order_by(AiRagTaskModel.id.asc())
            .limit(1)
        )
        try:
            stmt = stmt.with_for_update(skip_locked=True)
        except Exception:  # noqa: BLE001  个别方言不支持
            pass
        task = (await db.execute(stmt)).scalar_one_or_none()
        if task is None:
            return None
        task.status = "running"
        task.started_time = datetime.now()
        task.progress = 0
        await db.flush()
        await db.refresh(task)
        return _to_dict(task)


async def update_task(
    task_id: int,
    *,
    progress: int | None = None,
    step: str | None = None,
    status: str | None = None,
    message: str | None = None,
    error: str | None = None,
) -> None:
    """更新任务进度/状态（``progress`` 夹到 0-100）。"""
    async with async_db_session.begin() as db:
        task = await db.get(AiRagTaskModel, task_id)
        if task is None:
            return
        if progress is not None:
            task.progress = max(0, min(100, int(progress)))
        if step is not None:
            task.step = step
        if message is not None:
            task.message = message
        if error is not None:
            task.error = error
        if status is not None:
            task.status = status
            if status in TERMINAL_STATUSES:
                task.finished_time = datetime.now()
                if status == "succeeded":
                    task.progress = 100
        await db.flush()


async def reset_stale_running() -> int:
    """把 ``running`` 僵尸任务重置为 ``pending``（进程重启后调用）。"""
    async with async_db_session.begin() as db:
        rows = (
            (
                await db.execute(
                    select(AiRagTaskModel).where(
                        AiRagTaskModel.status == "running",
                        AiRagTaskModel.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        for task in rows:
            task.status = "pending"
            task.started_time = None
            task.progress = 0
            task.step = None
        await db.flush()
    if rows:
        log.warning(f"[RAG] 重置 {len(rows)} 个僵尸 running 任务为 pending")
    return len(rows)
