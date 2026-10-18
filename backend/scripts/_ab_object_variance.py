"""对象查询 A/B 的**方差**检查：对基线/实验两臂各重复跑 N 次，看各臂内 `data_accuracy`
的波动是否覆盖了两臂间的差值（回答「+0.10 是真的还是噪声」）。

每次重复前清空进程内 SQL 缓存（否则后次回放前次生成结果，指标逐项相同——实测踩坑）。

用法（backend 下）::

    python scripts/_ab_object_variance.py [repeats]
"""
from __future__ import annotations

import asyncio
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
ARMS = [("baseline", "false"), ("experiment", "true")]


async def _wait(R, rid: str, label: str) -> dict:
    while True:
        st = R.get_status(rid)
        if st and st["status"] in ("done", "error"):
            return st
        await asyncio.sleep(2)


async def main() -> None:
    from main import create_app
    create_app()
    from app.plugin.module_ai.query import eval_runner as R
    from app.plugin.module_ai.query import service as S
    from app.plugin.module_ai.query.eval_metrics import summarize
    from app.plugin.module_ai.query.eval_set import load_results

    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    # 记录每个臂的 data_accuracy 序列
    seq: dict[str, list[float]] = {name: [] for name, _ in ARMS}
    for name, val in ARMS:
        for i in range(repeats):
            S.sql_cache_clear()
            S._SETTINGS_CACHE = None
            t0 = time.perf_counter()
            rid = R.start_run(R._auth(),
                              filter={"split": "B", "datasource": "system"},
                              config={KEY: val})
            st = await _wait(R, rid, name)
            rows = await load_results(rid)
            s = summarize(rows)
            acc = float(s.get("data_accuracy", 0))
            obj = float(s.get("object_rate", 0))
            seq[name].append(acc)
            print(f"[{name:10s}] 第{i+1}/{repeats} 次  data_accuracy={acc:.2f} "
                  f"object_rate={obj:.2f}  status={st.get('status')}  "
                  f"用时={time.perf_counter()-t0:.0f}s", flush=True)
        S._SETTINGS_CACHE = None

    print("\n========== 方差对照（B 半·system，对象题集）==========", flush=True)
    means: dict[str, float] = {}
    spread: dict[str, float] = {}
    for name, _ in ARMS:
        v = seq[name]
        means[name] = sum(v) / len(v)
        spread[name] = max(v) - min(v)
        print(f"  {name:10s} 值={['%.2f' % x for x in v]}  "
              f"均值={means[name]:.2f}  极差={spread[name]:.2f}", flush=True)
    delta = means["experiment"] - means["baseline"]
    print(f"\n  两臂均值差 Δdata_accuracy = {delta:+.2f}", flush=True)
    # 若任一小样本极差(单臂 99% 波动上限)已覆盖 Δ，则差异不可信
    noise = max(spread.values())
    print(f"  单臂极差(噪声上限)={noise:.2f}  →  {'差异可能被噪声覆盖，不可信' if noise >= abs(delta) else '差异大于噪声，相对可信'}", flush=True)


asyncio.run(main())
