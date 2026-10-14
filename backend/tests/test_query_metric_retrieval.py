"""指标检索优化：命中指标时优先其对象 + 提示词注入。"""
from app.plugin.module_ai.query.service import (
    _metric_prompt_hint,
    _prioritize_metric_object,
)


def test_prioritize_metric_object_moves_first():
    allowed = {"a": {}, "coal_batch": {}, "c": {}}
    out = _prioritize_metric_object(allowed, {"object_code": "coal_batch"})
    assert list(out.keys())[0] == "coal_batch"
    assert set(out.keys()) == {"a", "coal_batch", "c"}


def test_prioritize_no_metric_keeps_order():
    allowed = {"a": {}, "b": {}}
    assert _prioritize_metric_object(allowed, None) == allowed


def test_prioritize_unknown_object_keeps_order():
    allowed = {"a": {}, "b": {}}
    assert _prioritize_metric_object(allowed, {"object_code": "nope"}) == allowed


def test_metric_prompt_hint_contains_key():
    h = _metric_prompt_hint({"key": "coal_batch_count", "name": "入厂批次数",
                             "object_code": "coal_batch"})
    assert "coal_batch_count" in h and "metric" in h


def test_metric_prompt_hint_empty_without_metric():
    assert _metric_prompt_hint(None) == ""
