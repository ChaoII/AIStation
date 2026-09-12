"""YOLO OBB 旋转框转换测试。"""
import math

from app.plugin.module_train.exporter import rotated_box_to_obb_corners


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
