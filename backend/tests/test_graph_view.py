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


# ---------------------------------------------------------------------------
# Task 3：版本管理 + 默认
# ---------------------------------------------------------------------------
def test_version_bump_and_restore():
    async def _impl():
        v = await _gv.create_view({"name": "V", "graph_kind": "saved", "domain_code": "d1",
                                   "state": {"layout": "cose"}})
        await _gv.update_view(v["code"], {"state": {"layout": "grid"}})
        await _gv.update_view(v["code"], {"state": {"layout": "concentric"}})
        vers = await _gv.list_versions(v["code"])
        assert len(vers) == 2 and vers[0]["version"] == 2
        await _gv.restore_version(v["code"], 1)
        return (await _gv.get_view(v["code"]))["state"]["layout"]

    layout = _run(_impl())
    assert layout == "cose"


def test_set_default_unique_per_domain():
    async def _impl():
        a = await _gv.create_view({"name": "A", "graph_kind": "saved", "domain_code": "d1"})
        b = await _gv.create_view({"name": "B", "graph_kind": "saved", "domain_code": "d1"})
        await _gv.set_default(a["code"], "d1")
        await _gv.set_default(b["code"], "d1")
        views = await _gv.list_views(domain_code="d1", kind="saved")
        return sum(1 for x in views if x["is_default"])

    cnt = _run(_impl())
    assert cnt == 1


# ---------------------------------------------------------------------------
# Task 4：分享与权限（share / can_view / list_shared / link）
# ---------------------------------------------------------------------------
class _P:
    """假的 principal，模拟 auth 主体（object_view.can_view_view 读 role_codes）。"""

    def __init__(self, roles):
        self.role_codes = set(roles)
        self.is_superuser = False


def test_share_and_can_view():
    async def _impl():
        v = await _gv.create_view({"name": "S", "graph_kind": "saved", "domain_code": "d1"})
        await _gv.share_view(v["code"], "roles", ["role_a"])
        ok, _ = await _gv.can_view_view(v["code"], _P(["role_a"]))
        ok2, _ = await _gv.can_view_view(v["code"], _P(["role_z"]))
        return ok, ok2

    ok, ok2 = _run(_impl())
    assert ok is True
    assert ok2 is False


def test_inherit_follows_domain():
    async def _impl():
        v = await _gv.create_view({"name": "I", "graph_kind": "saved", "domain_code": "d1"})
        return (await _gv.can_view_view(v["code"], _P([])))[0]

    ok = _run(_impl())
    assert ok is True


def test_shared_views_filters():
    async def _impl():
        a = await _gv.create_view({"name": "SA", "graph_kind": "saved", "domain_code": "d1"})
        b = await _gv.create_view({"name": "SB", "graph_kind": "saved", "domain_code": "d1"})
        await _gv.share_view(a["code"], "roles", ["role_a"])
        await _gv.share_view(b["code"], "roles", ["role_b"])
        names = {x["name"] for x in await _gv.list_shared_views(_P(["role_a"]))}
        return "SA" in names, "SB" in names

    sa_ok, sb_ok = _run(_impl())
    assert sa_ok is True
    assert sb_ok is False


def test_view_link():
    async def _impl():
        v = await _gv.create_view({"name": "L", "graph_kind": "saved", "domain_code": "d1"})
        r = await _gv.view_link(v["code"])
        return r["url"], r["view_code"]

    url, code = _run(_impl())
    assert code != ""
    assert "view=" in url
