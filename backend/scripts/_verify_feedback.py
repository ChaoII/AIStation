"""验证人类反馈链路真的能落库（含 ds:4 的修正 SQL 与 few-shot 沉淀）。"""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

Q = "反馈链路验证题__请忽略"


async def main() -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.service import AiQueryService

    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))

    # 造一条 ds:4 消息（模拟一次失败的问答）
    msg = await AiQueryService._save_message(
        1, Q, path="slow", datasource="ds:4", sql="SELECT 1", rows=[], is_error=True,
    )
    print(f"造消息 id={msg.id}")

    # 用户点踩 + 给出正确 SQL（ds:4 的表）
    out = await AiQueryService.feedback(
        msg.id, "down", 'SELECT COUNT(*) FROM "FUEL_CMCS_ASSAY"', auth
    )
    print(f"feedback 返回: {out}")

    async with async_db_session() as db:
        r = (
            await db.execute(
                text(
                    "SELECT feedback, COALESCE(correct_sql,'') FROM ai_query_messages WHERE id=:i"
                ),
                {"i": msg.id},
            )
        ).fetchone()
        print(f"库里 feedback={r[0]!r} correct_sql={r[1]!r}")
        n = (
            await db.execute(
                text(
                    "SELECT COUNT(*) FROM ai_query_fewshot WHERE is_deleted=false AND question=:q"
                ),
                {"q": Q},
            )
        ).scalar()
        print(f"沉淀的 few-shot 条数: {n}")
        # 清理验证数据
        await db.execute(text("DELETE FROM ai_query_fewshot WHERE question=:q"), {"q": Q})
        await db.execute(text("DELETE FROM ai_query_messages WHERE id=:i"), {"i": msg.id})
    print("已清理验证数据")


asyncio.run(main())
