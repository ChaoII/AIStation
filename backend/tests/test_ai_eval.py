"""AI 能力评估（影子回归）测试。"""
import asyncio

from app.plugin.module_ai.overview.service import AiOverviewService


class TestAiEval:
    def test_eval_match_true(self):
        assert AiOverviewService.eval_match("订单金额总和是 90500", ["90500"]) is True

    def test_eval_match_case_insensitive(self):
        assert AiOverviewService.eval_match("结果 success", ["SUCCESS"]) is True

    def test_eval_match_all_keywords(self):
        assert AiOverviewService.eval_match("显示 A 和 B", ["a", "b"]) is True

    def test_eval_match_missing_keyword(self):
        assert AiOverviewService.eval_match("显示 A", ["a", "b"]) is False

    def test_run_eval_precision(self):
        samples = [
            {"input": "q1", "expected_keywords": ["90500"], "actual": "90500"},
            {"input": "q2", "expected_keywords": ["abc"], "actual": "xyz"},
        ]
        r = asyncio.run(AiOverviewService.run_eval(samples))
        assert r["total"] == 2 and r["passed"] == 1 and r["precision"] == 0.5

    def test_health_check_shape(self):
        r = asyncio.run(AiOverviewService.health_check(days=7))
        assert "calls" in r and "error_rate" in r and "status" in r and "alerts" in r
        assert r["status"] in ("healthy", "warning", "critical")

    def test_audit_check_shape(self):
        r = asyncio.run(AiOverviewService.audit_check(days=7))
        assert "total" in r and "anonymous_calls" in r and "compliant" in r and "issues" in r

    def test_pipeline_graph_shape(self):
        from app.plugin.module_ai.query.service import AiQueryService
        from app.core.database import async_db_session
        from sqlalchemy import text as _t

        async def _go():
            async with async_db_session.begin() as db:
                await db.execute(_t("CREATE TABLE IF NOT EXISTS ai_pipeline (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, source_connection TEXT, source_table TEXT, target_object TEXT, mappings TEXT, enabled INTEGER DEFAULT 1, is_deleted INTEGER DEFAULT 0)"))
                await db.execute(_t("CREATE TABLE IF NOT EXISTS ai_pipeline_run (id INTEGER PRIMARY KEY AUTOINCREMENT, pipeline_id INTEGER, status TEXT, ran_at TEXT, is_deleted INTEGER DEFAULT 0)"))
            g = await AiQueryService.pipeline_graph()
            ids = {n["id"] for n in g["nodes"]}
            for e in g["edges"]:
                assert e["source"] in ids and e["target"] in ids
            return g
        g = asyncio.run(_go())
        assert "nodes" in g and "edges" in g

    def test_approval_center_shape(self):
        from app.plugin.module_ai.query.service import AiQueryService
        from app.core.database import async_db_session
        from sqlalchemy import text as _t

        async def _go():
            async with async_db_session.begin() as db:
                await db.execute(_t("CREATE TABLE IF NOT EXISTS ai_action_log (id INTEGER PRIMARY KEY AUTOINCREMENT, action_name TEXT, object_table TEXT, object_key TEXT, params TEXT, operator TEXT, result TEXT, detail TEXT, created_time TEXT, is_deleted INTEGER DEFAULT 0)"))
                await db.execute(_t("CREATE TABLE IF NOT EXISTS ai_ont_change_log (id INTEGER PRIMARY KEY AUTOINCREMENT, object_code TEXT, kind TEXT, action TEXT, detail TEXT, created_id INTEGER, created_time TEXT, is_deleted INTEGER DEFAULT 0)"))
            return await AiQueryService.approval_center()
        r = asyncio.run(_go())
        assert "actions" in r and "versions" in r and "total" in r
        assert r["total"] == len(r["actions"]) + len(r["versions"])

    def test_scan_sensitive_identifies(self, test_client):
        from app.plugin.module_ai.query.service import AiQueryService

        r = asyncio.run(AiQueryService.scan_sensitive("sys_user"))
        # sys_user 含 password/mobile/email 等敏感列 → 应识别至少一个
        assert r.get("ok") is True
        assert r["count"] >= 1
        assert any("password" in (i["column"] or "").lower() for i in r["identified"])

    def test_permission_check(self, test_client):
        from app.plugin.module_ai.query.service import AiQueryService
        from app.core.database import async_db_session
        from sqlalchemy import text as _t

        async def _go():
            async with async_db_session.begin() as db:
                await db.execute(_t("CREATE TABLE IF NOT EXISTS ai_access_rule (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, attribute TEXT, value TEXT, allowed_tables TEXT, sensitive_ok INTEGER DEFAULT 0, enabled INTEGER DEFAULT 1, is_deleted INTEGER DEFAULT 0)"))
                await db.execute(_t("CREATE TABLE IF NOT EXISTS ai_domain (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, code TEXT, description TEXT, tables TEXT, members TEXT, enabled INTEGER DEFAULT 1, is_deleted INTEGER DEFAULT 0)"))
            # 超管（user 1）对任意表全可见
            r = await AiQueryService.permission_check(1, "video_cameras")
            assert r["allowed"] is True and r["sensitive_visible"] is True
            # 非超管无规则 → 全开可查
            r2 = await AiQueryService.permission_check(999999, "video_cameras")
            assert "allowed" in r2 and "reason" in r2
        asyncio.run(_go())

    def test_data_lifetime_crud(self, test_client):
        from app.plugin.module_ai.query.service import AiQueryService

        async def _go():
            s = await AiQueryService.dl_save({"table": "video_alarm_records", "retention_days": 180})
            assert s.get("id")
            lst = await AiQueryService.dl_list()
            assert any(x["table"] == "video_alarm_records" for x in lst)
        asyncio.run(_go())

    def test_runtime_status_shape(self):
        from app.plugin.module_ai.overview.service import AiOverviewService

        r = asyncio.run(AiOverviewService.runtime_status())
        assert "apps" in r and "workflows" in r and "models" in r and "agents" in r
        assert "health" in r and "pipeline_status" in r

    def test_aip_control_shape(self):
        from app.plugin.module_ai.overview.service import AiOverviewService

        r = asyncio.run(AiOverviewService.aip_control(20))
        assert "runs" in r and "usage_dist" in r and "pending_review" in r and "total" in r
        assert isinstance(r["runs"], list)

    def test_compliance_posture_shape(self):
        from app.plugin.module_ai.overview.service import AiOverviewService

        r = asyncio.run(AiOverviewService.compliance_posture())
        assert "score" in r and "dims" in r and "findings" in r and "level" in r
        assert 0 <= r["score"] <= 100
        assert len(r["dims"]) >= 5

    def test_anomaly_and_decision(self):
        from app.plugin.module_ai.overview.service import AiOverviewService

        a = asyncio.run(AiOverviewService.anomaly_detect(7))
        assert "anomalies" in a and "total" in a and "baseline_latency_ms" in a
        d = asyncio.run(AiOverviewService.decision_center())
        assert "total" in d and "decisions" in d and isinstance(d["decisions"], list)
        for dec in d["decisions"]:
            assert "title" in dec and "reason" in dec and "pri" in dec
        ex = asyncio.run(AiOverviewService.decision_execute("autopilot"))
        assert "ok" in ex and "msg" in ex
        br = asyncio.run(AiOverviewService.eval_bench_run(
            [{"input": "x", "expected_keywords": ["a"], "actual": "a b"}], "pytest基准"))
        assert "ok" in br and "precision" in br
        bl = asyncio.run(AiOverviewService.eval_bench_list(10))
        assert isinstance(bl, list)
        ua = asyncio.run(AiOverviewService.unified_audit(7))
        assert "ai_calls" in ua and "audit_log" in ua and "approvals" in ua

    def test_activity_timeline(self):
        from app.plugin.module_ai.overview.service import AiOverviewService

        r = asyncio.run(AiOverviewService.activity_timeline(7, 50))
        assert "total" in r and "events" in r and isinstance(r["events"], list)
        for e in r["events"]:
            assert "time" in e and "title" in e and "kind" in e

    def test_compass_search(self, test_client):
        from app.plugin.module_ai.query.service import AiQueryService

        r = asyncio.run(AiQueryService.compass_search("摄像头"))
        assert "assets" in r and "objects" in r and "metrics" in r and "terms" in r
        r2 = asyncio.run(AiQueryService.compass_search(""))
        assert r2["assets"] == [] and r2["metrics"] == []

    def test_connector_types(self):
        from app.plugin.module_ai.query.service import AiQueryService

        r = asyncio.run(AiQueryService.connector_types())
        assert any(c["type"] == "postgres" for c in r)
        assert any(c["type"] == "rest_api" for c in r)

    def test_autopilot(self):
        from app.plugin.module_ai.query.service import AiQueryService

        r = asyncio.run(AiQueryService.autopilot())
        assert "total" in r and "actions" in r and isinstance(r["actions"], list)
        for a in r["actions"]:
            assert "type" in a and "suggestion" in a and "executable" in a

    def test_autopilot_execute_sensitive(self):
        from app.plugin.module_ai.query.service import AiQueryService

        r = asyncio.run(AiQueryService.autopilot_execute("scan_sensitive", "t_auto_pwd"))
        assert "ok" in r and "msg" in r
        r2 = asyncio.run(AiQueryService.autopilot_execute("none", ""))
        assert r2["ok"] is False
        r3 = asyncio.run(AiQueryService.autopilot_execute("generate_desc", "t_desc"))
        assert "ok" in r3

    def test_derived_metrics(self):
        from app.plugin.module_ai.query.service import AiQueryService

        r = asyncio.run(AiQueryService.list_derived_metrics())
        assert isinstance(r, list) and len(r) >= 1
        for d in r:
            assert "key" in d and "name" in d and "formula" in d and "base" in d
        c = asyncio.run(AiQueryService.compute_derived_metric("nope"))
        assert c["ok"] is False

    def test_security_audit(self):
        from app.plugin.module_ai.query.service import AiQueryService

        r = asyncio.run(AiQueryService.security_audit(30))
        assert "score" in r and "dims" in r and "action_logs" in r and "datasources" in r
        assert 0 <= r["score"] <= 100
        assert "sensitive_fields" in r and "access_rules" in r

    def test_derived_objects(self):
        from app.plugin.module_ai.query.service import AiQueryService

        r = asyncio.run(AiQueryService.derived_objects())
        assert "base_objects" in r and "derived_objects" in r and "total_derived" in r
        assert isinstance(r["derived_objects"], list)
        for d in r["derived_objects"]:
            assert "name" in d and "base_objects" in d and "attributes" in d

    def test_autopilot_auto_fix(self):
        from app.plugin.module_ai.query.service import AiQueryService

        r = asyncio.run(AiQueryService.autopilot_auto_fix())
        assert "attempted" in r and "fixed" in r and "results" in r
        assert isinstance(r["results"], list)

    def test_favorites_and_plugins(self):
        from app.plugin.module_ai.query.service import AiQueryService
        from app.core.database import async_db_session
        from sqlalchemy import text as _t

        async def _go():
            async with async_db_session.begin() as db:
                await db.execute(_t(
                    "CREATE TABLE IF NOT EXISTS ai_favorite "
                    "(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, ref TEXT, user_id INTEGER, "
                    "is_deleted INTEGER DEFAULT 0, created_time TEXT)"))
            f = await AiQueryService.favorites_add("table", "video_alarm_records", user_id=1)
            assert f["ok"] is True
            lst = await AiQueryService.favorites_list(user_id=1)
            assert any(x["ref"] == "video_alarm_records" for x in lst)
            if lst:
                await AiQueryService.favorites_remove(lst[0]["id"], user_id=1)
            lst2 = await AiQueryService.favorites_list(user_id=1)
            assert not any(x["ref"] == "video_alarm_records" and x["id"] == lst[0]["id"] for x in lst2)
            return True
        assert asyncio.run(_go())
        plugins = asyncio.run(AiQueryService.list_plugins())
        assert len(plugins) >= 4
        assert any(p["kind"] == "数据接入" for p in plugins)

    def test_lineage_propagate(self):
        from app.plugin.module_ai.query.service import AiQueryService

        r = asyncio.run(AiQueryService.lineage_propagate("video_alarm_records"))
        assert "root" in r and "affected_tables" in r and "affected_metrics" in r
        assert isinstance(r["affected_tables"], list)

    def test_dq_rules(self):
        from app.plugin.module_ai.query.service import AiQueryService

        rules = asyncio.run(AiQueryService.dq_rules_list())
        assert len(rules) >= 3 and any(r["key"] == "not_null" for r in rules)
        bad = asyncio.run(AiQueryService.dq_rules_run("t_none", "x", "unknown"))
        assert bad["ok"] is False

    def test_export_asset(self):
        from app.plugin.module_ai.query.service import AiQueryService
        from app.core.database import async_db_session
        from sqlalchemy import text as _t

        async def _go():
            async with async_db_session.begin() as db:
                await db.execute(_t("DROP TABLE IF EXISTS t_export"))
                await db.execute(_t("CREATE TABLE t_export (id INTEGER, name TEXT)"))
                await db.execute(_t("INSERT INTO t_export VALUES (1,'a'),(2,'b')"))
            r = await AiQueryService.export_asset("t_export", 10)
            assert r["ok"] is True and r["row_count"] == 2
            assert "name" in r["columns"]
            bad = await AiQueryService.export_asset("t_nope")
            assert bad["ok"] is False
            b = await AiQueryService.object_browse("t_export", 1, 2)
            assert b["ok"] is True and b["total"] == 2 and "has_next" in b
            return True
        assert asyncio.run(_go())

    def test_dataset_share(self):
        from app.plugin.module_ai.query.service import AiQueryService

        async def _go():
            s = await AiQueryService.share_create("video_alarm_records", user_id=1)
            assert s["ok"] is True and s["token"]
            lst = await AiQueryService.share_list(user_id=1)
            assert any(x["table"] == "video_alarm_records" for x in lst)
            if lst:
                await AiQueryService.share_remove(lst[0]["id"], user_id=1)
            lst2 = await AiQueryService.share_list(user_id=1)
            assert not any(x["id"] == lst[0]["id"] for x in lst2)
            return True
        assert asyncio.run(_go())

    def test_catalog_and_obj_relations_and_access(self):
        from app.plugin.module_ai.query.service import AiQueryService

        c = asyncio.run(AiQueryService.catalog_categories())
        assert "total" in c and "categories" in c and "category_count" in c
        assert isinstance(c["categories"], list)
        o = asyncio.run(AiQueryService.object_relations())
        assert "nodes" in o and "edges" in o and "node_count" in o
        a = asyncio.run(AiQueryService.access_walkthrough(1))
        assert "allowed_count" in a and "blocked_count" in a and "can_see_sensitive" in a
        g = asyncio.run(AiQueryService.guardrails_status())
        assert "total" in g and "enabled" in g and "checks" in g and "score" in g
        assert 0 <= g["score"] <= 100
        rep = asyncio.run(AiQueryService.governance_report())
        assert "summary" in rep and "markdown" in rep and "scores" in rep and "overview" in rep
        assert rep["markdown"] and rep["markdown"].startswith("#")
        h = asyncio.run(AiQueryService.asset_hotspots())
        assert "total" in h and "hot" in h and isinstance(h["hot"], list)
        lc = asyncio.run(AiQueryService.object_lifecycle())
        assert "objects" in lc and "published" in lc and "draft" in lc and "objects_list" in lc
        ks = asyncio.run(AiQueryService.kg_stats())
        assert "data_nodes" in ks and "entities" in ks and "relations" in ks

    def test_version_diff(self, test_client):
        from app.plugin.module_ai.query.service import AiQueryService
        from app.core.database import async_db_session
        from sqlalchemy import text as _t

        async def _go():
            async with async_db_session.begin() as db:
                await db.execute(_t(
                    "CREATE TABLE IF NOT EXISTS ai_asset_version "
                    "(id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, field_name TEXT, "
                    "snapshot TEXT, version_no INTEGER, operator TEXT, is_deleted INTEGER DEFAULT 0, created_time TEXT)"))
            # 表级
            await AiQueryService._record_version("t_diff", {"alias": "A", "domain": "d1"})
            await AiQueryService._record_version("t_diff", {"alias": "B", "domain": "d1"})
            vs = await AiQueryService.list_versions("t_diff")
            assert len(vs) >= 2
            d = await AiQueryService.version_diff(vs[0]["id"], vs[1]["id"])
            assert d["ok"] is True
            assert any(c["key"] == "alias" for c in d["changed"])
            return True
        assert asyncio.run(_go())

    def test_asset_publish(self, test_client):
        from app.plugin.module_ai.query.service import AiQueryService
        from app.core.database import async_db_session
        from types import SimpleNamespace as SN
        from sqlalchemy import text as _t

        async def _go():
            async with async_db_session.begin() as db:
                await db.execute(_t(
                    "CREATE TABLE IF NOT EXISTS ai_asset_version "
                    "(id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, field_name TEXT, "
                    "snapshot TEXT, version_no INTEGER, operator TEXT, is_deleted INTEGER DEFAULT 0, created_time TEXT)"))
            await AiQueryService._record_version("t_rel", {"alias": "X"})
            vs = await AiQueryService.list_versions("t_rel")
            assert vs
            r = await AiQueryService.asset_publish("t_rel", vs[0]["id"], SN(user=SN(id=7)))
            assert r["ok"] is True
            rel = await AiQueryService.asset_releases("t_rel")
            assert rel["published_version_id"] == vs[0]["id"]
            assert any(v["published"] for v in rel["versions"])
            return True
        assert asyncio.run(_go())
