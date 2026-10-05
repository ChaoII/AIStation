"""智能问数：后台跑基准（供 UI「跑基准」入口触发）。

进度与结果存进程级 dict，前端通过 GET /benchmark/status?run_id= 轮询。
复用 benchmark.py 的题集（GOLDEN / NL2SQL_GOLDEN）与宽松比对 lenient_match。
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from .benchmark import GOLDEN, NL2SQL_GOLDEN, lenient_match
from .service import AiQueryService

#: 进程级基准运行状态：run_id -> dict
_RUNS: dict[str, dict] = {}


def _mk_auth(user_id: int | None):
    return SimpleNamespace(user=SimpleNamespace(id=user_id))


async def _ask(question: str, force_slow: bool, user_id: int | None) -> dict:
    return await AiQueryService.ask(
        question, _mk_auth(user_id), None, "system", force_slow=force_slow
    )


def start_run(user_id: int | None) -> str:
    """启动后台基准任务，返回 run_id。非阻塞。"""
    run_id = f"bm_{int(time.time() * 1000)}"
    _RUNS[run_id] = {
        "run_id": run_id, "status": "running", "stage": "fast",
        "done": 0, "total": len(GOLDEN) + len(NL2SQL_GOLDEN),
        "current": "", "results": [], "report": None, "error": "",
    }
    task = asyncio.ensure_future(_run(run_id, user_id))
    _RUNS[run_id]["_task"] = task
    return run_id


def get_status(run_id: str | None) -> dict | None:
    if not run_id:
        return None
    r = _RUNS.get(run_id)
    if not r:
        return None
    return {k: v for k, v in r.items() if k != "_task"}


def _update(run_id: str, **kw) -> None:
    r = _RUNS.get(run_id)
    if r:
        r.update(kw)


async def _run(run_id: str, user_id: int | None) -> None:
    try:
        _update(run_id, status="running", stage="fast")
        fast_results = await _run_fast(run_id, GOLDEN, user_id)
        _update(run_id, stage="nl2sql")
        nl_results = await _run_nl2sql(run_id, NL2SQL_GOLDEN, user_id)
        _update(run_id, status="done", stage="done", report={
            "fast": _fast_report(fast_results),
            "nl2sql": _nl2sql_report(nl_results),
        })
    except Exception as e:  # noqa: BLE001
        _update(run_id, status="error", error=str(e))


async def _run_fast(run_id: str, items: list, user_id: int | None) -> list:
    out = []
    for item in items:
        _update(run_id, current=item.get("q", ""), done=len(out))
        t0 = time.perf_counter()
        d = await _ask(item["q"], False, user_id)
        ms = (time.perf_counter() - t0) * 1000
        out.append({
            "q": item["q"], "expected": item["metric"],
            "resolved": (d.get("metric") or {}).get("key"),
            "correct": (d.get("metric") or {}).get("key") == item["metric"],
            "path": d.get("path"), "ok": not d.get("is_error"),
            "ms": round(ms, 1),
        })
        _update(run_id, done=len(out))
    return out


async def _run_nl2sql(run_id: str, items: list, user_id: int | None) -> list:
    out = []
    for item in items:
        from .benchmark import _run_gold
        try:
            gold_cols, expected = await _run_gold(item["gold"])
        except Exception as e:  # noqa: BLE001
            gold_cols, expected = [], []
            _update(run_id, current=item.get("q", ""))
            out.append({"q": item["q"], "tag": item.get("tag"), "correct": False,
                        "path": "slow", "ok": False, "ms": 0, "n_rows": 0,
                        "sql": "", "gold_error": str(e)[:120]})
            _update(run_id, done=len(GOLDEN) + len(out))
            continue
        _update(run_id, current=item.get("q", ""))
        t0 = time.perf_counter()
        try:
            d = await _ask(item["q"], True, user_id)
            ms = (time.perf_counter() - t0) * 1000
            correct = (
                lenient_match(gold_cols, expected, d.get("columns") or [], d.get("rows") or [])
                and not d.get("is_error")
            )
        except Exception:  # noqa: BLE001
            ms = (time.perf_counter() - t0) * 1000
            correct = False
            d = {"is_error": True, "columns": [], "rows": [], "sql": "", "path": "slow"}
        out.append({
            "q": item["q"], "tag": item.get("tag"), "correct": correct,
            "path": d.get("path"), "ok": not d.get("is_error"),
            "ms": round(ms, 1), "n_rows": len(d.get("rows") or []),
            "sql": d.get("sql", ""),
        })
        _update(run_id, done=len(GOLDEN) + len(out))
    return out


def _fast_report(results: list) -> dict:
    n = len(results)
    if not n:
        return {"total": 0, "semantic_accuracy": 0, "fast_path_rate": 0,
                "exec_ok_rate": 0, "p50_ms": 0, "p95_ms": 0, "results": []}
    sem = sum(1 for x in results if x["correct"])
    fast = sum(1 for x in results if x["path"] == "fast")
    ok = sum(1 for x in results if x["ok"])
    ms = sorted(x["ms"] for x in results if x["path"] == "fast")

    def pct(a): return round(a / n, 3)
    p50 = ms[len(ms) // 2] if ms else 0
    p95 = ms[min(int(len(ms) * 0.95), len(ms) - 1)] if ms else 0
    return {"total": n, "semantic_accuracy": pct(sem), "fast_path_rate": pct(fast),
            "exec_ok_rate": pct(ok), "p50_ms": round(p50, 1), "p95_ms": round(p95, 1),
            "results": results}


def _nl2sql_report(results: list) -> dict:
    n = len(results)
    if not n:
        return {"total": 0, "accuracy": 0, "slow_rate": 0, "p50_ms": 0, "by_tag": {}, "results": []}
    acc = sum(1 for x in results if x["correct"])
    slow = sum(1 for x in results if x["path"] == "slow")
    ms = [x["ms"] for x in results]
    by_tag: dict[str, dict] = {}
    for x in results:
        t = x.get("tag") or "未分类"
        b = by_tag.setdefault(t, {"total": 0, "correct": 0})
        b["total"] += 1
        b["correct"] += 1 if x["correct"] else 0
    for b in by_tag.values():
        b["acc"] = round(b["correct"] / b["total"], 3)
    return {"total": n, "accuracy": round(acc / n, 3), "slow_rate": round(slow / n, 3),
            "p50_ms": round(sorted(ms)[len(ms) // 2], 1) if ms else 0,
            "by_tag": by_tag, "results": results}
