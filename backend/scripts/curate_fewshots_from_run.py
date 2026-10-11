"""反馈闭环：把某轮评测的**错题**沉淀成 few-shot（模型从错题里学）。

用法（backend 下）::

    python scripts/curate_fewshots_from_run.py --datasource=ds:4 [--run-id=ev_xxx] [--dry-run]

不传 ``--run-id`` 时自动取该数据源**最近一轮**评测。
沉淀的示例带 ``auto-curated:from-run`` 标记，可一键回滚：
``UPDATE ai_query_fewshot SET is_deleted=true WHERE description='auto-curated:from-run'``
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


async def main(datasource: str, run_id: str | None, dry: bool) -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.eval_curate import curate_from_run

    if not run_id:
        async with async_db_session() as db:
            run_id = (
                await db.execute(
                    text(
                        "SELECT run_id FROM ai_query_testresult WHERE is_deleted=false "
                        "AND trace->>'datasource'=:d GROUP BY run_id ORDER BY MAX(id) DESC LIMIT 1"
                    ),
                    {"d": datasource},
                )
            ).scalar()
    if not run_id:
        print(f"{datasource} 没有评测记录，先跑一轮")
        return
    print(f"用 run={run_id}（datasource={datasource}）")
    if dry:
        from app.plugin.module_ai.query.eval_curate import (
            _list_cases, _list_fewshots, _load_results, select_fewshot_candidates,
        )

        results = await _load_results(run_id)
        gold = {c["question"]: c["gold_sql"] for c in await _list_cases(datasource=datasource)}
        skip = {f["question"] for f in await _list_fewshots(datasource)}
        cands = select_fewshot_candidates(results, gold, skip)
        print(f"[dry-run] 候选错题 {len(cands)} 条：")
        for c in cands[:10]:
            print(f"  - {c['question'][:48]}")
        return

    out = await curate_from_run(run_id, datasource)
    print(f"候选 {out['candidates']}，入库 {out['added']}，跳过（金标不可用/退化）{out['skipped']}")


async def _rollback() -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        r = await db.execute(
            text(
                "UPDATE ai_query_fewshot SET is_deleted=true WHERE is_deleted=false "
                "AND description='auto-curated:from-run'"
            )
        )
    print(f"已回滚 auto-curated 沉淀 {getattr(r, 'rowcount', '?')} 条")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--datasource", default="ds:4")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rollback", action="store_true",
                    help="回滚所有 auto-curated 沉淀（做留出法对照前先清干净）")
    a = ap.parse_args()
    if a.rollback:
        asyncio.run(_rollback())
    else:
        asyncio.run(main(a.datasource, a.run_id, a.dry_run))
