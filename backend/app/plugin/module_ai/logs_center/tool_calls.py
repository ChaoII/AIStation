"""工具调用记录表（插件自建，不走 alembic）。

为什么单独建表：``ai_call_logs`` 只记"一次模型调用"，看不到**具体调了哪个工具、
参数是什么、花了多久**。这张表按"一次工具执行一行"记录，用来在办公室大屏上画
真正的执行时间线。

字段：
- ``agent_id`` / ``agent_name``  谁调的
- ``tool_name``                 工具名（如 kb_search / delegate_task_to_member）
- ``args``                      参数摘要（截断 300 字）
- ``duration_ms``               耗时
- ``ok``                        成功/失败
- ``created_time``              本地时间
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import text as _t

from app.core.database import async_db_session

_ENSURED = False

_DDL = (
    "CREATE TABLE IF NOT EXISTS ai_tool_calls ("
    "id VARCHAR(40) PRIMARY KEY, "
    "agent_id INTEGER, "
    "agent_name VARCHAR(128), "
    "tool_name VARCHAR(128), "
    "args TEXT, "
    "duration_ms INTEGER, "
    "ok BOOLEAN, "
    "created_time TIMESTAMP)"
)


async def ensure_tool_calls() -> None:
    global _ENSURED
    if _ENSURED:
        return
    async with async_db_session.begin() as db:
        await db.execute(_t(_DDL))
    _ENSURED = True


async def record(
    agent_id: int | None,
    agent_name: str | None,
    tool_name: str | None,
    args=None,
    duration_ms: int | None = None,
    ok: bool = True,
) -> None:
    """记一次工具执行；失败只告警，绝不打断主流程。"""
    try:
        await ensure_tool_calls()
        payload = ""
        if args:
            try:
                payload = json.dumps(args, ensure_ascii=False, default=str)[:300]
            except Exception:  # noqa: BLE001
                payload = str(args)[:300]
        async with async_db_session.begin() as db:
            await db.execute(
                _t(
                    "INSERT INTO ai_tool_calls "
                    "(id, agent_id, agent_name, tool_name, args, duration_ms, ok, created_time) "
                    "VALUES (:i, :a, :n, :t, :g, :d, :o, :c)"
                ),
                {
                    "i": uuid.uuid4().hex,
                    "a": int(agent_id) if agent_id else None,
                    "n": (agent_name or "")[:120],
                    "t": (tool_name or "")[:120],
                    "g": payload,
                    "d": int(duration_ms or 0),
                    "o": bool(ok),
                    "c": datetime.now(),
                },
            )
    except Exception as e:  # noqa: BLE001
        from app.core.logger import logger

        logger.warning(f"[tool_calls] 写入失败: {str(e)[:120]}")


async def list_calls(agent_id: int | None = None, limit: int = 20) -> list[dict]:
    """按 agent 取最近的工具执行记录（新的在前）。"""
    await ensure_tool_calls()
    sql = "SELECT agent_id, agent_name, tool_name, args, duration_ms, ok, created_time FROM ai_tool_calls"
    params: dict = {}
    if agent_id:
        sql += " WHERE agent_id = :a"
        params["a"] = int(agent_id)
    sql += " ORDER BY created_time DESC LIMIT :l"
    params["l"] = max(1, min(int(limit or 20), 100))
    async with async_db_session() as db:
        rows = (await db.execute(_t(sql), params)).fetchall()
    return [
        {
            "agent_id": r[0],
            "agent_name": r[1],
            "tool": r[2],
            "args": r[3],
            "duration_ms": r[4],
            "ok": bool(r[5]),
            "time": r[6].strftime("%H:%M:%S") if r[6] else "",
        }
        for r in rows
    ]
