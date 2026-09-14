"""属性规则判定测试。"""
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
