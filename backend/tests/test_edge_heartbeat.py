"""边缘心跳字段兼容测试（Agent 发 edge_code，云端兼容 code）。"""
from app.api.v1.module_video.edge.service import extract_device_code


def test_extract_prefers_code():
    assert extract_device_code({"code": "edge-01", "edge_code": "x"}) == "edge-01"


def test_extract_falls_back_to_edge_code():
    assert extract_device_code({"edge_code": "edge-01"}) == "edge-01"


def test_extract_empty():
    assert extract_device_code({}) == ""
    assert extract_device_code({"edge_code": "  "}) == ""
