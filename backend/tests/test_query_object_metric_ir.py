"""S2-T1：对象查询 IR 的 metric 节点与校验收敛（纯逻辑，可 PYTEST_NO_APP=1）。"""
from app.plugin.module_ai.query.object_query import ObjectQueryIR, parse_ir, validate_ir


def _allowed():
    return {
        "coal_batch": {
            "name": "入厂煤批次",
            "fields": {"FUELKINDNAME": {"name": "煤种", "type": "string", "options": []}},
            "links": {},
            "metrics": {"batch_count": {"name": "批次量"}},
        }
    }


def test_ir_metric_roundtrip():
    ir = ObjectQueryIR.from_dict({"object": "coal_batch", "metric": "batch_count"})
    assert ir.metric == "batch_count"
    assert ir.to_dict()["metric"] == "batch_count"


def test_validate_keeps_known_metric():
    ir, reasons = validate_ir(
        parse_ir('{"object":"coal_batch","metric":"batch_count"}'),
        _allowed(),
        metrics={"batch_count": {"key": "batch_count", "object_code": "coal_batch"}},
    )
    assert ir is not None and ir.metric == "batch_count"


def test_validate_metric_only_infers_object():
    ir, reasons = validate_ir(
        parse_ir('{"metric":"batch_count","group_by":[{"field":"FUELKINDNAME","alias":"煤种"}]}'),
        _allowed(),
        metrics={"batch_count": {"key": "batch_count", "object_code": "coal_batch"}},
    )
    assert ir is not None and ir.object == "coal_batch" and ir.metric == "batch_count"


def test_validate_drops_unknown_metric():
    ir, reasons = validate_ir(
        parse_ir('{"object":"coal_batch","metric":"nope",'
                 '"filters":[{"field":"FUELKINDNAME","op":"eq","value":"原煤"}]}'),
        _allowed(),
        metrics={"batch_count": {"key": "batch_count", "object_code": "coal_batch"}},
    )
    assert ir is not None and ir.metric == ""
    assert any("指标" in r for r in reasons)
