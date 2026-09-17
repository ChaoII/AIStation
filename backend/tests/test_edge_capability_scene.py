"""场景感知的边缘能力校验测试：PED_ATTR 必须声明 pedestrian_attribute 模型族。"""
from types import SimpleNamespace

from app.api.v1.module_video.edge.orchestrator import (
    EdgeOrchestrator,
    build_agent_task_config,
)
from app.api.v1.module_video.edge.service import capability_satisfies
from app.api.v1.module_video.scene.contract import AGENT_MODEL_FAMILIES

# Agent capability.cpp 默认构建上报的族（含 B1 的 obb/iseg）
_AGENT_CAPS = {
    "model_families": sorted(AGENT_MODEL_FAMILIES),
    "backends": ["ort"],
    "max_channels": 8,
}


class _Cam:
    id = 7
    name = "北门"
    rtsp_url_sub = "rtsp://cam/7"
    stream_id = "cam7"


class _Task:
    id = 321
    camera_id = 7
    algorithm_id = 11
    stream_type = "SUB"
    detect_region = None
    sensitivity = 50
    schedule_json = {}
    runtime_overrides = None
    params_overrides = None


def _scene_algo(scene_code: str) -> SimpleNamespace:
    """构造场景算法：scene_type 命中目录，algorithm_type 与场景码一致。"""
    return SimpleNamespace(
        name=scene_code,
        algorithm_type=scene_code,
        scene_type=scene_code,
        model_path=f"/models/{scene_code.lower()}.onnx",
        runtime_config={"backend": "ort", "device": "cpu"},
        preset_params={"confidence_threshold": 0.4, "labels": ["person"]},
    )


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


# B1/B2a 新增能力：场景 → Agent 侧规范模型 type（capability.cpp 上报族可满足能力校验）
_NEW_CAPABILITY_SCENES = {
    "OBB_DET": "obb",
    "I_SEG": "iseg",
    "SCENE_CLS": "classification",
}


def test_obb_iseg_scene_cls_gate_accepts_agent_reported_families():
    """OBB_DET/I_SEG/SCENE_CLS：Agent 上报对应族时能力校验必须通过（可下发）。"""
    for scene_code in _NEW_CAPABILITY_SCENES:
        ok, reason = EdgeOrchestrator._check_capability(
            _AGENT_CAPS, _scene_algo(scene_code), running_channels=0
        )
        assert ok is True, f"{scene_code} 能力校验失败：{reason}"
        assert reason == ""


def test_obb_iseg_scene_cls_dispatch_uses_canonical_model_type():
    """OBB_DET/I_SEG/SCENE_CLS：编译出的 TaskConfig 模型 type 必须是 Agent 可识别规范名。"""
    for scene_code, expected_type in _NEW_CAPABILITY_SCENES.items():
        algo = _scene_algo(scene_code)
        cfg = build_agent_task_config(_Task(), _Cam(), algo, events={}, capabilities=_AGENT_CAPS)
        assert cfg["scene_type"] == scene_code
        types = [m["type"] for m in cfg["models"]]
        assert expected_type in types, f"{scene_code} 下发模型 type={types}，期望 {expected_type}"
