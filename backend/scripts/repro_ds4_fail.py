"""复现 ds:4 失败题：抓真实报错（评测结果里没存 error 文案）。"""

from __future__ import annotations

import asyncio
import json
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

QUESTIONS = [
    "所有燃煤合同的合同数量合计是多少？",
    "燃煤采购结算主表中，所有记录的合同单价平均值是多少？",
    "燃煤采购结算的平均合同单价是多少？",
    "组态画面一共有多少个？",
]


async def main() -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query.service import AiQueryService

    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))

    for qtext in QUESTIONS:
        print("=" * 78)
        print(f"Q: {qtext}")
        try:
            rec = await AiQueryService._recall_grounding(qtext)
            tables = (rec or {}).get("tables") or []
            print(f"  _recall_grounding → tables={tables[:8]}")
        except Exception as e:  # noqa: BLE001
            print(f"  _recall_grounding 抛错: {type(e).__name__}: {str(e)[:200]}")
        try:
            d = await AiQueryService.ask(qtext, auth, None, "ds:4")
            print(f"  ask → is_error={d.get('is_error')} path={d.get('path')} "
                  f"took_ms={d.get('took_ms')} rows={len(d.get('rows') or [])}")
            print(f"  answer = {str(d.get('answer'))[:400]}")
            print(f"  sql = {str(d.get('sql'))[:300]}")
        except Exception as e:  # noqa: BLE001
            import traceback

            print(f"  ask 抛错: {type(e).__name__}: {str(e)[:300]}")
            tb = traceback.format_exc().splitlines()
            print("  --- traceback（前段=应用调用链）---")
            for ln in tb[:24]:
                s = ln.strip()
                if s.startswith("File") and "site-packages" not in s:
                    print("   ", s[:150])
                elif not s.startswith("File") and "sqlalchemy" not in s and len(s) < 120:
                    print("   ", s[:150])


asyncio.run(main())
