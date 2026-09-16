"""line_cross 云端时序几何求值器测试（SP4-b 收尾）。"""
from app.api.v1.module_video.inference.service import _match_conditions
from app.api.v1.module_video.inference.temporal import TemporalStore

CAM = 1
ALGO = "AI_DETECTION"
# 竖向绊线 x=0.5：起点 (0.5,0) → 终点 (0.5,1)，左侧(x<0.5)为 A 侧
VLINE = [[0.5, 0.0], [0.5, 1.0]]
ROI = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]


def _det(track_id, cx, cy, label="person", w=0.1, h=0.1):
    return {
        "label": label,
        "confidence": 0.9,
        "track_id": track_id,
        "bbox": {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h},
    }


def _cross(store, leaf, now):
    return _match_conditions(
        {"op": "and", "children": [leaf]},
        [],
        temporal=store,
        camera_id=CAM,
        alarm_type=ALGO,
        now=now,
        alarm_interval=0,
    )


def _leaf(**extra):
    leaf = {"subject": "line_cross", "line": VLINE, "dir": "A2B"}
    leaf.update(extra)
    return leaf


def test_cross_a2b_matches_left_to_right():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    assert _cross(s, _leaf(), 1001) is True


def test_cross_b2a_matches_only_reverse_direction():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1001)
    assert _cross(s, _leaf(), 1001) is False
    assert _cross(s, _leaf(dir="B2A"), 1001) is True
    assert _cross(s, _leaf(dir="both"), 1001) is True


def test_cross_same_side_does_not_match():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.1, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.3, 0.5)], 1001)
    assert _cross(s, _leaf(), 1001) is False


def test_cross_without_prev_does_not_match():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    assert _cross(s, _leaf(), 1001) is False


def test_cross_outside_segment_extent_does_not_match():
    """绊线只在两点之间有效；延长线上的位移不算越界。"""
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 1.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 1.5)], 1001)
    assert _cross(s, _leaf(), 1001) is False


def test_cross_region_filters_track():
    """越界发生在 region 外 → 被区域过滤掉。"""
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.05)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.05)], 1001)
    assert _cross(s, _leaf(region=ROI), 1001) is False
    assert _cross(s, _leaf(), 1001) is True


def test_cross_fires_once_per_crossing():
    """穿越后位置前移，不再重复命中。"""
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    assert _cross(s, _leaf(), 1001) is True
    s.observe(CAM, ALGO, [_det(1, 0.9, 0.5)], 1002)
    assert _cross(s, _leaf(), 1002) is False


def test_cross_invalid_inputs_do_not_raise():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    for bad in (
        {"subject": "line_cross", "line": None},
        {"subject": "line_cross", "line": [[0.5, 0.0]]},
        {"subject": "line_cross", "line": "line"},
        {"subject": "line_cross", "line": VLINE, "dir": "???"},
        {"subject": "line_cross", "line": [[0.5, "x"], [0.5, 1.0]]},
        {"subject": "line_cross", "line": [[0.5, 0.5], [0.5, 0.5]]},
    ):
        assert _cross(s, bad, 1001) is False


def test_temporal_subjects_contains_line_cross():
    from app.api.v1.module_video.inference.service import TEMPORAL_SUBJECTS

    assert "line_cross" in TEMPORAL_SUBJECTS
