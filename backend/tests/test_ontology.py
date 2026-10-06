"""本体（Ontology）回归测试：对象/属性/Link/Action/函数/能力/版本/留痕/接地 resolve/问数字段级ACL/本体治理。

覆盖在 Palantir 化中新增的本体能力，确保后续改动不回归。
"""
import asyncio

import pytest

from app.plugin.module_ai.query.service import (
    _scan_ont_tables,
)


# ---------------------------------------------------------------------------
# 纯函数：从 SQL 检测本体物化表
# ---------------------------------------------------------------------------
class TestScanOntTables:
    def test_detect_ont_tables(self):
        sql = "SELECT SUM(amount) AS s FROM ont_orders"
        assert _scan_ont_tables(sql) == ["ont_orders"]

    def test_empty_when_no_ont(self):
        assert _scan_ont_tables("SELECT COUNT(*) FROM video_alarm_records") == []

    def test_dedupe(self):
        assert _scan_ont_tables("SELECT a FROM ont_orders JOIN ont_orders b ON a=b") == ["ont_orders"]


# ---------------------------------------------------------------------------
# 建本体元数据表（SQLite 兼容），供 service 级测试使用
# ---------------------------------------------------------------------------
DDL = {
    "ai_ont_object": "CREATE TABLE IF NOT EXISTS ai_ont_object (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT, icon TEXT, key_prop TEXT, name_prop TEXT, description TEXT, enabled INTEGER DEFAULT 1, is_deleted INTEGER DEFAULT 0)",
    "ai_ont_property": "CREATE TABLE IF NOT EXISTS ai_ont_property (id INTEGER PRIMARY KEY AUTOINCREMENT, object_code TEXT, name TEXT, code TEXT, prop_type TEXT, required INTEGER DEFAULT 0, unique_col INTEGER DEFAULT 0, sensitive INTEGER DEFAULT 0, source_col TEXT, options TEXT, description TEXT, roles TEXT, is_deleted INTEGER DEFAULT 0)",
    "ai_ont_link": "CREATE TABLE IF NOT EXISTS ai_ont_link (id INTEGER PRIMARY KEY AUTOINCREMENT, source_object TEXT, target_object TEXT, name TEXT, card TEXT, source_field TEXT, target_field TEXT, description TEXT, is_deleted INTEGER DEFAULT 0)",
    "ai_ont_action": "CREATE TABLE IF NOT EXISTS ai_ont_action (id INTEGER PRIMARY KEY AUTOINCREMENT, object_code TEXT, name TEXT, code TEXT, input_schema TEXT, white_fields TEXT, approval INTEGER DEFAULT 0, target_table TEXT, method TEXT, description TEXT, is_deleted INTEGER DEFAULT 0)",
    "ai_ont_function": "CREATE TABLE IF NOT EXISTS ai_ont_function (id INTEGER PRIMARY KEY AUTOINCREMENT, object_code TEXT, name TEXT, code TEXT, expr TEXT, description TEXT, is_deleted INTEGER DEFAULT 0)",
    "ai_ont_capability": "CREATE TABLE IF NOT EXISTS ai_ont_capability (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, name TEXT, type TEXT, description TEXT, enabled INTEGER DEFAULT 1, is_deleted INTEGER DEFAULT 0)",
    "ai_ont_version": "CREATE TABLE IF NOT EXISTS ai_ont_version (id INTEGER PRIMARY KEY AUTOINCREMENT, object_code TEXT, version INTEGER, snapshot TEXT, created_time TEXT, is_deleted INTEGER DEFAULT 0)",
    "ai_ont_change_log": "CREATE TABLE IF NOT EXISTS ai_ont_change_log (id INTEGER PRIMARY KEY AUTOINCREMENT, object_code TEXT, kind TEXT, action TEXT, detail TEXT, created_id INTEGER, created_time TEXT, is_deleted INTEGER DEFAULT 0)",
}


@pytest.fixture(scope="module", autouse=True)
def _ont_tables(test_client):
    """在测试库建本体元数据表（SQLite）。"""
    async def _create():
        from app.core.database import async_db_session
        from sqlalchemy import text as _t
        async with async_db_session.begin() as db:
            for ddl in DDL.values():
                await db.execute(_t(ddl))
    asyncio.run(_create())


@pytest.fixture(scope="module")
def ontology_obj(test_client, auth_headers):
    """建一个本体对象「订单」+ 属性（含敏感/受限角色）。"""
    h = auth_headers
    test_client.post("/api/v1/ai/ontology/object/save", json={
        "code": "orders", "name": "订单", "key_prop": "id", "name_prop": "order_no",
        "description": "测试订单本体验证", "enabled": True}, headers=h)
    for p in [
        {"object_code": "orders", "name": "订单号", "code": "order_no", "prop_type": "string", "required": True, "unique_col": True},
        {"object_code": "orders", "name": "金额", "code": "amount", "prop_type": "number", "required": True},
        {"object_code": "orders", "name": "客户", "code": "customer", "prop_type": "string", "sensitive": True, "roles": ["analyst"]},
    ]:
        test_client.post("/api/v1/ai/ontology/property/save", json=p, headers=h)
    test_client.post("/api/v1/ai/ontology/link/save", json={
        "source_object": "orders", "target_object": "customers", "name": "下单客户",
        "card": "many_to_one", "source_field": "customer", "target_field": "name"}, headers=h)
    test_client.post("/api/v1/ai/ontology/materialize", json={"code": "orders"}, headers=h)
    return h


# ---------------------------------------------------------------------------
# 本体对象/函数/能力/版本/留痕（HTTP）
# ---------------------------------------------------------------------------
class TestOntologyCrud:
    def test_object_full(self, test_client, auth_headers, ontology_obj):
        r = test_client.get("/api/v1/ai/ontology/object/orders/full", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["ok"] and d["name"] == "订单"
        assert len(d["properties"]) == 3
        assert len(d["links"]) == 1

    def test_function_save_and_list(self, test_client, auth_headers, ontology_obj):
        test_client.post("/api/v1/ai/ontology/function/save", json={
            "object_code": "orders", "name": "平均金额", "code": "avg_amount",
            "expr": "AVG(amount)", "description": "订单平均金额"}, headers=auth_headers)
        r = test_client.get("/api/v1/ai/ontology/functions?object_code=orders", headers=auth_headers)
        assert r.status_code == 200
        assert any(x["code"] == "avg_amount" for x in r.json()["data"])

    def test_capability_save_and_list(self, test_client, auth_headers, ontology_obj):
        test_client.post("/api/v1/ai/ontology/capability/save", json={
            "code": "retail_query", "name": "零售问数", "type": "query",
            "description": "零售对象问数", "enabled": True}, headers=auth_headers)
        r = test_client.get("/api/v1/ai/ontology/capabilities", headers=auth_headers)
        assert r.status_code == 200
        assert any(x["code"] == "retail_query" for x in r.json()["data"])

    def test_version_publish_and_list(self, test_client, auth_headers, ontology_obj):
        test_client.post("/api/v1/ai/ontology/version/publish", json={"code": "orders"}, headers=auth_headers)
        r = test_client.get("/api/v1/ai/ontology/version/list?object_code=orders", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()["data"]) >= 1

    def test_changelog_recorded(self, test_client, auth_headers, ontology_obj):
        # object save 已留痕
        r = test_client.get("/api/v1/ai/ontology/changelog?object_code=orders", headers=auth_headers)
        assert r.status_code == 200
        assert len(r.json()["data"]) >= 1


# ---------------------------------------------------------------------------
# 接地 resolve（本体对象）
# ---------------------------------------------------------------------------
class TestOntologyResolve:
    def test_list_objects(self, test_client, auth_headers, ontology_obj):
        r = test_client.get("/api/v1/ai/ontology/objects", headers=auth_headers)
        assert r.status_code == 200
        assert any(x["code"] == "orders" for x in r.json()["data"])


# ---------------------------------------------------------------------------
# 本体字段级 ACL（问数 SQL 拦截无权限敏感/受限属性）
# ---------------------------------------------------------------------------
class TestOntSqlAcl:
    def test_violation_on_restricted_prop(self, ontology_obj):
        from app.plugin.module_ai.query.service import AiQueryService
        # 非超管（user_id=-1）查询受限属性 customer → 违规
        v = asyncio.run(AiQueryService._ont_sql_violations(
            "SELECT customer FROM ont_orders", user_id=-1))
        assert "ont_orders.customer" in v

    def test_allow_open_prop(self, ontology_obj):
        from app.plugin.module_ai.query.service import AiQueryService
        v = asyncio.run(AiQueryService._ont_sql_violations(
            "SELECT order_no FROM ont_orders", user_id=-1))
        assert "ont_orders.customer" not in v
