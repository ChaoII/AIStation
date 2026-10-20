"""图视图（Graph View）的单元与回归测试。

对齐设计：`docs/superpowers/specs/2026-10-20-ontology-p7-graph-views-design.md`
覆盖：保存视图 / 图模板 / 时间轴 的后端逻辑。
"""
import asyncio

import _ont_ddl
import pytest

from app.core.exceptions import CustomException
from app.plugin.module_ai.ontology import graph_view as _gv
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


# ---------------------------------------------------------------------------
# Task 2：核心 CRUD（create / list / get / update / remove）
# ---------------------------------------------------------------------------
def test_create_and_get_view():
    async def _impl():
        r = await _gv.create_view({
            "name": "默认图", "graph_kind": "saved", "domain_code": "fuel_business",
            "state": {"layout": "cose", "theme": "default", "selected": [],
                      "zoom": 1, "pan": {"x": 0, "y": 0}},
        }, actor="admin")
        assert r["ok"] is True
        v = await _gv.get_view(r["code"])
        assert v["state"]["layout"] == "cose"
        assert v["domain_code"] == "fuel_business"
        return r

    _run(_impl())


def test_create_view_requires_domain():
    async def _impl():
        with pytest.raises(CustomException):
            await _gv.create_view({"name": "x", "graph_kind": "saved", "domain_code": ""})

    _run(_impl())


def test_list_views_filters_by_kind():
    async def _impl():
        await _gv.create_view({"name": "A", "graph_kind": "saved", "domain_code": "d1"})
        await _gv.create_view({"name": "B", "graph_kind": "template", "domain_code": ""})
        saved = await _gv.list_views(domain_code="d1", kind="saved")
        tpl = await _gv.list_views(kind="template")
        return [x["name"] for x in saved], [x["name"] for x in tpl]

    saved, tpl = _run(_impl())
    assert saved == ["A"]
    assert tpl == ["B"]


def test_update_and_remove_view():
    async def _impl():
        v = await _gv.create_view({"name": "C", "graph_kind": "saved", "domain_code": "d1"})
        await _gv.update_view(v["code"], {"state": {"layout": "grid"}})
        up = await _gv.get_view(v["code"])
        await _gv.remove_view(v["code"])
        return up["state"]["layout"], await _gv.get_view(v["code"])

    layout, gone = _run(_impl())
    assert layout == "grid"
    assert gone is None
