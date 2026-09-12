"""边缘设备能力校验测试。"""
from app.api.v1.module_video.edge.service import capability_satisfies


def test_capability_ok():
    cap = {"model_families": ["det"], "backends": ["trt"], "max_channels": 4}
    ok, reason = capability_satisfies(cap, {"model_family": "det", "backend": "trt", "running_channels": 2})
    assert ok is True and reason == ""


def test_capability_missing_family():
    cap = {"model_families": ["det"], "backends": ["trt"], "max_channels": 4}
    ok, reason = capability_satisfies(cap, {"model_family": "ocr", "backend": "trt", "running_channels": 0})
    assert ok is False and "模型" in reason


def test_capability_full():
    cap = {"model_families": ["det"], "backends": ["trt"], "max_channels": 1}
    ok, reason = capability_satisfies(cap, {"model_family": "det", "backend": "trt", "running_channels": 1})
    assert ok is False and "路数" in reason
