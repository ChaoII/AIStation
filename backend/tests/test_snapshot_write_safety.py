"""检测回调内联快照写盘路径安全测试（目录穿越拒绝）。

不依赖真实 DB / Redis：假会话返回「无规则」，事件联动/通知/落库均短路。
核心断言：越界 ``snapshot_path`` 不得写到 DETECTIONS_DIR 之外，告警快照引用为空。
"""
import asyncio
import base64

from app.api.v1.module_video.event.service import EventService
from app.api.v1.module_video.inference import service
from app.config.setting import settings
from app.core import database
from app.utils import notification


class _Result:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _Session:
    """只读会话：无规则 / 无相机组。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        return _Result([])


class _BeginSession:
    """写会话：add 时赋 id，记录新增告警记录。"""

    def __init__(self, added):
        self._added = added

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, obj):
        obj.id = 100 + len(self._added)
        self._added.append(obj)

    async def flush(self):
        pass


class _Factory:
    def __init__(self):
        self.added = []

    def __call__(self):
        return _Session()

    def begin(self):
        return _BeginSession(self.added)


def _patch_runtime(monkeypatch):
    factory = _Factory()
    monkeypatch.setattr(database, "async_db_session", factory)

    async def _noop_linkage(*_args, **_kwargs):
        return []

    async def _noop_notify(*_args, **_kwargs):
        return None

    async def _noop_persist(*_args, **_kwargs):
        return 1

    monkeypatch.setattr(EventService, "execute_linkage_actions", _noop_linkage)
    monkeypatch.setattr(notification, "dispatch_notification", _noop_notify)
    monkeypatch.setattr(service, "_persist_edge_event", _noop_persist)
    return factory


def _event(snapshot_path):
    return {
        "task_id": 1,
        "camera_id": 7,
        "algorithm_type": "AI_DETECTION",
        "detections": [
            {
                "label": "person",
                "confidence": 0.9,
                "bbox": {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2},
            }
        ],
        "snapshot_data": base64.b64encode(b"img").decode(),
        "snapshot_path": snapshot_path,
        "frame_timestamp": 1000,
    }


def test_inline_snapshot_relative_traversal_rejected(monkeypatch, tmp_path):
    """``../`` 越界相对路径：拒绝写盘，不落快照引用。"""
    detectors_dir = tmp_path / "detections"
    monkeypatch.setattr(settings, "DETECTIONS_DIR", str(detectors_dir))
    factory = _patch_runtime(monkeypatch)

    res = asyncio.run(
        service.InferenceService.process_detection_callback(_event("../evil.jpg"))
    )

    assert res["alarm_created"] is True
    assert not (tmp_path / "evil.jpg").exists()
    assert factory.added[0].snapshot_path is None


def test_inline_snapshot_absolute_outside_rejected(monkeypatch, tmp_path):
    """越界绝对路径：拒绝写盘。"""
    detectors_dir = tmp_path / "detections"
    monkeypatch.setattr(settings, "DETECTIONS_DIR", str(detectors_dir))
    factory = _patch_runtime(monkeypatch)

    asyncio.run(
        service.InferenceService.process_detection_callback(
            _event(str(tmp_path / "outside.jpg"))
        )
    )

    assert not (tmp_path / "outside.jpg").exists()
    assert factory.added[0].snapshot_path is None


def test_inline_snapshot_nested_relative_written_inside(monkeypatch, tmp_path):
    """合法子目录相对路径：正常写入 DETECTIONS_DIR 内并落库。"""
    detectors_dir = tmp_path / "detections"
    monkeypatch.setattr(settings, "DETECTIONS_DIR", str(detectors_dir))
    factory = _patch_runtime(monkeypatch)

    asyncio.run(
        service.InferenceService.process_detection_callback(_event("2026-09-12/ok.jpg"))
    )

    written = detectors_dir / "2026-09-12" / "ok.jpg"
    assert written.read_bytes() == b"img"
    assert factory.added[0].snapshot_path == str(written)
