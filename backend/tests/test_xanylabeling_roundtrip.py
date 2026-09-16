"""x-anylabeling 旋转框「导出 → 导入」往返一致性测试。

背景：``exporter.xany_shapes`` 曾直接用 ``rotated_box_to_obb_corners`` 的
``min(x+y)`` 规范化角点顺序；在约 (45°,135°) 区间，规范化后的首边会变成
**高边**，而 ``importer._shape_to_annotation`` 假定 ``points[0] -> points[1]``
恒为宽边，导致重新导入后 width/height/angle 全部错误。

修复：xany 导出改用 ``reorder=False`` 的原始局部角点顺序
``[TL, TR, BR, BL]``，保证首边恒为宽边；YOLO OBB 仍用 ``reorder=True``。
"""
import math

from app.api.v1.module_annotation.dataset.x_anylabeling_importer import (
    _shape_to_annotation,
)
from app.plugin.module_train.exporter import xany_shapes

# 覆盖首边恰好为宽边（0/30/45）与首边被规范化为高边（60/90/120/150）的角度
_ANGLES_DEG = [0, 30, 45, 60, 90, 120, 150]


def _assert_roundtrip(deg: float, img_w: int, img_h: int) -> None:
    angle = math.radians(deg)
    ann = {
        "id": "a1",
        "type": "RotatedBox",
        "class_id": 0,
        "cx": 0.5,
        "cy": 0.5,
        "width": 0.3,
        "height": 0.1,
        "angle": angle,
    }

    shapes = xany_shapes([ann], img_w, img_h, {0: "c"})
    assert len(shapes) == 1
    assert shapes[0]["shape_type"] == "rotation"

    got = _shape_to_annotation(shapes[0], {"c": 0}, img_w, img_h)
    assert got is not None
    assert abs(got["width"] - ann["width"]) < 1e-6, f"{deg}° width 往返错误"
    assert abs(got["height"] - ann["height"]) < 1e-6, f"{deg}° height 往返错误"
    # angle 等价 mod π：轴对齐表示可能整体反向，比较 |sin|/|cos| 更稳健
    assert abs(abs(math.sin(got["angle"])) - abs(math.sin(angle))) < 1e-6, f"{deg}° sin 不匹配"
    assert abs(abs(math.cos(got["angle"])) - abs(math.cos(angle))) < 1e-6, f"{deg}° cos 不匹配"


def test_rotated_box_export_import_roundtrip_non_square():
    """非正方形图像（200×100）下多角度往返，width/height/angle 应保持一致。"""
    for deg in _ANGLES_DEG:
        _assert_roundtrip(deg, 200, 100)


def test_rotated_box_export_import_roundtrip_square():
    """正方形图像（100×100）各角度同样保持一致。"""
    for deg in _ANGLES_DEG:
        _assert_roundtrip(deg, 100, 100)
