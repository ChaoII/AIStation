"""S1-T4：upsert_object 校验支撑表属于目标数据源 schema。"""
import asyncio

import pytest


def test_upsert_object_rejects_unknown_backing_table(monkeypatch):
    async def _go():
        from app.plugin.module_ai.ontology import service as ont
        from app.plugin.module_ai.query import service as qs

        async def _fake_schema(ds_id):
            return [{"table": "FUEL_CB_COALBALANCE", "columns": [{"name": "ID"}]}]

        monkeypatch.setattr(qs, "list_ds_schema", _fake_schema)
        await ont.upsert_object(
            {
                "code": "__t_bad__",
                "name": "坏对象",
                "datasource_id": 4,
                "backing_table": "NOT_EXIST_TABLE",
            }
        )

    with pytest.raises(Exception) as ei:
        asyncio.run(_go())
    assert "schema" in str(ei.value)
