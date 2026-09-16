"""云边任务配置契约回归：后端协商 + 键对齐。

覆盖审计 CONTRACT §1.1（BLOCKER：默认 trt ↔ ort-only Agent 必拒）与
§1.2/§4.1（HIGH：runtime_config/preset_params 键漂移导致用户旋钮静默失效）。
"""
from app.api.v1.module_video.edge.orchestrator import (
    build_agent_task_config,
    resolve_backend,
    resolve_confidence,
    resolve_device,
    resolve_input_size,
    sensitivity_to_conf,
)
from app.api.v1.module_video.edge.service import capability_satisfies
from app.config.setting import settings

# ── 参考数据：ModelDeploy Agent 实际读取的键（config_adapter.cpp:from_json/parse_one_model）
_AGENT_READ_TOP_LEVEL = {
    "task_id", "camera", "decoder", "encoder", "preview", "roi", "schedule",
    "models", "tracking", "alarm_interval_sec", "heartbeat_sec", "algorithm_type",
    "tenant", "events",
}
_AGENT_READ_MODEL = {
    "name", "type", "backend", "device", "confidence_threshold", "input_size",
    "labels", "attributes", "password", "det_url", "cls_url", "rec_url", "dict_url",
    "url", "path",
}
_AGENT_READ_EVENTS = {"transport", "mqtt", "http", "buffer", "snapshot"}
_AGENT_READ_MQTT = {"broker", "topic", "qos", "client_id", "username", "password"}
# 产出但 Agent 不读、经审计判定为「信息性/无害」的键（保留以便排查，测试显式放行）
_INFORMATIONAL_TOP_LEVEL = {"scene_type"}
_INFORMATIONAL_EVENT = {"topic_prefix"}
_INFORMATIONAL_MODEL = {"cls_threshold"}


class _Cam:
    id = 7
    name = "北门"
    rtsp_url_sub = "rtsp://cam/7"
    stream_id = "cam7"


class _Task:
    id = 123
    camera_id = 7
    algorithm_id = 1
    stream_type = "SUB"
    detect_region = None
    sensitivity = 60
    schedule_json = None
    runtime_overrides = None
    params_overrides = None


class _Alg:
    def __init__(self, runtime_config=None, preset_params=None, algorithm_type="INTRUSION", scene_type=None):
        self.name = "算法"
        self.algorithm_type = algorithm_type
        self.scene_type = scene_type
        self.model_path = "/m/model.onnx"
        self.runtime_config = runtime_config if runtime_config is not None else {}
        self.preset_params = preset_params if preset_params is not None else {}


# ───────────────────────────── §1.1 后端协商（BLOCKER）

def test_backend_explicit_wins():
    assert resolve_backend({"backend": "trt"}, {"backends": ["ort"]}) == "trt"


def test_backend_derived_from_device_when_unspecified():
    """未指定后端时从设备上报取（ort-only Agent 得到 ort，而非旧的 trt 默认）。"""
    assert resolve_backend({}, {"backends": ["ort"]}) == "ort"
    assert resolve_backend({"backend": "auto"}, {"backends": ["ort"]}) == "ort"


def test_backend_prefers_trt_when_device_supports_it():
    assert resolve_backend({}, {"backends": ["ort", "trt"]}) == "trt"


def test_backend_legacy_engine_is_preference_not_hard_requirement():
    """旧模板 engine=tensorrt：设备支持则用 trt，不支持则回退设备可用后端（不阻断主流程）。"""
    assert resolve_backend({"engine": "tensorrt"}, {"backends": ["trt", "ort"]}) == "trt"
    assert resolve_backend({"engine": "tensorrt"}, {"backends": ["ort"]}) == "ort"


def test_backend_falls_back_to_default_without_capabilities():
    assert resolve_backend({}, None) == settings.EDGE_DEFAULT_BACKEND


def test_no_common_backend_yields_actionable_error():
    """显式要求设备不支持的后端 → 明确可操作报错（含设备可用后端）。"""
    ok, reason = capability_satisfies(
        {"model_families": ["det"], "backends": ["ort"]},
        {"model_family": "det", "backend": "trt"},
    )
    assert ok is False
    assert "trt" in reason and "ort" in reason


def test_device_without_reported_backends_is_rejected_clearly():
    ok, reason = capability_satisfies(
        {"model_families": ["det"], "backends": []},
        {"model_family": "det", "backend": "ort"},
    )
    assert ok is False
    assert "未上报" in reason


# ───────────────────────────── §1.2/§4.1 键对齐

def test_legacy_ui_keys_reach_orchestrator():
    """前端模板旧键（engine/gpu/input_width/confidence）必须真正生效。"""
    alg = _Alg(
        runtime_config={
            "engine": "tensorrt",
            "gpu": {"enabled": True, "device_id": 0},
            "threads": 4,
            "batch_size": 1,
            "input_width": 960,
            "input_height": 960,
        },
        preset_params={"confidence": 0.5, "nms_threshold": 0.45},
    )
    cfg = build_agent_task_config(
        _Task(), _Cam(), alg,
        events={},
        capabilities={"backends": ["ort"], "hardware": {"platform": "cpu"}},
    )
    model = cfg["models"][0]
    assert model["backend"] == "ort"  # engine=tensorrt 设备不支持 → 回退
    assert model["device"] == "cpu"  # 设备平台为 cpu（不再恒为 gpu）
    assert model["input_size"] == [960, 960]  # input_width/height 生效
    assert model["confidence_threshold"] == 0.5  # confidence 生效


def test_canonical_keys_work_too():
    alg = _Alg(
        runtime_config={"backend": "ort", "device": "cpu", "input_size": [640, 480]},
        preset_params={"confidence_threshold": 0.7},
    )
    cfg = build_agent_task_config(_Task(), _Cam(), alg, events={})
    model = cfg["models"][0]
    assert model["backend"] == "ort" and model["device"] == "cpu"
    assert model["input_size"] == [640, 480]
    assert model["confidence_threshold"] == 0.7


def test_sensitivity_wires_to_confidence_when_threshold_absent():
    """顶层灵敏度旋钮在边缘真正生效：无显式阈值时按 worker 同公式折算为置信度。"""
    task = _Task()
    task.sensitivity = 80
    alg = _Alg(runtime_config={"backend": "ort"}, preset_params={})
    cfg = build_agent_task_config(task, _Cam(), alg, events={})
    assert cfg["models"][0]["confidence_threshold"] == sensitivity_to_conf(80)
    # 顶层不再下发 Agent 不读的 sensitivity
    assert "sensitivity" not in cfg


def test_resolve_confidence_precedence():
    assert resolve_confidence({"confidence_threshold": 0.6}, 10) == 0.6
    assert resolve_confidence({"conf_threshold": 0.3}, 10) == 0.3
    assert resolve_confidence({"confidence": 0.2}, 10) == 0.2
    assert resolve_confidence({}, 50) == sensitivity_to_conf(50)


def test_resolve_input_size_variants():
    assert resolve_input_size({"input_size": [800, 600]}, {}) == [800, 600]
    assert resolve_input_size({}, {"input_width": 1280, "input_height": 720}) == [1280, 720]
    assert resolve_input_size({}, {}) == [640, 640]


def test_resolve_device_variants():
    assert resolve_device({"device": "gpu"}, {"hardware": {"platform": "cpu"}}) == "gpu"
    assert resolve_device({"gpu": {"enabled": True}}, {"hardware": {"platform": "cpu"}}) == "cpu"
    assert resolve_device({"gpu": {"enabled": True}}, None) == "gpu"
    assert resolve_device({}, {"hardware": {"platform": "nvidia"}}) == "gpu"


def test_orchestrator_produces_only_agent_readable_keys():
    """编排器产出的键必须都在 Agent 实际读取集合内（信息性键显式放行）。"""
    algs = [
        _Alg(runtime_config={"backend": "ort"}, preset_params={"labels": ["person"]}),
        _Alg(runtime_config={"backend": "ort"}, preset_params={}, algorithm_type="PED_ATTR", scene_type="PED_ATTR"),
        _Alg(runtime_config={"backend": "ort"}, preset_params={}, algorithm_type="OCR", scene_type="OCR_TEXT"),
        _Alg(runtime_config={"backend": "ort"}, preset_params={}, algorithm_type="LPR", scene_type="LPR"),
        _Alg(runtime_config={"backend": "ort"}, preset_params={}, algorithm_type="FACE_DETECT", scene_type="FACE_DET"),
    ]
    events_http = {"transport": "http", "http": {"url": "u", "token": "t"},
                   "buffer": {"dir": "d", "max_mb": 1},
                   "snapshot": {"enabled": True, "inline": True, "quality": 75, "max_width": 640}}
    events_mqtt = {"transport": "mqtt",
                   "mqtt": {"broker": "tcp://b:1", "topic_prefix": "p", "topic": "t", "qos": 1,
                            "client_id": "c", "username": "", "password": ""},
                   "buffer": {"dir": "d", "max_mb": 1},
                   "snapshot": {"enabled": True, "inline": True, "quality": 75, "max_width": 640}}
    for alg in algs:
        for events in (events_http, events_mqtt):
            cfg = build_agent_task_config(_Task(), _Cam(), alg, events=events)
            produced = set(cfg) - _AGENT_READ_TOP_LEVEL - _INFORMATIONAL_TOP_LEVEL
            assert not produced, f"未读顶层键: {produced} ({alg.scene_type})"
            ev = cfg["events"]
            assert not (set(ev) - _AGENT_READ_EVENTS - _INFORMATIONAL_EVENT), set(ev)
            if "mqtt" in ev:
                assert not (set(ev["mqtt"]) - _AGENT_READ_MQTT - _INFORMATIONAL_EVENT), set(ev["mqtt"])
            for model in cfg["models"]:
                extra = set(model) - _AGENT_READ_MODEL - _INFORMATIONAL_MODEL
                assert not extra, f"未读模型键: {extra} ({alg.scene_type})"
