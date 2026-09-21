"""COCO Panoptic 导出测试：mask 编码、段表、thing/stuff 区分子模块单元测试。"""
import numpy as np

from app.plugin.module_train.exporter import _panoptic_mask


def test_panoptic_mask_thing_and_stuff():
    # 100x100：stuff(0) 整图垫底；thing(1) 两个实例
    class_meta = {
        0: {"name": "bg", "is_instance": False},
        1: {"name": "car", "is_instance": True},
    }
    anns = [
        {"type": "Polygon", "class_id": 0, "points": [
            {"x": 0, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0, "y": 1}]},
        {"type": "Polygon", "class_id": 1, "points": [
            {"x": 0.1, "y": 0.1}, {"x": 0.4, "y": 0.1}, {"x": 0.4, "y": 0.4}, {"x": 0.1, "y": 0.4}]},
        {"type": "Polygon", "class_id": 1, "points": [
            {"x": 0.5, "y": 0.5}, {"x": 0.8, "y": 0.5}, {"x": 0.8, "y": 0.8}, {"x": 0.5, "y": 0.8}]},
    ]
    mask, segs = _panoptic_mask(anns, 100, 100, class_meta)
    assert mask.dtype == np.uint32
    # stuff id = 0*1000+0 = 0
    assert int(mask[0, 0]) == 0
    # thing instance1 id = 1*1000+1 = 1001
    assert int(mask[20, 20]) == 1001
    # thing instance2 id = 1*1000+2 = 1002
    assert int(mask[60, 60]) == 1002
    # 段表里两个 thing 段 id 分别为 1001/1002，area>0
    thing_ids = {s["id"] for s in segs if s["category_id"] == 1}
    assert thing_ids == {1001, 1002}
    for s in segs:
        if s["category_id"] == 1:
            assert s["area"] > 0


def test_panoptic_mask_stuff_merges_by_pid():
    """同类 stuff 多边形（同 pid）在掩码中合并为一段。"""
    class_meta = {0: {"name": "wall", "is_instance": False}}
    anns = [
        {"type": "Polygon", "class_id": 0, "points": [
            {"x": 0, "y": 0}, {"x": 0.5, "y": 0}, {"x": 0.5, "y": 1}, {"x": 0, "y": 1}]},
        {"type": "Polygon", "class_id": 0, "points": [
            {"x": 0.5, "y": 0}, {"x": 1, "y": 0}, {"x": 1, "y": 1}, {"x": 0.5, "y": 1}]},
    ]
    mask, segs = _panoptic_mask(anns, 100, 100, class_meta)
    assert len(segs) == 1
    assert segs[0]["id"] == 0
    assert segs[0]["category_id"] == 0
    assert segs[0]["area"] == 100 * 100


def test_panoptic_mask_partial_stuff_not_merged_with_void():
    """stuff 类 id=0 只局部覆盖时，未标注背景不得并入段 0（哨兵隔离）。"""
    class_meta = {0: {"name": "wall", "is_instance": False}}
    # 只覆盖左半 0..0.5（不做全图填充）
    anns = [
        {"type": "Polygon", "class_id": 0, "points": [
            {"x": 0, "y": 0}, {"x": 0.5, "y": 0}, {"x": 0.5, "y": 1}, {"x": 0, "y": 1}]},
    ]
    mask, segs = _panoptic_mask(anns, 100, 100, class_meta)
    assert len(segs) == 1
    seg0 = segs[0]
    assert seg0["id"] == 0
    assert seg0["category_id"] == 0
    # 段 0 area 仅等于该多边形覆盖的像素数（列 0..50 共 51 列 * 100 行 = 5100），而非整图 10000
    assert seg0["area"] == 51 * 100
    # bbox 只覆盖该多边形范围
    assert seg0["bbox"] == [0, 0, 51, 100]
    # 未标注背景像素以哨兵标记（uint32 位形 0xFFFFFFFF），不并入段 0
    assert int(mask[0, 75]) == np.iinfo(np.uint32).max
    assert int(mask[99, 99]) == np.iinfo(np.uint32).max
    # 段 0 范围内像素值仍为 0
    assert int(mask[0, 0]) == 0
    assert int(mask[99, 50]) == 0
    # 段 0 像素计数与 area 一致
    region_area = int((mask == 0).sum())
    assert region_area == seg0["area"]
