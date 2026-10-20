"""图视图（Graph View）的单元与回归测试。

对齐设计：`docs/superpowers/specs/2026-10-20-ontology-p7-graph-views-design.md`
覆盖：保存视图 / 图模板 / 时间轴 的后端逻辑。
"""
import asyncio

import _ont_ddl
import pytest

from app.plugin.module_ai.ontology import service as _svc


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module", autouse=True)
def _tables(test_client):
    """建全部本体元数据表（SQLite 测试库）。"""
    from sqlalchemy import text as _t

    from app.core.database import async_db_session, async_engine

    async def _create():
        await async_engine.dispose()
        async with async_db_session.begin() as db:
            for ddl in _ont_ddl.ONT_DDL.values():
                await db.execute(_t(ddl))

    _run(_create())


# ---------------------------------------------------------------------------
# Task 1：表结构
# ---------------------------------------------------------------------------
def test_graph_view_tables_exist():
    async def _impl():
        r = await _svc._exec(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('ai_ont_graph_view','ai_ont_graph_view_version')"
        )
        return {row[0] for row in r.fetchall()}

    names = _run(_impl())
    assert names == {"ai_ont_graph_view", "ai_ont_graph_view_version"}
