"""事件接入测试：边缘事件归一化、event_id 去重与 MQTT 消费者。"""
import asyncio

from app.api.v1.module_video.edge.consumer import (
    EdgeEventConsumer,
    build_mqtt_tls_context,
    dedup,
    normalize_edge_event,
    parse_mqtt_broker,
    uses_mqtt_tls,
)


def test_normalize_snapshot_ref():
    ev = {
        "event_id": "e1",
        "edge_code": "edge-01",
        "camera_id": 7,
        "task_id": 1,
        "detections": [
            {
                "label": "person",
                "confidence": 0.9,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
            }
        ],
        "snapshot": {"ref": "edge-01/cam7/2026-09-12/x.jpg"},
    }
    out = normalize_edge_event(ev)
    assert out["snapshot_path"] == "edge-01/cam7/2026-09-12/x.jpg"
    assert out["edge_code"] == "edge-01"
    assert out["detections"][0]["label"] == "person"


def test_normalize_event_v2_objects_to_detections():
    ev = {
        "event_id": "e2",
        "camera_id": 7,
        "task_id": 1,
        "schema_version": 2,
        "scene_type": "PED_ATTR",
        "objects": [
            {
                "label": "person",
                "label_id": 0,
                "confidence": 0.9,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "attributes": {"work_uniform": 0.2},
            }
        ],
    }
    out = normalize_edge_event(ev)
    assert out["scene_type"] == "PED_ATTR"
    assert len(out["detections"]) == 1
    d = out["detections"][0]
    assert d["label"] == "person" and d["bbox"]["x"] == 0.1
    # 属性为 {属性名: 分数}（分数=具有该属性的概率；违规=分数低于阈值）
    assert d["attributes"]["work_uniform"] == 0.2


def test_normalize_event_v2_merges_objects_attributes_into_detections():
    """事件 v2 同时含 detections 与 objects 时，属性/轨迹需按索引并入 detections。"""
    ev = {
        "event_id": "e2b",
        "camera_id": 7,
        "task_id": 1,
        "schema_version": 2,
        "scene_type": "PED_ATTR",
        "detections": [
            {
                "label": "person",
                "label_id": 0,
                "confidence": 0.9,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
            }
        ],
        "objects": [
            {
                "label": "person",
                "label_id": 0,
                "confidence": 0.9,
                "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
                "track_id": 42,
                "attributes": {"work_uniform": 0.2},
            }
        ],
    }
    out = normalize_edge_event(ev)
    d = out["detections"][0]
    assert d["attributes"]["work_uniform"] == 0.2
    assert d["track_id"] == 42


def test_normalize_event_v1_unchanged():
    ev = {"detections": [{"label": "person"}]}
    out = normalize_edge_event(ev)
    assert out["detections"] == [{"label": "person"}]


def test_normalize_frame_timestamp_from_ts():
    ev = {"event_id": "e2", "ts": "2026-09-12T08:00:00.123Z"}
    out = normalize_edge_event(ev)
    assert out["frame_timestamp"] == "2026-09-12T08:00:00.123Z"


def test_normalize_inline_snapshot_data():
    ev = {"event_id": "e3", "snapshot": {"data": "QUJD"}}
    out = normalize_edge_event(ev)
    assert out["snapshot_data"] == "QUJD"


def test_normalize_keeps_explicit_snapshot_path():
    ev = {"event_id": "e4", "snapshot_path": "keep/x.jpg", "snapshot": {"ref": "new/y.jpg"}}
    out = normalize_edge_event(ev)
    assert out["snapshot_path"] == "new/y.jpg"


def test_dedup_event_id():
    d = dedup()
    assert d.seen("e1") is False
    d.mark("e1")
    assert d.seen("e1") is True


def test_dedup_bounded_eviction():
    d = dedup(maxsize=2, ttl=600)
    d.mark("a")
    d.mark("b")
    d.mark("c")
    assert d.seen("a") is False
    assert d.seen("b") is True
    assert d.seen("c") is True


def test_parse_mqtt_broker():
    assert parse_mqtt_broker("mqtt://broker:1884") == ("broker", 1884)
    assert parse_mqtt_broker("tcp://1.2.3.4") == ("1.2.3.4", 1883)
    assert parse_mqtt_broker("broker.local") == ("broker.local", 1883)
    assert parse_mqtt_broker("mqtts://secure.example.com") == ("secure.example.com", 8883)
    assert parse_mqtt_broker("") == ("", 1883)


def test_consumer_disabled_returns_without_broker(monkeypatch):
    from app.config import setting

    monkeypatch.setattr(setting.settings, "MQTT_ENABLED", False)
    consumer = EdgeEventConsumer()
    assert asyncio.run(consumer.run()) is None


def test_consumer_processes_then_dedups(monkeypatch):
    from app.api.v1.module_video.inference import service as svc

    calls = []

    async def _fake_callback(event):
        calls.append(event)
        return {"alarm_created": True}

    monkeypatch.setattr(svc.InferenceService, "process_detection_callback", _fake_callback)

    consumer = EdgeEventConsumer()
    payload = {
        "event_id": "dup-1",
        "edge_code": "edge-01",
        "camera_id": 7,
        "task_id": 1,
        "detections": [{"label": "person"}],
        "snapshot": {"ref": "r/x.jpg"},
        "ts": "2026-09-12T08:00:00Z",
    }
    asyncio.run(consumer._process_payload(payload))
    asyncio.run(consumer._process_payload(payload))

    assert len(calls) == 1
    assert calls[0]["snapshot_path"] == "r/x.jpg"
    assert calls[0]["frame_timestamp"] == "2026-09-12T08:00:00Z"


def test_callback_keeps_snapshot_reference_without_base64(monkeypatch):
    """边缘事件只带相对快照引用时，告警记录应存该引用而非 None。"""
    from app.api.v1.module_video.inference.service import InferenceService
    from app.core import database

    captured = {}

    class _Result:
        def scalar_one_or_none(self):
            return None

        def scalars(self):
            return self

        def all(self):
            return []

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, stmt):
            return _Result()

    class _BeginSession(_Session):
        def add(self, obj):
            captured["record"] = obj

        async def flush(self):
            captured["record"].id = 99

    class _Factory:
        def __call__(self):
            return _Session()

        def begin(self):
            return _BeginSession()

    monkeypatch.setattr(database, "async_db_session", _Factory())

    event = {
        "task_id": 1,
        "camera_id": 7,
        "algorithm_type": "INTRUSION",
        "detections": [{"label": "person"}],
        "snapshot_path": "edge-01/cam7/2026-09-12/x.jpg",
        "frame_timestamp": "2026-09-12T08:00:00Z",
    }
    result = asyncio.run(InferenceService.process_detection_callback(event))
    assert result["alarm_created"] is True
    assert captured["record"].snapshot_path == "edge-01/cam7/2026-09-12/x.jpg"


def test_http_callback_normalizes_inline_snapshot(monkeypatch):
    """HTTP 回调路径必须与 MQTT 共用归一化，内联快照需映射为 snapshot_data。"""
    from app.api.v1.module_video.algorithm import controller as algo_ctrl
    from app.api.v1.module_video.inference import service as svc
    from app.config import setting

    monkeypatch.setattr(setting.settings, "INFERENCE_CALLBACK_TOKEN", "tok")

    captured = {}

    async def _fake_callback(event):
        captured["event"] = event
        return {"alarm_created": True}

    monkeypatch.setattr(svc.InferenceService, "process_detection_callback", _fake_callback)

    class _Req:
        headers = {"Authorization": "Bearer tok"}

    body = {
        "event_id": "http-inline-1",
        "edge_code": "edge-01",
        "camera_id": 7,
        "task_id": 1,
        "detections": [{"label": "person"}],
        "snapshot": {"data": "QUJD"},
        "ts": "2026-09-12T08:00:00Z",
    }
    resp = asyncio.run(algo_ctrl.detection_callback_controller(_Req(), body))

    assert resp.status_code == 200
    # 归一化生效：Agent 嵌套结构映射为回调兼容字段，内联快照不再被丢弃
    assert captured["event"]["snapshot_data"] == "QUJD"
    assert captured["event"]["frame_timestamp"] == "2026-09-12T08:00:00Z"
    assert captured["event"]["edge_code"] == "edge-01"


def test_http_callback_legacy_flat_payload_passthrough(monkeypatch):
    """旧版扁平回调（无 snapshot 嵌套）原样透传，不受归一化影响。"""
    from app.api.v1.module_video.algorithm import controller as algo_ctrl
    from app.api.v1.module_video.inference import service as svc
    from app.config import setting

    monkeypatch.setattr(setting.settings, "INFERENCE_CALLBACK_TOKEN", "tok")

    captured = {}

    async def _fake_callback(event):
        captured["event"] = event
        return {"alarm_created": True}

    monkeypatch.setattr(svc.InferenceService, "process_detection_callback", _fake_callback)

    class _Req:
        headers = {"Authorization": "Bearer tok"}

    body = {
        "event_id": "http-legacy-1",
        "camera_id": 7,
        "task_id": 1,
        "detections": [{"label": "person"}],
        "snapshot_path": "legacy/x.jpg",
    }
    resp = asyncio.run(algo_ctrl.detection_callback_controller(_Req(), body))

    assert resp.status_code == 200
    assert captured["event"]["snapshot_path"] == "legacy/x.jpg"
    assert "snapshot_data" not in captured["event"]


def _topic_matches(topic: str, pattern: str) -> bool:
    """按 MQTT 语义判断主题是否匹配通配模式（+ 匹配一级）。"""
    topic_levels = topic.split("/")
    pattern_levels = pattern.split("/")
    if len(topic_levels) != len(pattern_levels):
        return False
    return all(
        p == "+" or p == t for t, p in zip(topic_levels, pattern_levels, strict=True)
    )


def test_build_events_topic_matches_subscribe(monkeypatch):
    """Agent 发布主题必须命中云端消费者的订阅通配（Fix 1 回归）。"""
    from app.api.v1.module_video.edge.orchestrator import build_events
    from app.config import setting

    monkeypatch.setattr(setting.settings, "VIDEO_ANALYSIS_MODE", "cloud_edge")
    events = build_events(camera_id=7, edge_code="edge-01")
    mqtt = events["mqtt"]

    expected = f"{setting.settings.MQTT_TOPIC_PREFIX.rstrip('/')}/edge-01/camera/7/detect"
    assert mqtt["topic"] == expected
    assert _topic_matches(mqtt["topic"], setting.settings.MQTT_SUBSCRIBE_TOPIC)
    assert "+" not in mqtt["topic"]


def test_parse_mqtt_tls_schemes():
    assert uses_mqtt_tls("mqtts://secure.example.com:8883") is True
    assert uses_mqtt_tls("ssl://secure.example.com") is True
    assert uses_mqtt_tls("mqtt://plain:1883") is False
    assert uses_mqtt_tls("plain.host") is False
    assert uses_mqtt_tls("") is False


def test_build_mqtt_tls_context():
    import ssl

    assert build_mqtt_tls_context("mqtt://plain:1883") is None
    ctx = build_mqtt_tls_context("mqtts://secure.example.com")
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_consumer_start_stop_cycle_resets_flag(monkeypatch):
    """stop 后再次 start 必须清除 _stopped，保证可重启（Fix 3）。"""
    from app.config import setting

    monkeypatch.setattr(setting.settings, "MQTT_ENABLED", False)

    async def _scenario():
        consumer = EdgeEventConsumer()
        consumer._stopped = True
        await consumer.start()
        assert consumer._stopped is False
        await consumer.stop()
        assert consumer._stopped is True

    asyncio.run(_scenario())
