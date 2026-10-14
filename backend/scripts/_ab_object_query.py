"""对象查询（`object_query_enabled`，语义执行层）**留出法 A/B**。

唯一变量：`object_query_enabled`。其余配置不动。

⚠️ 两个必须遵守的前提（否则测出来的东西是假的）：

1. **不能传 `force_slow`**。`ask()` 在 `force_slow=True` 时**直接进 `_slow_path`**，
   会**完全绕过**对象查询分支 —— 那样两轮的 `path` 会一模一样，等于没测。
2. **必须清空进程内 SQL 缓存**（TTL 30min）。否则第二轮大量命中第一轮生成的 SQL，
   实验组实际在"回放"基线，两边指标会**逐项完全相同**（`_ab_two_stage.py` 踩过）。

另注：对象查询只作用于**系统库**（本体对象支撑表在系统库里），自定义数据源自动降级。

用法（backend 下）::

    python scripts/_ab_object_query.py
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

KEY = "object_query_enabled"


async def _wait(R, rid: str) -> dict:
    while True:
        st = R.get_status(rid)
        if st and st["status"] in ("done", "error"):
            return st
        await asyncio.sleep(2)


async def _one(R, label: str, cfg: dict) -> tuple[dict, dict, dict]:
    from app.plugin.module_ai.query import service as S
    from app.plugin.module_ai.query.eval_metrics import group_by, summarize
    from app.plugin.module_ai.query.eval_set import load_results

    dropped = S.sql_cache_clear()
    S._SETTINGS_CACHE = None
    t0 = time.perf_counter()
    # 只用分集 + 数据源过滤，**不传 force_slow**（见文件头）。
    # ⚠️ 必须限定 `datasource="system"`：对象查询只作用于系统库，自定义源会自动降级。
    #    当前库里 B 半多为 `ds:4`（自定义源），不限定的话两轮几乎无差异 —— 会得出假结论。
    rid = R.start_run(R._auth(),
                      filter={"split": "B", "datasource": "system"},
                      config=cfg)
    st = await _wait(R, rid)
    rows = await load_results(rid)
    s = summarize(rows)
    by_path = group_by(rows, "path")
    by_form = group_by(rows, "form")
    print(
        f"\n=== {label}  config={cfg}  status={st.get('status')}  "
        f"题数={st.get('total')} 用时={time.perf_counter() - t0:.0f}s  清缓存={dropped} 条",
        flush=True,
    )
    print("  summary: " + json.dumps(s, ensure_ascii=False), flush=True)
    print("  [path]  " + json.dumps(by_path, ensure_ascii=False), flush=True)
    print("  [form]  " + json.dumps(by_form, ensure_ascii=False), flush=True)
    if st.get("error"):
        print(f"  error={st.get('error')}", flush=True)
    return s, by_path, by_form


async def main() -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query import eval_runner as R
    from app.plugin.module_ai.query import service as S
    from app.plugin.module_ai.query.eval_set import list_cases
    from app.plugin.module_ai.query.service import AiQueryService

    before = (await AiQueryService._cfg()).get(KEY)
    cs = await list_cases()
    # 只统计**系统库**的 B 半题：对象查询只作用于系统库（自定义源自动降级）
    b = [c for c in cs
         if str(c.get("split") or "").upper() == "B"
         and (c.get("datasource") or "system") == "system"]
    print(f"B 半 · system 库题数 = {len(b)}（全集 {len(cs)}）  起始配置 {KEY}={before}", flush=True)
    if not b:
        print("⚠️ B 半在 system 库下没有题目：对象查询只作用于系统库，A/B 无意义。", flush=True)

    a_s, a_p, a_f = await _one(R, "A/基线 object_query=false", {KEY: "false"})
    b_s, b_p, b_f = await _one(R, "B/实验 object_query=true", {KEY: "true"})

    print("\n========== 对照（B 半，唯一变量 object_query_enabled）==========", flush=True)
    for k in ("data_accuracy", "generation_accuracy", "semantic_accuracy",
              "object_rate", "fast_rate", "error_rate", "avg_ms", "p95_ms"):
        va, vb = a_s.get(k), b_s.get(k)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            print(f"  {k:22s} 基线={va:>8.2f}  实验={vb:>8.2f}  Δ={vb - va:+.2f}", flush=True)
        else:
            print(f"  {k:22s} 基线={va}  实验={vb}", flush=True)

    print("  分 path（看到底有多少题真的走了对象查询）：", flush=True)
    for p in sorted(set(a_p) | set(b_p)):
        da, db = a_p.get(p, {}).get("accuracy"), b_p.get(p, {}).get("accuracy")
        na, nb = a_p.get(p, {}).get("total"), b_p.get(p, {}).get("total")
        mark = f"  Δ={db - da:+.2f}" if isinstance(da, (int, float)) and isinstance(db, (int, float)) else ""
        print(f"    {p or '-':10s} n={na}/{nb}  基线={da}  实验={db}{mark}", flush=True)

    print("  分 form：", flush=True)
    for f in sorted(set(a_f) | set(b_f)):
        da, db = a_f.get(f, {}).get("accuracy"), b_f.get(f, {}).get("accuracy")
        na, nb = a_f.get(f, {}).get("total"), b_f.get(f, {}).get("total")
        mark = f"  Δ={db - da:+.2f}" if isinstance(da, (int, float)) and isinstance(db, (int, float)) else ""
        print(f"    {f or '-':16s} n={na}/{nb}  基线={da}  实验={db}{mark}", flush=True)

    S._SETTINGS_CACHE = None
    after = (await AiQueryService._cfg()).get(KEY)
    print(f"\n恢复检查：{KEY} {before} -> {after} "
          f"{'OK' if before == after else '未恢复！'}", flush=True)


asyncio.run(main())
