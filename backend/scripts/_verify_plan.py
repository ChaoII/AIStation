"""验证两段式分解：多步题应先生成计划，且 SQL 仍能产出。"""

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

QS = [
    ("每个设备下上限值最高的两个测点是什么？", True),
    ("今天一共产生了多少条告警？", False),
]


async def main() -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query.plan import is_multistep
    from app.plugin.module_ai.query.service import AiQueryService

    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
    for q, _ in QS:
        print("=" * 70)
        print(f"Q: {q}")
        print(f"  is_multistep={is_multistep(q)}")
        d = await AiQueryService.ask(q, auth, None, "ds:4", force_slow=True)
        print(f"  path={d.get('path')} is_error={d.get('is_error')} rows={len(d.get('rows') or [])}")
        print(f"  SQL: {str(d.get('sql'))[:180]}")


asyncio.run(main())
