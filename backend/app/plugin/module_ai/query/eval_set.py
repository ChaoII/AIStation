"""问数评测：三张表（测试集 / 运行 / 逐题结果）+ 测试集 CRUD。

设计见 ``docs/superpowers/specs/2026-10-11-query-eval-module-design.md``。
建表沿用 ``_ensure_concept_table`` 的写法：幂等、DDL 内联、时间列不设默认
（写入时显式 ``now()``，兼容 SQLite 测试库）。
"""
from __future__ import annotations

import json

from app.core.database import async_db_session
from app.core.logger import log

_TESTCASE_DDL = (
    "CREATE TABLE IF NOT EXISTS ai_query_testcase ("
    "id BIGSERIAL PRIMARY KEY, question TEXT NOT NULL, gold_sql TEXT, "
    "datasource VARCHAR(32) DEFAULT 'system', difficulty VARCHAR(16), "
    "scenario VARCHAR(32), form VARCHAR(32), expected_metric VARCHAR(80), "
    "tags JSONB, verified BOOLEAN DEFAULT false, enabled BOOLEAN DEFAULT true, "
    "last_verified_at TIMESTAMP, notes TEXT, is_deleted BOOLEAN DEFAULT false, "
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


# ---------------------------------------------------------------------------
# 测试集 CRUD
# ---------------------------------------------------------------------------
_CASE_FIELDS = (
    "question", "gold_sql", "datasource", "difficulty", "scenario",
    "form", "expected_metric", "tags", "verified", "enabled", "notes",
)


def _case_row(r) -> dict:
    return {
        "id": r[0], "question": r[1], "gold_sql": r[2], "datasource": r[3],
        "difficulty": r[4], "scenario": r[5], "form": r[6], "expected_metric": r[7],
        "tags": r[8] if isinstance(r[8], list) else (json.loads(r[8]) if r[8] else []),
        "verified": bool(r[9]), "enabled": bool(r[10]),
    }


async def upsert_case(data: dict) -> dict:
    """按 ``(datasource, question)`` 幂等写入/更新一条测试题。"""
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
    }
    async with async_db_session.begin() as db:
        await db.execute(
            _t(
                "INSERT INTO ai_query_testcase"
                "(question,gold_sql,datasource,difficulty,scenario,form,expected_metric,"
                "tags,verified,enabled,notes,is_deleted,created_time,updated_time) "
                "VALUES (:q,:gold,:ds,:difficulty,:scenario,:form,:metric,"
                "CAST(:tags AS jsonb),:verified,:enabled,:notes,false,now(),now()) "
                "ON CONFLICT (datasource,question) DO UPDATE SET gold_sql=EXCLUDED.gold_sql, "
                "difficulty=EXCLUDED.difficulty, scenario=EXCLUDED.scenario, form=EXCLUDED.form, "
                "expected_metric=EXCLUDED.expected_metric, tags=EXCLUDED.tags, "
                "verified=EXCLUDED.verified, enabled=EXCLUDED.enabled, notes=EXCLUDED.notes, "
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
    async with async_db_session() as db:
        rows = (
            await db.execute(
                _t(
                    "SELECT id,question,gold_sql,datasource,difficulty,scenario,form,"
                    "expected_metric,tags,verified,enabled FROM ai_query_testcase "
                    "WHERE " + " AND ".join(conds) + " ORDER BY id"
                ),
                params,
            )
        ).fetchall()
    return [_case_row(r) for r in rows]


async def delete_cases(ids: list[int]) -> int:
    """软删测试题。"""
    from sqlalchemy import text as _t

    if not ids:
        return 0
    await ensure_eval_tables()
    async with async_db_session.begin() as db:
        await db.execute(
            _t("UPDATE ai_query_testcase SET is_deleted=true WHERE id IN :ids"),
            {"ids": tuple(int(i) for i in ids)},
        )
    return len(ids)


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
        })
    return out


async def list_runs(limit: int = 30) -> list[dict]:
    """历史运行列表（最近在前）。"""
    from sqlalchemy import text as _t

    await ensure_eval_tables()
    async with async_db_session() as db:
        rows = (
            await db.execute(
                _t(
                    "SELECT run_id,mode,ablation_group,status,total,done,started_at,finished_at,summary "
                    "FROM ai_query_testrun WHERE is_deleted=false ORDER BY id DESC LIMIT :n"
                ),
                {"n": int(limit)},
            )
        ).fetchall()
    return [
        {"run_id": r[0], "mode": r[1], "ablation_group": r[2], "status": r[3],
         "total": r[4], "done": r[5], "started_at": str(r[6] or ""), "finished_at": str(r[7] or ""),
         "summary": r[8] if isinstance(r[8], dict) else None}
        for r in rows
    ]
