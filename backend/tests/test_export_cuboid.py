"""AnyLabeling 导出 cuboid 形状单测：底部旋转矩形顶点 + 3D 参数附加字段。"""
import math

from app.plugin.module_train.exporter import xany_shapes
from app.api.v1.module_annotation.dataset.x_anylabeling_importer import (
    _infer_task_type,
    _shape_to_annotation,
)


def test_xany_shapes_cuboid():
    anns = [{
        "type": "Cuboid",
        "class_id": 1,
        "cx": 0.5, "cy": 0.5, "w": 0.4, "h": 0.2,
        "yaw": 0.0, "depth": 0.5, "top_cy": 0.3,
    }]
    shapes = xany_shapes(anns, 100, 100, {1: "car"})
    assert len(shapes) == 1
    s = shapes[0]
    assert s["shape_type"] == "cuboid"
    assert s["label"] == "car"
    # 底部旋转矩形 4 顶点（像素坐标），yaw=0 时按 w/h 展开
    pts = s["points"]
    assert len(pts) == 4
    assert pts[0] == [30.0, 40.0]
    assert pts[2] == [70.0, 60.0]
    # 3D 参数附加字段
    attrs = s["attributes"]
    assert attrs["cx"] == 0.5
    assert attrs["depth"] == 0.5
    assert attrs["top_cy"] == 0.3


def test_cuboid_roundtrip_via_attributes():
    """导出→导入往返：cuboid 不应被导入器丢弃，且几何/3D 参数无损还原。"""
    anns = [{
        "type": "Cuboid",
        "class_id": 1,
        "cx": 0.5, "cy": 0.45, "w": 0.4, "h": 0.2,
        "yaw": math.pi / 6, "depth": 0.6, "top_cy": 0.25,
    }]
    shapes = xany_shapes(anns, 200, 100, {1: "car"})
    assert shapes[0]["shape_type"] == "cuboid"

    # 导入器应识别为 cuboid 任务
    assert _infer_task_type(shapes) == "cuboid"

    # attributes 带底部矩形参数时直接还原
    restored = _shape_to_annotation(
        shapes[0], {"car": 1}, 200, 100
    )
    assert restored is not None
    assert restored["type"] == "Cuboid"
    assert restored["class_id"] == 1
    assert restored["cx"] == 0.5
    assert restored["cy"] == 0.45
    assert restored["w"] == 0.4
    assert restored["h"] == 0.2
    assert abs(restored["yaw"] - math.pi / 6) < 1e-9
    assert restored["depth"] == 0.6
    assert restored["top_cy"] == 0.25


def test_cuboid_roundtrip_from_points():
    """导出→导入往返（无 attributes 时从角点反推）：几何应与 exporter 逆运算一致。"""
    anns = [{
        "type": "Cuboid",
        "class_id": 2,
        "cx": 0.5, "cy": 0.5, "w": 0.4, "h": 0.2,
        "yaw": 0.0, "depth": 0.5, "top_cy": 0.15,
    }]
    shapes = xany_shapes(anns, 100, 100, {2: "bus"})
    shape = dict(shapes[0])
    shape.pop("attributes", None)

    restored = _shape_to_annotation(shape, {"bus": 2}, 100, 100)
    assert restored is not None
    assert restored["type"] == "Cuboid"
    assert abs(restored["cx"] - 0.5) < 1e-6
    assert abs(restored["cy"] - 0.5) < 1e-6
    assert abs(restored["w"] - 0.4) < 1e-6
    assert abs(restored["h"] - 0.2) < 1e-6
    assert abs(restored["yaw"]) < 1e-6
    # 无 attributes 时深度/顶面回落默认值
    assert restored["depth"] == 0.5
    assert restored["top_cy"] == 0.15
