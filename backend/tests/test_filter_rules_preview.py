from app.plugin.module_ai.query.service import AiQueryService


def test_preview_filter_rules_summary(monkeypatch):
    async def fake_load(datasource_id):
        class D: pass
        d = D(); d.filter_rules = None
        return d
    monkeypatch.setattr("app.plugin.module_ai.query.service._load_ds", fake_load)

    async def fake_schema(datasource_id, included_only=False):
        return [
            {"table": "SYS_USER", "comment": "", "columns": [{"name": "DELETED_TIME"}, {"name": "coal_amount"}]},
            {"table": "video_cameras", "comment": "", "columns": [{"name": "created_time"}]},
        ]
    monkeypatch.setattr("app.plugin.module_ai.query.service.list_ds_schema", fake_schema)

    import asyncio
    out = asyncio.run(AiQueryService.preview_filter_rules(4, rules=None))
    assert out["summary"]["table_total"] == 2
    assert out["summary"]["system_tables"] == 1
    assert out["summary"]["business_tables"] == 1
    assert out["summary"]["audit_fields"] == 2  # DELETED_TIME + created_time
    assert out["tables"][0]["reason"] == "前缀 SYS_"
    assert out["fields"][0]["is_audit"] is True
    assert out["fields"][1]["is_audit"] is False
