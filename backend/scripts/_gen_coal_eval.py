"""生成「燃煤业务语义执行层评测集」（dataset=coal_semantic_v1，数据源 ds:4）。

用法（backend 下）::

    python scripts/_gen_coal_eval.py [rounds]
"""
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

DS = "ds:4"
DATASET = "coal_semantic_v1"
AUTH = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))


async def main() -> None:
    from main import create_app

    create_app()
    from app.scripts.init_app import _ensure_missing_columns
    from app.plugin.module_ai.query import eval_generate as G

    await _ensure_missing_columns()
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    saved = rejected = 0
    print(f"===== 生成评测集 {DATASET}（{DS}，{rounds} 轮）=====")
    for i in range(rounds):
        try:
            out = await G.generate_round(
                DS, "medium", "对象聚合", 10, AUTH, dataset=DATASET)
        except Exception as e:  # noqa: BLE001
            print(f"  第{i + 1}轮异常：{type(e).__name__}: {str(e)[:120]}")
            continue
        print(f"  第{i + 1}轮：解析 {out.get('parsed')} / 收录 {out.get('saved')} / "
              f"拒绝 {out.get('rejected')}")
        saved += out.get("saved", 0)
        rejected += out.get("rejected", 0)
    print(f"合计：收录 {saved}，拒绝 {rejected}")


asyncio.run(main())
