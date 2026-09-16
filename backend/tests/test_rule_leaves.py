"""规则引擎通用叶子测试：object_present / zone_enter / count。

叶子基于单个检测事件里的 detections[] 评估：
- bbox 为归一化 {x, y, width, height}，中心 = (x + w/2, y + h/2)；
- region 为归一化多边形 [[x, y], ...]，判定检测框中心是否落在多边形内；
- 所有非法/缺失字段一律不命中且不抛异常（延续既有约定）。
"""
import pytest

from app.api.v1.module_video.inference.service import (
    _bbox_center,
    _in_region,
    _match_conditions,
    _matches_label,
    _point_in_polygon,
    _region_of,
)

# 单位正方形内部区域
SQUARE = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]


def _det(label="person", cx=0.5, cy=0.5, conf=0.9, w=0.1, h=0.1):
    """构造一条中心在 (cx, cy) 的归一化检测框。"""
    return {
        "label": label,
        "confidence": conf,
        "bbox": {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h},
    }


# ---------------------------------------------------------------- object_present
def test_object_present_any_detection():
    assert _match_conditions({"subject": "object_present"}, [_det()]) is True


def test_object_present_no_detection():
    assert _match_conditions({"subject": "object_present"}, []) is False


def test_object_present_label_match_and_miss():
    leaf = {"subject": "object_present", "label": "person"}
    assert _match_conditions(leaf, [_det("car"), _det("person")]) is True
    assert _match_conditions(leaf, [_det("car")]) is False


def test_object_present_labels_list():
    leaf = {"subject": "object_present", "labels": ["car", "truck"]}
    assert _match_conditions(leaf, [_det("truck")]) is True
    assert _match_conditions(leaf, [_det("person")]) is False


def test_object_present_region_inside_and_outside():
    leaf = {"subject": "object_present", "label": "person", "region": SQUARE}
    assert _match_conditions(leaf, [_det("person", cx=0.5, cy=0.5)]) is True
    assert _match_conditions(leaf, [_det("person", cx=0.05, cy=0.05)]) is False


def test_object_present_min_confidence():
    leaf = {"subject": "object_present", "label": "person", "min_confidence": 0.5}
    assert _match_conditions(leaf, [_det("person", conf=0.9)]) is True
    assert _match_conditions(leaf, [_det("person", conf=0.2)]) is False


def test_object_present_min_confidence_absent_is_no_filter():
    assert _match_conditions({"subject": "object_present", "min_confidence": None}, [_det(conf=0.1)]) is True


def test_object_present_min_confidence_non_numeric_not_match():
    leaf = {"subject": "object_present", "min_confidence": "高"}
    assert _match_conditions(leaf, [_det(conf=0.9)]) is False


# ------------------------------------------------------------------- zone_enter
def test_zone_enter_inside():
    leaf = {"subject": "zone_enter", "label": "person", "region": SQUARE}
    assert _match_conditions(leaf, [_det("person", cx=0.5, cy=0.5)]) is True


def test_zone_enter_outside():
    leaf = {"subject": "zone_enter", "label": "person", "region": SQUARE}
    assert _match_conditions(leaf, [_det("person", cx=0.9, cy=0.9)]) is False


def test_zone_enter_boundary_counts_as_inside():
    """落在多边形边界上的中心点视为命中（确定性边界语义）。"""
    leaf = {"subject": "zone_enter", "label": "person", "region": SQUARE}
    assert _match_conditions(leaf, [_det("person", cx=0.2, cy=0.5)]) is True


def test_zone_enter_missing_region_equals_object_present():
    leaf = {"subject": "zone_enter", "label": "person"}
    assert _match_conditions(leaf, [_det("person", cx=0.5, cy=0.5)]) is True
    assert _match_conditions(leaf, [_det("car")]) is False


def test_zone_enter_label_mismatch():
    leaf = {"subject": "zone_enter", "label": "person", "region": SQUARE}
    assert _match_conditions(leaf, [_det("car", cx=0.5, cy=0.5)]) is False


# ----------------------------------------------------------------------- count
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
def test_count_operators(op, value, expected):
    dets = [_det(), _det(), _det()]
    leaf = {"subject": "count", "label": "person", "op": op, "value": value}
    assert _match_conditions(leaf, dets) is expected


def test_count_with_region():
    dets = [_det(cx=0.5, cy=0.5), _det(cx=0.9, cy=0.9)]
    leaf = {"subject": "count", "label": "person", "region": SQUARE, "op": "==", "value": 1}
    assert _match_conditions(leaf, dets) is True


def test_count_label_filter():
    dets = [_det("person"), _det("car"), _det("car")]
    leaf = {"subject": "count", "label": "car", "op": "==", "value": 2}
    assert _match_conditions(leaf, dets) is True


def test_count_bad_op_not_match():
    leaf = {"subject": "count", "label": "person", "op": "~", "value": 1}
    assert _match_conditions(leaf, [_det()]) is False


def test_count_missing_op_not_match():
    leaf = {"subject": "count", "label": "person", "value": 1}
    assert _match_conditions(leaf, [_det()]) is False


def test_count_non_numeric_value_not_match():
    leaf = {"subject": "count", "label": "person", "op": ">=", "value": "多"}
    assert _match_conditions(leaf, [_det()]) is False


# ------------------------------------------------------------- 组合与非法输入
def test_combination_and_or_not():
    dets = [_det(cx=0.5, cy=0.5)]
    cond = {
        "op": "and",
        "children": [
            {"subject": "object_present", "label": "person", "region": SQUARE},
            {"subject": "count", "label": "person", "op": ">=", "value": 1},
        ],
    }
    assert _match_conditions(cond, dets) is True
    assert _match_conditions({"op": "not", "children": [cond]}, dets) is False


def test_non_dict_conditions_does_not_raise():
    assert _match_conditions([1, 2], [_det()]) is False
    assert _match_conditions("x", [_det()]) is False


def test_none_conditions_matches_all():
    assert _match_conditions(None, [_det()]) is True


def test_non_dict_detection_is_skipped():
    assert _match_conditions({"subject": "object_present"}, ["脏数据", None]) is False
    assert _match_conditions({"subject": "object_present"}, ["脏数据", _det()]) is True


def test_detections_none_or_non_list_does_not_raise():
    assert _match_conditions({"subject": "object_present"}, None) is False
    assert _match_conditions({"subject": "object_present"}, "bad") is False


def test_bad_region_not_match():
    leaf = {"subject": "object_present", "label": "person", "region": "not-a-polygon"}
    assert _match_conditions(leaf, [_det()]) is False


def test_bad_region_point_not_match():
    leaf = {"subject": "object_present", "label": "person", "region": [[0.2, 0.2], [0.8, "x"]]}
    assert _match_conditions(leaf, [_det()]) is False


def test_missing_bbox_region_not_match():
    leaf = {"subject": "object_present", "label": "person", "region": SQUARE}
    assert _match_conditions(leaf, [{"label": "person"}]) is False


# ---------------------------------------------------------------- 纯函数直测
def test_point_in_polygon_direct():
    assert _point_in_polygon(0.5, 0.5, [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]) is True
    assert _point_in_polygon(0.1, 0.5, [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]) is False


def test_bbox_center_direct():
    center = _bbox_center({"bbox": {"x": 0.2, "y": 0.4, "width": 0.2, "height": 0.2}})
    assert center == pytest.approx((0.3, 0.5))
    assert _bbox_center({"bbox": None}) is None
    assert _bbox_center({}) is None


def test_region_of_missing_and_valid():
    assert _region_of({}) is None
    assert _region_of({"region": None}) is None
    assert _region_of({"region": [[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]]}) == [(0.1, 0.1), (0.2, 0.2), (0.3, 0.3)]
    assert _region_of({"region": [[0.1, 0.1], [0.2, 0.2]]}) == []


def test_matches_label_direct():
    assert _matches_label({"label": "person"}, {"label": "person"}) is True
    assert _matches_label({"label": "car"}, {"label": "person"}) is False
    assert _matches_label({"label": "car"}, {}) is True
    assert _matches_label({"label": "car"}, {"labels": ["car"]}) is True


def test_in_region_direct():
    assert _in_region({"bbox": {"x": 0.45, "y": 0.45, "width": 0.1, "height": 0.1}}, {"region": SQUARE}) is True
    assert _in_region({"bbox": {"x": 0.0, "y": 0.0, "width": 0.1, "height": 0.1}}, {"region": SQUARE}) is False
    assert _in_region({"bbox": {"x": 0.9, "y": 0.9, "width": 0.1, "height": 0.1}}, {}) is True
