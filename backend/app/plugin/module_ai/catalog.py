"""共享数据目录接口。

**边界约定**：表/字段的"治理信息"（中文名、业务域、敏感标记、是否纳入范围、
业务概念）是**共用资产**，问数与本体**都只通过本模块读写**，
不允许互相直读对方的表（历史上本体直读了 `ai_query_concept` /
`ai_query_asset_columns`，方向反了，已收敛到这里）。
"""
from __future__ import annotations

import json

from app.core.logger import log


async def _rows(sql: str, **params):
    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session() as db:
        return (await db.execute(text(sql), params)).fetchall()


def _as_list(v) -> list[str]:
    """jsonb 列可能是 list，也可能是 JSON 字符串。"""
    if isinstance(v, list):
        return [str(x) for x in v]
    if not v:
        return []
    try:
        out = json.loads(v)
        return [str(x) for x in out] if isinstance(out, list) else []
    except Exception:  # noqa: BLE001
        return []


async def list_concepts() -> list[dict]:
    """业务概念（含同义词、指标映射、关联表）。"""
    try:
        rows = await _rows(
            "SELECT name, description, synonyms, domain, metric_key, tables "
            "FROM ai_query_concept WHERE is_deleted=false ORDER BY id"
        )
    except Exception as e:  # noqa: BLE001
        log.warning(f"[catalog] 读取业务概念失败: {str(e)[:120]}")
        return []
    return [
        {
            "name": (r[0] or "").strip(),
            "description": r[1] or "",
            "synonyms": r[2] or "",
            "domain": r[3] or "",
            "metric_key": r[4] or "",
            "tables": _as_list(r[5]),
        }
        for r in rows
        if (r[0] or "").strip()
    ]


async def list_sensitive_columns() -> set[tuple[str, str]]:
    """目录侧已标记敏感的 (表, 字段)。"""
    try:
        rows = await _rows(
            "SELECT COALESCE(table_name,''), COALESCE(column_name,'') "
            "FROM ai_query_asset_columns WHERE is_deleted=false AND sensitive=true"
        )
    except Exception as e:  # noqa: BLE001
        log.warning(f"[catalog] 读取敏感标记失败: {str(e)[:120]}")
        return set()
    return {(str(t), str(c)) for t, c in rows if t and c}


async def mark_sensitive(pairs: list[tuple[str, str]] | set[tuple[str, str]]) -> int:
    """把 (表, 字段) 标记为敏感；**幂等**（只更新原本未标记的行），返回新增行数。"""
    todo = [(str(t), str(c)) for t, c in (pairs or []) if t and c]
    if not todo:
        return 0
    from sqlalchemy import text

    from app.core.database import async_db_session

    changed = 0
    async with async_db_session.begin() as db:
        for t, c in todo:
            r = await db.execute(
                text(
                    "UPDATE ai_query_asset_columns SET sensitive=true "
                    "WHERE is_deleted=false AND table_name=:t AND column_name=:c "
                    "AND sensitive=false"
                ),
                {"t": t, "c": c},
            )
            changed += int(getattr(r, "rowcount", 0) or 0)
    return changed


async def included_tables() -> set[str]:
    """**已纳入问数范围**的表 —— 表范围的单一真源。"""
    try:
        rows = await _rows(
            "SELECT table_name FROM ai_query_assets WHERE is_deleted=false AND included=true"
        )
    except Exception as e:  # noqa: BLE001
        log.warning(f"[catalog] 读取范围表失败: {str(e)[:120]}")
        return set()
    return {str(r[0]) for r in rows}


async def log_writeback(*, action_name: str, object_table: str, object_key: str,
                        params: dict | None = None, operator: str = "",
                        result: str = "", detail: str = "",
                        raise_on_error: bool = False) -> int:
    """写一条「动作回写」审计记录（``ai_query_writeback_log``），返回新行 id。

    ``ai_query_writeback_log`` 由本目录统一拥有：本体**只经本接口写**，
    不再直写问数的表（直写会让本体的反向依赖复活，见模块 docstring）。

    - ``params`` 为 ``None`` 时写 NULL（与历史行为一致），而非 ``{}``；
    - ``raise_on_error=False``（默认）时吞掉异常并返回 0 —— 审计写入不该拖垮主流程；
      历史上有调用点依赖「写失败即抛」，这类调用传 ``raise_on_error=True`` 保持原语义；
    - 依赖 ``INSERT ... RETURNING id``（PostgreSQL / SQLite 3.35+；MySQL 不支持）。
    """
    from sqlalchemy import text

    from app.core.database import async_db_session

    try:
        async with async_db_session.begin() as db:
            res = await db.execute(
                text(
                    "INSERT INTO ai_query_writeback_log"
                    "(action_name,object_table,object_key,params,operator,result,detail) "
                    "VALUES (:n,:t,:k,:p,:o,:r,:d) RETURNING id"
                ),
                {
                    "n": action_name, "t": object_table, "k": str(object_key),
                    "p": json.dumps(params, ensure_ascii=False) if params is not None else None,
                    "o": operator or "", "r": result, "d": (detail or "")[:500],
                },
            )
            return int(res.scalar() or 0)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[catalog] 写回写审计失败: {str(e)[:120]}")
        if raise_on_error:
            raise
        return 0


async def last_writeback_id() -> int:
    """最近一条回写审计记录的 id（本体执行「决定」后回填 ``execution_id`` 用）。"""
    try:
        rows = await _rows(
            "SELECT id FROM ai_query_writeback_log WHERE object_table<>'' "
            "ORDER BY id DESC LIMIT 1"
        )
    except Exception as e:  # noqa: BLE001
        log.warning(f"[catalog] 读取最近回写 id 失败: {str(e)[:120]}")
        return 0
    return int(rows[0][0]) if rows else 0


async def list_writebacks(limit: int = 60) -> list[dict]:
    """最近若干条回写审计记录（活动时间线等展示用）。

    与 ``log_writeback``/``count_writebacks`` 同属本目录对 ``ai_query_writeback_log``
    的统一出口：调用方**不直读**该表（历史上有模块直接写 SQL 读它）。
    """
    try:
        rows = await _rows(
            "SELECT action_name, object_table, object_key, result, operator, created_time "
            "FROM ai_query_writeback_log WHERE is_deleted=false ORDER BY id DESC LIMIT :n",
            n=max(1, min(int(limit or 60), 500)),
        )
    except Exception as e:  # noqa: BLE001
        log.warning(f"[catalog] 读取回写审计失败: {str(e)[:120]}")
        return []
    return [
        {
            "action_name": r[0] or "",
            "object_table": r[1] or "",
            "object_key": str(r[2] or ""),
            "result": r[3] or "",
            "operator": str(r[4] or ""),
            "created_time": str(r[5]) if r[5] else "",
        }
        for r in rows
    ]


async def count_writebacks(object_table: str | None = None,
                           result: str | None = None) -> int:
    """回写审计条数（可按对象/结果过滤）——供本体侧统计与统一审计展示。"""
    try:
        where = ["is_deleted=false"]
        params: dict = {}
        if object_table:
            where.append("object_table=:c")
            params["c"] = object_table
        if result:
            where.append("result=:r")
            params["r"] = result
        rows = await _rows(
            "SELECT count(*) FROM ai_query_writeback_log WHERE " + " AND ".join(where),
            **params,
        )
    except Exception as e:  # noqa: BLE001
        log.warning(f"[catalog] 统计回写条数失败: {str(e)[:120]}")
        return 0
    return int(rows[0][0]) if rows else 0
