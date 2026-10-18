"""跑「燃煤业务语义执行层评测集」：基线 vs 三级降级（object_query 开/关）。"""
import asyncio
import json
import sys

sys.path.insert(0, '.')
from main import create_app

create_app()
from app.plugin.module_ai.query import eval_runner as R
from app.plugin.module_ai.query import service as S
from app.plugin.module_ai.query.eval_metrics import summarize
from app.plugin.module_ai.query.eval_set import load_results

FLT = {"dataset": "coal_semantic_v1", "datasource": "ds:4"}


async def _wait(rid):
    while True:
        st = R.get_status(rid)
        if st and st["status"] in ("done", "error"):
            return st
        await asyncio.sleep(2)


async def _one(label, cfg):
    S.sql_cache_clear()
    S._SETTINGS_CACHE = None
    rid = R.start_run(R._auth(), filter=FLT, config=cfg)
    await _wait(rid)
    s = summarize(await load_results(rid))
    print(f"[{label}] " + json.dumps(
        {k: s.get(k) for k in ("data_accuracy", "object_rate", "fast_rate",
                               "error_rate", "avg_ms", "p95_ms")}, ensure_ascii=False))
    return s


async def main():
    a = await _one("baseline ", {"object_query_enabled": "false"})
    b = await _one("experiment", {"object_query_enabled": "true"})
    print("\n===== 对比（coal_semantic_v1）=====")
    for k in ("data_accuracy", "object_rate", "fast_rate", "error_rate", "avg_ms", "p95_ms"):
        print(f"  {k:16s} 基线={a.get(k)}  实验={b.get(k)}")


asyncio.run(main())
