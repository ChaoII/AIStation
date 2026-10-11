"""给测试题打**留出法分集**标记（A/B）：近义题同集，供"只在 A 沉淀、只在 B 评测"。

用法（backend 下）::

    python scripts/split_eval_set.py [--datasource=ds:4] [--dry-run]
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


async def main(datasource: str | None, dry: bool) -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.eval_set import list_cases
    from app.plugin.module_ai.query.eval_split import assign_splits

    cases = await list_cases(datasource=datasource)
    print(f"待分集 {len(cases)} 题（datasource={datasource or '全部'}）")
    got = assign_splits([c["question"] for c in cases])
    dist = Counter(got.values())
    print(f"分集结果：A={dist.get('A', 0)}  B={dist.get('B', 0)}")
    # 形式分布对账（两半要尽量均衡）
    by = {"A": Counter(), "B": Counter()}
    for c in cases:
        by[got[c["question"]]][c.get("form") or "?"] += 1
    for tag in ("A", "B"):
        print(f"  {tag} 形式: " + ", ".join(f"{k}={v}" for k, v in by[tag].most_common(8)))

    if dry:
        print("\n[dry-run] 未写入")
        return
    async with async_db_session.begin() as db:
        for c in cases:
            notes = str(c.get("notes") or "")
            base = ",".join(x for x in notes.split(",") if x and not x.startswith("split:"))
            new = ",".join(x for x in (base, f"split:{got[c['question']]}") if x)
            await db.execute(
                text("UPDATE ai_query_testcase SET notes=:n, updated_time=now() WHERE id=:i"),
                {"n": new, "i": c["id"]},
            )
    print(f"\n已写入分集标记（{len(cases)} 题）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasource", default=None)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    asyncio.run(main(a.datasource, a.dry_run))
