"""时序规则叶子测试：dwell / count_window / absence（SP4-b）。

约定：
- 状态存储 ``TemporalStore`` 优先 Redis，测试用内存后端（``prefer_redis=False``）保证确定性；
- 时间由事件 ts 注入（``_match_conditions`` 的 ``now`` 参数），禁止依赖 wall clock；
- 时序叶子读取 ``camera_id/alarm_type/label`` 维度下的观测状态；
- 所有非法/缺失输入一律不命中且不抛异常（延续既有约定）。
"""
from datetime import datetime, timezone

import pytest

from app.api.v1.module_video.inference.service import (
    _has_temporal_leaf,
    _match_conditions,
)
from app.api.v1.module_video.inference.temporal import (
    TemporalStore,
    region_fingerprint,
    to_epoch,
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


def _eval(leaf, store, now, dets=None, camera_id=CAM, alarm_type=ALGO, alarm_interval=0):
    return _match_conditions(
        leaf,
        dets if dets is not None else [],
        temporal=store,
        camera_id=camera_id,
        alarm_type=alarm_type,
        now=now,
        alarm_interval=alarm_interval,
    )


# --------------------------------------------------------------------- dwell
def test_dwell_reached():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1)], 1006)
    assert _eval({"subject": "dwell", "label": "person", "min_sec": 5}, s, 1006) is True


def test_dwell_not_reached():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    assert _eval({"subject": "dwell", "label": "person", "min_sec": 5}, s, 1003) is False


def test_dwell_track_expired():
    """last_seen 超出 grace（=max(min_sec, alarm_interval)）→ 轨迹已过期，不命中。"""
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    assert _eval({"subject": "dwell", "label": "person", "min_sec": 5}, s, 1020) is False


def test_dwell_grace_uses_alarm_interval():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    assert _eval({"subject": "dwell", "label": "person", "min_sec": 5}, s, 1020, alarm_interval=30) is True


def test_dwell_last_seen_refresh_keeps_active():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1)], 1004)
    assert _eval({"subject": "dwell", "label": "person", "min_sec": 5}, s, 1008) is True


def test_dwell_track_id_filter():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1)], 1006)
    assert _eval({"subject": "dwell", "track_id": 1, "min_sec": 5}, s, 1006) is True
    assert _eval({"subject": "dwell", "track_id": 2, "min_sec": 5}, s, 1006) is False


def test_dwell_label_mismatch():
    s = _store()
    s.observe(CAM, ALGO, [_det("car", track_id=1)], 1000)
    assert _eval({"subject": "dwell", "label": "person", "min_sec": 5}, s, 1006) is False


# --------------------------------------------------------------- count_window
def test_count_window_dedup_same_track():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1), _det(track_id=1), _det(track_id=2)], 1000)
    leaf = {"subject": "count_window", "label": "person", "window_sec": 60, "op": "==", "value": 2}
    assert _eval(leaf, s, 1010) is True


def test_count_window_includes_within_window():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=2)], 1030)
    leaf = {"subject": "count_window", "label": "person", "window_sec": 60, "op": "==", "value": 2}
    assert _eval(leaf, s, 1050) is True


def test_count_window_excludes_outside_window():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=2)], 1030)
    leaf = {"subject": "count_window", "label": "person", "window_sec": 10, "op": "==", "value": 0}
    assert _eval(leaf, s, 1050) is True


@pytest.mark.parametrize(
    "op,value,expected",
    [
        (">=", 3, True),
        (">", 3, False),
        (">", 2, True),
        ("<=", 3, True),
        ("<", 3, False),
        ("<", 4, True),
        ("==", 3, True),
        ("==", 2, False),
    ],
)
def test_count_window_operators(op, value, expected):
    s = _store()
    for tid in (1, 2, 3):
        s.observe(CAM, ALGO, [_det(track_id=tid)], 1000)
    leaf = {"subject": "count_window", "label": "person", "window_sec": 60, "op": op, "value": value}
    assert _eval(leaf, s, 1010) is expected


def test_count_window_no_track_id_counts_events():
    """无 track_id 时按事件计数：两个不同时刻的事件 = 2 个目标。"""
    s = _store()
    s.observe(CAM, ALGO, [_det()], 1000)
    s.observe(CAM, ALGO, [_det()], 1005)
    leaf = {"subject": "count_window", "label": "person", "window_sec": 60, "op": "==", "value": 2}
    assert _eval(leaf, s, 1010) is True


def test_count_window_label_filter():
    s = _store()
    s.observe(CAM, ALGO, [_det("person", track_id=1), _det("car", track_id=2)], 1000)
    leaf = {"subject": "count_window", "label": "car", "window_sec": 60, "op": "==", "value": 1}
    assert _eval(leaf, s, 1005) is True


# ------------------------------------------------------------------ absence
def test_absence_after_gap():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    assert _eval({"subject": "absence", "label": "person", "gap_sec": 120}, s, 1200) is True


def test_absence_within_gap():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    assert _eval({"subject": "absence", "label": "person", "gap_sec": 120}, s, 1100) is False


def test_absence_no_history():
    """无历史视为尚未过期 → 不命中。"""
    s = _store()
    assert _eval({"subject": "absence", "label": "person", "gap_sec": 120}, s, 99999) is False


def test_absence_uses_latest_across_tracks():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=2)], 1150)
    assert _eval({"subject": "absence", "label": "person", "gap_sec": 120}, s, 1200) is False
    assert _eval({"subject": "absence", "label": "person", "gap_sec": 120}, s, 1270) is True


def test_absence_without_label_aggregates_all():
    s = _store()
    s.observe(CAM, ALGO, [_det("car", track_id=1)], 1000)
    assert _eval({"subject": "absence", "gap_sec": 120}, s, 1200) is True


# ----------------------------------------------------------------- 区域隔离
def test_region_scope_isolated():
    """带 region 的叶子读取区域桶；未限定区域的叶子读 all 桶，两者互不串扰。"""
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000, scope=region_fingerprint(SQUARE))
    s.observe(CAM, ALGO, [_det(track_id=1)], 1006, scope=region_fingerprint(SQUARE))
    assert _eval({"subject": "dwell", "label": "person", "min_sec": 5}, s, 1006) is False
    assert (
        _eval({"subject": "dwell", "label": "person", "region": SQUARE, "min_sec": 5}, s, 1006) is True
    )


# --------------------------------------------------------------- 组合与脏输入
def test_temporal_combination_and():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1), _det("car", track_id=9)], 1000)
    s.observe(CAM, ALGO, [_det(track_id=1)], 1006)
    cond = {
        "op": "and",
        "children": [
            {"subject": "dwell", "label": "person", "min_sec": 5},
            {"subject": "absence", "label": "car", "gap_sec": 1},
        ],
    }
    assert _eval(cond, s, 1006) is True


def test_temporal_missing_camera_not_match():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    # 未提供 camera_id → 无法定位状态，安全地不命中
    assert _match_conditions({"subject": "dwell", "min_sec": 5}, [], temporal=s, now=1006) is False


def test_temporal_bad_min_sec_not_match():
    s = _store()
    assert _eval({"subject": "dwell", "label": "person", "min_sec": "很久"}, s, 1006) is False


def test_count_window_bad_op_and_value_not_match():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    assert _eval({"subject": "count_window", "window_sec": 60, "op": "~", "value": 1}, s, 1005) is False
    assert (
        _eval({"subject": "count_window", "window_sec": 60, "op": ">=", "value": "多"}, s, 1005) is False
    )


def test_absence_bad_gap_not_match():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    assert _eval({"subject": "absence", "gap_sec": "x"}, s, 1200) is False


def test_temporal_bad_region_not_match():
    s = _store()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    leaf = {"subject": "dwell", "label": "person", "region": "not-a-polygon", "min_sec": 5}
    assert _eval(leaf, s, 1006) is False


def test_observe_dirty_does_not_raise():
    s = _store()
    s.observe(CAM, ALGO, None, 1000)
    s.observe(CAM, ALGO, "bad", 1000)
    s.observe(CAM, ALGO, ["脏数据", None, 1], 1000)
    s.observe(None, None, [_det()], 1000)
    assert isinstance(s.query(CAM, ALGO, "person"), dict)


def test_has_temporal_leaf():
    assert _has_temporal_leaf({"subject": "dwell", "min_sec": 1}) is True
    assert _has_temporal_leaf({"subject": "count_window"}) is True
    assert _has_temporal_leaf({"subject": "absence"}) is True
    assert _has_temporal_leaf({"op": "and", "children": [{"subject": "dwell"}]}) is True
    assert _has_temporal_leaf({"subject": "object_present"}) is False
    assert _has_temporal_leaf({"op": "not", "children": [{"subject": "count"}]}) is False
    assert _has_temporal_leaf(None) is False
    assert _has_temporal_leaf([1, 2]) is False


# ----------------------------------------------------------------- 纯函数直测
def test_to_epoch_numeric_and_iso():
    assert to_epoch(1000) == 1000.0
    assert to_epoch(1000.5) == 1000.5
    assert to_epoch("1000.5") == 1000.5
    expected = datetime(2026, 9, 12, 8, 0, 0, tzinfo=timezone.utc).timestamp()
    assert to_epoch("2026-09-12T08:00:00Z") == pytest.approx(expected)
    # 非法输入回退当前时间（> 0 且不抛异常）
    assert to_epoch("bad") > 0
    assert to_epoch(None) > 0
    assert to_epoch(True) > 0


def test_region_fingerprint_stable_and_invalid():
    assert region_fingerprint(None) is None
    assert region_fingerprint("bad") is None
    assert region_fingerprint([[0.2, 0.2], [0.8, 0.2]]) is None
    fp = region_fingerprint(SQUARE)
    assert fp is not None
    assert fp == region_fingerprint([[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]])


def test_store_falls_back_to_memory_when_redis_disabled(monkeypatch):
    from app.config.setting import settings

    monkeypatch.setattr(settings, "REDIS_ENABLE", False)
    s = TemporalStore()
    s.observe(CAM, ALGO, [_det(track_id=1)], 1000)
    assert s.query(CAM, ALGO, "person")
