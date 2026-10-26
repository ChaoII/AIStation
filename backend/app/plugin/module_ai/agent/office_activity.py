"""AI 办公室运行时活动表（插件自建表，不走 alembic）。

为什么单独建表：Team 协同过程中「谁被组长派了活」只有运行时知道，进程内字典在多 worker
下各自为政、重启即丢。这张表只存**短时状态**（带 expires_at），过期行由读写时顺手清理。

**为什么不用 `async_db_session`**：它是请求作用域会话的包装器，`begin()` 实际是
SAVEPOINT，写进去的行要等**请求结束**才提交——别的请求（比如前端每 20 秒拉一次名单）
在运行期间根本看不到「谁在忙」，状态就永远是待命（实测踩过）。这里必须用**独立会话**、
写一次提交一次，状态才能实时可见。

字段：
- ``agent_id``  智能体 id（主键，一个 agent 同时只有一条活动）
- ``status``    busy / wait / error
- ``task``      正在做的事（名牌上显示的一行）
- ``leader_id`` 由哪个组长派的（画弧线、追责都用它）
- ``expires_at`` 过期时间（本地时间，与项目其它表一致）
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import text as _t

from app.core.database import _async_session_factory

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
    async with _async_session_factory() as db:
        await db.execute(_t(_DDL))
        await db.commit()
    _ENSURED = True


async def mark(agent_id: int, task: str | None = None, leader_id: int | None = None,
               ttl_seconds: int = 180, status: str = "busy") -> None:
    """打点：把某个 agent 标记为「正在忙」，ttl 秒后自动过期。

    独立会话 + 立即提交：运行期间前端拉名单就能看到 busy（请求作用域会话要等请求结束才提交）。
    """
    await ensure_office_activity()
    now = datetime.now()
    exp = now + timedelta(seconds=max(int(ttl_seconds or 60), 10))
    async with _async_session_factory() as db:
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
        await db.commit()


async def active() -> dict[int, dict]:
    """取当前未过期的活动（顺手清掉过期行）。"""
    await ensure_office_activity()
    now = datetime.now()
    async with _async_session_factory() as db:
        await db.execute(_t("DELETE FROM ai_office_activity WHERE expires_at <= :n"), {"n": now})
        rows = (
            await db.execute(
                _t("SELECT agent_id, status, task, leader_id FROM ai_office_activity")
            )
        ).fetchall()
        await db.commit()
    return {
        int(r[0]): {"status": r[1] or "busy", "task": r[2] or "", "leader_id": r[3]}
        for r in rows
    }


async def clear(agent_ids) -> None:
    """把这些人标记为「已收工」（写一条 idle 行，150 秒后过期），而不是直接删。

    为什么不直接删：``office_view`` 还有一条兜底——「近 2 分钟有调用日志就算忙」
    （办公室之外的聊天/工作台也认）。刚跑完的人日志还很新，把活动行删掉就会立刻
    被这条兜底判成「工作中」，跑完还挂着「工作中」（用户实测最刺眼的一条）。
    留一条 idle 行把这个兜底压住，状态就干净地回到待命。
    """
    ids = [int(i) for i in (agent_ids or []) if i]
    if not ids:
        return
    await ensure_office_activity()
    now = datetime.now()
    exp = now + timedelta(seconds=150)
    async with _async_session_factory() as db:
        for i in ids:
            await db.execute(
                _t(
                    "INSERT INTO ai_office_activity (agent_id, status, task, leader_id, expires_at, updated_time) "
                    "VALUES (:a, 'idle', '', NULL, :e, :u) "
                    "ON CONFLICT (agent_id) DO UPDATE SET status='idle', task='', "
                    "expires_at=:e, updated_time=:u"
                ),
                {"a": i, "e": exp, "u": now},
            )
        await db.commit()


async def clear_all() -> None:
    await ensure_office_activity()
    async with _async_session_factory() as db:
        await db.execute(_t("DELETE FROM ai_office_activity"))
        await db.commit()
