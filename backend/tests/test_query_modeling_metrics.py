"""S3-T2：绑定型指标生成（prompt/解析/口径验证）。"""
import asyncio

from app.plugin.module_ai.query.modeling import parse_metrics, verify_metric


def test_parse_metrics_filters_unknown_object_and_bad_key():
    valid = {"coal_batch": {"fields": [{"code": "FUELKINDNAME"}]}}
    text = ('[{"key":"coal_batch_count","name":"入厂批次数","object_code":"coal_batch",'
            '"property_code":"","agg_fn":"count","bound_dimensions":["FUELKINDNAME"]},'
            '{"key":"x y","name":"坏","object_code":"coal_batch","agg_fn":"count"},'
            '{"key":"ghost","name":"幽灵","object_code":"nope","agg_fn":"count"}]')
    out = parse_metrics(text, valid)
    keys = [m["key"] for m in out]
    assert "coal_batch_count" in keys and "ghost" not in keys and "x y" not in keys


def test_parse_metrics_defaults_agg_to_count():
    valid = {"coal_batch": {"fields": []}}
    out = parse_metrics('[{"key":"k1","object_code":"coal_batch"}]', valid)
    assert out and out[0]["agg_fn"] == "count"


def test_verify_metric_ok(monkeypatch):
    async def _go():
        from app.plugin.module_ai.ontology import service as ont

        from app.plugin.module_ai.query import modeling as M

        async def _fake_agg(object_code, group_by="", aggs=None, filters=None, limit=50,
                            principal=None, scenario_code=""):
            return {"ok": True, "series": [{"label": "a", "value": 3}],
                    "rows": [["a", 3]]}

        monkeypatch.setattr(ont, "instance_aggregate", _fake_agg)
        return await M.verify_metric({"object_code": "coal_batch", "property_code": "",
                                      "agg_fn": "count", "bound_dimensions": []})

    r = asyncio.run(_go())
    assert r["ok"] is True


def test_verify_metric_rejects_when_aggregate_fails(monkeypatch):
    async def _go():
        from app.plugin.module_ai.ontology import service as ont

        from app.plugin.module_ai.query import modeling as M

        async def _fake_agg(*a, **k):
            return {"ok": False, "msg": "字段不在表里"}

        monkeypatch.setattr(ont, "instance_aggregate", _fake_agg)
        return await M.verify_metric({"object_code": "coal_batch", "property_code": "NOPE",
                                      "agg_fn": "count", "bound_dimensions": []})

    r = asyncio.run(_go())
    assert r["ok"] is False
