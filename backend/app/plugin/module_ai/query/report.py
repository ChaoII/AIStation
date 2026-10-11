"""自定义报表模板：表 / CRUD / 执行。

定位（见 spec）：把**困难题**从"每次靠模型现推"变成"**一次沉淀、长期复用**"。
与指标（`ai_query_metrics`）的关系：**共用执行链路**（参数渲染 / 白名单校验 /
标识符加引号 / 数据源执行），报表只多「多列 + 列定义 + 图表」，
且**不进快路径自动匹配**（由用户显式选择或澄清后选择）。
"""
from __future__ import annotations

import json
import uuid

from app.core.logger import log

_DDL = (
    "CREATE TABLE IF NOT EXISTS ai_query_reports ("
    "id SERIAL PRIMARY KEY, key VARCHAR(64) NOT NULL, name VARCHAR(120) NOT NULL, "
    "description TEXT, datasource VARCHAR(32) NOT NULL DEFAULT 'system', "
    "question TEXT, params JSONB, sql_template TEXT NOT NULL, columns JSONB, chart JSONB, "
    "verified BOOLEAN NOT NULL DEFAULT false, enabled BOOLEAN NOT NULL DEFAULT true, "
    "sort INT NOT NULL DEFAULT 100, "
    "uuid VARCHAR(64) NOT NULL, status VARCHAR(8) NOT NULL DEFAULT '0', "
    "is_deleted BOOLEAN NOT NULL DEFAULT false, "
    "created_time TIMESTAMP, updated_time TIMESTAMP, "
    "created_id INT, updated_id INT)"
)


async def ensure_report_tables() -> None:
    """建表（幂等）。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session.begin() as db:
        await db.execute(text(_DDL))


def _row(r) -> dict:
    return {
        "id": r[0], "key": r[1], "name": r[2], "description": r[3] or "",
        "datasource": r[4] or "system", "question": r[5] or "",
        "params": r[6] if isinstance(r[6], list) else (json.loads(r[6]) if r[6] else []),
        "sql_template": r[7] or "",
        "columns": r[8] if isinstance(r[8], list) else (json.loads(r[8]) if r[8] else []),
        "chart": r[9] if isinstance(r[9], dict) else (json.loads(r[9]) if r[9] else {}),
        "verified": bool(r[10]), "enabled": bool(r[11]), "sort": r[12] or 0,
    }


_COLS = ("id,key,name,description,datasource,question,params,sql_template,columns,chart,"
         "verified,enabled,sort")


async def list_reports(datasource: str | None = None, verified_only: bool = False) -> list[dict]:
    from sqlalchemy import text

    from app.core.database import async_db_session

    await ensure_report_tables()
    conds = ["is_deleted=false"]
    params: dict = {}
    if datasource:
        conds.append("datasource=:d")
        params["d"] = datasource
    if verified_only:
        conds.append("verified=true")
    async with async_db_session() as db:
        rows = (
            await db.execute(
                text(f"SELECT {_COLS} FROM ai_query_reports WHERE {' AND '.join(conds)} "
                     "ORDER BY sort, id"),
                params,
            )
        ).fetchall()
    return [_row(r) for r in rows]


async def get_report(report_id: int) -> dict | None:
    from sqlalchemy import text

    from app.core.database import async_db_session

    await ensure_report_tables()
    async with async_db_session() as db:
        r = (
            await db.execute(
                text(f"SELECT {_COLS} FROM ai_query_reports WHERE id=:i AND is_deleted=false"),
                {"i": report_id},
            )
        ).fetchone()
    return _row(r) if r else None


async def upsert_report(data: dict, auth=None) -> dict:
    """按 `key` 幂等写入/更新报表模板。"""
    from sqlalchemy import text

    from app.core.database import async_db_session

    await ensure_report_tables()
    key = str(data.get("key") or "").strip()
    if not key:
        raise ValueError("key 不能为空")
    uid = getattr(getattr(auth, "user", None), "id", None)
    common = {
        "k": key, "n": str(data.get("name") or key), "d": str(data.get("description") or ""),
        "ds": str(data.get("datasource") or "system"), "q": str(data.get("question") or ""),
        "p": json.dumps(data.get("params") or [], ensure_ascii=False),
        "sql": str(data.get("sql_template") or ""),
        "cols": json.dumps(data.get("columns") or [], ensure_ascii=False),
        "ch": json.dumps(data.get("chart") or {}, ensure_ascii=False),
        "v": bool(data.get("verified", False)), "en": bool(data.get("enabled", True)),
        "so": int(data.get("sort") or 100), "uid": uid,
    }
    async with async_db_session.begin() as db:
        existing = (
            await db.execute(
                text("SELECT id FROM ai_query_reports WHERE key=:k AND is_deleted=false"),
                {"k": key},
            )
        ).fetchone()
        if existing:
            await db.execute(
                text(
                    "UPDATE ai_query_reports SET name=:n, description=:d, datasource=:ds, "
                    "question=:q, params=CAST(:p AS jsonb), sql_template=:sql, "
                    "columns=CAST(:cols AS jsonb), chart=CAST(:ch AS jsonb), verified=:v, "
                    "enabled=:en, sort=:so, updated_id=:uid, updated_time=CURRENT_TIMESTAMP WHERE id=:i"
                ),
                {**common, "i": existing[0]},
            )
            rid = existing[0]
        else:
            await db.execute(
                text(
                    "INSERT INTO ai_query_reports(key,name,description,datasource,question,params,"
                    "sql_template,columns,chart,verified,enabled,sort,uuid,status,is_deleted,"
                    "created_time,updated_time,created_id,updated_id) "
                    "VALUES(:k,:n,:d,:ds,:q,CAST(:p AS jsonb),:sql,CAST(:cols AS jsonb),"
                    "CAST(:ch AS jsonb),:v,:en,:so,:uuid,'0',false,CURRENT_TIMESTAMP,"
                    "CURRENT_TIMESTAMP,:uid,:uid)"
                ),
                {**common, "uuid": uuid.uuid4().hex},
            )
            # 不用 RETURNING（测试库兼容性）：插完回查
            rid = (
                await db.execute(
                    text("SELECT id FROM ai_query_reports WHERE key=:k AND is_deleted=false"),
                    {"k": key},
                )
            ).scalar()
    return {"id": rid, "key": key}


async def delete_reports(ids: list[int]) -> int:
    from sqlalchemy import text

    from app.core.database import async_db_session

    if not ids:
        return 0
    await ensure_report_tables()
    async with async_db_session.begin() as db:
        r = await db.execute(
            text(
                "UPDATE ai_query_reports SET is_deleted=true, updated_time=CURRENT_TIMESTAMP "
                "WHERE id = ANY(:ids)"
            ),
            {"ids": list(ids)},
        )
    return int(getattr(r, "rowcount", 0) or 0)


async def run_report(report_id: int, params: dict | None = None, auth=None) -> dict:
    """带参数执行报表（**复用指标执行链路**：渲染 → 校验 → 加引号 → 执行）。"""
    from .service import (
        SYSTEM_DS, _execute_custom_ds_sql, _execute_sql, _render_template, _system_allowed,
        validate_sql,
    )

    rep = await get_report(report_id)
    if not rep:
        raise ValueError("报表不存在")
    sql = _render_template(rep["sql_template"], params or {})
    ds = rep["datasource"] or SYSTEM_DS
    if ds == SYSTEM_DS:
        sql = validate_sql(sql, await _system_allowed())
        res = await _execute_sql(sql)
    else:
        res = await _execute_custom_ds_sql(int(str(ds).split(":")[-1]), sql, auth)
    log.info(f"[report] 执行 {rep['key']} → {len(res.get('rows') or [])} 行")
    return {
        "id": rep["id"], "key": rep["key"], "name": rep["name"],
        "sql": res.get("sql") or sql,
        "columns": res.get("columns") or [],
        "rows": res.get("rows") or [],
        "took_ms": res.get("took_ms", 0),
    }
