"""distance 叶子与深度事件透传测试（B2a：人脸属性/活体/深度）。

约定：
- 事件契约（Agent 侧并行实现）：``objects[].depth`` 为深度（米，float），
  透传到 ``detections[].depth``（与 attributes/keypoints 同策略）。
- distance 叶子：``{"subject":"distance","op":"lt|gt|le|ge|eq","value":<米>,"label"?,"region"?}``；
  depth 缺失/非数值/非有限值一律跳过，绝不命中、绝不抛异常（fail-closed）。
- 复用既有 attribute 叶子承载人脸属性/活体分数（不新增叶子）。
"""
from app.api.v1.module_video.edge.consumer import normalize_edge_event
from app.api.v1.module_video.inference.service import _match_conditions, explain_conditions

SQUARE = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
DIST = {"subject": "distance", "op": "lt", "value": 1.0}


def _det(depth=None, label="person", cx=0.5, cy=0.5, attributes=None):
    """构造一条归一化检测框；depth 为 None 时不携带该字段。"""
    d = {
        "label": label,
        "confidence": 0.9,
        "bbox": {"x": cx - 0.05, "y": cy - 0.05, "width": 0.1, "height": 0.1},
    }
    if depth is not None:
        d["depth"] = depth
    if attributes is not None:
        d["attributes"] = attributes
    return d


def _eval(leaf, dets):
    return _match_conditions(leaf, dets)


# ------------------------------------------------------------------ 透传链路
def test_normalize_edge_event_passes_depth_and_attributes():
    """objects[].depth（新增）与 attributes（既有）都必须透传到 detections。"""
    ev = {
        "event_id": "d1",
        "camera_id": 7,
        "objects": [
            {
                "label": "face",
                "confidence": 0.9,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "attributes": {"gender_male": 0.91, "age_young": 0.83},
                "depth": 1.75,
            }
        ],
    }
    out = normalize_edge_event(ev)
    assert out["detections"][0]["depth"] == 1.75
    assert out["detections"][0]["attributes"] == {"gender_male": 0.91, "age_young": 0.83}


def test_normalize_edge_event_merges_depth_into_existing_detections():
    """同时含 detections 与 objects 时，depth 按索引并入（与 attributes/keypoints 同策略）。"""
    ev = {
        "event_id": "d2",
        "camera_id": 7,
        "detections": [{"label": "person", "confidence": 0.9, "bbox": {}}],
        "objects": [
            {"label": "person", "confidence": 0.9, "bbox": {}, "depth": 2.0},
        ],
    }
    out = normalize_edge_event(ev)
    assert out["detections"][0]["depth"] == 2.0


# --------------------------------------------------------------- distance 叶子
def test_distance_lt_hit_and_miss():
    assert _eval(DIST, [_det(0.8)]) is True
    assert _eval(DIST, [_det(1.5)]) is False
    assert _eval(DIST, [_det(1.0)]) is False  # lt 为严格小于


def test_distance_operators_are_configurable():
    d = [_det(1.0)]
    assert _eval({"subject": "distance", "op": "gt", "value": 0.5}, d) is True
    assert _eval({"subject": "distance", "op": "gt", "value": 1.0}, d) is False
    assert _eval({"subject": "distance", "op": "ge", "value": 1.0}, d) is True
    assert _eval({"subject": "distance", "op": "le", "value": 1.0}, d) is True
    assert _eval({"subject": "distance", "op": "eq", "value": 1.0}, d) is True
    assert _eval({"subject": "distance", "op": "eq", "value": 1.1}, d) is False


def test_distance_missing_or_invalid_depth_fails_closed():
    """depth 缺失/非数值/NaN → 跳过该检测，不命中。"""
    assert _eval(DIST, [_det()]) is False
    assert _eval(DIST, [_det("far")]) is False
    assert _eval(DIST, [_det(float("nan"))]) is False
    assert _eval(DIST, []) is False
    assert _eval(DIST, ["dirty"]) is False


def test_distance_missing_or_invalid_op_and_value_fails_closed():
    assert _eval({"subject": "distance", "value": 1.0}, [_det(0.5)]) is False
    assert _eval({"subject": "distance", "op": "<", "value": 1.0}, [_det(0.5)]) is False
    assert _eval({"subject": "distance", "op": "lt"}, [_det(0.5)]) is False
    assert _eval({"subject": "distance", "op": "lt", "value": "near"}, [_det(0.5)]) is False


def test_distance_picks_any_valid_detection():
    """存在多条检测时，任一条满足即命中（缺 depth 的检测被跳过）。"""
    assert _eval(DIST, [_det(), _det(0.6)]) is True
    assert _eval(DIST, [_det(), _det(2.0)]) is False


def test_distance_region_filter_uses_bbox_center():
    leaf = {**DIST, "region": SQUARE}
    assert _eval(leaf, [_det(0.5, cx=0.5, cy=0.5)]) is True
    assert _eval(leaf, [_det(0.5, cx=0.05, cy=0.05)]) is False


def test_distance_label_filter():
    leaf = {**DIST, "label": "car"}
    assert _eval(leaf, [_det(0.5, label="person")]) is False
    assert _eval(leaf, [_det(0.5, label="car")]) is True


def test_distance_detail_is_explainable():
    ok, hits = explain_conditions(DIST, [_det(0.8)])
    assert ok is True
    assert hits[0]["subject"] == "distance"
    assert "depth" in hits[0]["detail"]
    assert "0.80" in hits[0]["detail"]
    ok2, hits2 = explain_conditions(DIST, [_det(2.0)])
    assert ok2 is False and hits2 == []


# ------------------------------------ attribute 叶子承载人脸属性/活体（复用）
def test_face_attr_default_rule_matches_agent_emitted_names():
    """face_attr 事件按 ``{"gender_male":..,"age_young":..}`` 发射，默认规则须命中该字段名。"""
    leaf = {"subject": "attribute", "field": "gender_male", "op": "ge", "value": 0.5}
    assert _eval(leaf, [_det(attributes={"gender_male": 0.91, "age_young": 0.83})]) is True
    assert _eval(leaf, [_det(attributes={"gender_male": 0.10, "age_young": 0.83})]) is False
    assert _eval(leaf, [_det(attributes={"age_young": 0.9})]) is False


def test_face_antispoof_rule_alerts_on_non_liveness():
    """face_as 事件按 ``{"liveness":0.93}`` 发射；非活体（分数低）才告警。"""
    leaf = {"subject": "attribute", "field": "liveness", "op": "lt", "value": 0.5}
    assert _eval(leaf, [_det(attributes={"liveness": 0.20})]) is True
    assert _eval(leaf, [_det(attributes={"liveness": 0.93})]) is False
    assert _eval(leaf, [_det(attributes={"gender_male": 0.9})]) is False
