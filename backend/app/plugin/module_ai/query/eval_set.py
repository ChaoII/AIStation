"""问数评测：三张表（测试集 / 运行 / 逐题结果）+ 测试集 CRUD。

设计见 ``docs/superpowers/specs/2026-10-11-query-eval-module-design.md``。
建表沿用 ``_ensure_concept_table`` 的写法：幂等、DDL 内联、时间列不设默认
（写入时显式 ``now()``，兼容 SQLite 测试库）。
"""
from __future__ import annotations

import asyncio
import json

from app.core.database import async_db_session
from app.core.logger import log

_TESTCASE_DDL = (
    "CREATE TABLE IF NOT EXISTS ai_query_testcase ("
    "id BIGSERIAL PRIMARY KEY, question TEXT NOT NULL, gold_sql TEXT, "
    "datasource VARCHAR(32) DEFAULT 'system', difficulty VARCHAR(16), "
    "scenario VARCHAR(32), form VARCHAR(32), expected_metric VARCHAR(80), "
    "tags JSONB, verified BOOLEAN DEFAULT false, enabled BOOLEAN DEFAULT true, "
    "last_verified_at TIMESTAMP, notes TEXT, dataset VARCHAR(64) DEFAULT '', "
    "is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP, updated_time TIMESTAMP, UNIQUE(datasource, question))"
)

_TESTRUN_DDL = (
    "CREATE TABLE IF NOT EXISTS ai_query_testrun ("
    "id BIGSERIAL PRIMARY KEY, run_id VARCHAR(64) NOT NULL, mode VARCHAR(16) DEFAULT 'full', "
    "filter JSONB, config JSONB, ablation_group VARCHAR(64), status VARCHAR(16) DEFAULT 'running', "
    "total INT DEFAULT 0, done INT DEFAULT 0, summary JSONB, "
    "started_at TIMESTAMP, finished_at TIMESTAMP, is_deleted BOOLEAN DEFAULT false)"
)

_TESTRESULT_DDL = (
    "CREATE TABLE IF NOT EXISTS ai_query_testresult ("
    "id BIGSERIAL PRIMARY KEY, run_id VARCHAR(64) NOT NULL, testcase_id INT, question TEXT, "
    "ok BOOLEAN, is_error BOOLEAN, path VARCHAR(16), metric_key VARCHAR(80), sql TEXT, "
    "n_rows INT, took_ms INT, gold_match BOOLEAN, recall_hit JSONB, ontology_used JSONB, "
    "tool_calls JSONB, retries INT DEFAULT 0, trace JSONB, "
    "is_deleted BOOLEAN DEFAULT false, created_time TIMESTAMP)"
)


async def ensure_eval_tables() -> None:
    """建评测三张表（幂等）。"""
    from sqlalchemy import text as _t

    async with async_db_session.begin() as db:
        for ddl in (_TESTCASE_DDL, _TESTRUN_DDL, _TESTRESULT_DDL):
            await db.execute(_t(ddl))
        await db.execute(
            _t("CREATE INDEX IF NOT EXISTS ix_ai_query_testresult_run ON ai_query_testresult(run_id)")
        )
        await db.execute(
            _t("CREATE INDEX IF NOT EXISTS ix_ai_query_testcase_ds ON ai_query_testcase(datasource)")
        )
        # S1：既有库补 `dataset` 列（方言无关；SQLite 不支持 ADD COLUMN IF NOT EXISTS）
        await _ensure_column(db, "ai_query_testcase", "dataset", "VARCHAR(64) DEFAULT ''")


async def _ensure_column(db, table: str, col: str, ddl: str) -> None:
    """方言无关补列：仅当列不存在时 ALTER（PG/SQLite 均可用）。"""
    from sqlalchemy import inspect as _inspect
    from sqlalchemy import text as _t

    try:
        cols = await db.run_sync(
            lambda s: {c["name"] for c in _inspect(s.connection()).get_columns(table)}
        )
    except Exception:  # noqa: BLE001
        return
    if col not in cols:
        await db.execute(_t(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))


# ---------------------------------------------------------------------------
# 测试集 CRUD
# ---------------------------------------------------------------------------
_CASE_FIELDS = (
    "question", "gold_sql", "datasource", "difficulty", "scenario",
    "form", "expected_metric", "tags", "verified", "enabled", "notes", "dataset",
)


def _case_row(r) -> dict:
    notes = (r[11] if len(r) > 11 else "") or ""
    return {
        "id": r[0], "question": r[1], "gold_sql": r[2], "datasource": r[3],
        "difficulty": r[4], "scenario": r[5], "form": r[6], "expected_metric": r[7],
        "tags": r[8] if isinstance(r[8], list) else (json.loads(r[8]) if r[8] else []),
        "verified": bool(r[9]), "enabled": bool(r[10]),
        "notes": notes,
        # 评测数据集（S1）：用于组织「燃煤业务语义执行层评测集」等命名数据集
        "dataset": (r[12] if len(r) > 12 else "") or "",
        # 退化题（金标结果空/NULL/单值 0）：精度统计不计入分母
        "degenerate": "degenerate" in notes,
        # 指标快路径能答的题：它考的是"指标枚举"而非"模型生成 SQL"
        "metric_eligible": "metric" in notes.split(","),
        # 留出法分集（A/B）：错题沉淀只在 A 上做，评测只在 B 上跑，避免近义题泄漏
        "split": "B" if "split:B" in notes else ("A" if "split:A" in notes else ""),
    }


async def upsert_case(data: dict) -> dict:
    """按 id（优先）或 ``(datasource, question)`` 幂等写入/更新一条测试题。

    ⚠️ 必须支持按 id 更新：界面编辑时只该改这一行。旧实现只认
    ``UNIQUE(datasource, question)``，用户把题面改了就变成「新增一条 + 旧题残留」。
    """
    from sqlalchemy import text as _t

    await ensure_eval_tables()
    q = str(data.get("question") or "").strip()
    if not q:
        raise ValueError("question 不能为空")
    ds = str(data.get("datasource") or "system")
    params = {
        "q": q, "gold": str(data.get("gold_sql") or ""), "ds": ds,
        "difficulty": str(data.get("difficulty") or ""), "scenario": str(data.get("scenario") or ""),
        "form": str(data.get("form") or ""), "metric": str(data.get("expected_metric") or ""),
        "tags": json.dumps(data.get("tags") or [], ensure_ascii=False),
        "verified": bool(data.get("verified", False)), "enabled": bool(data.get("enabled", True)),
        "notes": str(data.get("notes") or ""),
        "dataset": str(data.get("dataset") or ""),
    }
    cid = data.get("id")
    async with async_db_session.begin() as db:
        if cid:
            res = await db.execute(
                _t(
                    "UPDATE ai_query_testcase SET question=:q, gold_sql=:gold, datasource=:ds, "
                    "difficulty=:difficulty, scenario=:scenario, form=:form, "
                    "expected_metric=:metric, tags=CAST(:tags AS jsonb), verified=:verified, "
                    "enabled=:enabled, notes=:notes, dataset=:dataset, updated_time=now() "
                    "WHERE id=:id AND is_deleted=false"
                ),
                {**params, "id": int(cid)},
            )
            if res.rowcount:
                return {"id": int(cid), "question": q, "datasource": ds}
        await db.execute(
            _t(
                "INSERT INTO ai_query_testcase"
                "(question,gold_sql,datasource,difficulty,scenario,form,expected_metric,"
                "tags,verified,enabled,notes,dataset,is_deleted,created_time,updated_time) "
                "VALUES (:q,:gold,:ds,:difficulty,:scenario,:form,:metric,"
                "CAST(:tags AS jsonb),:verified,:enabled,:notes,:dataset,false,now(),now()) "
                "ON CONFLICT (datasource,question) DO UPDATE SET gold_sql=EXCLUDED.gold_sql, "
                "difficulty=EXCLUDED.difficulty, scenario=EXCLUDED.scenario, form=EXCLUDED.form, "
                "expected_metric=EXCLUDED.expected_metric, tags=EXCLUDED.tags, "
                "verified=EXCLUDED.verified, enabled=EXCLUDED.enabled, notes=EXCLUDED.notes, "
                "dataset=EXCLUDED.dataset, "
                "is_deleted=false, updated_time=now()"
            ),
            params,
        )
    return {"question": q, "datasource": ds}


async def list_cases(
    datasource: str | None = None,
    difficulty: str | None = None,
    form: str | None = None,
    scenario: str | None = None,
    enabled: bool | None = None,
    dataset: str | None = None,
) -> list[dict]:
    """按条件列出测试题（均按 ``id`` 升序，保证确定性）。"""
    from sqlalchemy import text as _t

    await ensure_eval_tables()
    conds = ["is_deleted=false"]
    params: dict = {}
    if datasource:
        conds.append("datasource = :ds")
        params["ds"] = datasource
    if difficulty:
        conds.append("difficulty = :d")
        params["d"] = difficulty
    if form:
        conds.append("form = :f")
        params["f"] = form
    if scenario:
        conds.append("scenario = :s")
        params["s"] = scenario
    if enabled is not None:
        conds.append("enabled = :e")
        params["e"] = bool(enabled)
    if dataset:
        conds.append("dataset = :dset")
        params["dset"] = dataset
    async with async_db_session() as db:
        rows = (
            await db.execute(
                _t(
                    "SELECT id,question,gold_sql,datasource,difficulty,scenario,form,"
                    "expected_metric,tags,verified,enabled,notes,dataset FROM ai_query_testcase "
                    "WHERE " + " AND ".join(conds) + " ORDER BY id"
                ),
                params,
            )
        ).fetchall()
    return [_case_row(r) for r in rows]


async def delete_cases(ids: list[int]) -> int:
    """软删测试题，返回**实际删除条数**（旧实现直接返回请求数，删不存在的也会虚报）。"""
    from sqlalchemy import text as _t

    if not ids:
        return 0
    await ensure_eval_tables()
    # ⚠️ `WHERE id IN :ids` 传元组在 asyncpg 下是**语法错误**（旧实现一调用就 500）。
    # 这里显式拼占位符；id 已强制转 int，无注入风险。
    safe_ids = [int(i) for i in ids]
    placeholders = ", ".join(str(i) for i in safe_ids)
    async with async_db_session.begin() as db:
        res = await db.execute(
            _t(f"UPDATE ai_query_testcase SET is_deleted=true "
               f"WHERE id IN ({placeholders}) AND is_deleted=false")
        )
        return int(res.rowcount or 0)


async def import_cases(items: list[dict]) -> dict:
    """批量导入：缺 question/gold_sql 的跳过并计数。"""
    saved = skipped = 0
    for it in items or []:
        if not str(it.get("question") or "").strip() or not str(it.get("gold_sql") or "").strip():
            skipped += 1
            continue
        await upsert_case(it)
        saved += 1
    log.info(f"[ai-eval] 测试集导入：新增/更新 {saved} 条，跳过 {skipped} 条")
    return {"saved": saved, "skipped": skipped}


#: CSV 导入表头（顺序即无表头时的默认列序）
CASE_CSV_COLUMNS = ["question", "gold_sql", "datasource", "difficulty", "form",
                    "scenario", "dataset", "expected_metric"]


def parse_case_csv(text: str, default_datasource: str = "system") -> list[dict]:
    """解析 CSV/TSV 题库文本 → 题目字典列表。

    支持带表头（question,gold_sql,...）与无表头（按 CASE_CSV_COLUMNS 顺序）。
    旧实现只有 `import_cases()` 函数、没有解析与接口，界面上根本导不进题。
    """
    import csv
    import io

    raw = (text or "").strip()
    if not raw:
        return []
    # 自动识别分隔符（逗号/制表符）
    delim = "\t" if ("\t" in raw.split("\n", 1)[0] and "," not in raw.split("\n", 1)[0]) else ","
    rows = [r for r in csv.reader(io.StringIO(raw), delimiter=delim) if any(str(x).strip() for x in r)]
    if not rows:
        return []
    head = [str(h).strip().lower() for h in rows[0]]
    if "question" in head and "gold_sql" in head:
        cols = head
        body = rows[1:]
    else:
        cols = CASE_CSV_COLUMNS
        body = rows
    out: list[dict] = []
    for r in body:
        item = {c: (str(r[i]).strip() if i < len(r) else "") for i, c in enumerate(cols)}
        item.setdefault("datasource", default_datasource)
        if not item.get("datasource"):
            item["datasource"] = default_datasource
        out.append(item)
    return out


async def verify_cases(ids: list[int] | None = None, datasource: str | None = None,
                       dataset: str | None = None) -> dict:
    """校验金标 SQL：能执行且有行（非全 NULL）→ verified=true。

    结果写回 `verified / last_verified_at`，并返回逐题明细，供界面提示
    「哪些题的金标已经跑不通了」（以前只能靠生成流程校验，人工改题后无法复核）。
    """
    from app.core.database import async_db_session

    from .service import SYSTEM_DS, _execute_custom_ds_sql, _execute_sql

    cases = await list_cases(datasource=datasource, dataset=dataset)
    if ids:
        want = {int(i) for i in ids}
        cases = [c for c in cases if int(c["id"]) in want]
    items: list[dict] = []
    passed = failed = 0
    for c in cases:
        sql = str(c.get("gold_sql") or "").strip().rstrip(";")
        ds = c.get("datasource") or SYSTEM_DS
        ok, rows_n, err = False, 0, ""
        if not sql:
            err = "缺少金标 SQL"
        else:
            try:
                if ds == SYSTEM_DS:
                    # 用独立任务执行：系统 SQL 走的是请求作用域会话，一旦报错会污染整个请求
                    # 的事务（后续写回/查询全部 "current transaction is aborted"）。
                    # 新任务会拿到自己的会话（见 DBSessionMiddleware 的 owner-task 判定）。
                    res = await asyncio.create_task(_execute_sql(sql))
                else:
                    res = await _execute_custom_ds_sql(int(str(ds).split(":")[-1]), sql)
                rows = res.get("rows") or []
                rows_n = len(rows)
                flat = [v for r in rows for v in (r if isinstance(r, (list, tuple)) else [r])]
                ok = bool(rows) and not all(v is None for v in flat)
                if not ok:
                    err = "空结果（金标无法出数）"
            except Exception as e:  # noqa: BLE001
                err = str(e)[:200]
        # 写回校验状态（请求作用域会话：用 commit，不能嵌套 begin）
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            await db.execute(
                _t("UPDATE ai_query_testcase SET verified=:v, last_verified_at=now(), "
                   "updated_time=now() WHERE id=:i"),
                {"v": ok, "i": int(c["id"])},
            )
            await db.commit()
        if ok:
            passed += 1
        else:
            failed += 1
        items.append({"id": c["id"], "question": c["question"], "ok": ok,
                      "rows": rows_n, "error": err})
    return {"total": len(cases), "passed": passed, "failed": failed, "items": items[:200]}


async def load_results(run_id: str) -> list[dict]:
    """读回某轮的逐题结果（含 trace 关键字段），供报表聚合。"""
    from sqlalchemy import text as _t

    await ensure_eval_tables()
    async with async_db_session() as db:
        rows = (
            await db.execute(
                _t(
                    "SELECT testcase_id,question,ok,is_error,path,metric_key,sql,n_rows,took_ms,"
                    "gold_match,recall_hit,ontology_used,tool_calls,retries,trace "
                    "FROM ai_query_testresult WHERE run_id=:r AND is_deleted=false ORDER BY id"
                ),
                {"r": run_id},
            )
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        recall = 0.0
        try:
            import json as _j

            rh = r[10] if isinstance(r[10], dict) else _j.loads(r[10] or "{}")
            exp, rec = set(rh.get("expected") or []), rh.get("recalled") or []
            recall = (len(exp & set(rec)) / len(exp)) if exp else 1.0
        except Exception:  # noqa: BLE001
            recall = 0.0
        tr = r[14] if isinstance(r[14], dict) else {}
        out.append({
            "testcase_id": r[0], "question": r[1], "ok": bool(r[2]), "is_error": bool(r[3]),
            "path": r[4], "metric_key": r[5] or "", "sql": r[6] or "", "n_rows": r[7] or 0,
            "took_ms": r[8] or 0, "gold_match": bool(r[9]), "recall": recall,
            "ontology_used": r[11], "tool_calls": r[12], "retries": r[13] or 0,
            "difficulty": (tr or {}).get("difficulty"), "scenario": (tr or {}).get("scenario"),
            "form": (tr or {}).get("form"), "datasource": (tr or {}).get("datasource"),
            # 语义准确率的分母需要它；早期漏存 → 报表里 semantic_accuracy 恒为 0（实测踩坑）
            "expected_metric": (tr or {}).get("expected_metric") or "",
            # 退化题（金标为空/NULL/单值 0）：不计入精度分母
            "degenerate": bool((tr or {}).get("degenerate")),
            # 指标快路径能答的题：与"生成题"分开统计
            "metric_eligible": bool((tr or {}).get("metric_eligible")),
        })
    return out


async def list_result_brief(run_id: str) -> list[dict]:
    """逐题进度（轻量）：运行中实时表用，不带 trace/召回等大字段。"""
    from sqlalchemy import text as _t

    await ensure_eval_tables()
    async with async_db_session() as db:
        rows = (await db.execute(
            _t(
                "SELECT testcase_id,question,ok,is_error,path,n_rows,took_ms,gold_match "
                "FROM ai_query_testresult WHERE run_id=:r AND is_deleted=false ORDER BY id"
            ),
            {"r": run_id},
        )).fetchall()
    return [
        {"testcase_id": r[0], "question": r[1], "ok": bool(r[2]), "is_error": bool(r[3]),
         "path": r[4] or "", "n_rows": r[5] or 0, "took_ms": r[6] or 0,
         "gold_match": bool(r[7])}
        for r in rows
    ]


async def list_runs(limit: int = 30, mode: str | None = None,
                    dataset: str | None = None) -> list[dict]:
    """历史运行列表（最近在前）。

    ``mode`` 用于把「单轮评测 full」与「消融 ablation / 方差 variance / 消融组」分开列：
    它们的结果表口径不同，混在一个列表里点「查看报表」会看到空报表。
    """
    from sqlalchemy import text as _t

    await ensure_eval_tables()
    conds = ["is_deleted=false"]
    params: dict = {"n": int(limit)}
    if mode:
        # full 模式也包含老数据里 mode 为空的行
        conds.append("(mode = :m OR (:m = 'full' AND coalesce(mode,'') = ''))")
        params["m"] = mode
    if dataset:
        conds.append("(filter->>'dataset') = :dset")
        params["dset"] = dataset
    async with async_db_session() as db:
        rows = (
            await db.execute(
                _t(
                    "SELECT run_id,mode,ablation_group,status,total,done,started_at,finished_at,summary "
                    "FROM ai_query_testrun WHERE " + " AND ".join(conds) +
                    " ORDER BY id DESC LIMIT :n"
                ),
                params,
            )
        ).fetchall()
    return [
        {"run_id": r[0], "mode": r[1], "ablation_group": r[2], "status": r[3],
         "total": r[4], "done": r[5], "started_at": str(r[6] or ""), "finished_at": str(r[7] or ""),
         "summary": r[8] if isinstance(r[8], dict) else None}
        for r in rows
    ]
