"""keypoint_geometry 叶子与关键点事件透传测试（姿态切片）。

约定：
- 关键点契约（Agent 侧并行实现）：``objects[].keypoints = [[x, y, score], ...]``，
  坐标为归一化 0~1；本叶子按 COCO-17 人体姿态索引取点（见 service.py 常量）。
- 所有非法/缺失输入一律不命中且不抛异常（延续既有 fail-closed 约定）。
- 时序部分（smoke_phone 的 min_sec）用内存 TemporalStore 保证确定性。
"""
from app.api.v1.module_video.edge.consumer import normalize_edge_event
from app.api.v1.module_video.inference.service import (
    _has_temporal_leaf,
    _match_conditions,
    explain_conditions,
)
from app.api.v1.module_video.inference.temporal import TemporalStore

CAM = 1
ALGO = "FALL"
SQUARE = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]


def _pose(points: dict[int, tuple[float, float]], score: float = 0.9):
    """构造 COCO-17 关键点数组：未给出的点置 (0,0,0)（视为无效）。"""
    arr = [[0.0, 0.0, 0.0] for _ in range(17)]
    for idx, (x, y) in points.items():
        arr[idx] = [x, y, score]
    return arr


def _det(keypoints=None, label="person", cx=0.5, cy=0.5, track_id=None):
    """构造一条归一化检测框；keypoints 为 None 时不携带该字段。"""
    d = {
        "label": label,
        "confidence": 0.9,
        "bbox": {"x": cx - 0.05, "y": cy - 0.05, "width": 0.1, "height": 0.1},
    }
    if keypoints is not None:
        d["keypoints"] = keypoints
    if track_id is not None:
        d["track_id"] = track_id
    return d


def _standing():
    """直立：肩 (5,6) 在上、髋 (11,12) 在下，躯干与竖直方向夹角 0°。"""
    return _pose({5: (0.5, 0.3), 6: (0.5, 0.3), 11: (0.5, 0.6), 12: (0.5, 0.6)})


def _fallen():
    """倒地：肩与髋同一水平线，躯干与竖直方向夹角 90°。"""
    return _pose({5: (0.6, 0.5), 6: (0.6, 0.5), 11: (0.4, 0.5), 12: (0.4, 0.5)})


def _tilt45():
    """躯干与竖直方向夹角 45°（用于校验阈值/算子）。"""
    return _pose({5: (0.6, 0.4), 6: (0.6, 0.4), 11: (0.5, 0.5), 12: (0.5, 0.5)})


def _eval(leaf, dets, *, store=None, now=None, alarm_interval=0):
    return _match_conditions(
        leaf,
        dets,
        temporal=store,
        camera_id=CAM,
        alarm_type=ALGO,
        now=now,
        alarm_interval=alarm_interval,
    )


# ------------------------------------------------------------------ 透传链路
def test_normalize_edge_event_passes_keypoints():
    """事件 v2 的 objects[].keypoints 必须透传到 detections（否则求值器看不到）。"""
    ev = {
        "event_id": "kp1",
        "camera_id": 7,
        "objects": [
            {
                "label": "person",
                "confidence": 0.9,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "keypoints": [[0.5, 0.3, 0.9], [0.5, 0.6, 0.8]],
            }
        ],
    }
    out = normalize_edge_event(ev)
    assert out["detections"][0]["keypoints"] == [[0.5, 0.3, 0.9], [0.5, 0.6, 0.8]]


def test_normalize_edge_event_merges_keypoints_into_existing_detections():
    """同时含 detections 与 objects 时，keypoints 按索引并入（与 attributes/text 同策略）。"""
    ev = {
        "event_id": "kp2",
        "camera_id": 7,
        "detections": [{"label": "person", "confidence": 0.9, "bbox": {}}],
        "objects": [
            {
                "label": "person",
                "confidence": 0.9,
                "bbox": {},
                "keypoints": [[0.5, 0.3, 0.9]],
            }
        ],
    }
    out = normalize_edge_event(ev)
    assert out["detections"][0]["keypoints"] == [[0.5, 0.3, 0.9]]


# ----------------------------------------------------------------------- fall
def test_fall_hit_on_fallen_torso():
    leaf = {"subject": "keypoint_geometry", "rule": "fall"}
    assert _eval(leaf, [_det(_fallen())]) is True


def test_fall_miss_on_standing_torso():
    leaf = {"subject": "keypoint_geometry", "rule": "fall"}
    assert _eval(leaf, [_det(_standing())]) is False


def test_fall_threshold_and_op_are_configurable():
    leaf = {"subject": "keypoint_geometry", "rule": "fall", "op": ">=", "value": 30.0}
    assert _eval(leaf, [_det(_tilt45())]) is True
    strict = {"subject": "keypoint_geometry", "rule": "fall", "op": ">", "value": 90.0}
    assert _eval(strict, [_det(_fallen())]) is False
    lax = {"subject": "keypoint_geometry", "rule": "fall", "op": ">=", "value": 90.0}
    assert _eval(lax, [_det(_fallen())]) is True


def test_fall_missing_keypoints_is_false():
    assert _eval({"subject": "keypoint_geometry", "rule": "fall"}, [_det()]) is False
    assert _eval({"subject": "keypoint_geometry", "rule": "fall"}, [_det(_pose({}))]) is False
    # 只有肩没有髋 → 无法构成躯干轴
    assert _eval(
        {"subject": "keypoint_geometry", "rule": "fall"},
        [_det(_pose({5: (0.6, 0.5), 6: (0.6, 0.5)}))],
    ) is False


def test_fall_region_filter_uses_bbox_center():
    leaf = {"subject": "keypoint_geometry", "rule": "fall", "region": SQUARE}
    assert _eval(leaf, [_det(_fallen(), cx=0.5, cy=0.5)]) is True
    assert _eval(leaf, [_det(_fallen(), cx=0.05, cy=0.05)]) is False


def test_fall_invalid_value_or_op_is_false():
    assert _eval({"subject": "keypoint_geometry", "rule": "fall", "value": "x"}, [_det(_fallen())]) is False
    assert _eval({"subject": "keypoint_geometry", "rule": "fall", "op": "~"}, [_det(_fallen())]) is False
    assert _eval({"subject": "keypoint_geometry", "rule": "fall", "value": -1}, [_det(_fallen())]) is False


# ---------------------------------------------------------------------- climb
def test_climb_above_line_hit_below_line_miss():
    line = [[0.0, 0.5], [1.0, 0.5]]
    leaf = {"subject": "keypoint_geometry", "rule": "climb", "line": line}
    above = _pose({5: (0.5, 0.2), 6: (0.5, 0.2), 11: (0.5, 0.3), 12: (0.5, 0.3)})
    below = _pose({5: (0.5, 0.6), 6: (0.5, 0.6), 11: (0.5, 0.7), 12: (0.5, 0.7)})
    assert _eval(leaf, [_det(above)]) is True
    assert _eval(leaf, [_det(below)]) is False


def test_climb_vertical_line_fails_closed():
    leaf = {"subject": "keypoint_geometry", "rule": "climb", "line": [[0.5, 0.0], [0.5, 1.0]]}
    above = _pose({5: (0.5, 0.2), 6: (0.5, 0.2), 11: (0.5, 0.3), 12: (0.5, 0.3)})
    assert _eval(leaf, [_det(above)]) is False


def test_climb_invalid_line_fails_closed():
    leaf = {"subject": "keypoint_geometry", "rule": "climb", "line": [[0.5, 0.5]]}
    above = _pose({5: (0.5, 0.2), 6: (0.5, 0.2), 11: (0.5, 0.3), 12: (0.5, 0.3)})
    assert _eval(leaf, [_det(above)]) is False


def test_climb_height_threshold_without_line():
    above = _pose({5: (0.5, 0.2), 6: (0.5, 0.2), 11: (0.5, 0.3), 12: (0.5, 0.3)})
    low = _pose({5: (0.5, 0.6), 6: (0.5, 0.6), 11: (0.5, 0.7), 12: (0.5, 0.7)})
    leaf = {"subject": "keypoint_geometry", "rule": "climb", "value": 0.5}
    assert _eval(leaf, [_det(above)]) is True
    assert _eval(leaf, [_det(low)]) is False
    # 缺省高度阈值 0.5：0.45 < 0.5 命中
    mid = _pose({5: (0.5, 0.4), 6: (0.5, 0.4), 11: (0.5, 0.5), 12: (0.5, 0.5)})
    assert _eval({"subject": "keypoint_geometry", "rule": "climb"}, [_det(mid)]) is True


def test_climb_missing_keypoints_is_false():
    leaf = {"subject": "keypoint_geometry", "rule": "climb"}
    assert _eval(leaf, [_det()]) is False


# ---------------------------------------------------------------- smoke_phone
def _hand_near_head():
    return _pose({0: (0.5, 0.2), 9: (0.52, 0.22), 10: (0.7, 0.7)})


def _hand_far_from_head():
    return _pose({0: (0.5, 0.2), 9: (0.9, 0.9), 10: (0.8, 0.8)})


def test_smoke_phone_near_head_hit():
    leaf = {"subject": "keypoint_geometry", "rule": "smoke_phone"}
    assert _eval(leaf, [_det(_hand_near_head())]) is True
    assert _eval(leaf, [_det(_hand_far_from_head())]) is False


def test_smoke_phone_head_fallback_to_ears():
    """鼻子缺失时回退耳中点作为头部参照。"""
    leaf = {"subject": "keypoint_geometry", "rule": "smoke_phone"}
    kps = _pose({3: (0.48, 0.2), 4: (0.52, 0.2), 9: (0.5, 0.21), 10: (0.8, 0.8)})
    assert _eval(leaf, [_det(kps)]) is True


def test_smoke_phone_missing_wrist_or_head_is_false():
    leaf = {"subject": "keypoint_geometry", "rule": "smoke_phone"}
    assert _eval(leaf, [_det(_pose({0: (0.5, 0.2)}))]) is False
    assert _eval(leaf, [_det(_pose({9: (0.5, 0.2), 10: (0.5, 0.25)}))]) is False
    assert _eval(leaf, [_det()]) is False


def test_smoke_phone_min_sec_requires_sustained_track():
    leaf = {"subject": "keypoint_geometry", "rule": "smoke_phone", "min_sec": 5}
    store = TemporalStore(prefer_redis=False)
    store.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    store.observe(CAM, ALGO, [_det(track_id=1)], 1006)
    assert _eval(leaf, [_det(_hand_near_head())], store=store, now=1006) is True
    # 轨迹存在时长不足
    assert _eval(leaf, [_det(_hand_near_head())], store=store, now=1003) is False
    # 轨迹已过期（idle > grace）
    assert _eval(leaf, [_det(_hand_near_head())], store=store, now=2000) is False
    # 缺时序状态存储 → fail-closed
    assert _eval(leaf, [_det(_hand_near_head())], now=1006) is False


def test_smoke_phone_without_min_sec_is_single_frame():
    """未传 min_sec 时不依赖时序状态（单帧判定）。"""
    leaf = {"subject": "keypoint_geometry", "rule": "smoke_phone"}
    assert _eval(leaf, [_det(_hand_near_head())], now=None) is True


def test_smoke_phone_min_sec_invalid_is_false():
    leaf = {"subject": "keypoint_geometry", "rule": "smoke_phone", "min_sec": "x"}
    store = TemporalStore(prefer_redis=False)
    assert _eval(leaf, [_det(_hand_near_head())], store=store, now=1006) is False


# -------------------------------------------------------------- face_landmark
def _face_kps(n: int, score: float = 0.9):
    """构造 n 个有效人脸关键点（坐标为归一化值，互不重叠）。"""
    return [[(i + 1) / (n + 1), (i + 1) / (n + 1), score] for i in range(n)]


def test_face_landmark_hit_when_enough_valid_points():
    leaf = {"subject": "keypoint_geometry", "rule": "face_landmark"}
    assert _eval(leaf, [_det(_face_kps(5))]) is True
    assert _eval(leaf, [_det(_face_kps(6))]) is True


def test_face_landmark_miss_when_too_few_valid_points():
    """缺省最少 5 个有效点：4 个有效点不命中（fail-closed）。"""
    leaf = {"subject": "keypoint_geometry", "rule": "face_landmark"}
    assert _eval(leaf, [_det(_face_kps(4))]) is False
    assert _eval(leaf, [_det()]) is False
    assert _eval(leaf, [_det([])]) is False


def test_face_landmark_low_score_points_not_counted():
    """分数低于 0.3 的关键点视为未检出，不计入有效点数。"""
    leaf = {"subject": "keypoint_geometry", "rule": "face_landmark", "value": 3}
    kps = _face_kps(2, score=0.9) + _face_kps(4, score=0.1)
    assert _eval(leaf, [_det(kps)]) is False


def test_face_landmark_threshold_and_op_are_configurable():
    leaf = {"subject": "keypoint_geometry", "rule": "face_landmark", "op": ">=", "value": 3}
    assert _eval(leaf, [_det(_face_kps(3))]) is True
    assert _eval(leaf, [_det(_face_kps(2))]) is False
    strict = {"subject": "keypoint_geometry", "rule": "face_landmark", "op": ">", "value": 3}
    assert _eval(strict, [_det(_face_kps(3))]) is False


def test_face_landmark_invalid_threshold_or_op_fails_closed():
    bad_value = {"subject": "keypoint_geometry", "rule": "face_landmark", "value": "x"}
    assert _eval(bad_value, [_det(_face_kps(9))]) is False
    neg = {"subject": "keypoint_geometry", "rule": "face_landmark", "value": -1}
    assert _eval(neg, [_det(_face_kps(9))]) is False
    bad_op = {"subject": "keypoint_geometry", "rule": "face_landmark", "op": "~", "value": 1}
    assert _eval(bad_op, [_det(_face_kps(9))]) is False


def test_face_landmark_region_filter_uses_bbox_center():
    leaf = {"subject": "keypoint_geometry", "rule": "face_landmark", "region": SQUARE}
    assert _eval(leaf, [_det(_face_kps(9), cx=0.5, cy=0.5)]) is True
    assert _eval(leaf, [_det(_face_kps(9), cx=0.05, cy=0.05)]) is False


def test_face_landmark_detail_is_explainable():
    leaf = {"subject": "keypoint_geometry", "rule": "face_landmark", "op": ">=", "value": 5}
    ok, hits = explain_conditions(leaf, [_det(_face_kps(7))])
    assert ok is True
    assert hits[0]["subject"] == "keypoint_geometry"
    assert "face_kp" in hits[0]["detail"] and "7" in hits[0]["detail"]


# -------------------------------------------------------------------- gesture
def test_gesture_is_documented_stub_and_always_false():
    """gesture 规则为已声明的桩实现：任何输入均不命中（缺 21 点手部关键点模型）。"""
    leaf = {"subject": "keypoint_geometry", "rule": "gesture"}
    kps = _pose({0: (0.5, 0.2), 9: (0.5, 0.2), 10: (0.5, 0.25)})
    assert _eval(leaf, [_det(kps)]) is False
    ok, hits = explain_conditions(leaf, [_det(kps)])
    assert ok is False and hits == []
    ok2, hits2 = explain_conditions(leaf, [_det(kps)], temporal=None)
    assert ok2 is False


# ------------------------------------------------------------- 非法输入与说明
def test_invalid_leaf_never_raises():
    store = TemporalStore(prefer_redis=False)
    bad_leaves = [
        {"subject": "keypoint_geometry"},
        {"subject": "keypoint_geometry", "rule": "dance"},
        {"subject": "keypoint_geometry", "rule": 123},
        {"subject": "keypoint_geometry", "rule": "fall", "op": ["x"]},
    ]
    for leaf in bad_leaves:
        assert _eval(leaf, [_det(_fallen())], store=store, now=1000) is False
    # 脏检测项（非 dict / keypoints 非法）也不得抛异常
    assert _eval({"subject": "keypoint_geometry", "rule": "fall"}, ["x"]) is False
    assert _eval(
        {"subject": "keypoint_geometry", "rule": "fall"},
        [_det([["a", "b", "c"]])],
    ) is False


def test_keypoint_geometry_detail_is_explainable():
    leaf = {"subject": "keypoint_geometry", "rule": "fall", "op": ">=", "value": 60.0}
    ok, hits = explain_conditions(leaf, [_det(_fallen())])
    assert ok is True
    assert hits[0]["subject"] == "keypoint_geometry"
    assert "fall" in hits[0]["detail"]
    miss_leaf = {"subject": "keypoint_geometry", "rule": "fall", "op": ">=", "value": 60.0}
    ok2, _ = explain_conditions(miss_leaf, [_det(_standing())])
    assert ok2 is False


def test_smoke_phone_min_sec_is_recognized_as_stateful_leaf():
    """带 min_sec 的 smoke_phone 必须被识别为「需要时序观测」的叶子。"""
    assert _has_temporal_leaf({"subject": "keypoint_geometry", "rule": "smoke_phone", "min_sec": 5}) is True
    assert _has_temporal_leaf({"subject": "keypoint_geometry", "rule": "smoke_phone"}) is False
    assert _has_temporal_leaf({"subject": "keypoint_geometry", "rule": "fall"}) is False
