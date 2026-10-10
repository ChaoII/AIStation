"""问数评测执行器：逐题执行 + 进度 + 逐题 trace；配置覆盖；消融（串行）。

进度沿用 ``benchmark_runner`` 的进程级 `_RUNS` 模式（前端轮询 status）。
配置覆盖必须**恢复**（全局配置，见 Review Focus #1）；消融**串行**（Review Focus #5）。
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace

from app.core.logger import log

from .eval_metrics import gold_tables, recall_at_k, summarize

#: 消融维度（spec §七）。
ABLATION_KEYS: tuple[str, ...] = (
    "recall_enabled", "agno_semantic_enabled", "kg_enabled", "agno_tool_agent",
    "decomposed_planning", "empty_self_correct", "fewshot_auto_curate", "enum_hint_enabled",
)

#: 进程级运行状态：run_id -> dict
_RUNS: dict[str, dict] = {}


def _auth(user_id: int = 1):
    return SimpleNamespace(user=SimpleNamespace(id=user_id))


def get_status(run_id: str | None) -> dict | None:
    r = _RUNS.get(run_id) if run_id else None
    if not r:
        return None
    return {k: v for k, v in r.items() if k != "_task"}


async def _ask(question: str, auth, datasource: str, force_slow: bool = False) -> dict:
    from .service import AiQueryService

    return await AiQueryService.ask(question, auth, None, datasource, force_slow=force_slow)


async def _resolve_schema(datasource: str) -> dict:
    from .service import SYSTEM_DS, AiQueryService, list_ds_schema

    if (datasource or SYSTEM_DS) == SYSTEM_DS:
        return await AiQueryService._system_schema()
    try:
        recs = await list_ds_schema(int(str(datasource).split(":")[-1]))
    except Exception:  # noqa: BLE001
        return {}
    return {
        r["table"]: [
            f"{c.get('name')}({c.get('type')})【{c.get('comment')}】" for c in (r.get("columns") or [])
        ]
        for r in recs
    }


# ---------------------------------------------------------------------------
# 配置覆盖（覆盖 → 用 → **恢复**）
# ---------------------------------------------------------------------------
@asynccontextmanager
async def override_settings(overrides: dict):
    """临时覆盖 `ai_query_settings` 的若干键；退出时**恢复原值**并清配置缓存。"""
    from sqlalchemy import text as _t

    from app.core.database import async_db_session
    from . import service as _svc

    saved: dict[str, str | None] = {}
    try:
        async with async_db_session.begin() as db:
            for k, v in (overrides or {}).items():
                row = (
                    await db.execute(
                        _t("SELECT value FROM ai_query_settings WHERE key=:k"), {"k": k}
                    )
                ).fetchone()
                saved[k] = row[0] if row else None
                if row:
                    await db.execute(
                        _t("UPDATE ai_query_settings SET value=:v WHERE key=:k"),
                        {"k": k, "v": str(v)},
                    )
                else:
                    await db.execute(
                        _t(
                            "INSERT INTO ai_query_settings"
                            "(key,value,uuid,status,is_deleted,created_time,updated_time)"
                            " VALUES(:k,:v,:u,'0',false,now(),now())"
                        ),
                        {"k": k, "v": str(v), "u": uuid.uuid4().hex},
                    )
        _svc._SETTINGS_CACHE = None
        yield
    finally:
        try:
            async with async_db_session.begin() as db:
                for k, old in saved.items():
                    if old is None:
                        await db.execute(
                            _t("DELETE FROM ai_query_settings WHERE key=:k"), {"k": k}
                        )
                    else:
                        await db.execute(
                            _t("UPDATE ai_query_settings SET value=:v WHERE key=:k"),
                            {"k": k, "v": old},
                        )
        except Exception as e:  # noqa: BLE001 - 恢复失败必须留下痕迹
            log.warning(f"[ai-eval] 配置恢复失败（可能污染后续评测）: {e}")
        _svc._SETTINGS_CACHE = None


# ---------------------------------------------------------------------------
# 一轮运行
# ---------------------------------------------------------------------------
async def _run_once(run_id: str, auth, flt: dict, datasource_override: str | None = None) -> None:
    from .eval_set import list_cases

    try:
        cases = await list_cases(
            datasource=datasource_override or flt.get("datasource"),
            difficulty=flt.get("difficulty"),
            form=flt.get("form"),
            scenario=flt.get("scenario"),
            enabled=True,
        )
        if flt.get("limit"):
            cases = cases[: int(flt["limit"])]
        _RUNS[run_id].update(total=len(cases))
        results: list[dict] = []
        schemas: dict[str, dict] = {}
        for c in cases:
            _RUNS[run_id]["current"] = c["question"]
            ds = c["datasource"] or "system"
            if ds not in schemas:
                schemas[ds] = await _resolve_schema(ds)
            t0 = time.perf_counter()
            try:
                d = await _ask(c["question"], auth, ds, force_slow=bool(flt.get("force_slow")))
            except Exception as e:  # noqa: BLE001 - 单题异常不得中断整轮
                d = {"is_error": True, "answer": str(e)[:200], "sql": "", "path": "slow"}
            ms = int((time.perf_counter() - t0) * 1000)
            # `retrieved` 是 grounding 字典 `{"tables":[...], "objects":[...]}`（见 service._answer）
            # 早期误按 dict{table:score} 取 keys → recalled 变成 ["tables",...] → Recall 恒为 0。这里取 tables。
            raw_rec = d.get("retrieved")
            if isinstance(raw_rec, dict):
                rec = [str(t) for t in (raw_rec.get("tables") or [])]
            else:
                rec = [str(t) for t in (raw_rec or [])]
            gt = gold_tables(c.get("gold_sql") or "", schemas.get(ds) or {})
            row = {
                "testcase_id": c["id"], "question": c["question"],
                "ok": not d.get("is_error"), "is_error": bool(d.get("is_error")),
                "path": d.get("path"), "metric_key": (d.get("metric") or {}).get("key", ""),
                "expected_metric": c.get("expected_metric") or "",
                "sql": d.get("sql") or "", "n_rows": len(d.get("rows") or []),
                "took_ms": d.get("took_ms") or ms,
                "gold_match": _lenient(d, c),
                "recall": recall_at_k(gt, rec, k=8),
                "recall_hit": json.dumps({"expected": sorted(gt), "recalled": rec[:8]},
                                         ensure_ascii=False),
                "ontology_used": json.dumps(d.get("ontology_used") or [], ensure_ascii=False),
                "difficulty": c.get("difficulty"), "scenario": c.get("scenario"),
                "form": c.get("form"), "datasource": ds,
            }
            results.append(row)
            await _save_result(run_id, row)
            _RUNS[run_id]["done"] = len(results)
        await _finish_run(run_id, results, status="done")
    except Exception as e:  # noqa: BLE001
        log.error(f"[ai-eval] 运行失败: {e}")
        _RUNS[run_id].update(status="error", error=str(e)[:300])


def _lenient(d: dict, case: dict) -> bool:
    """数据级比对：复用 benchmark 的宽松比对（列集合 + 行集合）。"""
    try:
        from .benchmark import lenient_match

        cols = [m for m in (case.get("_gold_cols") or [])]
        rows = case.get("_gold_rows") or []
        if not cols and not rows:
            # 未预取金标结果时，退化为「SQL 跑通且非错误」
            return not d.get("is_error") and bool(d.get("sql"))
        return bool(lenient_match(cols, rows, d.get("columns") or [], d.get("rows") or []))
    except Exception:  # noqa: BLE001
        return not d.get("is_error")


async def _save_result(run_id: str, row: dict) -> None:
    from sqlalchemy import text as _t

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        await db.execute(
            _t(
                "INSERT INTO ai_query_testresult"
                "(run_id,testcase_id,question,ok,is_error,path,metric_key,sql,n_rows,took_ms,"
                "gold_match,recall_hit,ontology_used,tool_calls,retries,trace,is_deleted,created_time) "
                "VALUES (:run_id,:tc,:q,:ok,:err,:path,:metric,:sql,:n,:ms,:gm,"
                "CAST(:rh AS jsonb),CAST(:ou AS jsonb),CAST(:tcalls AS jsonb),:rt,CAST(:tr AS jsonb),"
                "false,now())"
            ),
            {
                "run_id": run_id, "tc": row["testcase_id"], "q": row["question"],
                "ok": row["ok"], "err": row["is_error"], "path": row["path"],
                "metric": row["metric_key"], "sql": row["sql"], "n": row["n_rows"],
                "ms": row["took_ms"], "gm": row["gold_match"], "rh": row["recall_hit"],
                "ou": row["ontology_used"], "tcalls": "[]", "rt": 0,
                "tr": json.dumps({k: row[k] for k in ("difficulty", "scenario", "form", "datasource")},
                                 ensure_ascii=False),
            },
        )


async def _finish_run(run_id: str, results: list[dict], status: str = "done") -> None:
    from sqlalchemy import text as _t

    from app.core.database import async_db_session

    summary = summarize(results)
    async with async_db_session.begin() as db:
        await db.execute(
            _t(
                "UPDATE ai_query_testrun SET status=:st, done=:d, summary=CAST(:s AS jsonb),"
                " finished_at=now() WHERE run_id=:r"
            ),
            {"st": status, "d": len(results), "s": json.dumps(summary, ensure_ascii=False),
             "r": run_id},
        )
    _RUNS[run_id].update(status=status, summary=summary)


def start_run(auth, filter: dict | None = None, mode: str = "full",
              config: dict | None = None) -> str:
    """启动一轮评测（后台），返回 run_id。"""
    from sqlalchemy import text as _t

    from app.core.database import async_db_session
    from .eval_set import ensure_eval_tables

    run_id = f"ev_{uuid.uuid4().hex[:12]}"
    flt = dict(filter or {})
    _RUNS[run_id] = {
        "run_id": run_id, "status": "running", "mode": mode, "filter": flt,
        "config": config or {}, "total": 0, "done": 0, "current": "",
        "summary": None, "error": "",
    }

    async def _bootstrap() -> None:
        await ensure_eval_tables()
        async with async_db_session.begin() as db:
            await db.execute(
                _t(
                    "INSERT INTO ai_query_testrun"
                    "(run_id,mode,filter,config,status,total,done,started_at,is_deleted) "
                    "VALUES (:r,:m,CAST(:f AS jsonb),CAST(:c AS jsonb),'running',0,0,now(),false)"
                ),
                {"r": run_id, "m": mode, "f": json.dumps(flt, ensure_ascii=False),
                 "c": json.dumps(config or {}, ensure_ascii=False)},
            )

    async def _job() -> None:
        try:
            await _bootstrap()
            if config:
                async with override_settings(config):
                    await _run_once(run_id, auth, flt)
            else:
                await _run_once(run_id, auth, flt)
        except Exception as e:  # noqa: BLE001
            _RUNS[run_id].update(status="error", error=str(e)[:300])

    _RUNS[run_id]["_task"] = asyncio.ensure_future(_job())
    return run_id


# ---------------------------------------------------------------------------
# 消融（串行）
# ---------------------------------------------------------------------------
async def _run_ablation_group(name: str, auth, flt: dict, overrides: dict, run_id: str) -> dict:
    """跑一组（可覆盖配置），返回该组 summary。"""
    sub = f"{run_id}_{name}"
    _RUNS[run_id]["current"] = f"消融组：{name}"
    # 子 run 必须先注册，否则 _run_once 内 _RUNS[sub] 会 KeyError（消融实测踩坑）
    _RUNS[sub] = {
        "run_id": sub, "status": "running", "mode": "ablation-group",
        "group": name, "filter": dict(flt or {}), "total": 0, "done": 0,
        "current": "", "summary": None, "error": "",
    }
    if overrides:
        async with override_settings(overrides):
            await _run_once(sub, auth, flt)
    else:
        await _run_once(sub, auth, flt)
    return _RUNS.get(sub, {}).get("summary") or {}


def start_ablation(auth, keys: list[str] | None = None, filter: dict | None = None) -> str:
    """启动消融：先跑「全开」基线，再逐个「关掉」；**串行**执行。"""
    run_id = f"ab_{uuid.uuid4().hex[:12]}"
    flt = dict(filter or {})
    use_keys = list(keys or ABLATION_KEYS)
    _RUNS[run_id] = {
        "run_id": run_id, "status": "running", "mode": "ablation",
        "groups": ["baseline", *use_keys], "current": "", "table": {}, "error": "",
    }

    async def _job() -> None:
        try:
            for name in ["baseline", *use_keys]:
                overrides = {} if name == "baseline" else {name: "false"}
                summary = await _run_ablation_group(name, auth, flt, overrides, run_id)
                _RUNS[run_id]["table"][name] = summary
            base = _RUNS[run_id]["table"].get("baseline") or {}
            for name, s in _RUNS[run_id]["table"].items():
                if name == "baseline":
                    continue
                s["delta_data_accuracy"] = round(
                    float(s.get("data_accuracy", 0)) - float(base.get("data_accuracy", 0)), 4)
                s["delta_avg_ms"] = round(
                    float(s.get("avg_ms", 0)) - float(base.get("avg_ms", 0)), 1)
            _RUNS[run_id].update(status="done")
        except Exception as e:  # noqa: BLE001
            _RUNS[run_id].update(status="error", error=str(e)[:300])

    _RUNS[run_id]["_task"] = asyncio.ensure_future(_job())
    return run_id


def get_ablation_report(run_id: str | None) -> dict | None:
    r = _RUNS.get(run_id) if run_id else None
    if not r:
        return None
    return {"run_id": run_id, "status": r.get("status"), "groups": r.get("groups"),
            "current": r.get("current"), "table": r.get("table"), "error": r.get("error")}
