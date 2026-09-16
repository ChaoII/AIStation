"""规则作用域匹配与多规则多条告警测试（假 DB）。

覆盖 SP6-a Task 2：
- 相机组作用域：直绑相机规则 + 绑组规则可同时命中 → 各自建告警；
- 单条命中时兼容旧返回体（alarm_id / alarm_created / rule_matched 保留）；
- 无规则时保留既有兼容路径（建 rule=None 告警，rule_matched 为 None）；
- 有规则但全未命中 → rule_not_matched（不新增 alarm_ids/rule_matched_list）。

假会话仅替换 DB 访问（返回多条规则 + 相机 group_id），评估逻辑
（``explain_conditions`` / ``_eval_temporal``）均为真实实现，不做 mock。
"""
import asyncio

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
MATCH_CAR = {"op": "and", "children": [{"subject": "object_present", "label": "car"}]}
DWELL_PERSON = {
    "op": "and",
    "children": [{"subject": "dwell", "label": "person", "min_sec": 5}],
}


class _FakeRule:
    """预置告警规则；camera_id/group_id 仅用于构造作用域查询的假数据。"""

    severity = "WARNING"
    notify_channels = []
    alarm_type = ALGO
    interval_seconds = 0

    def __init__(self, rule_id, name, conditions, *, camera_id=None, group_id=None):
        self.id = rule_id
        self.name = name
        self.conditions = conditions
        self.camera_id = camera_id
        self.group_id = group_id


class _Result:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _Session:
    """只读会话：按选中实体区分「相机所属组」与「作用域规则」两类查询。"""

    def __init__(self, rules, cam_group_id, statements):
        self._rules = list(rules)
        self._cam_group_id = cam_group_id
        self._statements = statements

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        self._statements.append(stmt)
        entity = stmt.column_descriptions[0].get("entity")
        if entity is AlarmRuleModel:
            return _Result(self._rules)
        # 相机所属组查询：无组返回空结果
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
        self.statements = []
        self.added = []

    def __call__(self):
        return _Session(self._rules, self._cam_group_id, self.statements)

    def begin(self):
        return _BeginSession(self.added)


def _patch_runtime(monkeypatch, rules, cam_group_id):
    """注入假 DB / 内存时序存储，短路事件联动、通知分发与边缘事件落库。"""
    factory = _Factory(rules, cam_group_id)
    monkeypatch.setattr(database, "async_db_session", factory)
    monkeypatch.setattr(service, "temporal_store", TemporalStore(prefer_redis=False))

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


def _detection_at(cx, cy, label="person", track_id=1):
    """构造中心为 (cx, cy) 的检测框（line_cross 用）。"""
    w = h = 0.1
    det = {
        "label": label,
        "confidence": 0.9,
        "bbox": {"x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h},
    }
    if track_id is not None:
        det["track_id"] = track_id
    return det


def _event(detections=None, ts=1000):
    return {
        "task_id": 1,
        "camera_id": CAM,
        "algorithm_type": ALGO,
        "detections": detections if detections is not None else [_detection()],
        "event_id": "ev-scope",
        "frame_timestamp": ts,
    }


def _run(event):
    return asyncio.run(service.InferenceService.process_detection_callback(event))


# ------------------------------------------------- 多规则（直绑 + 组绑）多条告警
def test_direct_and_group_rules_both_match_create_two_alarms(monkeypatch):
    """直绑相机规则 + 绑组规则同时命中 → 两条告警，rule_matched_list 含两者。"""
    direct = _FakeRule(1, "直绑规则", MATCH_PERSON, camera_id=CAM)
    group = _FakeRule(2, "组规则", MATCH_PERSON, group_id=GROUP)
    factory = _patch_runtime(monkeypatch, [direct, group], GROUP)

    res = _run(_event())

    assert res["alarm_created"] is True
    assert len(res["alarm_ids"]) == 2
    assert res["alarm_ids"] == [100, 101]
    assert res["alarm_id"] == 100
    assert res["rule_matched_list"] == ["直绑规则", "组规则"]
    assert res["rule_matched"] == "直绑规则"
    assert len(factory.added) == 2


def test_scope_query_adds_group_condition_when_camera_grouped(monkeypatch):
    """相机有组时，作用域规则查询须同时覆盖直绑与组绑两种条件。"""
    group = _FakeRule(2, "组规则", MATCH_PERSON, group_id=GROUP)
    factory = _patch_runtime(monkeypatch, [group], GROUP)

    _run(_event())

    rule_sql = [s for s in factory.statements if s.column_descriptions[0].get("entity") is AlarmRuleModel]
    assert rule_sql, "必须发起作用域规则查询"
    rendered = str(rule_sql[-1].whereclause)
    assert "video_alarm_rules.camera_id" in rendered
    assert "video_alarm_rules.group_id" in rendered


def test_scope_query_camera_only_when_camera_has_no_group(monkeypatch):
    """相机无组时，作用域规则查询不得带上组条件。"""
    direct = _FakeRule(1, "直绑规则", MATCH_PERSON, camera_id=CAM)
    factory = _patch_runtime(monkeypatch, [direct], None)

    _run(_event())

    rule_sql = [s for s in factory.statements if s.column_descriptions[0].get("entity") is AlarmRuleModel]
    assert rule_sql and "video_alarm_rules.group_id" not in str(rule_sql[-1].whereclause)


def test_group_rule_matches_single_alarm(monkeypatch):
    """仅绑组规则时：相机属于该组 → 单条命中，保留旧字段。"""
    group = _FakeRule(2, "组规则", MATCH_PERSON, group_id=GROUP)
    _patch_runtime(monkeypatch, [group], GROUP)

    res = _run(_event())

    assert res["alarm_created"] is True
    assert res["alarm_id"] == 100
    assert res["rule_matched"] == "组规则"
    assert res["alarm_ids"] == [100]
    assert res["rule_matched_list"] == ["组规则"]
    assert res["event_id"] == "ev-scope"


# ------------------------------------------------------ 单条命中：旧返回体兼容
def test_single_rule_match_preserves_legacy_shape(monkeypatch):
    """单条直绑规则命中：alarm_created/alarm_id/rule_matched 与旧行为一致。"""
    direct = _FakeRule(1, "直绑规则", MATCH_PERSON, camera_id=CAM)
    _patch_runtime(monkeypatch, [direct], None)

    res = _run(_event())

    assert res == {
        "alarm_id": 100,
        "alarm_created": True,
        "rule_matched": "直绑规则",
        "alarm_ids": [100],
        "rule_matched_list": ["直绑规则"],
        "event_id": "ev-scope",
    }


def test_single_rule_unmatched_keeps_legacy_shape(monkeypatch):
    """单条规则未命中：返回体与旧行为完全一致（不新增聚合字段）。"""
    direct = _FakeRule(1, "直绑规则", MATCH_CAR, camera_id=CAM)
    _patch_runtime(monkeypatch, [direct], None)

    res = _run(_event())

    assert res == {
        "alarm_created": False,
        "reason": "rule_not_matched",
        "event_id": "ev-scope",
    }


def test_no_rules_with_detections_keeps_legacy_alarm(monkeypatch):
    """无任何规则且有检测：保留既有兼容路径（建 rule=None 告警）。"""
    factory = _patch_runtime(monkeypatch, [], None)

    res = _run(_event())

    assert res["alarm_created"] is True
    assert res["rule_matched"] is None
    assert res["alarm_id"] == 100
    assert res["alarm_ids"] == [100]
    assert res["rule_matched_list"] == []
    assert len(factory.added) == 1


def test_no_detections_without_temporal_rule_early_returns(monkeypatch):
    """空检测且无时序规则：no_detections 早退（无新增聚合字段）。"""
    direct = _FakeRule(1, "直绑规则", MATCH_PERSON, camera_id=CAM)
    _patch_runtime(monkeypatch, [direct], None)

    res = _run(_event(detections=[]))

    assert res == {"alarm_created": False, "reason": "no_detections"}


# ------------------------------------------------------ 时序观测：每条规则各观测一次
def test_temporal_observe_runs_per_temporal_rule(monkeypatch):
    """含两条时序规则的事件：``_observe_temporal_event`` 每条规则各执行一次。"""
    r1 = _FakeRule(1, "时序规则A", DWELL_PERSON, camera_id=CAM)
    r2 = _FakeRule(2, "时序规则B", DWELL_PERSON, group_id=GROUP)
    _patch_runtime(monkeypatch, [r1, r2], GROUP)

    calls = []

    def _spy(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(service, "_observe_temporal_event", _spy)

    _run(_event())

    assert len(calls) == 2


# ------------------------------------- 多时序规则共享观测：两条 line_cross 均命中
LINE_CROSS_PERSON = {
    "op": "and",
    "children": [{
        "subject": "line_cross",
        "label": "person",
        "line": [[0.5, 0.0], [0.5, 1.0]],
        "dir": "A2B",
    }],
}


def test_two_line_cross_rules_both_fire(monkeypatch):
    """同相机同 alarm_type 的两条 line_cross 规则必须都命中。

    回归：重复观测会覆盖 prev 位置，导致第二条时序规则的 line_cross 永不命中。
    """
    r1 = _FakeRule(1, "越线规则A", LINE_CROSS_PERSON, camera_id=CAM)
    r2 = _FakeRule(2, "越线规则B", LINE_CROSS_PERSON, camera_id=CAM)
    _patch_runtime(monkeypatch, [r1, r2], None)

    # 第 1 帧：位于绊线左侧，无越线 → 不告警
    first = _run(_event(detections=[_detection_at(0.2, 0.5)], ts=1000))
    assert first["alarm_created"] is False
    assert first["reason"] == "rule_not_matched"

    # 第 2 帧：移动到绊线右侧 → 两条规则都应命中
    second = _run(_event(detections=[_detection_at(0.8, 0.5)], ts=1001))
    assert second["alarm_created"] is True
    assert second["rule_matched_list"] == ["越线规则A", "越线规则B"]
    assert len(second["alarm_ids"]) == 2


# ------------------------------------------------- 单规则异常隔离（审计 §6-4）

def test_rule_exception_does_not_abort_other_rules(monkeypatch):
    """某条规则评估抛错：不得中断后续规则，失败规则须在返回体中可观测。"""
    r1 = _FakeRule(1, "坏规则", MATCH_PERSON, camera_id=CAM)
    r2 = _FakeRule(2, "好规则", MATCH_PERSON, camera_id=CAM)
    r3 = _FakeRule(3, "又坏", MATCH_PERSON, camera_id=CAM)
    _patch_runtime(monkeypatch, [r1, r2, r3], None)

    calls: list = []

    async def _eval(rule, *args, **kwargs):
        calls.append(getattr(rule, "id", None))
        if getattr(rule, "id", None) in (1, 3):
            raise RuntimeError("boom")
        return {"alarm_id": 100 + rule.id, "rule_id": rule.id, "rule_name": rule.name, "hit_leaves": []}

    monkeypatch.setattr(service, "_evaluate_rule", _eval)

    res = _run(_event())

    assert calls == [1, 2, 3]  # 后续规则未被中断
    assert res["alarm_created"] is True
    assert res["alarm_ids"] == [102]
    assert [e["rule_id"] for e in res["rule_error_list"]] == [1, 3]


def test_all_rules_failing_is_observable_and_not_matched(monkeypatch):
    """全部规则失败：返回未命中 + 失败清单，事件不得以 matched=True 掩盖。"""
    r1 = _FakeRule(1, "坏A", MATCH_PERSON, camera_id=CAM)
    r2 = _FakeRule(2, "坏B", MATCH_PERSON, camera_id=CAM)
    _patch_runtime(monkeypatch, [r1, r2], None)

    async def _eval(rule, *args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_evaluate_rule", _eval)

    res = _run(_event())

    assert res["alarm_created"] is False
    assert res["reason"] == "rule_not_matched"
    assert [e["rule_id"] for e in res["rule_error_list"]] == [1, 2]
