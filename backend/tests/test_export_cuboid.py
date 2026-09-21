"""AnyLabeling 导出 cuboid 形状单测：底部旋转矩形顶点 + 3D 参数附加字段。"""
from app.plugin.module_train.exporter import xany_shapes


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
