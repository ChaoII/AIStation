"""场景感知的边缘能力校验测试：PED_ATTR 必须声明 pedestrian_attribute 模型族。"""
from app.api.v1.module_video.edge.orchestrator import EdgeOrchestrator
from app.api.v1.module_video.edge.service import capability_satisfies


class _PedAlg:
    """归属 PED_ATTR 场景的算法：仅靠 _resolve_model_type 会被误判为 det。"""

    name = "行人属性"
    algorithm_type = "PED_ATTR"
    model_path = "s3://m/det.onnx"
    runtime_config = {"backend": "trt"}
    scene_type = "PED_ATTR"


def test_capability_satisfies_all_model_families():
    """requirement.model_families 要求全部具备。"""
    caps = {"model_families": ["det"], "backends": ["trt"], "max_channels": 4}
    ok, reason = capability_satisfies(caps, {"model_families": ["det", "pedestrian_attribute"]})
    assert ok is False
    assert "pedestrian_attribute" in reason


def test_capability_satisfies_single_back_compat():
    """旧的单个 model_family 用法保持兼容。"""
    caps = {"model_families": ["det"], "backends": ["trt"], "max_channels": 4}
    ok, reason = capability_satisfies(caps, {"model_family": "det"})
    assert ok is True
    assert reason == ""


def test_ped_attr_gate_rejects_device_without_attribute_family():
    caps = {"model_families": ["det"], "backends": ["trt"], "max_channels": 4}
    ok, reason = EdgeOrchestrator._check_capability(caps, _PedAlg(), running_channels=0)
    assert ok is False
    assert "pedestrian_attribute" in reason


def test_ped_attr_gate_accepts_device_with_attribute_family():
    caps = {"model_families": ["det", "pedestrian_attribute"], "backends": ["trt"], "max_channels": 4}
    ok, reason = EdgeOrchestrator._check_capability(caps, _PedAlg(), running_channels=0)
    assert ok is True
    assert reason == ""
