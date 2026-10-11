"""用**已执行验证过的指标**生成评测题（保证非退化：金标必有非空结果）。

背景：ds:4 原 50 题里 92% 建在空表上（退化题，任何 SQL 都算对）。
指标模板本身已经在目标库执行验证过（结果非 NULL），
所以「指标名 → 问句」是**最可靠的非退化题来源**。

用法（backend 下）::

    python scripts/seed_eval_from_metrics.py --datasource=ds:4 --dry-run
    python scripts/seed_eval_from_metrics.py --datasource=ds:4
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


async def main(datasource: str, dry: bool) -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query.eval_generate import _run_gold
    from app.plugin.module_ai.query.eval_metrics import is_degenerate_result
    from app.plugin.module_ai.query.eval_set import list_cases, upsert_case
    from app.plugin.module_ai.query.service import AiQueryService

    metrics = await AiQueryService.list_metrics(datasource)
    existing = {c["question"] for c in await list_cases(datasource=datasource)}
    print(f"{datasource}: 指标 {len(metrics)} 个，现有题 {len(existing)} 道")

    saved = skipped = dup = degen = 0
    for m in metrics:
        if not m.get("enabled"):
            continue
        q = f"{m['name']}是多少？"
        if q in existing:
            dup += 1
            continue
        res = await _run_gold(m["sql_template"], datasource, None)
        if not res["ok"] or not res["rows"]:
            skipped += 1
            continue
        if is_degenerate_result(res["rows"]):
            degen += 1
            continue
        if dry:
            print(f"  + {q}  ← {m['key']}")
            saved += 1
            continue
        await upsert_case({
            "question": q, "gold_sql": m["sql_template"], "datasource": datasource,
            "difficulty": "简单", "scenario": f"{datasource} 业务量",
            "form": "快路径指标", "expected_metric": m["key"],
            "verified": True, "notes": "",
        })
        existing.add(q)
        saved += 1

    print(f"\n{'[dry-run] 将' if dry else '已'}新增 {saved} 道题"
          f"（已存在跳过 {dup}，指标不可执行跳过 {skipped}，结果退化跳过 {degen}）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasource", default="ds:4")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.datasource, a.dry_run))
