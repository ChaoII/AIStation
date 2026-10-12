"""两段式分解（`two_stage_planning`）**留出法 A/B 重测**。

背景：旧结论「−3.78 分」**已作废**——当时 `_cfg_bool` 有 bug（值为真时返回 `default`），
以 `default=False` 读取的开关**从未生效**，那次测的是噪声。

本脚本在修复后重测：
- 同一批 **B 半**（留出法）题目，唯一变量 `two_stage_planning`；
- **纯生成**（`force_slow`）→ 剔除指标快路径的干扰；
- 每轮结束打印 `load_results + summarize` 口径与分 form / difficulty 对照。

用法（backend 下）::

    python scripts/_ab_two_stage.py
"""

from __future__ import annotations

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

KEY = "two_stage_planning"


async def _wait(R, rid: str) -> dict:
    while True:
        st = R.get_status(rid)
        if st and st["status"] in ("done", "error"):
            return st
        await asyncio.sleep(2)


async def _one(R, label: str, cfg: dict) -> tuple[dict, dict]:
    from app.plugin.module_ai.query.eval_metrics import group_by, summarize
    from app.plugin.module_ai.query.eval_set import load_results

    t0 = time.perf_counter()
    rid = R.start_run(R._auth(), filter={"force_slow": True, "split": "B"}, config=cfg)
    st = await _wait(R, rid)
    rows = await load_results(rid)
    s = summarize(rows)
    print(
        f"\n=== {label}  config={cfg}  status={st.get('status')}  "
        f"题数={st.get('total')} 用时={time.perf_counter() - t0:.0f}s",
        flush=True,
    )
    print("  summary: " + json.dumps(s, ensure_ascii=False), flush=True)
    print("  [form] " + json.dumps(group_by(rows, "form"), ensure_ascii=False), flush=True)
    print("  [difficulty] " + json.dumps(group_by(rows, "difficulty"), ensure_ascii=False),
          flush=True)
    if st.get("error"):
        print(f"  error={st.get('error')}", flush=True)
    return s, group_by(rows, "form")


async def main() -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query import eval_runner as R
    from app.plugin.module_ai.query import service as S
    from app.plugin.module_ai.query.eval_set import list_cases
    from app.plugin.module_ai.query.service import AiQueryService

    before = (await AiQueryService._cfg()).get(KEY)
    cs = await list_cases()
    b = [c for c in cs if str(c.get("split") or "").upper() == "B"]
    print(f"B 半题数 = {len(b)}（全集 {len(cs)}）  起始配置 {KEY}={before}", flush=True)

    a_s, a_f = await _one(R, "A/基线 two_stage=false", {KEY: "false"})
    b_s, b_f = await _one(R, "B/实验 two_stage=true", {KEY: "true"})

    print("\n========== 对照（B 半，唯一变量 two_stage_planning）==========", flush=True)
    for k in ("data_accuracy", "generation_accuracy", "semantic_accuracy",
              "fast_rate", "error_rate", "avg_ms"):
        va, vb = a_s.get(k), b_s.get(k)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            print(f"  {k:22s} 基线={va:>8.2f}  实验={vb:>8.2f}  Δ={vb - va:+.2f}", flush=True)
        else:
            print(f"  {k:22s} 基线={va}  实验={vb}", flush=True)
    print("  分 form：", flush=True)
    for f in sorted(set(a_f) | set(b_f)):
        da = a_f.get(f, {}).get("accuracy")
        db = b_f.get(f, {}).get("accuracy")
        na = a_f.get(f, {}).get("total")
        nb = b_f.get(f, {}).get("total")
        mark = ""
        if isinstance(da, (int, float)) and isinstance(db, (int, float)):
            mark = f"  Δ={db - da:+.2f}"
        print(f"    {f or '-':16s} n={na}/{nb}  基线={da}  实验={db}{mark}", flush=True)

    S._SETTINGS_CACHE = None
    after = (await AiQueryService._cfg()).get(KEY)
    print(f"\n恢复检查：{KEY} {before} -> {after} "
          f"{'OK' if before == after else '未恢复！'}", flush=True)


asyncio.run(main())
