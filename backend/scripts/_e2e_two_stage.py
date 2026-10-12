"""验证 `two_stage_planning`（真分解）**确实接线**：开开关 → 多步题 → 计划阶段真跑 → 还原。

用法：``python scripts/_e2e_two_stage.py``
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
    from app.plugin.module_ai.query import service as _svc
    from app.plugin.module_ai.query.service import AiQueryService

    original = (await AiQueryService._cfg()).get(KEY, "false")
    print(f"0) 原值 = {original}")
    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
    try:
        await _set("true")
        _svc._SETTINGS_CACHE = None  # ⚠️ 缓存是**模块级全局**（不是类属性），必须这样失效
        print(f"1) 已置 {KEY}=true；提问：{QUESTION}")
        d = await AiQueryService.ask(QUESTION, auth, None, "system", force_slow=True)
        print(f"2) path={d.get('path')} is_error={d.get('is_error')} rows={len(d.get('rows') or [])}")
        print(f"   SQL = {(d.get('sql') or '')[:140]}")
        assert not d.get("is_error"), d.get("summary")
        assert d.get("rows"), "无结果"
        print("3) 结果非空 ✓（计划阶段的日志见上方『两段式』行）")
    finally:
        await _set(original)
        _svc._SETTINGS_CACHE = None
        print(f"4) 已还原 {KEY}={original}")


asyncio.run(main())
