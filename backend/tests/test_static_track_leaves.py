"""静止/跟踪时序叶子测试：static / track（SP4-b 扩展）。

约定（延续 test_temporal_leaves.py）：
- 状态存储优先 Redis，测试用内存后端（``prefer_redis=False``）保证确定性；
- 时间由事件 ts 注入（``now`` 参数），禁止依赖 wall clock；
- 所有非法/缺失输入一律不命中且不抛异常（fail-closed）。

static 语义（产品决策）：某**真实轨迹**（有效 track_id >= 0）存在时长 >= min_sec、
仍活跃（未超 grace），且**相对首帧中心的最大位移** <= max_move（缺省 0.02）。
track 语义：存在至少一条活跃真实轨迹（可选要求存在时长 >= min_sec）。
"""
import pytest

from app.api.v1.module_video.inference.service import (
    _has_temporal_leaf,
    _match_conditions,
    explain_conditions,
)
from app.api.v1.module_video.inference.temporal import (
    TemporalStore,
    region_fingerprint,
)

CAM = 1
ALGO = "AI_DETECTION"
SQUARE = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]


def _det(label="person", track_id=None, cx=0.5, cy=0.5, conf=0.9, w=0.1, h=0.1):
    """构造一条归一化检测框；track_id 为 None 时不携带。"""
    d = {
        "label": label,
        "confidence": conf,
        "bbox": {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h},
    }
    if track_id is not None:
        d["track_id"] = track_id
    return d


def _store():
    return TemporalStore(prefer_redis=False)


def _eval(leaf, store, now, alarm_interval=0):
    return _match_conditions(
        leaf,
        [],
        temporal=store,
        camera_id=CAM,
        alarm_type=ALGO,
        now=now,
        alarm_interval=alarm_interval,
    )


# ---------------------------------------------------- 状态存储：最大位移
def test_query_moves_first_observation_is_zero():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.2, cy=0.5)], 1000)
    assert s.query_moves(CAM, ALGO, "person", "all") == {"t:1": 0.0}


def test_query_moves_tracks_max_displacement_from_first():
    """位移取「相对首帧的最大值」：先走远再折返，位移仍记最远距离。"""
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.2, cy=0.5)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.6, cy=0.5)], 1001)
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.2, cy=0.5)], 1002)
    moves = s.query_moves(CAM, ALGO, "person", "all")
    assert moves["t:1"] == pytest.approx(0.4)


def test_query_moves_does_not_rewind_on_older_or_duplicate_ts():
    """乱序/重复时间戳不得让位移回退或放大。"""
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.2, cy=0.5)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.6, cy=0.5)], 1001)
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.2, cy=0.5)], 999)
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.6, cy=0.5)], 1001)
    assert s.query_moves(CAM, ALGO, "person", "all")["t:1"] == pytest.approx(0.4)


def test_query_moves_region_bucket_isolated():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.5, cy=0.5)], 1000, scope="bucketA")
    assert s.query_moves(CAM, ALGO, "person", "bucketA")["t:1"] == 0.0
    assert s.query_moves(CAM, ALGO, "person", "bucketB") == {}


# ------------------------------------------------------------------ static
def test_static_hit_when_stationary_long_enough():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1)], 1006)
    assert _eval({"subject": "static", "min_sec": 5}, s, 1006) is True


def test_static_no_hit_when_moving():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.5)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.65)], 1003)
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.65)], 1006)
    assert _eval({"subject": "static", "min_sec": 5}, s, 1006) is False


def test_static_no_hit_below_min_sec():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1)], 1002)
    assert _eval({"subject": "static", "min_sec": 5}, s, 1002) is False


def test_static_no_hit_without_track_id():
    """无 track_id（按事件成键）不具备轨迹身份 → 不命中。"""
    s = _store()
    s.observe(CAM, ALGO, [_det()], 1000)
    s.observe(CAM, ALGO, [_det()], 1006)
    assert _eval({"subject": "static", "min_sec": 5}, s, 1006) is False


def test_static_no_hit_when_track_expired():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1)], 1006)
    assert _eval({"subject": "static", "min_sec": 5}, s, 1020) is False
    # grace 放宽（alarm_interval）后仍算活跃
    assert _eval({"subject": "static", "min_sec": 5}, s, 1020, alarm_interval=30) is True


def test_static_track_id_filter():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1)], 1006)
    assert _eval({"subject": "static", "min_sec": 5, "track_id": 1}, s, 1006) is True
    assert _eval({"subject": "static", "min_sec": 5, "track_id": 2}, s, 1006) is False


def test_static_custom_max_move_threshold():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.5)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.55)], 1003)
    s.observe(CAM, ALGO, [_det(track_id=1, cx=0.55)], 1006)
    # 位移约 0.05：缺省阈值 0.02 不命中，放宽到 0.06 命中
    assert _eval({"subject": "static", "min_sec": 5}, s, 1006) is False
    assert _eval({"subject": "static", "min_sec": 5, "max_move": 0.06}, s, 1006) is True


def test_static_label_filter():
    s = _store()
    s.observe(CAM, ALGO, [_det("car", track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det("car", track_id=1)], 1006)
    assert _eval({"subject": "static", "label": "person", "min_sec": 5}, s, 1006) is False
    assert _eval({"subject": "static", "label": "car", "min_sec": 5}, s, 1006) is True


def test_static_region_scope_filter():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000, scope=region_fingerprint(SQUARE))
    s.observe(CAM, ALGO, [_det(track_id=1)], 1006, scope=region_fingerprint(SQUARE))
    # 无 region 读 all 桶 → 不命中；带 region 读区域桶 → 命中
    assert _eval({"subject": "static", "min_sec": 5}, s, 1006) is False
    assert _eval({"subject": "static", "min_sec": 5, "region": SQUARE}, s, 1006) is True


@pytest.mark.parametrize(
    "leaf",
    [
        {"subject": "static"},  # 缺 min_sec
        {"subject": "static", "min_sec": "很久"},
        {"subject": "static", "min_sec": -1},
        {"subject": "static", "min_sec": 5, "max_move": "大"},
        {"subject": "static", "min_sec": 5, "max_move": -0.1},
        {"subject": "static", "min_sec": 5, "track_id": "x"},
        {"subject": "static", "min_sec": 5, "region": "not-a-polygon"},
    ],
)
def test_static_invalid_inputs_fail_closed(leaf):
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1)], 1006)
    assert _eval(leaf, s, 1006) is False


# ------------------------------------------------------------------- track
def test_track_hit_when_track_present():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    assert _eval({"subject": "track"}, s, 1000) is True


def test_track_no_hit_without_track_id():
    s = _store()
    s.observe(CAM, ALGO, [_det()], 1000)
    assert _eval({"subject": "track"}, s, 1000) is False


def test_track_ignores_negative_track_id():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=-1)], 1000)
    assert _eval({"subject": "track"}, s, 1000) is False


def test_track_min_sec_duration():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1)], 1006)
    assert _eval({"subject": "track", "min_sec": 5}, s, 1006) is True
    assert _eval({"subject": "track", "min_sec": 10}, s, 1006) is False


def test_track_expired_after_grace():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    assert _eval({"subject": "track"}, s, 1001) is False
    assert _eval({"subject": "track"}, s, 1001, alarm_interval=30) is True


def test_track_region_scope_filter():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000, scope=region_fingerprint(SQUARE))
    assert _eval({"subject": "track"}, s, 1000) is False
    assert _eval({"subject": "track", "region": SQUARE}, s, 1000) is True


def test_track_label_filter():
    s = _store()
    s.observe(CAM, ALGO, [_det("person", track_id=1)], 1000)
    assert _eval({"subject": "track", "label": "car"}, s, 1000) is False
    assert _eval({"subject": "track", "label": "person"}, s, 1000) is True


@pytest.mark.parametrize(
    "leaf",
    [
        {"subject": "track", "min_sec": "x"},
        {"subject": "track", "min_sec": -2},
        {"subject": "track", "region": "not-a-polygon"},
    ],
)
def test_track_invalid_inputs_fail_closed(leaf):
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    assert _eval(leaf, s, 1000) is False


# ------------------------------------------------------------- detail / 接线
def test_static_and_track_details():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1)], 1006)
    matched, hits = explain_conditions(
        {"subject": "static", "min_sec": 5}, [], temporal=s, camera_id=CAM,
        alarm_type=ALGO, now=1006,
    )
    assert matched is True
    assert hits[0]["detail"] == "static 6s move=0.000"

    matched, hits = explain_conditions(
        {"subject": "track"}, [], temporal=s, camera_id=CAM, alarm_type=ALGO, now=1006
    )
    assert matched is True
    assert hits[0]["detail"] == "track 1"


def test_has_temporal_leaf_recognizes_static_and_track():
    assert _has_temporal_leaf({"subject": "static", "min_sec": 5}) is True
    assert _has_temporal_leaf({"subject": "track"}) is True
    assert _has_temporal_leaf({"subject": "object_present"}) is False
