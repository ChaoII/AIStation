"""YOLO 导出类 id 连续化测试。"""
from app.plugin.module_train.exporter import _format_yolo_lines, _write_yaml, build_class_mapping


def test_build_class_mapping_contiguous():
    assert build_class_mapping({2, 5, 7}) == {2: 0, 5: 1, 7: 2}


def test_build_class_mapping_empty():
    assert build_class_mapping(set()) == {}


def test_write_yaml_uses_mapped_names(tmp_path):
    path = tmp_path / "dataset.yaml"
    _write_yaml(
        str(path),
        "/data",
        [0, 1],
        {2: "cat", 5: "dog"},
        class_id_map={2: 0, 5: 1},
    )
    text = path.read_text(encoding="utf-8")
    assert "nc: 2" in text
    assert '"0": "cat"' in text
    assert '"1": "dog"' in text


def test_yolo_lines_skip_invalid_class_id():
    """class_id 为 -1 或缺失时不得写出非法标签行（与收集器保持一致）。"""
    box = {"type": "AxisAlignedBox", "x1": 0.1, "y1": 0.1, "x2": 0.2, "y2": 0.2}
    anns = [
        {**box, "class_id": -1},
        dict(box),  # 缺失 class_id
        {**box, "class_id": 3},
    ]
    lines = _format_yolo_lines(anns, "detection", class_id_map={3: 0})
    assert len(lines) == 1
    assert lines[0].startswith("0 ")
