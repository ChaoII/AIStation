"""清掉引用**空表/范围外表**的评测题（金标必空或退化，没区分度）。

用法（backend 下）::

    python scripts/purge_empty_cases.py --datasource=ds:4 [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter

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
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.eval_metrics import gold_tables
    from app.plugin.module_ai.query.eval_set import list_cases
    from app.plugin.module_ai.query.service import list_ds_schema

    ds_id = int(datasource.split(":")[-1])
    in_scope = {
        str(r["table"]).upper()
        for r in await list_ds_schema(ds_id, included_only=True)
    }
    print(f"{datasource} 范围内表 {len(in_scope)} 张")

    cases = await list_cases(datasource=datasource)
    bad: list[tuple[int, str, list[str]]] = []
    for c in cases:
        used = {str(t).upper() for t in gold_tables(c["gold_sql"] or "")}
        out_of = sorted(t for t in used if t not in in_scope)
        if out_of:
            bad.append((c["id"], c["question"], out_of))
    print(f"共 {len(cases)} 题，引用**范围外/空表**的 {len(bad)} 题")
    print("  涉及的表分布:", Counter(t for _, _, ts in bad for t in ts).most_common(8))
    for i, q, ts in bad[:8]:
        print(f"  #{i} {q[:40]} → {ts[:2]}")

    if dry or not bad:
        print("\n[dry-run] 未改动" if dry else "无需改动")
        return
    async with async_db_session.begin() as db:
        for i, _q, _ts in bad:
            await db.execute(
                text(
                    "UPDATE ai_query_testcase SET enabled=false, "
                    "notes='empty_table', updated_time=now() WHERE id=:i"
                ),
                {"i": i},
            )
    print(f"\n已禁用 {len(bad)} 题（notes='empty_table'）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasource", default="ds:4")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.datasource, a.dry_run))
