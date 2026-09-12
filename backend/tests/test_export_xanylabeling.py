"""X-AnyLabeling shapes 转换测试（归一化→像素、全形状、真实类名）。"""
import math

from app.plugin.module_train.exporter import xany_shapes


def test_rectangle_pixelized_and_named():
    anns = [{"type": "AxisAlignedBox", "class_id": 2, "x1": 0.1, "y1": 0.2, "x2": 0.4, "y2": 0.6}]
    shapes = xany_shapes(anns, 100, 200, {2: "cat"})
    assert shapes[0]["label"] == "cat"
    assert shapes[0]["shape_type"] == "rectangle"
    assert shapes[0]["points"][0] == [10.0, 40.0]
    assert shapes[0]["points"][2] == [40.0, 120.0]


def test_rotated_box_pixelized():
    anns = [{"type": "RotatedBox", "class_id": 1, "cx": 0.5, "cy": 0.5, "width": 0.2, "height": 0.1, "angle": 0.0}]
    shapes = xany_shapes(anns, 100, 100, {1: "box"})
    assert shapes[0]["shape_type"] == "rotation"
    xs = [p[0] for p in shapes[0]["points"]]
    ys = [p[1] for p in shapes[0]["points"]]
    assert min(xs) == 40.0 and max(xs) == 60.0
    assert min(ys) == 45.0 and max(ys) == 55.0


def test_rotated_box_pixelized_non_square():
    """非正方形图像：旋转框须在像素空间旋转，角点直接为像素坐标。"""
    anns = [{"type": "RotatedBox", "class_id": 1, "cx": 0.5, "cy": 0.5,
             "width": 0.2, "height": 0.1, "angle": math.pi / 2}]
    shapes = xany_shapes(anns, 200, 100, {1: "box"})
    assert shapes[0]["shape_type"] == "rotation"
    xs = [p[0] for p in shapes[0]["points"]]
    ys = [p[1] for p in shapes[0]["points"]]
    assert abs(min(xs) - 95.0) < 1e-6
    assert abs(max(xs) - 105.0) < 1e-6
    assert abs(min(ys) - 30.0) < 1e-6
    assert abs(max(ys) - 70.0) < 1e-6


def test_keypoint_and_ocr_and_polygon_present():
    anns = [
        {"type": "Polygon", "class_id": 0, "points": [{"x": 0.1, "y": 0.1}, {"x": 0.2, "y": 0.1}, {"x": 0.2, "y": 0.2}]},
        {"type": "Keypoint", "class_id": 1, "keypoints": [{"x": 0.5, "y": 0.5, "visibility": "Visible"}]},
        {"type": "Ocr", "class_id": 2, "points": [{"x": 0.1, "y": 0.1}, {"x": 0.3, "y": 0.1}, {"x": 0.3, "y": 0.2}, {"x": 0.1, "y": 0.2}], "text": "hi"},
    ]
    shapes = xany_shapes(anns, 100, 100, {0: "a", 1: "b", 2: "c"})
    types = {s["shape_type"] for s in shapes}
    assert "polygon" in types
    assert "point" in types
    assert any(s.get("description") == "hi" for s in shapes)
