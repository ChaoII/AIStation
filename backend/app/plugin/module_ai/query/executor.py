"""智能问数：自定义数据源连接与执行（阶段B）。

支持 PostgreSQL / MySQL / SQLite 的只读连接、表结构探查、SQL 执行。
file / api 类型不支持自由 SQL，请用「指标模板」方式查询。
"""
from __future__ import annotations

import time

from sqlalchemy import text

from app.core.exceptions import CustomException

MAX_ROWS = 1000
QUERY_TIMEOUT = 10


def _url(cfg: dict) -> str | None:
    import urllib.parse

    t = cfg.get("type") or "postgres"
    host = cfg.get("host") or ""
    port = cfg.get("port") or 0
    db = cfg.get("database") or ""
    user = cfg.get("username") or ""
    pwd = urllib.parse.quote(cfg.get("password") or "")
    if t == "postgres":
        return f"postgresql+asyncpg://{user}:{pwd}@{host}:{port}/{db}"
    if t == "mysql":
        return f"mysql+asyncmy://{user}:{pwd}@{host}:{port}/{db}"
    if t == "sqlite":
        return f"sqlite+aiosqlite:///{db}"
    return None


def build_engine(cfg: dict):
    from sqlalchemy.ext.asyncio import create_async_engine

    url = _url(cfg)
    if not url:
        raise CustomException(msg=f"数据源类型「{cfg.get('type')}」不支持自由 SQL，请用指标模板查询")
    return create_async_engine(url, echo=False, pool_pre_ping=True, pool_size=3)


async def test_connection(cfg: dict) -> dict:
    """测试连接：成功返回 ok；失败返回错误信息。"""
    if (cfg.get("type") or "") == "api":
        return {"ok": True, "message": "HTTP 接口数据源，使用指标模板查询"}
    eng = build_engine(cfg)
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": str(e)}
    finally:
        await eng.dispose()
    return {"ok": True, "message": "连接成功"}


async def execute_select(cfg: dict, sql: str) -> dict:
    """对数据源执行只读 SELECT。

    驱动/语法异常**必须包装成 ``CustomException``**：上层（``ask`` 的快路径）
    只认 ``CustomException`` 才会「记录错误 → 回退慢路径」；
    裸 ``ProgrammingError`` 会直接冒泡把整题打崩（实测 ds:4 未加引号时就是这样）。
    """
    eng = build_engine(cfg)
    start = time.time()
    try:
        async with eng.connect() as conn:
            result = await conn.execute(text(sql))
            rows = result.fetchall()
            cols = list(result.keys())
    except Exception as e:  # noqa: BLE001
        raise CustomException(msg=f"数据源执行失败：{str(e)[:300]}") from e
    finally:
        await eng.dispose()
    # 必须带 `took_ms`：调用方（_slow_path）会读它，缺了就是 KeyError
    # ——外部数据源问数整条路会直接 400（真实踩过）。
    return {"columns": cols,
            "rows": [[_json_cell(v) for v in r] for r in rows[:MAX_ROWS]],
            "took_ms": int((time.time() - start) * 1000)}


def _json_cell(v):
    """把返回值转成 JSON 安全类型（Decimal→float、日期→iso 等）。"""
    if v is None:
        return None
    if isinstance(v, bool) or isinstance(v, (int, float, str)):
        return v
    from decimal import Decimal

    if isinstance(v, Decimal):
        return float(v)
    from datetime import date, datetime, time

    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_json_cell(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _json_cell(x) for k, x in v.items()}
    return str(v)


async def introspect_schema(cfg: dict) -> list[dict]:
    """探查表与字段，返回 [{table, columns:[{name,type,comment,is_sensitive}]}]。"""
    db_type = cfg.get("type") or "postgres"
    eng = build_engine(cfg)
    try:
        async with eng.connect() as conn:
            if db_type == "postgres":
                rows = (await conn.execute(text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema='public' ORDER BY table_name"
                ))).fetchall()
                tables = [r[0] for r in rows]
                out = []
                for t in tables:
                    # **注释才是语义**：真实业务库的表/列名常是英文缩写
                    # （FUEL_CB_COALBALANCE / COALMONEY），中文注释（"燃煤采购结算主表"
                    # / "煤款金额"）是"人话 → 字段"唯一的桥。
                    # 旧实现把 `column_default`（默认值）塞进 comment 字段，
                    # 于是注释**从来没被读过**；导入本体后属性名全是英文，
                    # 问数只能瞎猜（实测编出 coal_amount 这种不存在的列）。
                    cols = (await conn.execute(text(
                        "SELECT c.column_name, c.data_type, "
                        "COALESCE(col_description("
                        "  (quote_ident(c.table_schema)||'.'||quote_ident(c.table_name))::regclass,"
                        "  c.ordinal_position)::text, '') AS comment "
                        "FROM information_schema.columns c "
                        "WHERE c.table_schema='public' AND c.table_name=:t "
                        "ORDER BY c.ordinal_position"
                    ), {"t": t})).fetchall()
                    tcmt = (await conn.execute(text(
                        "SELECT COALESCE(obj_description("
                        "  (quote_ident(:s)||'.'||quote_ident(:t))::regclass)::text, '')"
                    ), {"s": "public", "t": t})).scalar() or ""
                    out.append({
                        "table": t,
                        "comment": tcmt,
                        "columns": [
                            {"name": c[0], "type": c[1], "comment": c[2],
                             "is_sensitive": False}
                            for c in cols
                        ],
                    })
                return out
            if db_type == "mysql":
                rows = (await conn.execute(text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema=DATABASE() ORDER BY table_name"
                ))).fetchall()
                out = []
                for t in [r[0] for r in rows]:
                    cols = (await conn.execute(text(
                        "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_schema=DATABASE() AND table_name=:t ORDER BY ordinal_position"
                    ), {"t": t})).fetchall()
                    out.append({
                        "table": t,
                        "columns": [
                            {"name": c[0], "type": c[1], "comment": "", "is_sensitive": False}
                            for c in cols
                        ],
                    })
                return out
            if db_type == "sqlite":
                rows = (await conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ))).fetchall()
                out = []
                for t in [r[0] for r in rows]:
                    cols = (await conn.execute(text(f"PRAGMA table_info('{t}')"))).fetchall()
                    out.append({
                        "table": t,
                        "columns": [
                            {"name": c[1], "type": c[2], "comment": "", "is_sensitive": False}
                            for c in cols
                        ],
                    })
                return out
    finally:
        await eng.dispose()
    return []
