"""自定义报表模板：表 / CRUD / 执行。

定位（见 spec）：把**困难题**从"每次靠模型现推"变成"**一次沉淀、长期复用**"。
与指标（`ai_query_metrics`）的关系：**共用执行链路**（参数渲染 / 白名单校验 /
标识符加引号 / 数据源执行），报表只多「多列 + 列定义 + 图表」，
且**不进快路径自动匹配**（由用户显式选择或澄清后选择）。
"""
from __future__ import annotations

import json
import re
import uuid

from app.core.logger import log

#: 模板占位符：`{key}`（与 service._render_template 保持一致）
_PARAM_RE = re.compile(r"\{(\w+)\}")

#: 常见参数 key → 中文标签（没有命中就用 key 本身，不硬猜）
_LABELS = {
    "start": "起始", "end": "结束", "start_date": "起始日期", "end_date": "结束日期",
    "begin": "起始", "finish": "结束", "date": "日期", "day": "日期",
    "year": "年份", "month": "月份", "quarter": "季度",
    "limit": "条数", "top": "条数", "offset": "偏移",
    "dept": "部门", "dept_id": "部门", "org": "组织", "org_id": "组织",
    "device": "设备", "device_id": "设备", "camera": "摄像头", "camera_id": "摄像头",
    "keyword": "关键字", "name": "名称", "status": "状态", "type": "类型",
}


def _infer_type(template: str, start: int) -> str:
    """推断参数类型：引号内 → 文本；`LIMIT/OFFSET` 或紧邻比较符 → 数值。

    只做**可解释**的推断，猜不准就回退文本（宁宽松不误判）。
    """
    head = template[:start]
    line = head.rsplit("\n", 1)[-1]
    if line.count("'") % 2 == 1:
        return "text"
    if re.search(r"(?i)(limit|offset)\s*$", head.rstrip()):
        return "number"
    if re.search(r"(?:>=|<=|<>|!=|>|<|=)\s*$", head.rstrip()):
        return "number"
    return "text"


def extract_params(sql_template: str) -> list[dict]:
    """从 SQL 模板抽取参数定义（按出现顺序去重）。

    报表参数原来是"永远为空"的死表单：`存为报表` 不带 params，运行弹窗永远显示
    "该报表无需参数"。这里让**模板自己说明它需要什么参数**，形成闭环。
    """
    defs: list[dict] = []
    seen: set[str] = set()
    for m in _PARAM_RE.finditer(sql_template or ""):
        key = m.group(1)
        if key in seen:
            continue
        seen.add(key)
        defs.append({
            "key": key,
            "label": _LABELS.get(key.lower(), key),
            "type": _infer_type(sql_template, m.start()),
            "required": True,
            "default": "",
        })
    return defs


def validate_params(defs: list[dict] | None, params: dict | None) -> dict:
    """运行前校验参数：缺必填 / 空值 / 类型不符 → 明确报错（不把 `{key}` 发给数据库）。"""
    from app.core.exceptions import CustomException

    out: dict = {}
    for d in defs or []:
        key = str(d.get("key") or "").strip()
        if not key:
            continue
        label = d.get("label") or key
        val = (params or {}).get(key)
        if val is None or (isinstance(val, str) and not val.strip()):
            val = d.get("default")
        if val is None or (isinstance(val, str) and not val.strip()):
            if d.get("required", True):
                raise CustomException(msg=f"缺少必填参数「{label}」")
            continue
        if d.get("type") == "number":
            s = str(val).strip()
            if not re.fullmatch(r"-?\d+(?:\.\d+)?", s):
                raise CustomException(msg=f"参数「{label}」必须是数字")
            out[key] = s
        else:
            out[key] = str(val).strip()
    return out

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
    sql_template = str(data.get("sql_template") or "")
    # 参数：显式给了就用给的（人工可覆盖），否则**从模板自动抽取**（否则运行表单永远是死的）
    params = data.get("params")
    if not params:
        params = extract_params(sql_template)
    common = {
        "k": key, "n": str(data.get("name") or key), "d": str(data.get("description") or ""),
        "ds": str(data.get("datasource") or "system"), "q": str(data.get("question") or ""),
        "p": json.dumps(params, ensure_ascii=False),
        "sql": sql_template,
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
    # 参数闭环：先校验（缺必填/类型不符 → 明确报错），再渲染；渲染后兜底查残留占位符
    defs = rep.get("params") or extract_params(rep.get("sql_template") or "")
    values = validate_params(defs, params)
    sql = _render_template(rep.get("sql_template") or "", values)
    leftover = _PARAM_RE.search(sql)
    if leftover:
        from app.core.exceptions import CustomException

        raise CustomException(msg=f"参数「{leftover.group(1)}」未提供，无法执行")
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
