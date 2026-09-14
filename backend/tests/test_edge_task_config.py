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


class _AlgAttr:
    name = "工作服"
    algorithm_type = "PED_ATTR"
    scene_type = "PED_ATTR"
    model_path = "/models/zhgd_det.onnx"
    runtime_config = {"backend": "ort", "device": "cpu"}
    preset_params = {"cls_path": "/models/zhgd_ml.onnx",
                     "attributes": ["safety_helmet", "work_uniform"],
                     "confidence_threshold": 0.4, "cls_threshold": 0.5}


class _TaskAttr(_Task):
    algorithm_id = 2


def test_ped_attr_pipeline_config():
    cfg = build_agent_task_config(_TaskAttr(), _Cam(), _AlgAttr(), events={})
    assert cfg["scene_type"] == "PED_ATTR"
    m = cfg["models"][0]
    assert m["type"] == "pedestrian_attribute"
    assert m["det_url"] == "/models/zhgd_det.onnx"
    assert m["cls_url"] == "/models/zhgd_ml.onnx"
    assert m["attributes"] == ["safety_helmet", "work_uniform"]
    assert m["cls_threshold"] == 0.5


class _AlgOcr:
    name = "仪表读数"
    algorithm_type = "OCR"
    scene_type = "OCR_TEXT"
    model_path = "/models/ocr_det.onnx"
    runtime_config = {"backend": "ort", "device": "cpu"}
    preset_params = {
        "cls_path": "/models/ocr_cls.onnx",
        "rec_path": "/models/ocr_rec.onnx",
        "dict_path": "/models/ocr_dict.txt",
        "input_size": [960, 960],
    }


class _TaskOcr(_Task):
    algorithm_id = 3


def test_ocr_pipeline_config():
    cfg = build_agent_task_config(_TaskOcr(), _Cam(), _AlgOcr(), events={})
    assert cfg["scene_type"] == "OCR_TEXT"
    m = cfg["models"][0]
    assert m["type"] == "ocr"
    assert m["det_url"] == "/models/ocr_det.onnx"
    assert m["cls_url"] == "/models/ocr_cls.onnx"
    assert m["rec_url"] == "/models/ocr_rec.onnx"
    assert m["dict_url"] == "/models/ocr_dict.txt"
    assert m["input_size"] == [960, 960]


class _AlgLpr:
    name = "车牌识别"
    algorithm_type = "LPR"
    scene_type = "LPR"
    model_path = "/models/lpr_det.onnx"
    runtime_config = {"backend": "ort", "device": "cpu"}
    preset_params = {
        "rec_path": "/models/lpr_rec.onnx",
        "input_size": [640, 640],
        "confidence_threshold": 0.5,
    }


class _TaskLpr(_Task):
    algorithm_id = 4


def test_lpr_pipeline_config():
    cfg = build_agent_task_config(_TaskLpr(), _Cam(), _AlgLpr(), events={})
    assert cfg["scene_type"] == "LPR"
    assert len(cfg["models"]) == 1
    m = cfg["models"][0]
    assert m["type"] == "lpr"
    assert m["det_url"] == "/models/lpr_det.onnx"
    assert m["rec_url"] == "/models/lpr_rec.onnx"
    assert m["input_size"] == [640, 640]
    assert m["confidence_threshold"] == 0.5
    assert m["backend"] == "ort"
    assert m["device"] == "cpu"


class _AlgLprList(_AlgLpr):
    name = "车牌黑白名单"
    scene_type = "LPR_LIST"
    runtime_config = {"backend": "trt", "device": "gpu", "model_password": "pw", "rec_path": "/rt/rec.onnx"}
    preset_params = {}


class _TaskLprList(_Task):
    algorithm_id = 5


def test_lpr_list_runtime_rec_path_and_password():
    """LPR_LIST 同样产出 lpr 条目，rec_path/password 可来自 runtime_config。"""
    cfg = build_agent_task_config(_TaskLprList(), _Cam(), _AlgLprList(), events={})
    m = cfg["models"][0]
    assert m["type"] == "lpr"
    assert m["det_url"] == "/models/lpr_det.onnx"
    assert m["rec_url"] == "/rt/rec.onnx"
    assert m["password"] == "pw"
    assert m["backend"] == "trt"


class _AlgTrack(_Alg):
    """跟踪开关来自 algorithm.runtime_config.tracking。"""
    runtime_config = {
        "backend": "ort",
        "device": "cpu",
        "tracking": {"enabled": True, "algorithm": "bytetrack"},
    }


def test_tracking_enabled_from_runtime_config():
    cfg = build_agent_task_config(_Task(), _Cam(), _AlgTrack(), events={})
    assert cfg["tracking"]["enabled"] is True
    assert cfg["tracking"]["algorithm"] == "bytetrack"


class _TaskTrack(_Task):
    """跟踪开关经任务运行时覆盖传入。"""
    runtime_overrides = {"tracking": {"enabled": True, "algorithm": "botsort"}}


def test_tracking_enabled_from_runtime_overrides():
    cfg = build_agent_task_config(_TaskTrack(), _Cam(), _Alg(), events={})
    assert cfg["tracking"]["enabled"] is True
    assert cfg["tracking"]["algorithm"] == "botsort"


def test_tracking_default_disabled():
    """缺省不含 tracking 配置时应关闭跟踪，algorithm 缺省 bytetrack。"""
    cfg = build_agent_task_config(_Task(), _Cam(), _Alg(), events={})
    assert cfg["tracking"]["enabled"] is False
    assert cfg["tracking"]["algorithm"] == "bytetrack"
