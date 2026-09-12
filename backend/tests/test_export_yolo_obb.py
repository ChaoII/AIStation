"""YOLO OBB 旋转框转换测试。"""
import math

from app.plugin.module_train.exporter import _format_yolo_lines, rotated_box_to_obb_corners


def test_obb_corners_zero_angle():
    pts = rotated_box_to_obb_corners(0.5, 0.5, 0.4, 0.2, 0.0)
    assert len(pts) == 8
    # 左上→右上→右下→左下
    assert pts[0] == 0.3 and pts[1] == 0.4
    assert pts[2] == 0.7 and pts[3] == 0.4
    assert pts[4] == 0.7 and pts[5] == 0.6
    assert pts[6] == 0.3 and pts[7] == 0.6


def test_obb_corners_90deg_swap_extent():
    pts = rotated_box_to_obb_corners(0.5, 0.5, 0.4, 0.2, math.pi / 2)
    assert len(pts) == 8
    # 旋转 90° 后，宽高在坐标轴上互换
    assert abs(pts[0] - 0.4) < 1e-6 and abs(pts[1] - 0.3) < 1e-6


def test_yolo_obb_non_square_rotates_in_pixel_space():
    """非正方形图像：旋转须在像素空间进行，否则 x/y 缩放不同导致角点错误。"""
    anns = [{"type": "RotatedBox", "class_id": 1, "cx": 0.5, "cy": 0.5,
             "width": 0.2, "height": 0.1, "angle": math.pi / 2}]
    lines = _format_yolo_lines(anns, "rotated_detection", class_id_map={1: 0},
                               img_w=200, img_h=100)
    assert len(lines) == 1
    vals = [float(v) for v in lines[0].split()[1:]]
    assert len(vals) == 8
    xs, ys = vals[0::2], vals[1::2]
    # 正确像素角点 x∈[95,105], y∈[30,70] → 归一化 [0.475,0.525] / [0.3,0.7]
    assert abs(min(xs) - 95 / 200) < 1e-6
    assert abs(max(xs) - 105 / 200) < 1e-6
    assert abs(min(ys) - 30 / 100) < 1e-6
    assert abs(max(ys) - 70 / 100) < 1e-6
