"""燃煤评测集 A/B **方差**：两臂各重复 N 次（**交替顺序**，避免缓存系统性偏袒某一臂），
报告准确率的波动与两臂均值差。

用法（backend 下）::

    python _coal_variance.py [repeats]
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, '.')
from main import create_app

create_app()
from app.plugin.module_ai.query import eval_runner as R
from app.plugin.module_ai.query import service as S
from app.plugin.module_ai.query.eval_metrics import summarize
from app.plugin.module_ai.query.eval_set import load_results

FLT = {"dataset": "coal_semantic_v1", "datasource": "ds:4"}
ARMS = [("baseline", {"object_query_enabled": "false"}),
        ("experiment", {"object_query_enabled": "true"})]


async def _wait(rid):
    while True:
        st = R.get_status(rid)
        if st and st["status"] in ("done", "error"):
            return st
        await asyncio.sleep(2)


async def _one(cfg: dict) -> dict:
    S.sql_cache_clear()
    S._SETTINGS_CACHE = None
    rid = R.start_run(R._auth(), filter=FLT, config=cfg)
    await _wait(rid)
    return summarize(await load_results(rid))


async def main() -> None:
    repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    seq: dict[str, list[dict]] = {name: [] for name, _ in ARMS}
    for i in range(repeats):
        for name, cfg in ARMS:          # **交替**：同轮两臂紧邻，缓存冷热对称
            t0 = time.perf_counter()
            s = await _one(cfg)
            seq[name].append(s)
            print(f"[{name:10s}] 第{i + 1}/{repeats} 次  "
                  f"acc={s.get('data_accuracy'):.4f} object={s.get('object_rate'):.2f} "
                  f"err={s.get('error_rate'):.2f} avg={s.get('avg_ms'):.0f}ms "
                  f"用时={time.perf_counter() - t0:.0f}s", flush=True)

    print("\n========== 方差对照（coal_semantic_v1）==========", flush=True)
    means, spreads = {}, {}
    for name, _ in ARMS:
        vals = [x.get("data_accuracy", 0) for x in seq[name]]
        means[name] = sum(vals) / len(vals)
        spreads[name] = max(vals) - min(vals)
        print(f"  {name:10s} acc={['%.4f' % v for v in vals]} "
              f"均值={means[name]:.4f} 极差={spreads[name]:.4f}", flush=True)
    delta = means["experiment"] - means["baseline"]
    noise = max(spreads.values())
    print(f"\n  两臂均值差 Δacc = {delta:+.4f}；单臂极差(噪声) = {noise:.4f} → "
          f"{'差异被噪声覆盖，不可信' if noise >= abs(delta) else '差异大于噪声'}", flush=True)


asyncio.run(main())
