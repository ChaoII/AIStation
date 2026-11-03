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
    "decomposed_planning", "empty_self_correct", "fewshot_auto_curate",
)

#: 进程级运行状态：run_id -> dict
_RUNS: dict[str, dict] = {}


def _auth(user_id: int = 1):
    """评测身份 = **管理员**。

    必须带 ``is_superuser=True``：否则 `_allowed_for_user` 会走数据域 / ABAC 分支，
    把 ``sys_user``、``annotation_dataset`` 等核心表挡在白名单外，慢路径直接报
    「表 xxx 不在可查询白名单内」——那样测到的是**权限配置**而非 NL2SQL 生成质量。
    """
    return SimpleNamespace(user=SimpleNamespace(id=user_id, is_superuser=True))


def get_status(run_id: str | None) -> dict | None:
    r = _RUNS.get(run_id) if run_id else None
    if not r:
        return None
    return {k: v for k, v in r.items() if k != "_task"}


async def _fingerprint() -> dict:
    """记录本轮用的「模型 + 关键配置」指纹，供跨版本回归对比。

    没有它，两次跑分对不上就说不清是「代码/提示词改了」还是「换了模型」。
    """
    from datetime import datetime

    out: dict = {"at": datetime.now().isoformat(timespec="seconds")}
    try:
        from .service import AiQueryService

        rt = await AiQueryService._get_runtime()
        out["model"] = str(rt.get("model") or "")
        out["model_id"] = rt.get("id") or rt.get("model_id")
        out["usage"] = str(rt.get("usage") or "")
        out["base_url"] = str(rt.get("base_url") or "")
    except Exception as e:  # noqa: BLE001
        out["model_error"] = str(e)[:120]
    try:
        from .service import AiQueryService, nl2sql_max_tokens

        cfg = await AiQueryService._cfg()
        keys = ("nl2sql_thinking_mode", "nl2sql_max_tokens", "nl2sql_call_timeout",
                "recall_enabled", "agno_semantic_enabled", "kg_enabled", "agno_tool_agent",
                "decomposed_planning", "empty_self_correct", "fewshot_auto_curate",
                "enum_hint_enabled", "two_stage_planning", "self_consistency_n")
        out["config"] = {k: cfg.get(k) for k in keys if k in cfg}
        out["max_tokens_effective"] = nl2sql_max_tokens(cfg)
    except Exception as e:  # noqa: BLE001
        out["config_error"] = str(e)[:120]
    return out


async def _ask(question: str, auth, datasource: str, force_slow: bool = False) -> dict:
    from .service import AiQueryService, bypass_caches, set_eval_context

    # 评测打标：会话写入 is_eval=true → 不进用户的问数历史 / 使用统计
    set_eval_context(True)
    try:
        # 评测必须**旁路缓存**：SQL 缓存 TTL 30 分钟，命中就等于回放上一轮生成的结果，
        # 「改完再评一次」必然得到同样的数字（对比/消融/方差全部失真）；
        # 反过来，评测生成的 SQL 也会写进共享缓存、30 分钟内喂给真实用户。
        with bypass_caches():
            return await AiQueryService.ask(
                question, auth, None, datasource, force_slow=force_slow)
    finally:
        set_eval_context(False)


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
    """临时覆盖问数配置：**任务内生效，不写库、不影响其他人**。

    旧实现直接 ``UPDATE ai_query_settings`` 跑完再恢复。那是全局可变状态：
    一次消融要跑几分钟，期间**所有真实用户的问数都跑在消融配置下**
    （实测配置里就有 ``recall_enabled`` 这种会改变答案的开关）。
    「退出时恢复」只保证了结束态，没解决进行中的污染。

    现在改成 ``service.config_override`` 的 ContextVar 覆盖层：不落库，
    只影响当前任务及其子任务；哪怕进程在消融中途崩掉，也不会留下被改过的配置。
    """
    from .service import config_override

    with config_override(overrides or {}):
        yield


# ---------------------------------------------------------------------------
# 一轮运行
# ---------------------------------------------------------------------------
async def _run_gold_sql(datasource: str, sql: str) -> dict:
    """执行**金标 SQL**取回列/行，供结果级比对。

    早期不取金标结果 → ``_lenient`` 退化成「SQL 跑通即算对」，
    于是 ``data_accuracy`` 实际只是**可执行率**（实测发现）。失败返回 ``{}``
    （该题退化为跑通即可，不因取数失败把题判错）。
    """
    if not sql:
        return {}
    try:
        from .service import SYSTEM_DS, _execute_custom_ds_sql, _execute_sql

        if (datasource or SYSTEM_DS) == SYSTEM_DS:
            res = await _execute_sql(sql)
        else:
            res = await _execute_custom_ds_sql(int(str(datasource).split(":")[-1]), sql)
        return {"columns": res.get("columns") or [], "rows": res.get("rows") or []}
    except Exception as e:  # noqa: BLE001
        log.warning(f"[ai-eval] 金标取数失败（该题退化为跑通即可）: {str(e)[:120]}")
        return {}


async def _pick_cases(flt: dict, datasource_override: str | None = None) -> list[dict]:
    """按 filter 取题：``datasource/dataset/difficulty/form/scenario`` + ``limit`` + ``split``。

    抽成独立函数便于单测，也把「数据集」纳入统一的取题口径（S4）。
    """
    from .eval_set import list_cases

    flt = flt or {}
    cases = await list_cases(
        datasource=datasource_override or flt.get("datasource"),
        difficulty=flt.get("difficulty"),
        form=flt.get("form"),
        scenario=flt.get("scenario"),
        enabled=True,
        dataset=flt.get("dataset"),
    )
    if flt.get("limit"):
        cases = cases[: int(flt["limit"])]
    # 留出法：只跑指定分集（A/B）
    if flt.get("split"):
        want = str(flt["split"]).upper()
        cases = [c for c in cases if str(c.get("split") or "").upper() == want]
    return cases


async def _run_once(run_id: str, auth, flt: dict, datasource_override: str | None = None) -> None:
    try:
        cases = await _pick_cases(flt, datasource_override)
        # 结果比对要用**本体列名同义表**（CODE≡编码）——每轮加载一次（进程内缓存）
        try:
            from .benchmark import load_label_synonyms

            await load_label_synonyms()
        except Exception as e:  # noqa: BLE001
            log.warning(f"[ai-eval] 列名同义表加载失败（退化为字符串启发式）: {str(e)[:100]}")
        _RUNS[run_id].update(total=len(cases))
        # `total` 必须**落库**：历史列表与进度条都读 DB。旧实现只写内存，
        # 于是 63 次运行全是 total=0，界面上显示成「12 / 0」（实测）。
        await _persist_run_progress(run_id, total=len(cases))
        results: list[dict] = []
        schemas: dict[str, dict] = {}
        gold_cache: dict[int, dict] = {}
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
            # 金标结果按题缓存：同一轮里同一题只取一次数
            gc = gold_cache.get(c["id"])
            if gc is None:
                gc = await _run_gold_sql(ds, c.get("gold_sql") or "")
                gold_cache[c["id"]] = gc
            row = {
                "testcase_id": c["id"], "question": c["question"],
                "ok": not d.get("is_error"), "is_error": bool(d.get("is_error")),
                "path": d.get("path"), "metric_key": (d.get("metric") or {}).get("key", ""),
                "expected_metric": c.get("expected_metric") or "",
                "sql": d.get("sql") or "", "n_rows": len(d.get("rows") or []),
                # took_ms 用**端到端**耗时：d["took_ms"] 只是 SQL 执行时间（几十~几百毫秒），
                # 旧实现直接拿它当延迟上报，于是报表里 avg=468ms / p50=242ms，
                # 而用户实际等的是 5~15 秒 —— 数字好看但毫无意义。执行时间放进 trace。
                "took_ms": ms,
                "exec_ms": int(d.get("took_ms") or 0),
                "gold_match": _lenient(
                    d, {**c, "_gold_cols": gc.get("columns"), "_gold_rows": gc.get("rows")}
                ),
                "recall": recall_at_k(gt, rec, k=8),
                "recall_hit": json.dumps({"expected": sorted(gt), "recalled": rec[:8]},
                                         ensure_ascii=False),
                "ontology_used": json.dumps(d.get("ontology_used") or [], ensure_ascii=False),
                "difficulty": c.get("difficulty"), "scenario": c.get("scenario"),
                "form": c.get("form"), "datasource": ds,
                # 退化题（金标为空/NULL/单值 0）：报表统计时不计入分母
                "degenerate": bool(c.get("degenerate")),
                # 指标快路径能答的题：报表里与"生成题"分开统计
                "metric_eligible": bool(c.get("metric_eligible")),
            }
            results.append(row)
            await _save_result(run_id, row)
            _RUNS[run_id]["done"] = len(results)
            # 进度也要落库（历史列表的「进度」列读的是 DB，不是内存）
            await _persist_run_progress(run_id, done=len(results))
        await _finish_run(run_id, results, status="done")
    except Exception as e:  # noqa: BLE001
        log.error(f"[ai-eval] 运行失败: {e}")
        _RUNS[run_id].update(status="error", error=str(e)[:300])
        # 失败必须回写 DB：否则那条运行在历史里永远显示「运行中」（实测 3 条 10 月的孤儿）
        await _fail_run(run_id, str(e))


def _lenient(d: dict, case: dict) -> bool:
    """数据级比对：复用 benchmark 的宽松比对（列集合 + 行集合）。"""
    try:
        from .benchmark import lenient_match

        cols = list(case.get("_gold_cols") or [])
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
                "tr": json.dumps(
                    {k: row[k] for k in ("difficulty", "scenario", "form", "datasource",
                                         "expected_metric", "degenerate", "metric_eligible")}
                    | {"exec_ms": row.get("exec_ms", 0)},
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


async def _persist_run_progress(run_id: str, total: int | None = None,
                                done: int | None = None) -> None:
    """把 total/done 落库（历史列表与进度条读 DB，不读内存）。"""
    from sqlalchemy import text as _t

    from app.core.database import async_db_session

    sets, params = [], {"r": run_id}
    if total is not None:
        sets.append("total=:t")
        params["t"] = int(total)
    if done is not None:
        sets.append("done=:d")
        params["d"] = int(done)
    if not sets:
        return
    try:
        async with async_db_session.begin() as db:
            await db.execute(
                _t(f"UPDATE ai_query_testrun SET {', '.join(sets)} WHERE run_id=:r"), params)
    except Exception as e:  # noqa: BLE001 - 进度写失败不应中断整轮
        log.warning(f"[ai-eval] 进度落库失败（忽略）: {str(e)[:120]}")


async def _fail_run(run_id: str, error: str, done: int | None = None,
                    status: str = "error") -> None:
    """把失败/停止回写到 DB：状态 + 原因 + 结束时间（否则历史里永远「运行中」）。"""
    from sqlalchemy import text as _t

    from app.core.database import async_db_session

    from .ddl_dialect import json_empty

    payload = json.dumps({"error": (error or "")[:300]}, ensure_ascii=False)
    try:
        async with async_db_session.begin() as db:
            await db.execute(
                _t(
                    "UPDATE ai_query_testrun SET status=:st, finished_at=now(), "
                    f"summary=COALESCE(summary, {json_empty()}) || CAST(:e AS jsonb), "
                    "done=COALESCE(:d, done) WHERE run_id=:r"
                ),
                {"r": run_id, "e": payload, "d": done, "st": status},
            )
    except Exception as e:  # noqa: BLE001
        log.warning(f"[ai-eval] 失败状态落库失败（忽略）: {str(e)[:120]}")


async def _finish_meta_run(run_id: str, summary: dict | None, extra: dict | None = None,
                           total: int | None = None, done: int | None = None) -> None:
    """给「消融/方差」这类**元运行**写终态：summary 里带上基线指标 + 额外信息。"""
    from sqlalchemy import text as _t

    from app.core.database import async_db_session

    payload = dict(summary or {})
    if extra:
        payload["meta"] = extra
    sets = ["status='done'", "finished_at=now()", "summary=CAST(:s AS jsonb)"]
    params: dict = {"r": run_id, "s": json.dumps(payload, ensure_ascii=False, default=str)}
    if total is not None:
        sets.append("total=:t")
        params["t"] = int(total)
    if done is not None:
        sets.append("done=:d")
        params["d"] = int(done)
    try:
        async with async_db_session.begin() as db:
            await db.execute(_t(f"UPDATE ai_query_testrun SET {', '.join(sets)} WHERE run_id=:r"),
                             params)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[ai-eval] 元运行落终态失败（忽略）: {str(e)[:120]}")


async def _ensure_run_row(run_id: str, mode: str, flt: dict | None, config: dict | None,
                          ablation_group: str = "") -> None:
    """确保某 run 在 `ai_query_testrun` 里有行。

    消融的子 run 之前直接写结果表、不建运行行 → `_finish_run` 的 UPDATE 命中 0 行，
    结果永远是不可达的孤儿（实测 10 个 `ab_*` run_id 没有运行记录）。
    """
    from sqlalchemy import text as _t

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        exists = (await db.execute(
            _t("SELECT 1 FROM ai_query_testrun WHERE run_id=:r"), {"r": run_id})).scalar()
        if exists:
            return
        await db.execute(
            _t(
                "INSERT INTO ai_query_testrun(run_id,mode,filter,config,ablation_group,status,"
                "total,done,started_at,is_deleted) "
                "VALUES (:r,:m,CAST(:f AS jsonb),CAST(:c AS jsonb),:g,'running',0,0,now(),false)"
            ),
            {"r": run_id, "m": mode, "f": json.dumps(flt or {}, ensure_ascii=False),
             "c": json.dumps(config or {}, ensure_ascii=False), "g": ablation_group or None},
        )


async def reconcile_stale_runs(timeout_min: int = 30) -> int:
    """启动期对账：把「状态 running 但已超时」的运行标为 error。

    进度只存在进程内 `_RUNS`，进程重启后内存清空、DB 却仍是 running
    → 界面上永远显示「运行中」（实测 3 条 10 月的孤儿）。顺带清理
    「有结果、无运行记录」的孤儿结果（旧版消融子 run 遗留）。
    """
    from sqlalchemy import text as _t

    from app.core.database import async_db_session

    from .ddl_dialect import cutoff_text, json_empty, stale_where

    # 方言差异：`(:m || ' minutes')::interval` 是 **PG 专有**语法，SQLite 会把 `::` 当成
    # 参数前缀，整条 UPDATE 报 `unrecognized token: ":"` 被 except 吞掉 —— 启动日志里
    # 「启动对账失败（忽略）」就是这么来的，等于这个兜底**从来没生效过**（僵尸 running
    # 一直挂在界面上）。非 PG 改成「Python 算好截止时间再传参」。
    cond, param_name = stale_where("started_at", "m")
    stale_params: dict = (
        {"m": str(int(timeout_min))} if param_name == "m"
        else {"cutoff": cutoff_text(int(timeout_min))}
    )

    fixed = 0
    try:
        async with async_db_session.begin() as db:
            res = await db.execute(
                _t(
                    "UPDATE ai_query_testrun SET status='error', finished_at=now(), "
                    f"summary=COALESCE(summary,{json_empty()}) || "
                    "CAST(:e AS jsonb) "
                    f"WHERE status='running' AND {cond}"
                ),
                {"e": json.dumps({"error": "进程重启/超时，评测已中断"}, ensure_ascii=False),
                 **stale_params},
            )
            fixed = res.rowcount or 0
            # 历史脏数据回填：老版本 total 从不落库（全是 0），已完成的运行用 done 补齐，
            # 否则界面一直显示「12 / 0」。
            await db.execute(
                _t(
                    "UPDATE ai_query_testrun SET total=done "
                    "WHERE status='done' AND coalesce(total,0)=0 AND coalesce(done,0)>0"
                )
            )
            await db.execute(
                _t(
                    # 不能写 `DELETE FROM ai_query_testresult r WHERE ...`：SQLite
                    # **不支持 DELETE 带表别名**（近 "r": syntax error），PG 支持。
                    # 用「表名限定」的相关子查询，两种方言都能跑。
                    "DELETE FROM ai_query_testresult WHERE NOT EXISTS "
                    "(SELECT 1 FROM ai_query_testrun t "
                    " WHERE t.run_id = ai_query_testresult.run_id)"
                )
            )
    except Exception as e:  # noqa: BLE001
        log.warning(f"[ai-eval] 启动对账失败（忽略）: {str(e)[:120]}")
    if fixed:
        log.warning(f"[ai-eval] 启动对账：{fixed} 条僵尸「运行中」已标记为中断")
    return fixed


def stop_run(run_id: str) -> bool:
    """停止一个进行中的评测（含消融/方差的子运行）。"""
    r = _RUNS.get(run_id)
    if not r:
        return False
    task = r.get("_task")
    if task is not None and not task.done():
        try:
            task.cancel()
        except Exception:  # noqa: BLE001
            pass
    # 级联：消融/方差主 run 下面是子 run（id 前缀相同）
    for sub, sr in list(_RUNS.items()):
        if sub.startswith(run_id + "_"):
            t = sr.get("_task")
            if t is not None and not t.done():
                try:
                    t.cancel()
                except Exception:  # noqa: BLE001
                    pass
            sr.update(status="stopped")
    r.update(status="stopped", error="用户手动停止")
    try:
        asyncio.ensure_future(_fail_run(run_id, "用户手动停止", done=r.get("done"),
                                        status="stopped"))
    except Exception:  # noqa: BLE001
        pass
    return True


def start_run(auth, filter: dict | None = None, mode: str = "full",
              config: dict | None = None, internal: bool = False) -> str:
    """启动一轮评测（后台），返回 run_id。"""
    from sqlalchemy import text as _t

    from app.core.database import async_db_session
    from app.core.exceptions import CustomException

    from .eval_set import ensure_eval_tables

    if mode == "full" and not internal:
        # 并发互斥：两个全量评测同时跑会互相抢模型/连接，结果也难归因
        busy = [rid for rid, r in _RUNS.items()
                if r.get("status") == "running"
                and r.get("mode") in ("full", "ablation", "variance")]
        if busy:
            raise CustomException(msg="已有评测在运行，请先停止或等待其完成")

    run_id = f"ev_{uuid.uuid4().hex[:12]}"
    flt = dict(filter or {})
    _RUNS[run_id] = {
        "run_id": run_id, "status": "running", "mode": mode, "filter": flt,
        "config": config or {}, "total": 0, "done": 0, "current": "",
        "summary": None, "error": "",
    }

    async def _bootstrap() -> None:
        await ensure_eval_tables()
        # 指纹（模型 + 关键配置）随运行一起落库：没有它，两次跑分差异无法归因
        fp = await _fingerprint()
        _RUNS[run_id]["fingerprint"] = fp
        cfg_payload = {**(config or {}), "fingerprint": fp}
        async with async_db_session.begin() as db:
            await db.execute(
                _t(
                    "INSERT INTO ai_query_testrun"
                    "(run_id,mode,filter,config,status,total,done,started_at,is_deleted) "
                    "VALUES (:r,:m,CAST(:f AS jsonb),CAST(:c AS jsonb),'running',0,0,now(),false)"
                ),
                {"r": run_id, "m": mode, "f": json.dumps(flt, ensure_ascii=False),
                 "c": json.dumps(cfg_payload, ensure_ascii=False, default=str)},
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
            await _fail_run(run_id, str(e))

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
    # 子 run 必须**先落库一行**：否则 _finish_run 的 UPDATE 命中 0 行，
    # 结果就成为不可达孤儿（实测 10 个 ab_* run_id 没有运行记录）。
    await _ensure_run_row(sub, "ablation-group", flt, overrides, ablation_group=name)
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
            await _ensure_run_row(run_id, "ablation", flt, {"groups": ["baseline", *use_keys]})
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
            # 主 run 也要落终态（否则历史里既看不到、重启后又丢）
            await _finish_meta_run(
                run_id, base,
                extra={"groups": ["baseline", *use_keys]},
                total=len(_RUNS[run_id]["table"]), done=len(_RUNS[run_id]["table"]),
            )
        except Exception as e:  # noqa: BLE001
            _RUNS[run_id].update(status="error", error=str(e)[:300])
            await _fail_run(run_id, str(e))

    _RUNS[run_id]["_task"] = asyncio.ensure_future(_job())
    return run_id


def get_ablation_report(run_id: str | None) -> dict | None:
    r = _RUNS.get(run_id) if run_id else None
    if not r:
        return None
    return {"run_id": run_id, "status": r.get("status"), "groups": r.get("groups"),
            "current": r.get("current"), "table": r.get("table"), "error": r.get("error")}


async def _wait_sub_run(sub_id: str) -> dict:
    """等一个子评测跑完（供方差/重复执行使用）。"""
    while True:
        st = get_status(sub_id)
        if st and st["status"] in ("done", "error"):
            return st
        await asyncio.sleep(2)


def start_variance(auth, repeats: int = 3, filter: dict | None = None) -> str:
    """启动**方差**评测：同一批题重复跑 N 次（串行），回答"这个差异是真的吗"。

    为什么必须有它：同一配置（代码路径完全相同）三次跑同一批 B 半 53 题，
    `data_accuracy` = 75.47% / 83.02% / 84.91%（差 10 分）→ 单次 A/B 的差值
    **不能归因给功能**。对标 Palantir AIP Evals 的 "examine the variance across executions"。

    ⚠️ 每次重复前**必须清空 SQL 缓存**：否则后次在回放前次的生成结果，
    两轮指标会**逐项完全相同**（实测踩过，整轮作废）。
    """
    run_id = f"vr_{uuid.uuid4().hex[:12]}"
    flt = dict(filter or {})
    n = max(2, min(int(repeats or 3), 6))
    _RUNS[run_id] = {
        "run_id": run_id, "status": "running", "mode": "variance",
        "repeats": n, "done": 0, "current": "", "runs": [], "report": None, "error": "",
    }

    async def _job() -> None:
        try:
            from .eval_set import load_results
            from .eval_variance import variance_report
            from .service import sql_cache_clear

            await _ensure_run_row(run_id, "variance", flt, {"repeats": n})
            for i in range(n):
                sql_cache_clear()  # ← 不清就是回放，见 docstring
                _RUNS[run_id].update(current=f"第 {i + 1}/{n} 次", done=i)
                await _persist_run_progress(run_id, total=n, done=i)
                sub = start_run(auth, filter=flt or None, internal=True)
                st = await _wait_sub_run(sub)
                if st.get("status") == "error":
                    raise RuntimeError(f"第 {i + 1} 次失败：{st.get('error')}")
                _RUNS[run_id]["runs"].append({"run_id": sub, "rows": await load_results(sub)})
            _RUNS[run_id]["report"] = variance_report([x["rows"] for x in _RUNS[run_id]["runs"]])
            _RUNS[run_id].update(status="done", done=n, current="")
            rep = _RUNS[run_id]["report"] or {}
            # 方差主 run 落终态：历史里能看到「均值准确率 / 噪声带」
            await _finish_meta_run(
                run_id,
                {"data_accuracy": rep.get("mean", 0.0), "n_runs": rep.get("n_runs", n),
                 "spread": rep.get("spread"), "std": rep.get("std"), "repeats": n},
                extra={"sub_runs": [x["run_id"] for x in _RUNS[run_id]["runs"]]},
                total=n, done=n,
            )
        except Exception as e:  # noqa: BLE001
            _RUNS[run_id].update(status="error", error=str(e)[:300])
            await _fail_run(run_id, str(e))

    _RUNS[run_id]["_task"] = asyncio.ensure_future(_job())
    return run_id


def get_variance_report(run_id: str | None) -> dict | None:
    r = _RUNS.get(run_id) if run_id else None
    if not r:
        return None
    return {
        "run_id": run_id, "status": r.get("status"), "repeats": r.get("repeats"),
        "done": r.get("done"), "current": r.get("current"),
        "sub_runs": [x["run_id"] for x in (r.get("runs") or [])],
        "report": r.get("report"), "error": r.get("error"),
    }
