"""绑定型指标执行：走本体实例层（不依赖 sql_template）。"""
import asyncio
from types import SimpleNamespace


def test_execute_metric_bound_uses_instance_aggregate(monkeypatch):
    async def _go():
        from app.plugin.module_ai.ontology import service as ont

        from app.plugin.module_ai.query import service as S

        async def _fake_agg(object_code, group_by="", aggs=None, filters=None, limit=50,
                            principal=None, scenario_code=""):
            return {"ok": True, "rows": [["合计", 277]], "series": []}

        monkeypatch.setattr(ont, "instance_aggregate", _fake_agg)
        m = {"key": "coal_batch_count", "name": "入厂批次数", "datasource": "ds:4",
             "object_code": "coal_batch", "property_code": "", "agg_fn": "count",
             "bound_dimensions": [], "sql_template": "SELECT 1 AS 数值"}
        return await S._execute_metric(m, {}, SimpleNamespace(user=SimpleNamespace(id=1)))

    r = asyncio.run(_go())
    assert r["columns"] == ["合计", "入厂批次数"]
    assert r["rows"] == [["合计", 277]]
