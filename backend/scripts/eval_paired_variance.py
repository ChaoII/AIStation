"""配对 A/B 方差评测：同一批题、多组配置、各跑 N 次，回答"这个差异是真的吗"。

为什么现有的 `start_variance` 不够
----------------------------------
它只重复**同一套配置**，能给出噪声带，却没法比较两组配置的差异是否超过噪声。
而实测：同配置重跑 81 题会翻 **7~8 题（≈10%）** —— 单轮 A/B 差 1~2 题时，
把它归因给功能是**统计上不成立的**（本项目已经因此误判过一次：先得出"语义通道
是负贡献"，配对多次后发现方向反了）。

做法
----
- 多组配置**交替**跑（A,B,A,B…），把机器负载漂移摊平；
- 每轮之间清 SQL 缓存（评测本身也旁路，这里是双保险）；
- 结论按**逐题多数票**给，而不是单轮总分。

用法::

    cd backend
    uv run python scripts/eval_paired_variance.py --repeats 3 --dataset fuel-v2
    uv run python scripts/eval_paired_variance.py --configs "baseline,agno_semantic_enabled=false,recall_enabled=false"
"""
from __future__ import annotations

import argparse
import asyncio
import time

from sqlalchemy import text

from app.core.database import async_db_session


def _parse(configs: str) -> list[tuple[str, dict]]:
    """``baseline,key=false,a=1&b=2`` → 名字 + 覆盖字典（``&`` 连接多个覆盖）。"""
    out: list[tuple[str, dict]] = []
    for raw in (configs or "baseline").split(","):
        item = raw.strip()
        if not item:
            continue
        if item == "baseline" or "=" not in item:
            out.append((item or "baseline", {}))
            continue
        ov: dict[str, str] = {}
        for pair in item.split("&"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                ov[k.strip()] = v.strip()
        out.append((item, ov))
    return out or [("baseline", {})]


def _bootstrap() -> None:
    """必须先把应用构造一次：否则 ORM 关系解析不到（金标取数全部失败、
    accuracy 恒为 0 —— 实测踩过，脚本"跑成功"但数字全是 0）。
    """
    from main import create_app

    create_app()


async def _wait(rid: str, timeout: int = 3600) -> dict:
    from app.plugin.module_ai.query import eval_runner as R

    try:
        await asyncio.wait_for(R._RUNS[rid].get("_task"), timeout=timeout)
    except asyncio.TimeoutError:
        print(f"! 超时 {rid}", flush=True)
    return (R._RUNS.get(rid) or {}).get("summary") or {}


async def _load(rid: str) -> dict[str, bool]:
    async with async_db_session() as db:
        rows = (await db.execute(
            text("SELECT question, gold_match FROM ai_query_testresult WHERE run_id=:r"),
            {"r": rid})).fetchall()
    return {r[0]: bool(r[1]) for r in rows}


def _majority(maps: list[dict[str, bool]]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for q in maps[0]:
        votes = [m[q] for m in maps if q in m]
        out[q] = sum(1 for v in votes if v) * 2 > len(votes)
    return out


def _flips(maps: list[dict[str, bool]]) -> int:
    """同一配置内部会翻转的题数 = 噪声带。"""
    return sum(1 for q in maps[0] if len({m.get(q) for m in maps if q in m}) > 1)


async def main() -> None:  # pragma: no cover - 运维脚本
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="baseline,agno_semantic_enabled=false")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--dataset", default="fuel-v2")
    args = ap.parse_args()

    _bootstrap()

    from app.plugin.module_ai.query import eval_runner as R
    from app.plugin.module_ai.query.service import sql_cache_clear

    configs = _parse(args.configs)
    flt = {"dataset": args.dataset} if args.dataset else {}
    auth = R._auth()
    runs: dict[str, list[dict[str, bool]]] = {name: [] for name, _ in configs}

    for i in range(max(2, args.repeats)):
        for name, overrides in configs:
            sql_cache_clear()
            t0 = time.perf_counter()
            if overrides:
                async with R.override_settings(overrides):
                    rid = R.start_run(auth, filter=flt, internal=True)
                    s = await _wait(rid)
            else:
                rid = R.start_run(auth, filter=flt, internal=True)
                s = await _wait(rid)
            rows = await _load(rid)
            if not rows or not s:
                raise SystemExit(
                    f"运行 {name}#{i + 1} 没有产出结果（{rid}）："
                    f"status={(R._RUNS.get(rid) or {}).get('status')} "
                    f"err={(R._RUNS.get(rid) or {}).get('error')} —— 中止，避免把 0.0 当结论")
            runs[name].append(rows)
            print(f"OK {name}#{i + 1} acc={s.get('data_accuracy')} "
                  f"{int(time.perf_counter() - t0)}s", flush=True)

    print("\n===== 结果 =====")
    majors = {}
    for name, maps in runs.items():
        accs = [round(sum(1 for v in m.values() if v) / max(len(m), 1), 4) for m in maps]
        majors[name] = _majority(maps)
        mean = sum(accs) / len(accs)
        print(f"{name:<28} acc={accs} mean={mean:.4f} 内部翻转={_flips(maps)}/{len(maps[0])}")

    base_name = configs[0][0]
    base = majors[base_name]
    for name, _ in configs[1:]:
        m = majors[name]
        gain = [q for q in base if not base[q] and m.get(q)]
        loss = [q for q in base if base[q] and not m.get(q)]
        acc_base = sum(1 for v in base.values() if v) / len(base)
        acc_this = sum(1 for v in m.values() if v) / len(m)
        print(f"\n{name}: 多数票 {acc_this:.4f} vs {base_name} {acc_base:.4f} "
              f"(Δ={acc_this - acc_base:+.4f})；变对 {len(gain)} 题、变错 {len(loss)} 题")
        for q in gain[:6]:
            print(f"   + {q}")
        for q in loss[:6]:
            print(f"   - {q}")
    print("\n注：|Δ| 小于各配置内部翻转率带来的噪声时，**不能**归因给配置。")


if __name__ == "__main__":
    asyncio.run(main())
