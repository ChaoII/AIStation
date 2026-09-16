"""PaddleOCR det 条目转换测试（矩形纳入 det）。"""

from app.plugin.module_train.exporter import paddle_ocr_det_entries


def test_det_entries_include_axis_aligned_box():
    anns = [{"type": "AxisAlignedBox", "class_id": 0, "x1": 0.1, "y1": 0.2, "x2": 0.4, "y2": 0.5, "text": "abc"}]
    entries = paddle_ocr_det_entries(anns, 100, 100)
    assert len(entries) == 1
    assert entries[0]["transcription"] == "abc"
    pts = entries[0]["points"]
    assert pts == [[10.0, 20.0], [40.0, 20.0], [40.0, 50.0], [10.0, 50.0]]


def test_det_entries_polygon_and_ocr():
    anns = [
        {"type": "Polygon", "points": [{"x": 0.1, "y": 0.1}, {"x": 0.3, "y": 0.1}, {"x": 0.3, "y": 0.2}, {"x": 0.1, "y": 0.2}], "text": "p"},
        {"type": "Ocr", "points": [{"x": 0.5, "y": 0.5}, {"x": 0.7, "y": 0.5}, {"x": 0.7, "y": 0.6}, {"x": 0.5, "y": 0.6}], "text": "o"},
    ]
    entries = paddle_ocr_det_entries(anns, 100, 100)
    assert len(entries) == 2
    assert entries[0]["transcription"] == "p"
    assert entries[1]["transcription"] == "o"


def test_det_entries_centered_box_pixelized():
    """中心式矩形（x/y/width/height）同样纳入 det 并转像素 4 点。"""
    anns = [{"type": "AxisAlignedBox", "class_id": 0, "x": 0.5, "y": 0.5, "width": 0.2, "height": 0.1, "text": "c"}]
    entries = paddle_ocr_det_entries(anns, 200, 100)
    assert len(entries) == 1
    flat = [round(v, 6) for pt in entries[0]["points"] for v in pt]
    assert flat == [80.0, 45.0, 120.0, 45.0, 120.0, 55.0, 80.0, 55.0]


def test_det_entries_skip_unsupported_shape():
    anns = [{"type": "RotatedBox", "cx": 0.5, "cy": 0.5, "width": 0.2, "height": 0.1, "angle": 0.0, "text": "r"}]
    assert paddle_ocr_det_entries(anns, 100, 100) == []
