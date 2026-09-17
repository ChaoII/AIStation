"""叶子能力注册表测试：与求值器支持集必须一致（单一事实源对拍）。"""

from app.api.v1.module_video.inference.service import TEMPORAL_SUBJECTS
from app.api.v1.module_video.scene.leaves import IMPLEMENTED_LEAVES, LEAF_CAPABILITIES

# 求值器当前实际支持的非时序叶子（见 inference/service.py:_match_conditions）
_EVALUABLE_NON_TEMPORAL = {
    "attribute",
    "text_match",
    "ocr_label",
    "object_present",
    "zone_enter",
    "count",
    "keypoint_geometry",
}


def test_implemented_leaves_match_evaluator():
    expected = _EVALUABLE_NON_TEMPORAL | set(TEMPORAL_SUBJECTS)
    assert IMPLEMENTED_LEAVES == expected


def test_every_entry_declares_contract():
    for subject, cap in LEAF_CAPABILITIES.items():
        assert isinstance(cap.get("label"), str) and cap["label"], subject
        assert isinstance(cap.get("implemented"), bool), subject
        assert isinstance(cap.get("params"), list), subject
        assert isinstance(cap.get("ops"), list), subject
        for p in cap["params"]:
            assert isinstance(p.get("key"), str) and isinstance(p.get("type"), str), subject


def test_implemented_flags_consistent():
    for subject, cap in LEAF_CAPABILITIES.items():
        assert cap["implemented"] is (subject in IMPLEMENTED_LEAVES), subject


def test_unimplemented_leaves_listed_for_ui():
    """未实现叶子必须列出（供前端置灰），至少覆盖人脸/活体类。"""
    assert {"face_match", "liveness"} <= set(LEAF_CAPABILITIES)
    for s in ("face_match", "liveness"):
        assert LEAF_CAPABILITIES[s]["implemented"] is False


def test_keypoint_geometry_leaf_registered_as_implemented():
    """姿态切片：keypoint_geometry 已实现（fall/climb/smoke_phone），必须与求值器对拍。"""
    cap = LEAF_CAPABILITIES["keypoint_geometry"]
    assert cap["implemented"] is True
    assert "keypoint_geometry" in IMPLEMENTED_LEAVES
    keys = {p["key"] for p in cap["params"]}
    assert {"rule", "region", "line", "min_sec", "op", "value"} <= keys
    # op 不登记为该叶子的受限算子集：缺省由 rule 决定，声明非空会强制所有规则带 op
    assert cap["ops"] == []


def test_group_leaves_registered():
    """跨相机聚合叶子必须进入注册表且标记为已实现（与求值器对拍）。"""
    for s in ("group_count", "group_coverage"):
        assert s in LEAF_CAPABILITIES, s
        assert LEAF_CAPABILITIES[s]["implemented"] is True, s
        assert s in IMPLEMENTED_LEAVES, s


def test_rule_capabilities_api(test_client, auth_headers):
    resp = test_client.get("/api/v1/video/scene/rule-capabilities", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data["logic"]) >= {"and", "or"}
    subjects = {x["subject"] for x in data["leaves"]}
    assert "object_present" in subjects and "line_cross" in subjects
