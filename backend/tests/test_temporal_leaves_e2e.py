"""时序叶子云端端到端测试（SP4-b）。

端到端链路（不依赖真实 DB / Redis / 网络）：
    多次带 track_id 的检测回调 → ``process_detection_callback``
    → 写入时序观测状态（inference/temporal.py）
    → 评估规则条件树（dwell / count_window 叶子）→ 创建告警。

确定性保证：
- 时间由回调 ``frame_timestamp`` 注入（事件 ts），禁止依赖 wall clock；
- 状态存储替换为内存后端（``TemporalStore(prefer_redis=False)``）；
- 假 DB 会话返回预置规则；事件联动与通知分发被短路，避免副作用。
"""
import asyncio

from app.api.v1.module_video.event.service import EventService
from app.api.v1.module_video.inference import service
from app.api.v1.module_video.inference.temporal import TemporalStore
from app.core import database
from app.utils import notification

CAM = 7
ALGO = "AI_DETECTION"


class _FakeRule:
    """预置告警规则：conditions 由用例注入，其余字段满足回调读取需求。"""

    id = 1
    name = "时序规则"
    severity = "WARNING"
    notify_channels = []
    alarm_type = ALGO
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
    """只读会话：查询规则时返回预置规则。"""

    def __init__(self, rule):
        self._rule = rule

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        return _Result([self._rule] if self._rule else [])


class _BeginSession:
    """写会话：add 时直接赋 id，flush 不落库。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, obj):
        obj.id = 99

    async def flush(self):
        pass


class _Factory:
    """模拟 ``async_db_session``：可调用（查询）并带 ``begin()``（写入）。"""

    def __init__(self, rule):
        self._rule = rule

    def __call__(self):
        return _Session(self._rule)

    def begin(self):
        return _BeginSession()


def _patch_runtime(monkeypatch, rule, store):
    """注入假 DB / 内存时序存储，并短路事件联动与通知分发。"""
    monkeypatch.setattr(database, "async_db_session", _Factory(rule))
    monkeypatch.setattr(service, "temporal_store", store)

    async def _noop_linkage(*_args, **_kwargs):
        return []

    async def _noop_notify(*_args, **_kwargs):
        return None

    monkeypatch.setattr(EventService, "execute_linkage_actions", _noop_linkage)
    monkeypatch.setattr(notification, "dispatch_notification", _noop_notify)


def _event(ts, track_id=1, label="person"):
    """构造一次云端检测回调事件；track_id=None 表示事件不携带轨迹。"""
    det = {
        "label": label,
        "confidence": 0.9,
        "bbox": {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2},
    }
    if track_id is not None:
        det["track_id"] = track_id
    return {
        "task_id": 1,
        "camera_id": CAM,
        "algorithm_type": ALGO,
        "detections": [det],
        "frame_timestamp": ts,
    }


def _run(events):
    """顺序驱动回调，返回每次结果列表。"""
    return [
        asyncio.run(service.InferenceService.process_detection_callback(ev))
        for ev in events
    ]


# ------------------------------------------------------------------ dwell
def test_dwell_alarm_when_duration_reached(monkeypatch):
    """同一 track_id 跨事件累计停留 >= min_sec 时产出告警。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRule({
        "op": "and",
        "children": [{"subject": "dwell", "label": "person", "min_sec": 5}],
    })
    _patch_runtime(monkeypatch, rule, store)

    # 首帧：停留 0s，未达阈值 → 不告警
    first = asyncio.run(service.InferenceService.process_detection_callback(_event(1000)))
    assert first == {"alarm_created": False, "reason": "rule_not_matched"}
    # 同一轨迹持续到第 6 秒：达到 min_sec=5 → 告警
    second = asyncio.run(service.InferenceService.process_detection_callback(_event(1006)))
    assert second["alarm_created"] is True
    assert second["rule_matched"] == rule.name


def test_dwell_no_alarm_below_duration(monkeypatch):
    """轨迹存在但未达时长阈值 → 全程不告警。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRule({
        "op": "and",
        "children": [{"subject": "dwell", "label": "person", "min_sec": 10}],
    })
    _patch_runtime(monkeypatch, rule, store)

    results = _run([_event(1000), _event(1005), _event(1009)])
    assert all(r["alarm_created"] is False for r in results)


def test_dwell_different_tracks_do_not_accumulate(monkeypatch):
    """不同 track_id 各自独立计时，不叠加同一停留时长。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRule({
        "op": "and",
        "children": [{"subject": "dwell", "label": "person", "min_sec": 5}],
    })
    _patch_runtime(monkeypatch, rule, store)

    results = _run([_event(1000, track_id=1), _event(1010, track_id=2)])
    assert all(r["alarm_created"] is False for r in results)


def test_dwell_without_track_id_never_accumulates(monkeypatch):
    """无 track_id 时每次事件独立成键，无法形成跨事件轨迹 → 不告警。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRule({
        "op": "and",
        "children": [{"subject": "dwell", "label": "person", "min_sec": 5}],
    })
    _patch_runtime(monkeypatch, rule, store)

    results = _run([_event(1000, track_id=None), _event(1010, track_id=None)])
    assert all(r["alarm_created"] is False for r in results)


# ------------------------------------------------------------ count_window
def test_count_window_alarm_when_gather_threshold_reached(monkeypatch):
    """滑窗内去重轨迹数达到阈值时产出告警（GATHER 场景）。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRule({
        "op": "and",
        "children": [{
            "subject": "count_window",
            "label": "person",
            "window_sec": 5,
            "op": ">=",
            "value": 3,
        }],
    })
    _patch_runtime(monkeypatch, rule, store)

    results = _run([
        _event(1000, track_id=1),
        _event(1001, track_id=2),
        _event(1002, track_id=3),
    ])
    assert [r["alarm_created"] for r in results] == [False, False, True]


# ----------------------------------------------------------------- absence
class _FakeRuleThrottled(_FakeRule):
    """带节流间隔的规则（absence 防抖依赖 interval_seconds）。"""

    interval_seconds = 30


def _heartbeat(ts):
    """构造一次空检测心跳事件（Agent 静默期上报）。"""
    return {
        "task_id": 1,
        "camera_id": CAM,
        "algorithm_type": ALGO,
        "detections": [],
        "heartbeat": True,
        "frame_timestamp": ts,
    }


def test_absence_alarm_on_heartbeat_after_gap(monkeypatch):
    """先出现目标，静默超过 gap_sec 后由心跳事件触发 absence 告警。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRule({
        "op": "and",
        "children": [{"subject": "absence", "label": "person", "gap_sec": 30}],
    })
    _patch_runtime(monkeypatch, rule, store)

    first = asyncio.run(service.InferenceService.process_detection_callback(_event(1000)))
    assert first == {"alarm_created": False, "reason": "rule_not_matched"}

    early = asyncio.run(service.InferenceService.process_detection_callback(_heartbeat(1010)))
    assert early == {"alarm_created": False, "reason": "rule_not_matched"}

    after = asyncio.run(service.InferenceService.process_detection_callback(_heartbeat(1040)))
    assert after["alarm_created"] is True
    assert after["rule_matched"] == rule.name


def test_absence_heartbeat_throttled_within_interval(monkeypatch):
    """同一节流窗口内，心跳触发的 absence 告警不重复。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRuleThrottled({
        "op": "and",
        "children": [{"subject": "absence", "label": "person", "gap_sec": 30}],
    })
    _patch_runtime(monkeypatch, rule, store)

    asyncio.run(service.InferenceService.process_detection_callback(_event(1000)))
    first = asyncio.run(service.InferenceService.process_detection_callback(_heartbeat(1040)))
    assert first["alarm_created"] is True

    second = asyncio.run(service.InferenceService.process_detection_callback(_heartbeat(1045)))
    assert second == {"alarm_created": False, "reason": "rule_not_matched"}


def test_absence_rearms_after_detection_resumes(monkeypatch):
    """检测恢复后重新计时，再次静默超时可再次告警。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRuleThrottled({
        "op": "and",
        "children": [{"subject": "absence", "label": "person", "gap_sec": 30}],
    })
    _patch_runtime(monkeypatch, rule, store)

    asyncio.run(service.InferenceService.process_detection_callback(_event(1000)))
    assert asyncio.run(
        service.InferenceService.process_detection_callback(_heartbeat(1040))
    )["alarm_created"] is True

    # 目标重新出现（推进 last_seen，解除 gap 条件）
    asyncio.run(service.InferenceService.process_detection_callback(_event(1050)))
    assert asyncio.run(
        service.InferenceService.process_detection_callback(_heartbeat(1090))
    )["alarm_created"] is True


def test_heartbeat_without_temporal_rule_is_noop(monkeypatch):
    """规则非时序时，空检测心跳维持既有 no_detections 语义。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRule({
        "op": "and",
        "children": [{"subject": "object_present", "label": "person"}],
    })
    _patch_runtime(monkeypatch, rule, store)

    res = asyncio.run(service.InferenceService.process_detection_callback(_heartbeat(1000)))
    assert res == {"alarm_created": False, "reason": "no_detections"}
