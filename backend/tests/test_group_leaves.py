"""跨相机聚合叶子（group_count / group_coverage）测试。"""
from app.api.v1.module_video.inference.service import _match_conditions
from app.api.v1.module_video.inference.temporal import TemporalStore

CAM_A, CAM_B, ALGO = 1, 2, "AI_DETECTION"


def _det(track_id, label="person", cx=0.5, cy=0.5, w=0.1, h=0.1):
    return {
        "label": label,
        "confidence": 0.9,
        "track_id": track_id,
        "bbox": {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h},
    }


def _ev(store, leaf, cam, now, ids):
    """调用评估入口：group_camera_ids 透传给跨相机聚合叶子。"""
    return _match_conditions(
        leaf,
        [],
        temporal=store,
        camera_id=cam,
        alarm_type=ALGO,
        now=now,
        alarm_interval=0,
        group_camera_ids=ids,
    )


def test_query_multi_keys_include_camera_id():
    """query_multi 键含 camera_id 前缀：跨相机同 track_id 不被合并。"""
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM_A, ALGO, [_det(1)], 1000)
    s.observe(CAM_B, ALGO, [_det(1)], 1001)
    merged = s.query_multi([CAM_A, CAM_B], ALGO)
    assert set(merged.keys()) == {(CAM_A, "t:1"), (CAM_B, "t:1")}


def test_group_count_sums_dedup_across_cameras():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM_A, ALGO, [_det(1), _det(2)], 1000)
    s.observe(CAM_B, ALGO, [_det(1), _det(3)], 1001)  # track 1 与 A 相机同号但独立
    leaf = {"subject": "group_count", "window_sec": 60, "op": ">=", "value": 4}
    assert _ev(s, leaf, CAM_A, 1002, [CAM_A, CAM_B]) is True  # 2 + 2 = 4（不去重跨相机）
    assert _ev(s, leaf, CAM_A, 1002, [CAM_A]) is False  # 单相机只有 2


def test_group_count_window_excludes_stale():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM_A, ALGO, [_det(1)], 1000)
    s.observe(CAM_B, ALGO, [_det(2)], 1001)
    leaf = {"subject": "group_count", "window_sec": 10, "op": ">=", "value": 2}
    assert _ev(s, leaf, CAM_A, 1005, [CAM_A, CAM_B]) is True
    assert _ev(s, leaf, CAM_A, 1020, [CAM_A, CAM_B]) is False  # 两条都已超出窗口


def test_group_count_without_group_context_never_matches():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM_A, ALGO, [_det(1)], 1000)
    leaf = {"subject": "group_count", "window_sec": 60, "op": ">=", "value": 1}
    assert _ev(s, leaf, CAM_A, 1001, None) is False
    assert _ev(s, leaf, CAM_A, 1001, []) is False


def test_group_count_op_branches():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM_A, ALGO, [_det(1)], 1000)
    s.observe(CAM_B, ALGO, [_det(2), _det(3)], 1001)
    base = {"subject": "group_count", "window_sec": 60, "value": 3}
    assert _ev(s, {**base, "op": ">="}, CAM_A, 1002, [CAM_A, CAM_B]) is True
    assert _ev(s, {**base, "op": ">"}, CAM_A, 1002, [CAM_A, CAM_B]) is False
    assert _ev(s, {**base, "op": "=="}, CAM_A, 1002, [CAM_A, CAM_B]) is True
    assert _ev(s, {**base, "op": "<="}, CAM_A, 1002, [CAM_A, CAM_B]) is True
    assert _ev(s, {**base, "op": "<"}, CAM_A, 1002, [CAM_A, CAM_B]) is False


def test_group_coverage_ratio_over_group_size():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM_A, ALGO, [_det(1)], 1000)
    leaf = {"subject": "group_coverage", "window_sec": 60, "op": ">=", "value": 0.5}
    # 组内 4 台相机，仅 1 台有目标 → 0.25 < 0.5
    assert _ev(s, leaf, CAM_A, 1001, [CAM_A, CAM_B, 3, 4]) is False
    assert _ev(s, leaf, CAM_A, 1001, [CAM_A, CAM_B]) is True  # 1/2 = 0.5


def test_group_coverage_without_group_context_never_matches():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM_A, ALGO, [_det(1)], 1000)
    leaf = {"subject": "group_coverage", "window_sec": 60, "op": ">=", "value": 0.1}
    assert _ev(s, leaf, CAM_A, 1001, None) is False


def test_group_leaves_invalid_inputs_return_false_without_raising():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM_A, ALGO, [_det(1)], 1000)
    ids = [CAM_A, CAM_B]
    # 缺 window_sec
    assert _ev(s, {"subject": "group_count", "op": ">=", "value": 1}, CAM_A, 1001, ids) is False
    # 非法 op
    assert (
        _ev(s, {"subject": "group_count", "window_sec": 60, "op": "!=", "value": 1}, CAM_A, 1001, ids)
        is False
    )
    # 非数值 value
    assert (
        _ev(
            s,
            {"subject": "group_count", "window_sec": 60, "op": ">=", "value": "abc"},
            CAM_A,
            1001,
            ids,
        )
        is False
    )
    # 非数值 window_sec
    assert (
        _ev(
            s,
            {"subject": "group_coverage", "window_sec": "x", "op": ">=", "value": 0.5},
            CAM_A,
            1001,
            ids,
        )
        is False
    )
    # 缺 now
    assert _ev(s, {"subject": "group_count", "window_sec": 60, "op": ">=", "value": 1}, CAM_A, None, ids) is False
