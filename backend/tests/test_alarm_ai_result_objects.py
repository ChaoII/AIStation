"""告警 ai_result 补存 v2 objects 测试。"""
import asyncio

from app.api.v1.module_video.inference import service
from app.api.v1.module_video.inference.temporal import TemporalStore

CAM, ALGO = 9, "DET_ZONE"


def _ev(objects=None, detections=None, ts=1000):
    return {
        "task_id": 1,
        "camera_id": CAM,
        "algorithm_type": ALGO,
        "objects": objects if objects is not None else [],
        "detections": detections if detections is not None else [],
        "frame_timestamp": ts,
    }


def test_objects_persisted_verbatim(monkeypatch):
    """事件带 objects 时原样落库（含 attributes/track_id）。"""
    captured = {}

    class _Rule:
        id = 1
        name = "r"
        severity = "WARNING"
        notify_channels = []
        alarm_type = ALGO
        interval_seconds = 0
        conditions = None

    # 直接劫持 AlarmRecordModel 构造，捕获 ai_result
    import app.api.v1.module_video.alarm.model as alarm_model

    real_init = alarm_model.AlarmRecordModel.__init__

    def _init(self, **kw):
        captured.update(kw)
        real_init(self, **kw)

    monkeypatch.setattr(alarm_model.AlarmRecordModel, "__init__", _init)
    # _patch_runtime 复用既有 helper（假 DB + 内存 store + 短路联动/通知）
    from test_temporal_leaves_e2e import _patch_runtime

    _patch_runtime(monkeypatch, _Rule(), TemporalStore(prefer_redis=False))
    obj = {
        "label": "person",
        "confidence": 0.9,
        "bbox": {"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2},
        "track_id": 3,
        "attributes": {"work_uniform": 0.2},
    }
    asyncio.run(
        service.InferenceService.process_detection_callback(
            _ev(objects=[obj], detections=[dict(obj)])
        )
    )
    assert captured["ai_result"]["objects"] == [obj]
    assert captured["ai_result"]["detections"], "detections 兼容字段必须保留"


def test_objects_derived_from_detections_when_missing(monkeypatch):
    """HTTP 兼容路径无 objects 时由 detections 派生。"""
    captured = {}
    import app.api.v1.module_video.alarm.model as alarm_model

    real_init = alarm_model.AlarmRecordModel.__init__

    def _init(self, **kw):
        captured.update(kw)
        real_init(self, **kw)

    monkeypatch.setattr(alarm_model.AlarmRecordModel, "__init__", _init)
    from test_temporal_leaves_e2e import _FakeRule, _patch_runtime

    _patch_runtime(monkeypatch, _FakeRule(None), TemporalStore(prefer_redis=False))
    det = {
        "label": "car",
        "confidence": 0.8,
        "bbox": {"x": 0.4, "y": 0.4, "width": 0.1, "height": 0.1},
    }
    asyncio.run(
        service.InferenceService.process_detection_callback(_ev(objects=[], detections=[det]))
    )
    objs = captured["ai_result"]["objects"]
    assert len(objs) == 1 and objs[0]["label"] == "car"
