"""给**已入库**的测试题回填「退化题」标记（金标结果为空/NULL/单值 0）。

用法（backend 下）::

    python scripts/flag_degenerate_cases.py [--datasource=ds:4]

退化题仍然保留（覆盖面），但精度统计不计入分母 —— 否则「任何 SQL 都能答对」把数字抬虚高。
"""
from __future__ import annotations

import argparse
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


async def main(datasource: str | None) -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query.eval_generate import _run_gold
    from app.plugin.module_ai.query.eval_metrics import is_degenerate_result
    from app.plugin.module_ai.query.eval_set import list_cases, upsert_case

    cases = await list_cases(datasource=datasource)
    print(f"待回填 {len(cases)} 题（datasource={datasource or '全部'}）")
    stat: dict[str, int] = {}
    changed = 0
    for c in cases:
        res = await _run_gold(c["gold_sql"], c["datasource"], None)
        if not res["ok"]:
            flag = "error"
        elif is_degenerate_result(res["rows"]):
            flag = "degenerate"
        else:
            flag = "real"
        stat[flag] = stat.get(flag, 0) + 1
        notes = "degenerate" if flag == "degenerate" else ""
        if notes != (c.get("notes") or ""):
            await upsert_case({
                "question": c["question"], "gold_sql": c["gold_sql"],
                "datasource": c["datasource"], "difficulty": c["difficulty"],
                "scenario": c["scenario"], "form": c["form"],
                "expected_metric": c.get("expected_metric") or "",
                "verified": True, "notes": notes,
            })
            changed += 1
    print(f"回填完成：有真实数据={stat.get('real', 0)} 退化={stat.get('degenerate', 0)} "
          f"金标报错={stat.get('error', 0)}；本次改动 {changed} 条")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasource", default=None)
    a = ap.parse_args()
    asyncio.run(main(a.datasource))
