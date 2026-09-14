"""规则编译层测试：参数注入 + 条件校验。"""
import pytest

from app.api.v1.module_video.scene.compile import RuleCompileError, compile_rule

ROI = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
LINE = [[0.5, 0.0], [0.5, 1.0]]


def _and(*leaves):
    return {"op": "and", "children": list(leaves)}


def test_injects_roi_into_region_leaves():
    cond = _and({"subject": "object_present", "label": "person"})
    out = compile_rule("DET_ZONE", {"roi": ROI}, cond)
    leaf = out["children"][0]
    assert leaf["region"] == ROI
    assert leaf["label"] == "person"


def test_direction_overrides_leaf_dir():
    """direction 参数必须覆盖 LINE_CROSS 默认规则的 dir 预填值。"""
    cond = _and({"subject": "line_cross", "dir": "A2B"})
    out = compile_rule("LINE_CROSS", {"line": LINE, "direction": "B2A"}, cond)
    leaf = out["children"][0]
    assert leaf["line"] == LINE
    assert leaf["dir"] == "B2A"


def test_missing_param_keeps_leaf_default():
    cond = _and({"subject": "line_cross", "dir": "A2B"})
    out = compile_rule("LINE_CROSS", {}, cond)
    assert out["children"][0]["dir"] == "A2B"
    assert "line" not in out["children"][0]


def test_threshold_and_window_injection():
    cond = _and(
        {"subject": "object_present"},
        {"subject": "count_window", "op": ">=", "value": 5},
    )
    out = compile_rule("GATHER", {"confidence_threshold": 0.6, "window_sec": 8, "count": 3}, cond)
    present, cw = out["children"]
    assert present["min_confidence"] == 0.6
    assert cw["window_sec"] == 8 and cw["value"] == 3


def test_empty_conditions_returns_empty_dict():
    assert compile_rule("DET_ZONE", {"roi": ROI}, None) == {}
    assert compile_rule("DET_ZONE", {"roi": ROI}, {}) == {}


def test_rejects_unknown_subject():
    with pytest.raises(RuleCompileError):
        compile_rule("DET_ZONE", {}, _and({"subject": "nope"}))


def test_rejects_unimplemented_subject():
    with pytest.raises(RuleCompileError):
        compile_rule("FACE_REC", {}, _and({"subject": "face_match", "op": "gte", "value": 0.6}))


def test_rejects_missing_required_key():
    with pytest.raises(RuleCompileError):
        compile_rule("DET_ZONE", {}, _and({"subject": "attribute", "op": "lt"}))  # 缺 field/value


def test_rejects_bad_op_and_bad_value():
    with pytest.raises(RuleCompileError):
        compile_rule("OVERCROWD", {}, _and({"subject": "count", "op": "~", "value": 3}))
    with pytest.raises(RuleCompileError):
        compile_rule("OVERCROWD", {}, _and({"subject": "count", "op": ">=", "value": "x"}))


def test_rejects_malformed_region():
    with pytest.raises(RuleCompileError):
        compile_rule("DET_ZONE", {"roi": [[0.1, 0.1]]}, _and({"subject": "object_present"}))


def test_not_node_is_preserved():
    cond = {"op": "not", "children": [{"subject": "object_present", "label": "person"}]}
    out = compile_rule("DET_ZONE", {}, cond)
    assert out["op"] == "not"
