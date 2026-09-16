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


def test_group_leaf_rejected_on_camera_scope():
    """组叶子用于相机作用域规则 → 编译报错；组作用域放行。"""
    cond = _and({"subject": "group_count", "window_sec": 60, "op": ">=", "value": 2})
    with pytest.raises(RuleCompileError):
        compile_rule("GATHER", {}, cond, scope="camera")
    assert compile_rule("GATHER", {}, cond, scope="group")["children"][0]["subject"] == "group_count"


def test_camera_leaf_allowed_on_group_scope():
    """相机叶子用于组作用域规则 → 允许（语义：组内任一相机命中即命中）。"""
    cond = _and({"subject": "object_present", "label": "person"})
    out = compile_rule("DET_ZONE", {}, cond, scope="group")
    assert out["children"][0]["subject"] == "object_present"


def test_default_scope_does_not_enforce_group_ownership():
    """scope 缺省（None）放行组叶子，兼容既有调用点。"""
    cond = _and({"subject": "group_count", "window_sec": 60, "op": ">=", "value": 2})
    out = compile_rule("GATHER", {}, cond)
    assert out["children"][0]["subject"] == "group_count"


def test_group_params_do_not_break_count_window_binding():
    """组叶子走独立参数键，既有 count_window 的 window_sec/count 语义不变。"""
    cond = _and(
        {"subject": "count_window", "op": ">=", "value": 5},
        {"subject": "group_count", "op": ">=", "value": 2},
    )
    out = compile_rule(
        "GATHER",
        {"window_sec": 8, "count": 3, "group_window_sec": 30, "group_count": 4},
        cond,
    )
    cw, gc = out["children"]
    assert cw["window_sec"] == 8 and cw["value"] == 3
    assert gc["window_sec"] == 30 and gc["value"] == 4


def test_group_leaf_requires_window_and_value():
    """group_count / group_coverage 的 window_sec、value 为必填。"""
    with pytest.raises(RuleCompileError):
        compile_rule("GATHER", {}, _and({"subject": "group_count", "op": ">=", "value": 2}))
    with pytest.raises(RuleCompileError):
        compile_rule("GATHER", {}, _and({"subject": "group_coverage", "op": ">=", "window_sec": 60}))
    with pytest.raises(RuleCompileError):
        compile_rule("GATHER", {}, _and({"subject": "group_coverage", "op": "~", "window_sec": 60, "value": 0.5}))
