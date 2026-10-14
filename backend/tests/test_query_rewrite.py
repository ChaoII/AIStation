"""P2 多轮查询重写（G7）：`query/rewrite.py` 纯逻辑测试（可 `PYTEST_NO_APP=1` 快测）。"""
from __future__ import annotations

from app.plugin.module_ai.query.rewrite import (
    build_rewrite_prompt,
    finalize_rewrite,
    needs_rewrite,
    recent_history,
)


def _hist():
    return [
        {"question": "华东区域今天有多少告警", "sql": "SELECT 1", "datasource": "system"},
        {"question": "那上周呢", "sql": "SELECT 2", "datasource": "system"},
    ]


def test_needs_rewrite_no_history_is_false():
    assert needs_rewrite("那上周呢", None) is False
    assert needs_rewrite("那上周呢", []) is False


def test_needs_rewrite_reference_word():
    assert needs_rewrite("那上周呢", _hist()) is True
    assert needs_rewrite("换成华东呢", _hist()) is True
    assert needs_rewrite("还有呢", _hist()) is True


def test_needs_rewrite_short_sentence():
    assert needs_rewrite("上周呢", _hist()) is True


def test_needs_rewrite_self_contained_is_false():
    # 看起来自包含的问题，即使有历史也不该重写（省一次 LLM 调用）
    assert needs_rewrite("统计每个区域今天的告警数量", _hist()) is False


def test_recent_history_takes_last_two_and_skips_errors():
    msgs = [
        {"question": "q1", "sql": "S1", "datasource": "system", "is_error": True},
        {"question": "q2", "sql": "S2", "datasource": "system"},
        {"question": "q3", "sql": "", "datasource": "system"},   # 无 sql 也保留（是成功轮）
        {"question": "q4", "sql": "S4", "datasource": "ds:4"},
    ]
    out = recent_history(msgs)
    # 只取最近 2 条成功，q1 因 is_error 被跳过
    assert [m["question"] for m in out] == ["q3", "q4"]
    assert out[-1]["datasource"] == "ds:4"


def test_build_rewrite_prompt_contains_history_and_question():
    p = build_rewrite_prompt("那上周呢", _hist())
    assert "华东区域今天有多少告警" in p
    assert "那上周呢" in p
    assert "自包含" in p


def test_finalize_rewrite():
    # 空 / 相同 / 过长 → None（调用方用原问题）
    assert finalize_rewrite("q", "") is None
    assert finalize_rewrite("q", None) is None
    assert finalize_rewrite("q", "q") is None
    assert finalize_rewrite("q", "q。") is None
    assert finalize_rewrite("q", "x" * 500) is None
    # 合法 → 去引号围栏
    assert finalize_rewrite("q", "华东上周呢") == "华东上周呢"
    assert finalize_rewrite("q", "「华东上周呢」") == "华东上周呢"
