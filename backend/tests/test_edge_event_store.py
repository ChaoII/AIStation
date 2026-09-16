"""边缘事件落库测试：筛选 / 幂等 / 命中叶子。

- 落库断言针对真实测试库：同步会话读回（与异步引擎同一 SQLite 文件），
  避免 mock 掉被测的持久化逻辑。
- 回调控制流用既有假 DB/monkeypatch 手法（参考 test_temporal_leaves_e2e.py），
  锁定「空检测早退不落库」「未命中/命中均落库」两条路径。
"""
import asyncio
import json
from uuid import uuid4

import pytest

from app.api.v1.module_video.inference import service
from app.core import database

# 归一化后的边缘事件样例（v2：含 objects + 兼容 detections）
EV = {
    "event_id": "ev-1",
    "edge_code": "edge-01",
    "camera_id": 1,
    "task_id": 2,
    "algorithm_type": "DET_ZONE",
    "ts": "2026-09-15T00:00:00.000Z",
    "objects": [
        {
            "label": "person",
            "confidence": 0.9,
            "bbox": {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2},
        }
    ],
    "detections": [
        {
            "label": "person",
            "confidence": 0.9,
            "bbox": {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2},
        }
    ],
    "latency_ms": 12.3,
}


@pytest.fixture(autouse=True)
def _schema(test_client):
    """确保应用生命周期已启动（建表）；落库断言读真实测试库。"""
    return test_client


@pytest.fixture
def db_session():
    """同步只读会话，与异步落库共用同一 SQLite 测试库。"""
    session = database.db_session()
    try:
        yield session
    finally:
        session.close()


def test_empty_event_is_not_persisted(db_session):
    """objects 与 detections 皆空（静默期心跳）→ 不落库。"""
    from app.api.v1.module_video.edge.store import count_events

    before = count_events(db_session)
    result = asyncio.run(
        service._persist_edge_event(
            {**EV, "event_id": f"ev-empty-{uuid4().hex}", "objects": [], "detections": []},
            matched=False,
            rule_id=None,
            matched_leaves=[],
        )
    )
    assert result is None
    assert count_events(db_session) == before


def test_same_event_id_is_idempotent(db_session):
    """同一 event_id 重复插入：首次返回 id，重复返回 None，且不报错。"""
    # 每次运行用全新 event_id，避免持久化测试库（pytest_aistation.db）的历史行干扰
    event = {**EV, "event_id": f"ev-idem-{uuid4().hex}"}

    async def _run():
        first = await service._persist_edge_event(
            event,
            matched=True,
            rule_id=1,
            matched_leaves=[{"path": "and/0", "subject": "object_present"}],
        )
        second = await service._persist_edge_event(
            event, matched=True, rule_id=1, matched_leaves=[]
        )
        return first, second

    first, second = asyncio.run(_run())
    assert first is not None
    assert second is None


def test_snapshot_data_not_persisted(db_session):
    """内联 base64（snapshot_data）不入库，仅保留 snapshot_ref。"""
    snapshot_event_id = f"ev-snap-{uuid4().hex}"
    asyncio.run(
        service._persist_edge_event(
            {
                **EV,
                "event_id": snapshot_event_id,
                "snapshot_data": "AAAA",
                "snapshot_path": "s3://bucket/x.jpg",
            },
            matched=False,
            rule_id=None,
            matched_leaves=[],
        )
    )
    from app.api.v1.module_video.edge.store import get_event_by_event_id

    row = get_event_by_event_id(db_session, snapshot_event_id)
    assert row is not None
    dumped = json.dumps(row.objects, ensure_ascii=False) + json.dumps(
        row.detections, ensure_ascii=False
    )
    assert "snapshot_data" not in dumped
    assert "AAAA" not in dumped
    assert row.snapshot_ref == "s3://bucket/x.jpg"


# --------------------------------------------------------- 回调控制流（假 DB）
class _FakeRule:
    """预置告警规则；conditions 由用例注入。"""

    id = 1
    name = "假规则"
    severity = "WARNING"
    notify_channels = []
    alarm_type = "DET_ZONE"
    interval_seconds = 0

    def __init__(self, conditions):
        self.conditions = conditions


class _Result:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _Session:
    def __init__(self, rule):
        self._rule = rule

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        return _Result([self._rule] if self._rule else [])


class _BeginSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, obj):
        obj.id = 99

    async def flush(self):
        pass


class _Factory:
    def __init__(self, rule):
        self._rule = rule

    def __call__(self):
        return _Session(self._rule)

    def begin(self):
        return _BeginSession()


def _patch_runtime(monkeypatch, rule):
    """注入假 DB 并短路事件联动 / 通知分发，避免副作用。"""
    monkeypatch.setattr(database, "async_db_session", _Factory(rule))

    async def _noop_linkage(*_args, **_kwargs):
        return []

    async def _noop_notify(*_args, **_kwargs):
        return None

    from app.api.v1.module_video.event.service import EventService
    from app.utils import notification

    monkeypatch.setattr(EventService, "execute_linkage_actions", _noop_linkage)
    monkeypatch.setattr(notification, "dispatch_notification", _noop_notify)


def _record_persist(monkeypatch):
    """替换落库调用并记录入参，验证控制流。"""
    calls = []

    async def _fake(event, *, matched, rule_id, matched_leaves):
        calls.append({"matched": matched, "rule_id": rule_id, "leaves": matched_leaves})
        return 1

    monkeypatch.setattr(service, "_persist_edge_event", _fake)
    return calls


def _person_detection():
    return {
        "label": "person",
        "confidence": 0.9,
        "bbox": {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2},
    }


def test_callback_no_detections_skips_persist(monkeypatch):
    """空检测且非时序规则：no_detections 早退，落库不被调用（即便带 absence 也如此）。"""
    rule = _FakeRule(
        {"op": "and", "children": [{"subject": "object_present", "label": "person"}]}
    )
    _patch_runtime(monkeypatch, rule)
    calls = _record_persist(monkeypatch)

    result = asyncio.run(
        service.InferenceService.process_detection_callback(
            {
                "task_id": 1,
                "camera_id": 3,
                "algorithm_type": "DET_ZONE",
                "detections": [],
                "event_id": "ev-hb",
                "frame_timestamp": 1000,
            }
        )
    )
    assert result == {"alarm_created": False, "reason": "no_detections"}
    assert calls == []


def test_callback_absence_heartbeat_not_persisted(monkeypatch):
    """时序规则：空检测心跳触发 absence 告警，但心跳本身不落库（真实库验证）。

    走真实回调 + 真实落库，仅替换规则查询之外的副作用（联动/通知）与内存时序状态。
    """
    from app.api.v1.module_video.alarm.model import AlarmRuleModel
    from app.api.v1.module_video.edge.store import get_event_by_event_id
    from app.api.v1.module_video.inference.temporal import TemporalStore

    camera_id = 880001
    algo = "SP5B_ABSENCE"
    seen_event_id = f"ev-abs-seen-{uuid4().hex}"
    absent_event_id = f"ev-abs-absent-{uuid4().hex}"

    async def _seed_rule():
        async with database.async_db_session.begin() as s:
            s.add(
                AlarmRuleModel(
                    name="sp5b-absence-rule",
                    camera_id=camera_id,
                    alarm_type=algo,
                    severity="WARNING",
                    interval_seconds=0,
                    status=True,
                    is_deleted=False,
                    conditions={
                        "op": "and",
                        "children": [
                            {"subject": "absence", "label": "person", "gap_sec": 30}
                        ],
                    },
                )
            )

    asyncio.run(_seed_rule())
    monkeypatch.setattr(service, "temporal_store", TemporalStore(prefer_redis=False))

    async def _noop_linkage(*_args, **_kwargs):
        return []

    async def _noop_notify(*_args, **_kwargs):
        return None

    from app.api.v1.module_video.event.service import EventService
    from app.utils import notification

    monkeypatch.setattr(EventService, "execute_linkage_actions", _noop_linkage)
    monkeypatch.setattr(notification, "dispatch_notification", _noop_notify)

    def _persisted(event_id: str) -> bool:
        """按 event_id 精确查库：隔离断言，不受其他写入者（后台任务/并发套件）的全局计数干扰。"""
        session = database.db_session()
        try:
            return get_event_by_event_id(session, event_id) is not None
        finally:
            session.close()

    # 首帧有检测：记 last_seen，但 absence 未达 gap → 未命中（有检测仍落库）
    asyncio.run(
        service.InferenceService.process_detection_callback(
            {
                "task_id": 1,
                "camera_id": camera_id,
                "algorithm_type": algo,
                "detections": [_person_detection()],
                "event_id": seen_event_id,
                "frame_timestamp": 1000,
            }
        )
    )
    # 静默超 gap 的空检测心跳：触发 absence 告警，但事件本身不得落库
    result = asyncio.run(
        service.InferenceService.process_detection_callback(
            {
                "task_id": 1,
                "camera_id": camera_id,
                "algorithm_type": algo,
                "detections": [],
                "heartbeat": True,
                "event_id": absent_event_id,
                "frame_timestamp": 1040,
            }
        )
    )
    assert result.get("alarm_created") is True
    # 只落「有检测」的那一条；absence 心跳（空检测）被落库层过滤
    assert _persisted(seen_event_id) is True
    assert _persisted(absent_event_id) is False


def test_callback_unmatched_with_detections_persists(monkeypatch):
    """有检测但未命中规则：matched=False、matched_leaves=[]，且返回体新增 event_id。"""
    rule = _FakeRule(
        {"op": "and", "children": [{"subject": "object_present", "label": "car"}]}
    )
    _patch_runtime(monkeypatch, rule)
    calls = _record_persist(monkeypatch)

    result = asyncio.run(
        service.InferenceService.process_detection_callback(
            {
                "task_id": 1,
                "camera_id": 3,
                "algorithm_type": "DET_ZONE",
                "detections": [_person_detection()],
                "event_id": "ev-miss",
                "frame_timestamp": 1000,
            }
        )
    )
    assert result == {
        "alarm_created": False,
        "reason": "rule_not_matched",
        "event_id": "ev-miss",
    }
    assert calls == [{"matched": False, "rule_id": rule.id, "leaves": []}]


def test_callback_matched_persists_with_hit_leaves(monkeypatch):
    """命中规则：落库带命中叶子，返回体新增 event_id。"""
    rule = _FakeRule(
        {"op": "and", "children": [{"subject": "object_present", "label": "person"}]}
    )
    _patch_runtime(monkeypatch, rule)
    calls = _record_persist(monkeypatch)

    result = asyncio.run(
        service.InferenceService.process_detection_callback(
            {
                "task_id": 1,
                "camera_id": 3,
                "algorithm_type": "DET_ZONE",
                "detections": [_person_detection()],
                "event_id": "ev-hit",
                "frame_timestamp": 1000,
            }
        )
    )
    assert result.get("alarm_created") is True
    assert result.get("event_id") == "ev-hit"
    assert calls and calls[0]["matched"] is True
    assert calls[0]["leaves"][0]["subject"] == "object_present"
