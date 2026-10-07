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
