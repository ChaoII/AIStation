"""AI 办公室运行时活动表（插件自建表，不走 alembic）。

为什么单独建表：Team 协同过程中「谁被组长派了活」只有运行时知道，进程内字典在多 worker
下各自为政、重启即丢。这张表只存**短时状态**（带 expires_at），过期行由读写时顺手清理。

字段：
- ``agent_id``  智能体 id（主键，一个 agent 同时只有一条活动）
- ``status``    busy / wait
- ``task``      正在做的事（名牌上显示的一行）
- ``leader_id`` 由哪个组长派的（画弧线、追责都用它）
- ``expires_at`` 过期时间（本地时间，与项目其它表一致）
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import text as _t

from app.core.database import async_db_session

_ENSURED = False

_DDL = (
    "CREATE TABLE IF NOT EXISTS ai_office_activity ("
    "agent_id INTEGER PRIMARY KEY, "
    "status VARCHAR(16) NOT NULL DEFAULT 'busy', "
    "task VARCHAR(255), "
    "leader_id INTEGER, "
    "expires_at TIMESTAMP NOT NULL, "
    "updated_time TIMESTAMP)"
)


async def ensure_office_activity() -> None:
    """幂等建表（启动后首次访问时执行一次）。"""
    global _ENSURED
    if _ENSURED:
        return
    async with async_db_session.begin() as db:
        await db.execute(_t(_DDL))
    _ENSURED = True


async def mark(agent_id: int, task: str | None = None, leader_id: int | None = None,
               ttl_seconds: int = 180, status: str = "busy") -> None:
    """打点：把某个 agent 标记为「正在忙」，ttl 秒后自动过期。"""
    await ensure_office_activity()
    now = datetime.now()
    exp = now + timedelta(seconds=max(int(ttl_seconds or 60), 10))
    async with async_db_session.begin() as db:
        await db.execute(
            _t(
                "INSERT INTO ai_office_activity (agent_id, status, task, leader_id, expires_at, updated_time) "
                "VALUES (:a, :s, :t, :l, :e, :u) "
                "ON CONFLICT (agent_id) DO UPDATE SET status=:s, task=:t, leader_id=:l, "
                "expires_at=:e, updated_time=:u"
            ),
            {
                "a": int(agent_id),
                "s": status,
                "t": (task or "")[:250],
                "l": int(leader_id) if leader_id else None,
                "e": exp,
                "u": now,
            },
        )


async def active() -> dict[int, dict]:
    """取当前未过期的活动（顺手清掉过期行）。"""
    await ensure_office_activity()
    now = datetime.now()
    async with async_db_session.begin() as db:
        await db.execute(_t("DELETE FROM ai_office_activity WHERE expires_at <= :n"), {"n": now})
        rows = (
            await db.execute(
                _t("SELECT agent_id, status, task, leader_id FROM ai_office_activity")
            )
        ).fetchall()
    return {
        int(r[0]): {"status": r[1] or "busy", "task": r[2] or "", "leader_id": r[3]}
        for r in rows
    }


async def clear_all() -> None:
    await ensure_office_activity()
    async with async_db_session.begin() as db:
        await db.execute(_t("DELETE FROM ai_office_activity"))
