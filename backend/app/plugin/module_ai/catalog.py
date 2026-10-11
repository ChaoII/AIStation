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
