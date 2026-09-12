"""事件接入测试：边缘事件归一化、event_id 去重与 MQTT 消费者。"""
import asyncio

from app.api.v1.module_video.edge.consumer import (
    EdgeEventConsumer,
    dedup,
    normalize_edge_event,
    parse_mqtt_broker,
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
