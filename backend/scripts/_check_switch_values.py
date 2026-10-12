"""核实：修复 `_cfg_bool` 后，是否有 default=False 的开关被**意外打开**（行为变化审计）。

用法：``python scripts/_check_switch_values.py``
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

#: 以 default=False 读取的开关（修复后它们**可能真的被打开**，必须核对库里是不是 false）
DEFAULT_FALSE_KEYS = ("two_stage_planning", "agno_tool_agent")


async def main() -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.service import AiQueryService

    cfg = await AiQueryService._cfg()
    async with async_db_session() as db:
        rows = (
            await db.execute(
                text("SELECT key,value FROM ai_query_settings WHERE is_deleted=false")
            )
        ).fetchall()
    db_vals = {r[0]: r[1] for r in rows}
    print("库里显式配置的开关：")
    for k in DEFAULT_FALSE_KEYS:
        print(f"  {k:24s} db={db_vals.get(k)!r:10s} 生效={AiQueryService._cfg_bool(cfg, k, False)}")
    on = [k for k in DEFAULT_FALSE_KEYS if AiQueryService._cfg_bool(cfg, k, False)]
    if on:
        print(f"\n⚠️ 修复后这些 default=False 开关**变为开启**（行为会变）：{on}")
        print("   → 必须确认是否有意为之；无意请把库里值改成 false")
    else:
        print("\n✓ 无意外开启：两个开关在库里都是 false，修复不改变当前默认行为")


asyncio.run(main())
