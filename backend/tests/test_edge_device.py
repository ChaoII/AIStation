"""边缘设备能力校验测试。"""
from app.api.v1.module_video.edge.schema import (
    EdgeDeviceCreateSchema,
    EdgeDeviceOutSchema,
    EdgeDeviceUpdateSchema,
)
from app.api.v1.module_video.edge.service import capability_satisfies


def test_out_schema_hides_secret():
    """出参 schema 不得包含控制面密钥字段。"""
    assert "secret" not in EdgeDeviceOutSchema.model_fields


def test_input_schema_keeps_secret():
    """入参 schema 仍允许配置密钥。"""
    assert "secret" in EdgeDeviceCreateSchema.model_fields
    assert "secret" in EdgeDeviceUpdateSchema.model_fields


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
