"""属性规则判定测试。"""
import asyncio

from app.api.v1.module_video.inference.service import _match_conditions


def test_attribute_leaf_match():
    # 属性为 {名: 分数}；分数=具有该属性的概率，违规=分数低于阈值
    cond = {"op": "and", "children": [{"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.5}]}
    dets = [{"label": "person", "attributes": {"work_uniform": 0.2}}]
    assert _match_conditions(cond, dets) is True


def test_attribute_leaf_no_match():
    cond = {"op": "and", "children": [{"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.1}]}
    dets = [{"label": "person", "attributes": {"work_uniform": 0.2}}]
    assert _match_conditions(cond, dets) is False


def test_empty_conditions_match_all():
    assert _match_conditions(None, [{"label": "person"}]) is True
    assert _match_conditions({}, [{"label": "person"}]) is True


def test_or_and_not():
    dets = [{"label": "person", "attributes": {"work_uniform": 0.2}}]
    assert _match_conditions({"op": "or", "children": [
        {"subject": "attribute", "field": "safety_helmet", "op": "lt", "value": 0.5},
        {"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.5},
    ]}, dets) is True
    assert _match_conditions({"op": "not", "children": [
        {"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.5},
    ]}, dets) is False


def test_attribute_null_value_does_not_raise():
    """JSON null 的 value 不得抛异常，按不命中处理。"""
    cond = {"op": "and", "children": [
        {"subject": "attribute", "field": "work_uniform", "op": "lt", "value": None},
    ]}
    dets = [{"label": "person", "attributes": {"work_uniform": 0.2}}]
    assert _match_conditions(cond, dets) is False


def test_attribute_non_numeric_value_does_not_raise():
    """属性分数为非数值字符串时不得抛异常，按不命中处理。"""
    cond = {"op": "and", "children": [
        {"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.5},
    ]}
    dets = [{"label": "person", "attributes": {"work_uniform": "高"}}]
    assert _match_conditions(cond, dets) is False


class _FakeRule:
    id = 1
    name = "属性规则"
    severity = "WARNING"
    notify_channels = []
    alarm_type = "PED_ATTR"
    # 阈值 0.1，事件分数 0.9 → lt 不成立 → 规则不命中
    conditions = {"op": "and", "children": [
        {"subject": "attribute", "field": "work_uniform", "op": "lt", "value": 0.1},
    ]}


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, stmt):
        return _FakeResult([_FakeRule()])


def test_callback_rule_not_matched(monkeypatch):
    """规则条件不命中时，回调须返回 rule_not_matched 且不创建告警。

    通过 monkeypatch 替换 async_db_session（本次不查真实库），验证纯逻辑分支。
    """
    from app.api.v1.module_video.inference import service
    from app.core import database

    monkeypatch.setattr(database, "async_db_session", lambda: _FakeSession())

    event = {
        "task_id": 1,
        "camera_id": 2,
        "algorithm_type": "PED_ATTR",
        "detections": [{"label": "person", "attributes": {"work_uniform": 0.9}}],
    }
    result = asyncio.run(service.InferenceService.process_detection_callback(event))
    assert result == {"alarm_created": False, "reason": "rule_not_matched"}
