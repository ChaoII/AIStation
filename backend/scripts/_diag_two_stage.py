"""验证 `two_stage_planning` 分支**确实被走到**：桩掉规划 LLM（不花它的钱），真跑一次 ask。

用法：``python scripts/_diag_two_stage.py``
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

KEY = "two_stage_planning"
QUESTION = "每个摄像头告警数最高的前 3 个是哪些"


async def _set(value: str) -> None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        r = await db.execute(
            text("SELECT id FROM ai_query_settings WHERE key=:k AND is_deleted=false"), {"k": KEY}
        )
        row = r.fetchone()
        if row:
            await db.execute(
                text("UPDATE ai_query_settings SET value=:v WHERE id=:i"), {"v": value, "i": row[0]}
            )
        else:
            await db.execute(
                text(
                    "INSERT INTO ai_query_settings(key,value,uuid,status,is_deleted,"
                    "created_time,updated_time) "
                    "VALUES(:k,:v,:u,'0',false,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                ),
                {"k": KEY, "v": value, "u": uuid.uuid4().hex},
            )


async def main() -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query import service as S
    from app.plugin.module_ai.query.service import AiQueryService

    original = (await AiQueryService._cfg()).get(KEY, "false")
    print(f"0) 原值 = {original}")

    calls: list[str] = []
    nl2sql_calls: list[int] = []

    async def _fake_plan(prompt: str, runtime, temperature):
        """桩：不花 LLM 钱，但证明分支被走到。"""
        calls.append("plan")
        return '{"tables":["video_cameras"],"group_by":["name"],"order_limit":"按告警数倒序取前 3"}'

    _orig_nl2sql = AiQueryService._nl2sql.__func__

    async def _spy_nl2sql(cls, *a, **kw):  # type: ignore[no-untyped-def]
        nl2sql_calls.append(1)
        return await _orig_nl2sql(cls, *a, **kw)

    AiQueryService._nl2sql = classmethod(_spy_nl2sql)  # type: ignore[assignment]
    AiQueryService._plan_llm = staticmethod(_fake_plan)  # type: ignore[assignment]
    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
    try:
        await _set("true")
        S._SETTINGS_CACHE = None
        cfg = await AiQueryService._cfg()
        print(f"1) 置 {KEY}=true；cfg 读到 = {cfg.get(KEY)!r}")
        print(f"   问前 SQL 缓存 = {S._sql_cache_get(QUESTION, 'system')!r}")
        d = await AiQueryService.ask(QUESTION, auth, None, "system", force_slow=True)
        print(f"2) _nl2sql 调用次数 = {len(nl2sql_calls)}；规划阶段被调用 = {bool(calls)}")
        print(f"   cached={d.get('cached')} path={d.get('path')} rows={len(d.get('rows') or [])}")
        print(f"   SQL = {(d.get('sql') or '')[:150]}")
        assert calls, "开关为 true 且是多步题，规划阶段却没被调用 → 接线断了"
        assert not d.get("is_error"), d.get("summary")
        print("\n=== two_stage_planning 真接线：通过 ===")
    finally:
        await _set(original)
        S._SETTINGS_CACHE = None
        print(f"4) 已还原 {KEY}={original}")


asyncio.run(main())
