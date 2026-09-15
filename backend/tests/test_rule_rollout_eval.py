"""规则灰度接入评估链路测试（SP6-b Task 3）。

端到端驱动 ``process_detection_callback``，仅替换 DB 访问与副作用
（事件联动/通知/边缘事件落库），灰度 gating（``rule_active_now``）与条件求值
（``explain_conditions`` / ``_eval_temporal``）均为**真实实现**，不做 mock。

假会话为本文件专用最小实现：按选中实体区分「相机所属组」与「作用域规则」两类查询，
写会话仅记录新增告警（不落库）。
"""
import asyncio
import zlib

from app.api.v1.module_video.alarm.model import AlarmRuleModel
from app.api.v1.module_video.event.service import EventService
from app.api.v1.module_video.inference import service
from app.api.v1.module_video.inference.temporal import TemporalStore
from app.core import database
from app.utils import notification

CAM = 7
GROUP = 7
ALGO = "AI_DETECTION"

MATCH_PERSON = {"op": "and", "children": [{"subject": "object_present", "label": "person"}]}
DWELL_PERSON = {
    "op": "and",
    "children": [{"subject": "dwell", "label": "person", "min_sec": 5}],
}


class _FakeRule:
    """预置告警规则；schedule_json/rollout 缺省为「无灰度配置」。"""

    severity = "WARNING"
    notify_channels = []
    alarm_type = ALGO
    interval_seconds = 0
    schedule_json = None
    rollout = None

    def __init__(
        self,
        rule_id,
        name,
        conditions,
        *,
        camera_id=None,
        group_id=None,
        rollout=None,
        schedule_json=None,
    ):
        self.id = rule_id
        self.name = name
        self.conditions = conditions
        self.camera_id = camera_id
        self.group_id = group_id
        if rollout is not None:
            self.rollout = rollout
        if schedule_json is not None:
            self.schedule_json = schedule_json


class _Result:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _Session:
    """只读会话：按选中实体区分「相机所属组」与「作用域规则」两类查询。"""

    def __init__(self, rules, cam_group_id):
        self._rules = list(rules)
        self._cam_group_id = cam_group_id

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0].get("entity")
        if entity is AlarmRuleModel:
            return _Result(self._rules)
        # 相机所属组 / 组内相机查询：无组返回空
        return _Result([] if self._cam_group_id is None else [self._cam_group_id])


class _BeginSession:
    """写会话：add 时递增赋 id，flush 不落库；记录新增的告警记录。"""

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
    """模拟 ``async_db_session``：可调用（读）并带 ``begin()``（写）。"""

    def __init__(self, rules, cam_group_id):
        self._rules = rules
        self._cam_group_id = cam_group_id
        self.added = []

    def __call__(self):
        return _Session(self._rules, self._cam_group_id)

    def begin(self):
        return _BeginSession(self.added)


def _patch_runtime(monkeypatch, rules, cam_group_id, store=None):
    """注入假 DB / 内存时序存储，短路事件联动、通知分发与边缘事件落库。"""
    factory = _Factory(rules, cam_group_id)
    monkeypatch.setattr(database, "async_db_session", factory)
    monkeypatch.setattr(service, "temporal_store", store or TemporalStore(prefer_redis=False))

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


def _detection(label="person", track_id=1):
    det = {
        "label": label,
        "confidence": 0.9,
        "bbox": {"x": 0.4, "y": 0.4, "width": 0.2, "height": 0.2},
    }
    if track_id is not None:
        det["track_id"] = track_id
    return det


def _event(detections=None, ts=1000, camera_id=CAM):
    return {
        "task_id": 1,
        "camera_id": camera_id,
        "algorithm_type": ALGO,
        "detections": detections if detections is not None else [_detection()],
        "event_id": "ev-rollout",
        "frame_timestamp": ts,
    }


def _run(event):
    return asyncio.run(service.InferenceService.process_detection_callback(event))


def _bucket(rule_id, camera_id):
    """与 gating 实现一致的分桶：``crc32("{rule_id}:{camera_id}") % 100``。"""
    return zlib.crc32(f"{rule_id}:{camera_id}".encode()) % 100


def _pick_camera(rule_id, percent, hit):
    """查一个分桶命中/未命中的相机 id，保证用例确定性。"""
    for camera_id in range(1, 1000):
        if (_bucket(rule_id, camera_id) < percent) is hit:
            return camera_id
    raise AssertionError("找不到满足分桶条件的相机 id")


# ------------------------------------------------------ 1) percent=0 → 跳过且不告警
def test_percent_zero_rule_skipped_and_no_alarm(monkeypatch):
    """percent=0 的规则被灰度跳过：不告警，且返回体标注 rollout_zero。"""
    rule = _FakeRule(1, "灰度0", MATCH_PERSON, camera_id=CAM, rollout={"percent": 0})
    factory = _patch_runtime(monkeypatch, [rule], None)

    res = _run(_event())

    assert res["alarm_created"] is False
    assert res["rule_skipped_list"] == [{"rule_id": 1, "reason": "rollout_zero"}]
    assert factory.added == []


# ------------------------------------------------------ 2) 逐条独立：跳过者不影响其他规则
def test_skipped_rule_does_not_block_other_rule(monkeypatch):
    """同相机两条规则：percent=0 跳过、percent=100 正常告警，互不影响。"""
    off = _FakeRule(1, "灰度0", MATCH_PERSON, camera_id=CAM, rollout={"percent": 0})
    on = _FakeRule(2, "全量", MATCH_PERSON, camera_id=CAM, rollout={"percent": 100})
    factory = _patch_runtime(monkeypatch, [off, on], None)

    res = _run(_event())

    assert res["alarm_created"] is True
    assert res["rule_matched_list"] == ["全量"]
    assert res["alarm_ids"] == [100]
    assert res["rule_skipped_list"] == [{"rule_id": 1, "reason": "rollout_zero"}]
    assert len(factory.added) == 1


# ------------------------------------------------------ 3) 白名单强制生效（忽略 percent=0）
def test_whitelist_forces_rule_active_despite_zero_percent(monkeypatch):
    """白名单命中的相机在 percent=0 下仍生效（alarm_created=True，无跳过项）。"""
    rule = _FakeRule(
        1,
        "白名单强制",
        MATCH_PERSON,
        camera_id=CAM,
        rollout={"percent": 0, "whitelist": [CAM]},
    )
    factory = _patch_runtime(monkeypatch, [rule], None)

    res = _run(_event())

    assert res["alarm_created"] is True
    assert res["rule_matched_list"] == ["白名单强制"]
    assert "rule_skipped_list" not in res
    assert len(factory.added) == 1


# ------------------------------------------------------ 4) 组规则按相机分桶
def test_group_rule_bucket_gates_per_camera(monkeypatch):
    """组规则 percent=50：命中桶的相机告警，未命中的相机被跳过（rollout_bucket）。"""
    rule_id = 9
    rule = _FakeRule(rule_id, "组规则", MATCH_PERSON, group_id=GROUP, rollout={"percent": 50})
    hit_cam = _pick_camera(rule_id, 50, True)
    miss_cam = _pick_camera(rule_id, 50, False)

    _patch_runtime(monkeypatch, [rule], GROUP)
    hit = _run(_event(camera_id=hit_cam))
    assert hit["alarm_created"] is True
    assert hit["rule_matched_list"] == ["组规则"]

    _patch_runtime(monkeypatch, [rule], GROUP)
    miss = _run(_event(camera_id=miss_cam))
    assert miss["alarm_created"] is False
    assert miss["rule_skipped_list"] == [{"rule_id": rule_id, "reason": "rollout_bucket"}]


# ------------------------------------------------------ 5) 跳过规则不写时序状态
def test_skipped_temporal_rule_writes_no_state(monkeypatch):
    """被灰度跳过的时序规则：不观测、不评估，时序存储中不留任何状态。"""
    store = TemporalStore(prefer_redis=False)
    rule = _FakeRule(1, "时序灰度0", DWELL_PERSON, camera_id=CAM, rollout={"percent": 0})
    _patch_runtime(monkeypatch, [rule], None, store=store)

    first = _run(_event(ts=1000))
    second = _run(_event(ts=1006))

    assert first["alarm_created"] is False and second["alarm_created"] is False
    assert first["rule_skipped_list"] == [{"rule_id": 1, "reason": "rollout_zero"}]
    assert store.query(CAM, ALGO, "person") == {}
