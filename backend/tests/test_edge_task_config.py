"""Agent TaskConfig / 事件通道契约编译测试。"""
from app.api.v1.module_video.edge import orchestrator as orch
from app.api.v1.module_video.edge.orchestrator import (
    build_agent_task_config,
    build_events,
    normalize_broker_scheme,
)


class _Cam:
    id = 7
    name = "北门"
    rtsp_url_sub = "rtsp://cam/7"
    stream_id = "cam7"


class _Alg:
    name = "入侵检测"
    algorithm_type = "INTRUSION"
    model_path = "/abs/det.onnx"
    runtime_config = {"backend": "ort", "device": "cpu"}
    preset_params = {"confidence_threshold": 0.4, "labels": ["person"]}


class _Task:
    id = 123
    camera_id = 7
    algorithm_id = 1
    stream_type = "SUB"
    detect_region = {"points": [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]}
    sensitivity = 60
    schedule_json = {"slots": [{"day": 0, "start": 8, "end": 18}]}
    runtime_overrides = None
    params_overrides = None


def test_normalize_broker_scheme():
    assert normalize_broker_scheme("mqtt://h:1883") == "tcp://h:1883"
    assert normalize_broker_scheme("mqtts://h:8883") == "ssl://h:8883"
    assert normalize_broker_scheme("h:1883") == "tcp://h:1883"
    assert normalize_broker_scheme("tcp://h:1883") == "tcp://h:1883"
    assert normalize_broker_scheme("") == ""


def test_task_config_contract_fields():
    cfg = build_agent_task_config(_Task(), _Cam(), _Alg(), events={})
    assert cfg["algorithm_type"] == "INTRUSION"
    assert cfg["tenant"] == "default"
    assert cfg["preview"] == {"enabled": True, "format": "snapshot"}
    assert cfg["schedule"] == {"slots": [{"day": 0, "start": 8, "end": 18}]}


def test_build_events_mqtt(monkeypatch):
    monkeypatch.setattr(orch.settings, "VIDEO_ANALYSIS_MODE", "cloud_edge")
    monkeypatch.setattr(orch.settings, "MQTT_BROKER_URL", "mqtt://broker:1883")
    monkeypatch.setattr(orch.settings, "MQTT_USERNAME", "u")
    monkeypatch.setattr(orch.settings, "MQTT_PASSWORD", "p")
    ev = build_events(camera_id=7, edge_code="edge-01")
    assert ev["transport"] == "mqtt"
    assert ev["mqtt"]["broker"] == "tcp://broker:1883"
    assert ev["mqtt"]["client_id"] == "aistation-agent-edge-01"
    assert ev["mqtt"]["username"] == "u"
    assert ev["mqtt"]["password"] == "p"
    assert ev["mqtt"]["topic"].endswith("/camera/7/detect")
    assert ev["snapshot"]["inline"] is True


def test_build_events_http(monkeypatch):
    monkeypatch.setattr(orch.settings, "VIDEO_ANALYSIS_MODE", "cloud_only")
    ev = build_events(camera_id=7, edge_code="local")
    assert ev["transport"] == "http"
    assert ev["http"]["url"].endswith("/video/algorithm/detection/callback")
    assert ev["snapshot"]["enabled"] is True
