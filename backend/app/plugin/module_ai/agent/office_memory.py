"""办公室的对话记忆（插件自建表，不走 alembic）。

为什么不用 agno 自己的 Team 会话表：实测在真实 run 里 TeamSession 没有落盘
（`asave_session` 没被触发），而 «追问要能接上» 是硬需求。这里用一张极简表
只存「问 / 答」最近几轮，派活时拼进组长指令——不依赖框架内部实现，行为确定、
可测。

写入用 ``async_db_session.begin()``（``async_db_session()`` 只给会话不提交）。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text as _t

from app.core.database import async_db_session

_ENSURED = False

_DDL = (
    "CREATE TABLE IF NOT EXISTS ai_office_memory ("
    "id VARCHAR(40) PRIMARY KEY, "
    "user_id INTEGER, "
    "question TEXT, "
    "answer TEXT, "
    "created_time TIMESTAMP)"
)


async def ensure_memory() -> None:
    global _ENSURED
    if _ENSURED:
        return
    async with async_db_session.begin() as db:
        await db.execute(_t(_DDL))
    _ENSURED = True


async def add(user_id: int | None, question: str, answer: str) -> None:
    """记一轮问答；失败只告警，不影响派活。"""
    try:
        await ensure_memory()
        async with async_db_session.begin() as db:
            await db.execute(
                _t(
                    "INSERT INTO ai_office_memory (id, user_id, question, answer, created_time) "
                    "VALUES (:i, :u, :q, :a, :c)"
                ),
                {
                    "i": uuid.uuid4().hex,
                    "u": int(user_id or 0),
                    "q": (question or "")[:2000],
                    "a": (answer or "")[:4000],
                    "c": datetime.now(),
                },
            )
    except Exception as e:  # noqa: BLE001
        from app.core.logger import logger

        logger.warning(f"[office_memory] 写入失败: {str(e)[:120]}")


async def recent(user_id: int | None, limit: int = 3) -> list[dict]:
    """最近几轮问答（新的在后）。"""
    try:
        await ensure_memory()
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    _t(
                        "SELECT question, answer FROM ai_office_memory "
                        "WHERE user_id = :u ORDER BY created_time DESC LIMIT :l"
                    ),
                    {"u": int(user_id or 0), "l": max(1, min(int(limit or 3), 10))},
                )
            ).fetchall()
    except Exception:  # noqa: BLE001
        return []
    return [{"question": r[0] or "", "answer": r[1] or ""} for r in reversed(rows)]


async def clear(user_id: int | None) -> None:
    await ensure_memory()
    async with async_db_session.begin() as db:
        await db.execute(
            _t("DELETE FROM ai_office_memory WHERE user_id = :u"), {"u": int(user_id or 0)}
        )


def as_prompt(history: list[dict], max_chars: int = 1200) -> str:
    """把历史压成一段给组长的指令文本（只取摘要，避免把上下文撑爆）。"""
    if not history:
        return ""
    lines = ["## 这个办公室最近几轮（用于理解追问，不要复述）"]
    for h in history:
        q = " ".join((h.get("question") or "").split())[:120]
        a = " ".join((h.get("answer") or "").split())[:260]
        lines.append(f"- 用户：{q}")
        lines.append(f"  结论：{a}")
    out = "\n".join(lines)
    return out[:max_chars]
