"""TemporalStore 轨迹位置观测测试（SP4-b line_cross 基础）。"""
from app.api.v1.module_video.inference.temporal import TemporalStore

CAM = 1
ALGO = "AI_DETECTION"


def _det(track_id, cx, cy, label="person", w=0.1, h=0.1):
    """构造一条带中心 (cx, cy) 的归一化检测框。"""
    return {
        "label": label,
        "confidence": 0.9,
        "track_id": track_id,
        "bbox": {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h},
    }


def test_query_positions_first_observation_has_no_prev():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    assert s.query_positions(CAM, ALGO, "person", "all") == {"t:1": (None, (0.2, 0.5))}


def test_query_positions_second_observation_moves_cur_to_prev():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    assert s.query_positions(CAM, ALGO, "person", "all") == {"t:1": ((0.2, 0.5), (0.8, 0.5))}


def test_query_positions_ignores_detections_without_bbox():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [{"label": "person", "track_id": 1}], 1000)
    assert s.query_positions(CAM, ALGO, "person", "all") == {}


def test_query_positions_aggregate_all_labels():
    s = TemporalStore(prefer_redis=False)
    s.observe(
        CAM,
        ALGO,
        [_det(1, 0.2, 0.5, label="person"), _det(2, 0.3, 0.5, label="car")],
        1000,
    )
    assert set(s.query_positions(CAM, ALGO, None, "all")) == {"t:1", "t:2"}


def test_query_positions_scoped_by_region_bucket():
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000, scope="bucketA")
    assert s.query_positions(CAM, ALGO, "person", "bucketA") == {"t:1": (None, (0.2, 0.5))}
    assert s.query_positions(CAM, ALGO, "person", "bucketB") == {}


def test_repeated_observe_same_ts_does_not_advance_position():
    """同一事件时间戳被重复观测（多规则共享 scope）时不得二次推进位置。

    否则 prev 会被覆盖为 cur，line_cross 的 prev==cur 恒不命中。
    """
    s = TemporalStore(prefer_redis=False)
    # 两个规则对同一帧各观测一次：第二次必须是 no-op
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    assert s.query_positions(CAM, ALGO, "person", "all") == {"t:1": (None, (0.2, 0.5))}
    # 下一帧正常推进：prev 仍是上一帧位置
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    assert s.query_positions(CAM, ALGO, "person", "all") == {"t:1": ((0.2, 0.5), (0.8, 0.5))}


def test_observe_older_ts_does_not_rewind_position():
    """乱序到达的更早事件不得覆盖较新位置（位置只前进不后退）。"""
    s = TemporalStore(prefer_redis=False)
    s.observe(CAM, ALGO, [_det(1, 0.2, 0.5)], 1000)
    s.observe(CAM, ALGO, [_det(1, 0.8, 0.5)], 1001)
    s.observe(CAM, ALGO, [_det(1, 0.3, 0.5)], 999)
    assert s.query_positions(CAM, ALGO, "person", "all") == {"t:1": ((0.2, 0.5), (0.8, 0.5))}
