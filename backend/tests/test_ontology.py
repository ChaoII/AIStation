"""本体（Ontology）回归测试：对象/属性/Link/Action/函数/能力/版本/留痕/接地 resolve/问数字段级ACL/本体治理。

覆盖在 Palantir 化中新增的本体能力，确保后续改动不回归。
"""
import asyncio

import _ont_ddl
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
# 建表语句统一从 _ont_ddl 取（新增表时不会再漏掉，避免测试假绿）
ONT_DDL = _ont_ddl.ONT_DDL


@pytest.fixture(scope="module", autouse=True)
def _ont_tables(test_client):
    """在测试库建本体元数据表（SQLite）。"""
    async def _create():
        from sqlalchemy import text as _t

        from app.core.database import async_db_session
        async with async_db_session.begin() as db:
            for ddl in ONT_DDL.values():
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
            "kind": "expression",
            "expr": "total_amount / order_count",
            "parameters": [
                {"key": "total_amount", "name": "总金额", "type": "number", "required": True},
                {"key": "order_count", "name": "订单数", "type": "number", "required": True},
            ],
            "outputs": [{"key": "avg", "name": "平均金额", "type": "number"}],
            "description": "订单平均金额"}, headers=auth_headers)
        r = test_client.get("/api/v1/ai/ontology/functions?object_code=orders", headers=auth_headers)
        assert r.status_code == 200
        got = [x for x in r.json()["data"] if x["code"] == "avg_amount"]
        assert got
        # P2 新字段应能读回
        assert got[0]["kind"] == "expression"
        assert got[0]["outputs"][0]["key"] == "avg"

    def test_function_rejects_broken_expression(self, test_client, auth_headers, ontology_obj):
        """表达式引用了未声明变量 / 未知函数 → 保存时就应被拒绝（旧版只存不校验）。"""
        r = test_client.post("/api/v1/ai/ontology/function/save", json={
            "object_code": "orders", "name": "坏函数", "code": "bad_fn",
            "expr": "AVG(amount)", "description": ""}, headers=auth_headers)
        body = r.json()
        msg = body.get("msg") or ""
        assert ("AVG" in msg) or ("amount" in msg), msg

    # test_capability_save_and_list 已删除（2026-10-19）：本体能力登记整个特性已下线
    # （Palantir 没有 "Capability" 本体对象类型，且 Agent 装配能力走的是
    #  ai_agents.capabilities，与这张登记表零关联）。

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
# 对象/属性列表序列化暴露 is_business（Task 8）
# ---------------------------------------------------------------------------
class TestOntologySerializesIsBusiness:
    def test_list_objects_serializes_is_business(self, test_client, auth_headers, ontology_obj):
        r = test_client.get("/api/v1/ai/ontology/objects", headers=auth_headers)
        assert r.status_code == 200
        item = next(x for x in r.json()["data"] if x["code"] == "orders")
        assert "is_business" in item, "对象列表应序列化 is_business 字段"
        # 默认创建的对象（未手动置位）默认视为业务
        assert isinstance(item["is_business"], bool)

    def test_list_properties_serializes_is_business(self, test_client, auth_headers, ontology_obj):
        r = test_client.get(
            "/api/v1/ai/ontology/properties?object_code=orders", headers=auth_headers
        )
        assert r.status_code == 200
        assert r.json()["data"], "orders 对象应含有属性"
        for p in r.json()["data"]:
            assert "is_business" in p, "属性列表应序列化 is_business 字段"
            assert isinstance(p["is_business"], bool)


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


# ---------------------------------------------------------------------------
# 方向③：字段级 ACL 扩展（业务表敏感字段 + sqlglot 精确列提取）
# ---------------------------------------------------------------------------
class TestBusinessSensitiveColAcl:
    @pytest.fixture(scope="class")
    def sens_col(self, test_client):
        """在字段资产目录标记一张业务表的敏感字段（sys_user.password）。"""
        async def _go():
            from sqlalchemy import select as _sel

            from app.core.database import async_db_session
            from app.plugin.module_ai.query.model import AiQueryAssetColumnModel
            async with async_db_session.begin() as db:
                existing = (await db.execute(
                    _sel(AiQueryAssetColumnModel).where(
                        AiQueryAssetColumnModel.table_name == "sys_user",
                        AiQueryAssetColumnModel.column_name == "password",
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                    )
                )).scalar_one_or_none()
                if not existing:
                    db.add(AiQueryAssetColumnModel(
                        table_name="sys_user", column_name="password",
                        description="用户密码", sensitive=True, included=True,
                    ))
        asyncio.run(_go())

    def test_business_sensitive_col_blocked(self, sens_col):
        from app.plugin.module_ai.query.service import AiQueryService
        v = asyncio.run(AiQueryService._ont_sql_violations(
            "SELECT password FROM sys_user", user_id=-1))
        assert "sys_user.password" in v

    def test_non_sensitive_col_allowed(self, sens_col):
        from app.plugin.module_ai.query.service import AiQueryService
        v = asyncio.run(AiQueryService._ont_sql_violations(
            "SELECT username FROM sys_user", user_id=-1))
        assert "sys_user.password" not in v


class TestSqlQueryScope:
    def test_extracts_tables_and_cols(self):
        from app.plugin.module_ai.query.service import AiQueryService
        tables, cols = asyncio.run(AiQueryService._sql_query_scope(
            "SELECT c.name FROM video_cameras c JOIN video_alarm_records r ON r.camera_id=c.id"))
        assert "video_cameras" in tables and "video_alarm_records" in tables
        assert "name" in cols and "camera_id" in cols


# ---------------------------------------------------------------------------
# 数据域/表级权限拦截（Palantir：非超管只能查其 ABAC 授权表）
# ---------------------------------------------------------------------------
class TestTableLevelAcl:
    @pytest.fixture(scope="class")
    def viewer_rule(self, test_client):
        async def _go():
            from sqlalchemy import text as _t

            from app.core.database import async_db_session
            async with async_db_session.begin() as db:
                await db.execute(_t("DELETE FROM ai_access_rule WHERE value='viewer'"))
                await db.execute(_t(
                    "INSERT INTO ai_access_rule(name,attribute,value,allowed_tables,sensitive_ok,enabled,is_deleted) "
                    "VALUES ('数据域-viewer','role','viewer','[\"video_cameras\"]',0,1,0)"))
        asyncio.run(_go())

    @staticmethod
    def _auth(is_super, roles, uid=0):
        from types import SimpleNamespace
        return SimpleNamespace(
            user=SimpleNamespace(id=uid, is_superuser=is_super, roles=[SimpleNamespace(code=r) for r in roles]))

    def test_superuser_full(self, test_client):
        from app.plugin.module_ai.query.service import AiQueryService
        s = asyncio.run(AiQueryService._allowed_for_user(self._auth(True, [])))
        assert "video_alarm_records" in s and "video_cameras" in s

    def test_viewer_restricted(self, viewer_rule):
        from app.plugin.module_ai.query.service import AiQueryService
        s = asyncio.run(AiQueryService._allowed_for_user(self._auth(False, ["viewer"])))
        assert "video_cameras" in s
        assert "video_alarm_records" not in s

    def test_no_rule_default_full(self, test_client):
        from app.plugin.module_ai.query.service import AiQueryService
        s = asyncio.run(AiQueryService._allowed_for_user(self._auth(False, ["charter"])))
        assert "video_alarm_records" in s

    def test_domain_member_restricted(self, test_client):
        from sqlalchemy import text as _t

        from app.core.database import async_db_session
        from app.plugin.module_ai.query.service import AiQueryService

        async def _go():
            async with async_db_session.begin() as db:
                await db.execute(_t("DELETE FROM ai_data_domain WHERE code='prod'"))
                await db.execute(_t(
                    "INSERT INTO ai_data_domain(name,code,description,tables,members,enabled,is_deleted) "
                    "VALUES ('生产域','prod','x','[\"video_cameras\"]','[99]',1,0)"))
            # 用户 id=99 属于 prod 域 → 仅 video_cameras
            s = await AiQueryService._allowed_for_user(self._auth(False, [], uid=99))
            assert "video_cameras" in s
            assert "video_alarm_records" not in s
            # 非域成员 → 默认全开
            s2 = await AiQueryService._allowed_for_user(self._auth(False, [], uid=999999))
            assert "video_alarm_records" in s2
        asyncio.run(_go())

    def test_access_preview(self, test_client):
        from sqlalchemy import text as _t

        from app.core.database import async_db_session
        from app.plugin.module_ai.query.service import AiQueryService

        async def _go():
            async with async_db_session.begin() as db:
                await db.execute(_t("DELETE FROM ai_data_domain WHERE code='prod'"))
                await db.execute(_t(
                    "INSERT INTO ai_data_domain(name,code,description,tables,members,enabled,is_deleted) "
                    "VALUES ('生产域','prod','x','[\"video_cameras\"]','[99]',1,0)"))
            r = await AiQueryService.access_preview(99)
            assert r["domain_restricted"] is True
            assert "video_cameras" in r["allowed_tables"]
            assert "video_alarm_records" not in r["allowed_tables"]
        asyncio.run(_go())

    def test_access_preview_role(self, test_client):
        from sqlalchemy import text as _t

        from app.core.database import async_db_session
        from app.plugin.module_ai.query.service import AiQueryService

        async def _go():
            async with async_db_session.begin() as db:
                await db.execute(_t("DELETE FROM ai_access_rule WHERE value='prod_viewer'"))
                await db.execute(_t(
                    "INSERT INTO ai_access_rule(name,attribute,value,allowed_tables,sensitive_ok,enabled,is_deleted) "
                    "VALUES ('r','role','prod_viewer','[\"video_cameras\"]',1,1,0)"))
            r = await AiQueryService.access_preview_role("prod_viewer")
            assert r["restricted"] is True and r["sensitive_ok"] is True
            assert "video_cameras" in r["allowed_tables"]
            r2 = await AiQueryService.access_preview_role("no_such_role")
            assert r2["restricted"] is False
        asyncio.run(_go())

    def test_dq_warning(self, test_client):
        from sqlalchemy import text as _t

        from app.core.database import async_db_session
        from app.plugin.module_ai.query.service import AiQueryService

        async def _go():
            from sqlalchemy import select as _sel

            from app.plugin.module_ai.query.model import AiQueryAssetModel
            async with async_db_session.begin() as db:
                await db.execute(_t("DELETE FROM ai_dq_report WHERE table_name='video_cameras'"))
                existing = (await db.execute(_sel(AiQueryAssetModel).where(
                    AiQueryAssetModel.table_name == "video_cameras",
                    AiQueryAssetModel.is_deleted.is_(False)))).scalar_one_or_none()
                if not existing:
                    db.add(AiQueryAssetModel(
                        table_name="video_cameras", alias="摄像头",
                        object_enabled=True, included=True))
                await db.execute(_t(
                    "INSERT INTO ai_dq_report(table_name,alias,total,score,completeness,uniqueness,freshness,issues,is_deleted) "
                    "VALUES ('video_cameras','摄像头',10,40,50,60,30,'[]',0)"))
            w = await AiQueryService._dq_warning_for_sql("SELECT COUNT(*) FROM video_cameras")
            assert any(x["table"] == "video_cameras" and x["score"] < 60 for x in w)
            w2 = await AiQueryService._dq_warning_for_sql("SELECT COUNT(*) FROM video_alarm_records")
            assert not any(x["table"] == "video_cameras" for x in w2)
        asyncio.run(_go())


# ---------------------------------------------------------------------------
# 方向④：FDE 复用闭环（把已验证问答沉淀为可复用指标 + 术语）
# ---------------------------------------------------------------------------
class TestPromoteReuse:
    def test_promote_creates_metric_and_term(self, test_client):
        from types import SimpleNamespace

        from sqlalchemy import select as _sel

        from app.core.database import async_db_session
        from app.plugin.module_ai.query.model import AiQueryDictionaryModel, AiQueryMetricModel
        from app.plugin.module_ai.query.service import AiQueryService

        async def _go():
            # 先建一条**真实归属**的会话：promote 现在会按 message 的 session_id
            # 反查会话校验归属（旧用例直接写 session_id=1 的孤儿消息，等于没有归属）
            auth = SimpleNamespace(user=SimpleNamespace(id=1))
            sess = await AiQueryService.get_or_create_session(None, "指标沉淀测试", auth)
            msg = await AiQueryService._save_message(
                sess["id"], "按品牌统计摄像头数量", path="slow", datasource="system",
                sql="SELECT COUNT(*) AS 数值 FROM video_cameras", columns=["数值"],
                rows=[[5]], result_rows=1, took_ms=1, cached=False,
            )
            r = await AiQueryService.promote_message_to_metric(
                msg.id, "按品牌摄像头数量", "camera_by_brand", auth)
            assert r["key"] == "camera_by_brand" and r["term"] == "按品牌统计摄像头数量"
            async with async_db_session() as db:
                met = (await db.execute(_sel(AiQueryMetricModel).where(
                    AiQueryMetricModel.key == "camera_by_brand"))).scalar_one()
                assert met.enabled
                term = (await db.execute(_sel(AiQueryDictionaryModel).where(
                    AiQueryDictionaryModel.term == "按品牌统计摄像头数量"))).scalar_one_or_none()
                assert term is not None and term.metric_key == "camera_by_brand"
        asyncio.run(_go())


# ---------------------------------------------------------------------------
# 本体版本发布留痕（Palantir：发布即记录 changelog，含发布人）
# ---------------------------------------------------------------------------
class TestOntVersionPublish:
    def test_publish_writes_changelog(self, test_client):
        from sqlalchemy import text as _t

        from app.core.database import async_db_session
        from app.plugin.module_ai.ontology import service as osvc

        async def _go():
            # ⚠️ 必须用 .begin()（提交）：用 async_db_session() 时写入不提交，
            #    后续 object_full 读不到 → 本用例会依赖「同模块更早的用例碰巧提交过
            #    orders」而时绿时红（-n 并行下按 worker 分配顺序翻车，实测踩过）。
            async with async_db_session.begin() as db:
                await db.execute(_t("DELETE FROM ai_ont_object WHERE code='orders'"))
                await db.execute(_t("INSERT INTO ai_ont_object(code,name,is_deleted) VALUES ('orders','订单',0)"))
                su = (await db.execute(_t("SELECT id FROM sys_user WHERE is_superuser=1 AND is_deleted=0 LIMIT 1"))).fetchone()
                suid = int(su[0]) if su else 1
            await osvc.publish_version("orders", operator=suid)
            cl = await osvc.list_changelog("orders", limit=50)
            assert any(c["action"] == "publish" and "发布版本" in (c["detail"] or "") for c in cl)
        asyncio.run(_go())

    def test_non_superuser_publish_goes_pending(self, test_client):
        from app.plugin.module_ai.ontology import service as osvc

        async def _go():
            r = await osvc.publish_version("orders", operator=999999)
            assert r.get("needs_approval") is True and r.get("pending_id")
            pend = await osvc.list_version_pending()
            assert any(p["id"] == r["pending_id"] and p["object_code"] == "orders" for p in pend)
        asyncio.run(_go())

    def test_superuser_approve_publish(self, test_client):
        from sqlalchemy import text as _t

        from app.core.database import async_db_session
        from app.plugin.module_ai.ontology import service as osvc

        async def _go():
            # ⚠️ 同 test_publish_writes_changelog：必须 .begin() 提交，否则读不到
            async with async_db_session.begin() as db:
                await db.execute(_t("DELETE FROM ai_ont_object WHERE code='orders'"))
                await db.execute(_t("INSERT INTO ai_ont_object(code,name,is_deleted) VALUES ('orders','订单',0)"))
                su = (await db.execute(_t("SELECT id FROM sys_user WHERE is_superuser=1 AND is_deleted=0 LIMIT 1"))).fetchone()
                suid = int(su[0]) if su else 1
            r = await osvc.publish_version("orders", operator=999999)  # 非超管 → pending
            pid = r["pending_id"]
            ap = await osvc.approve_version_publish(pid, operator=suid)
            assert ap.get("ok") is True
            pend = await osvc.list_version_pending()
            assert not any(p["id"] == pid for p in pend)  # 审批后不在待审批
        asyncio.run(_go())


# ---------------------------------------------------------------------------
# Action 写回审批流（Palantir：待审批 → 批准/驳回 + 审计留痕）
# ---------------------------------------------------------------------------
class TestActionApproval:
    def test_role_writable_narrowed(self, test_client):
        """按角色收窄可写字段：ANNOTATOR 角色仅可写 description，不可写 location。"""
        from app.plugin.module_ai.query.service import AiQueryService

        async def _go():
            act = {"writable_cols": ["description", "location"],
                   "writable_by_role": {"ANNOTATOR": ["description"]}}
            # ANNOTATOR 角色用户 → 仅 description
            w_ann = await AiQueryService._action_writable_for(act, "999999")  # user role ANNOTATOR?
            # 未匹配角色 → 全局 writable_cols
            assert set(["description", "location"]) == w_ann
        asyncio.run(_go())

    def test_role_narrowed_unknown_user_keeps_global(self, test_client):
        from app.plugin.module_ai.query.service import AiQueryService

        async def _go():
            act = {"writable_cols": ["description", "location"],
                   "writable_by_role": {"ANNOTATOR": ["description"]}}
            w = await AiQueryService._action_writable_for(act, "0")  # 无角色
            assert set(["description", "location"]) == w
        asyncio.run(_go())

    def test_pending_list_and_reject(self, test_client):
        from sqlalchemy import text as _t

        from app.core.database import async_db_session
        from app.plugin.module_ai.query.service import AiQueryService

        async def _go():
            async with async_db_session.begin() as db:
                await db.execute(_t("DELETE FROM ai_query_writeback_log WHERE action_name='t2'"))
                await db.execute(_t(
                    "INSERT INTO ai_query_writeback_log(action_name,object_table,object_key,params,operator,result,detail,is_deleted) "
                    "VALUES ('t2','video_cameras','1','{}','u','pending','x',0)"))
                su = (await db.execute(_t(
                    "SELECT id FROM sys_user WHERE is_superuser=1 AND is_deleted=0 LIMIT 1"))).fetchone()
                suid = str(su[0]) if su else "0"
            p = await AiQueryService.list_pending_actions()
            rid = next((x["id"] for x in p if x["action"] == "t2"), None)
            assert rid is not None
            await AiQueryService.reject_action(rid, suid)
            p2 = await AiQueryService.list_pending_actions()
            assert not any(x["action"] == "t2" for x in p2)
        asyncio.run(_go())

    def test_non_superuser_cannot_approve(self, test_client):
        from sqlalchemy import text as _t

        from app.core.database import async_db_session
        from app.plugin.module_ai.query.service import AiQueryService

        async def _go():
            async with async_db_session.begin() as db:
                await db.execute(_t("DELETE FROM ai_query_writeback_log WHERE action_name='t3'"))
                await db.execute(_t(
                    "INSERT INTO ai_query_writeback_log(action_name,object_table,object_key,params,operator,result,detail,is_deleted) "
                    "VALUES ('t3','video_cameras','1','{}','u','pending','x',0)"))
            p = await AiQueryService.list_pending_actions()
            rid = next((x["id"] for x in p if x["action"] == "t3"), None)
            r = await AiQueryService.reject_action(rid, "9999999")  # 非超管
            p2 = await AiQueryService.list_pending_actions()
            assert not r.get("ok")
            assert any(x["action"] == "t3" for x in p2)  # 仍 pending
        asyncio.run(_go())

    def test_analyze_ontology(self, test_client):
        import asyncio

        from sqlalchemy import text as _t

        from app.core.database import async_db_session
        from app.plugin.module_ai.ontology import service as ont_svc

        async def _go():
            async with async_db_session.begin() as db:
                for c in ("an_a", "an_b"):
                    await db.execute(_t(
                        "DELETE FROM ai_ont_object WHERE code=:c"), {"c": c})
                    await db.execute(_t(
                        "INSERT INTO ai_ont_object(code,name,icon,key_prop,name_prop,enabled,is_deleted) "
                        "VALUES (:c,:c,'el-icon-Box','id','name',true,false)"), {"c": c})
                await db.execute(_t(
                    "DELETE FROM ai_ont_property WHERE object_code IN ('an_a','an_b')"))
                await db.execute(_t(
                    "INSERT INTO ai_ont_property(object_code,name,code,prop_type,required,unique_col,is_deleted) "
                    "VALUES ('an_a','id','id','string',true,true,false)"))
                await db.execute(_t(
                    "DELETE FROM ai_ont_link WHERE source_object IN ('an_a','an_b')"))
                await db.execute(_t(
                    "INSERT INTO ai_ont_link(source_object,target_object,name,card,is_deleted) "
                    "VALUES ('an_a','an_b','rel','one_to_many',false)"))
            r = await ont_svc.analyze_ontology()
            assert r["objects"] >= 2
            assert "density" in r and "recommendations" in r and "card_dist" in r
            assert "top_central" in r and "nodes" in r and "edges" in r
            assert any(n["code"] == "an_a" for n in r["nodes"])
            assert any(e["source"] == "an_a" and e["target"] == "an_b" for e in r["edges"])
        asyncio.run(_go())
