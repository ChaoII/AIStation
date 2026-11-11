"""对比同一数据集的两次运行（默认取最近两条 holdout-v2），打印准确率变化与逐题翻转。

用法：uv run python scripts/compare_holdout.py [--dataset holdout-v2] [--base RUN] [--target RUN]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="holdout-v2")
    ap.add_argument("--base", default="")
    ap.add_argument("--target", default="")
    args = ap.parse_args()

    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query.eval_compare import compare_runs
    from app.plugin.module_ai.query.eval_set import load_results, load_run_meta

    base, target = args.base, args.target
    if not (base and target):
        async with async_db_session() as db:
            rows = (await db.execute(text(
                "SELECT run_id FROM ai_query_testrun "
                "WHERE filter->>'dataset'=:d AND status='done' AND is_deleted=false "
                "ORDER BY id DESC LIMIT 2"
            ), {"d": args.dataset})).fetchall()
        if len(rows) < 2:
            raise SystemExit("需要两次已完成的同数据集运行")
        target, base = rows[0][0], rows[1][0]

    bm, tm = await load_run_meta(base), await load_run_meta(target)
    out = compare_runs(await load_results(base), await load_results(target), bm, tm)
    print(f"[runs] base={base}  target={target}")
    print(f"[acc ] {out['base']['data_accuracy']:.4f} -> {out['target']['data_accuracy']:.4f} "
          f"(fixed={out['fixed']}, regressed={out['regressed']}, same={out['same']})")
    rb, rt = out["base"].get("rules") or {}, out["target"].get("rules") or {}
    print(f"[rules] hash {rb.get('hash')} -> {rt.get('hash')}  changed={out.get('rules_changed')}")
    for it in out["items"]:
        if it["status"] in ("fixed", "regressed"):
            print(f"  {it['status']:9s} {it['question'][:34]}")
            if it["status"] == "regressed":
                print("      got :", " ".join(str(it.get("target_sql") or "").split())[:160])
                print("      prev:", " ".join(str(it.get("base_sql") or "").split())[:160])


if __name__ == "__main__":
    asyncio.run(main())
