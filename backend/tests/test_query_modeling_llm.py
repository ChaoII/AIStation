"""S3-T1：建模 LLM 容错解析（纯逻辑）。"""
from app.plugin.module_ai.query.modeling import parse_json_objects


def test_parse_plain_json_array():
    assert parse_json_objects('[{"a":1},{"a":2}]') == [{"a": 1}, {"a": 2}]


def test_parse_fenced_and_noisy():
    t = '说明如下：\n```json\n{"metrics":[{"key":"k1"}]}\n```\n完毕'
    out = parse_json_objects(t)
    assert {"key": "k1"} in out


def test_parse_truncated_salvages_complete_objects():
    t = '[{"key":"k1","name":"甲"},{"key":"k2","name":"乙"},{"key":"k3","na'
    out = parse_json_objects(t)
    assert {"key": "k1", "name": "甲"} in out
    assert {"key": "k2", "name": "乙"} in out


def test_parse_garbage_returns_empty():
    assert parse_json_objects("这是一段没有 JSON 的话") == []
