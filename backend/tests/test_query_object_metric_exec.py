"""S2-T3：对象查询执行绑定型指标（走 instance_aggregate）。"""
import asyncio


def _meta(code):
    return {"code": code, "name": "入厂煤批次", "table": "FUEL_CMCS_INFACTORYBATCH",
            "key_prop": "ID", "name_prop": "FUELKINDNAME", "edits_enabled": False,
            "datasource_id": 4, "props": [], "cols": ["FUELKINDNAME"],
            "real_cols": {"FUELKINDNAME"}, "materialized": True}


def test_execute_ir_metric_uses_instance_aggregate(monkeypatch):
    async def _go():
        from app.plugin.module_ai.ontology import service as ont
        from app.plugin.module_ai.query import object_exec as oe
        from app.plugin.module_ai.query.object_query import ObjectQueryIR

        seen = {}

        async def _fake_meta(code):
            return _meta(code)

        async def _fake_agg(object_code, group_by="", aggs=None, filters=None, limit=50,
                            principal=None, scenario_code=""):
            seen.update(object_code=object_code, group_by=group_by, aggs=aggs)
            return {"ok": True, "series": [{"label": "原煤", "value": 85}],
                    "rows": [["原煤", 85]], "group_by": group_by}

        monkeypatch.setattr(ont, "_instance_meta", _fake_meta)
        monkeypatch.setattr(ont, "instance_aggregate", _fake_agg)
        ir = ObjectQueryIR.from_dict({"object": "coal_batch", "metric": "batch_count",
                                      "group_by": [{"field": "FUELKINDNAME", "alias": "煤种"}]})
        metrics = {"batch_count": {"key": "batch_count", "object_code": "coal_batch",
                                   "property_code": "", "agg_fn": "count", "name": "批次量"}}
        return await oe.execute_ir(ir, principal=None, metrics=metrics), seen

    r, seen = asyncio.run(_go())
    assert r["ok"] is True
    assert seen["object_code"] == "coal_batch" and seen["aggs"][0]["fn"] == "count"
    assert seen["group_by"] == "FUELKINDNAME"
    assert r["shape"] == "metric-agg"


def test_execute_ir_nonbound_metric_degrades(monkeypatch):
    async def _go():
        from app.plugin.module_ai.ontology import service as ont
        from app.plugin.module_ai.query import object_exec as oe
        from app.plugin.module_ai.query.object_query import ObjectQueryIR

        async def _fake_meta(code):
            return _meta(code)

        monkeypatch.setattr(ont, "_instance_meta", _fake_meta)
        ir = ObjectQueryIR.from_dict({"object": "coal_batch", "metric": "x"})
        metrics = {"x": {"key": "x", "object_code": "coal_batch", "property_code": "", "agg_fn": ""}}
        return await oe.execute_ir(ir, principal=None, metrics=metrics)

    r = asyncio.run(_go())
    assert r["ok"] is False
