"""S2-T2：IR 提示词与词表注入绑定指标（纯逻辑）。"""
from app.plugin.module_ai.query.object_query import build_allowed, render_ir_prompt


def test_build_allowed_attaches_metrics():
    allowed = build_allowed(
        [{"code": "coal_batch", "name": "入厂煤批次"}],
        {"coal_batch": [{"code": "FUELKINDNAME", "name": "煤种", "prop_type": "string", "options": []}]},
        {"coal_batch": []},
        metrics_by_object={"coal_batch": [
            {"key": "batch_count", "name": "批次量", "agg_fn": "count",
             "property_code": "", "bound_dimensions": ["FUELKINDNAME"]},
        ]},
    )
    assert "batch_count" in allowed["coal_batch"]["metrics"]
    assert allowed["coal_batch"]["metrics"]["batch_count"]["name"] == "批次量"


def test_prompt_injects_metrics():
    allowed = build_allowed(
        [{"code": "coal_batch", "name": "入厂煤批次"}],
        {"coal_batch": [{"code": "FUELKINDNAME", "name": "煤种", "prop_type": "string", "options": []}]},
        {"coal_batch": []},
        metrics_by_object={"coal_batch": [
            {"key": "batch_count", "name": "批次量", "agg_fn": "count", "bound_dimensions": ["FUELKINDNAME"]},
        ]},
    )
    p = render_ir_prompt("各煤种的批次量", allowed, metrics={"batch_count": {"key": "batch_count"}})
    assert "batch_count" in p and '"metric"' in p


def test_prompt_without_metrics_unchanged():
    allowed = build_allowed(
        [{"code": "coal_batch", "name": "入厂煤批次"}],
        {"coal_batch": [{"code": "FUELKINDNAME", "name": "煤种", "prop_type": "string", "options": []}]},
        {"coal_batch": []},
    )
    p = render_ir_prompt("各煤种的批次量", allowed)
    # 无绑定指标时：不出现任何指标 key，但输出格式仍给出 metric 可选项
    assert "batch_count" not in p
    assert '"metric"' in p
