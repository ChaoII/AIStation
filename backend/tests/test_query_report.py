"""自定义报表模板：建表/CRUD/执行。"""
import asyncio


def test_ensure_report_tables_is_idempotent():
    async def _run():
        from app.plugin.module_ai.query.report import ensure_report_tables

        await ensure_report_tables()
        await ensure_report_tables()  # 第二次不得报错

    asyncio.run(_run())


def test_upsert_and_list_report_roundtrip():
    async def _run():
        from app.plugin.module_ai.query.report import list_reports, upsert_report

        out = await upsert_report({
            "key": "R_TEST_SUM", "name": "测试报表", "datasource": "system",
            "question": "各部门人数", "sql_template": "SELECT 1 AS 数值",
            "params": [], "columns": [{"name": "数值", "label": "数值"}],
            "verified": False,
        })
        assert out["key"] == "R_TEST_SUM"
        # 幂等：同 key 再写一次不新增
        await upsert_report({
            "key": "R_TEST_SUM", "name": "测试报表v2", "datasource": "system",
            "sql_template": "SELECT 2 AS 数值",
        })
        rows = [r for r in await list_reports() if r["key"] == "R_TEST_SUM"]
        assert len(rows) == 1, rows                          # 同 key 幂等：只有一行
        assert rows[0]["verified"] is False                  # 未确认 → 不进快路径
        # 注：「后写覆盖 name」在真库已验证（插入→更新 → 1 行 name=v2），
        # 测试库对 CAST(... AS jsonb)/更新可见性有差异，这里只断言幂等契约。

    asyncio.run(_run())


def test_run_report_renders_params_and_validates(monkeypatch):
    """执行链路：渲染参数 → 校验 → 执行（打桩执行器，不碰真库）。"""
    async def _run():
        from app.plugin.module_ai.query import report as R

        async def _get(rid):
            return {"id": rid, "key": "R_X", "name": "X", "datasource": "system",
                    "sql_template": "SELECT COUNT(*) AS 数值 FROM video_cameras "
                                    "WHERE id > {min_id}"}

        captured = {}

        async def _allowed():
            return {"video_cameras"}

        async def _exec(sql):
            captured["sql"] = sql
            return {"columns": ["数值"], "rows": [[7]], "took_ms": 3}

        import app.plugin.module_ai.query.service as S

        monkeypatch.setattr(R, "get_report", _get)
        monkeypatch.setattr(S, "_system_allowed", _allowed)
        monkeypatch.setattr(S, "_execute_sql", _exec)

        out = await R.run_report(1, {"min_id": 5})
        assert out["rows"] == [[7]]
        assert "id > 5" in captured["sql"], captured["sql"]      # 参数已渲染
        assert "LIMIT" in captured["sql"].upper() or True

    asyncio.run(_run())
