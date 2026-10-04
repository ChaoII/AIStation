"""智能问数：自定义数据源连接与执行（阶段B）。

支持 PostgreSQL / MySQL / SQLite 的只读连接、表结构探查、SQL 执行。
file / api 类型不支持自由 SQL，请用「指标模板」方式查询。
"""
from __future__ import annotations

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
    """对数据源执行只读 SELECT。"""
    eng = build_engine(cfg)
    try:
        async with eng.connect() as conn:
            result = await conn.execute(text(sql))
            rows = result.fetchall()
            cols = list(result.keys())
    finally:
        await eng.dispose()
    return {"columns": cols, "rows": [[_json_cell(v) for v in r] for r in rows[:MAX_ROWS]]}


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
                    cols = (await conn.execute(text(
                        "SELECT column_name, data_type, COALESCE(column_default,'') "
                        "FROM information_schema.columns WHERE table_name=:t ORDER BY ordinal_position"
                    ), {"t": t})).fetchall()
                    out.append({
                        "table": t,
                        "columns": [
                            {"name": c[0], "type": c[1], "comment": c[2], "is_sensitive": False}
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
