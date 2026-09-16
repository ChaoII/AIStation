"""告警出参 snapshot_url 计算字段测试。"""
from app.api.v1.module_video.alarm.schema import AlarmRecordOutSchema
from app.api.v1.module_video.inference import snapshot as snap


def test_snapshot_url_computed(monkeypatch, tmp_path):
    monkeypatch.setattr(snap.settings, "DETECTIONS_DIR", str(tmp_path))
    f = tmp_path / "2026-09-12" / "a.jpg"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"x")
    schema = AlarmRecordOutSchema(
        camera_id=1, alarm_type="INTRUSION", snapshot_path=str(f)
    )
    dumped = schema.model_dump()
    assert dumped["snapshot_url"] == "/api/v1/video/detections/2026-09-12/a.jpg"


def test_snapshot_url_none_when_no_path():
    schema = AlarmRecordOutSchema(camera_id=1, alarm_type="INTRUSION", snapshot_path=None)
    assert schema.model_dump()["snapshot_url"] is None
