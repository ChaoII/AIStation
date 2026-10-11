"""跑一轮评测 + 一次消融，打印总览/分维度/逐题 trace/消融对照（进程内，不需 HTTP 后端）。

用法（backend 下）::

    python scripts/run_eval_once.py --run-limit=40 --ablation-limit=20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


async def _wait_run(run_id: str):
    from app.plugin.module_ai.query import eval_runner as R

    while True:
        st = R.get_status(run_id)
        if st and st["status"] in ("done", "error"):
            return st
        await asyncio.sleep(2)


async def main(run_limit: int, abl_limit: int, skip_run: bool = False,
               force_slow: bool = False, datasource: str = "") -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query import eval_runner as R
    from app.plugin.module_ai.query.eval_metrics import group_by
    from app.plugin.module_ai.query.eval_set import load_results, list_cases
    from app.plugin.module_ai.query.service import AiQueryService

    total = len(await list_cases())
    print(f"测试集 {total} 题；本轮全量取前 {run_limit or total} 题")
    auth = R._auth()

    if not skip_run:
        flt = {"limit": run_limit} if run_limit else {}
        if force_slow:
            flt["force_slow"] = True
        if datasource:
            flt["datasource"] = datasource
        rid = R.start_run(auth, filter=flt or None)
        st = await _wait_run(rid)
        print("\n=== 全量运行 summary ===")
        print(json.dumps(st.get("summary") or {}, ensure_ascii=False))
        rows = await load_results(rid)
        # 报表走的是 load_results + summarize（不是内存里的 summary）→ 这里对齐校验
        from app.plugin.module_ai.query.eval_metrics import summarize as _sum

        print("报表口径（load_results+summarize）: "
              + json.dumps(_sum(rows), ensure_ascii=False))
        for f in ("difficulty", "form", "datasource", "scenario"):
            print(f"[{f}] " + json.dumps(group_by(rows, f), ensure_ascii=False))
        print("\n=== 逐题 trace（前 5 条）===")
        for r in rows[:5]:
            print(f"  {r['question'][:28]} | path={r['path']} metric={r['metric_key']} "
                  f"rows={r['n_rows']} ms={r['took_ms']} recall={r['recall']:.2f} "
                  f"ont={len(r['ontology_used'] or [])}")
        print(f"  运行状态={st.get('status')} error={st.get('error')!r}")

    if abl_limit:
        before = (await AiQueryService._cfg()).get("recall_enabled")
        aflt = {"limit": abl_limit}
        if force_slow:
            aflt["force_slow"] = True
        ab = R.start_ablation(
            auth, keys=["recall_enabled", "agno_semantic_enabled"],
            filter=aflt,
        )
        while True:
            rep = R.get_ablation_report(ab)
            if rep and rep["status"] in ("done", "error"):
                break
            await asyncio.sleep(2)
        print(f"\n=== 消融对照（{abl_limit} 题/组）status={rep.get('status')} "
              f"error={rep.get('error')!r} ===")
        for name, v in (rep.get("table") or {}).items():
            keys = ("data_accuracy", "recall_at_k", "fast_rate", "avg_ms", "delta_data_accuracy")
            print(f"  {name}: " + json.dumps({k: v.get(k) for k in keys}, ensure_ascii=False))
        AiQueryService._SETTINGS_CACHE = None
        after = (await AiQueryService._cfg()).get("recall_enabled")
        print(f"  配置恢复检查：recall_enabled {before} -> {after} "
              f"{'OK' if before == after else '未恢复！'}")


def cli() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-limit", type=int, default=40)
    ap.add_argument("--ablation-limit", type=int, default=20)
    ap.add_argument("--skip-run", action="store_true")
    ap.add_argument("--force-slow", action="store_true")
    ap.add_argument("--datasource", default="")
    a = ap.parse_args()
    asyncio.run(main(a.run_limit, a.ablation_limit, a.skip_run, a.force_slow, a.datasource))


if __name__ == "__main__":
    cli()
