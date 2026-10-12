"""跑 N 次重复评测并输出**方差报告**（同一批题、同一配置）。

用法（backend 下）::

    python scripts/run_variance.py --split=B --repeats=3 --force-slow

输出：每次的 data_accuracy、跨次均值/标准差/极差（=噪声带）、逐题不稳定清单、两两 McNemar。

⚠️ 每重复一次就是一轮完整评测（B 半 53 题 ≈ 15–20 分钟），**按需跑，别当日常**。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


async def _wait(R, rid: str) -> dict:
    while True:
        st = R.get_status(rid)
        if st and st["status"] in ("done", "error"):
            return st
        await asyncio.sleep(2)


async def main(split: str, repeats: int, force_slow: bool, datasource: str) -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query import eval_runner as R
    from app.plugin.module_ai.query import service as S
    from app.plugin.module_ai.query.eval_set import load_results
    from app.plugin.module_ai.query.eval_variance import variance_report

    flt: dict = {}
    if split:
        flt["split"] = split
    if force_slow:
        flt["force_slow"] = True
    if datasource:
        flt["datasource"] = datasource

    all_runs: list[list[dict]] = []
    for i in range(1, repeats + 1):
        S.sql_cache_clear()          # 每次重复都必须清缓存，否则后次在回放前次（实测踩过）
        S._SETTINGS_CACHE = None
        t0 = time.perf_counter()
        rid = R.start_run(R._auth(), filter=flt or None)
        st = await _wait(R, rid)
        rows = await load_results(rid)
        all_runs.append(rows)
        print(f"  第 {i}/{repeats} 次：run={rid} 题数={st.get('total')} "
              f"用时={time.perf_counter() - t0:.0f}s", flush=True)

    rep = variance_report(all_runs)
    print("\n=== 方差报告 ===")
    print("  每次准确率: " + json.dumps(rep["per_run_accuracy"]))
    print(f"  均值={rep['mean']}  标准差={rep['std']}  "
          f"极差(=噪声带)={rep['spread']}  {rep['min']}~{rep['max']}")
    print(f"  题数={rep['n_questions']}  稳定通过={rep['always_pass']}  "
          f"稳定失败={rep['always_fail']}  不稳定={len(rep['unstable'])}")
    if rep["unstable"]:
        print("  不稳定题（跨次翻转）：")
        for u in rep["unstable"][:10]:
            print(f"    {u['rate']:.2f}  {u['question']}")
    print("  两两配对（McNemar 精确）：")
    for p in rep["pairs"]:
        print(f"    {p['a']} vs {p['b']}: 翻转 {p['b01']}/{p['b10']}  p={p['p']}  "
              f"{'显著' if p['significant'] else '不显著（噪声可解释）'}")
    print(f"\n  判读：**任何小于噪声带（{rep['spread']} 分）的差异都不能归因给功能**")


def cli() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="B", help="留出法 A/B 半（默认 B）")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--force-slow", action="store_true")
    ap.add_argument("--datasource", default="")
    a = ap.parse_args()
    asyncio.run(main(a.split, a.repeats, a.force_slow, a.datasource))


if __name__ == "__main__":
    cli()
