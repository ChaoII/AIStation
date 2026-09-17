"""用户规则正则安全性测试（审计 #10 ReDoS）。

覆盖：
- 灾难性嵌套量词（如 ``(a+)+$``）被静态拒绝，绝不进入 ``re`` 执行，因此不会挂起；
- 超长模式被拒绝；单事件待匹配文本被截断（限制最坏回溯规模）；
- 已编译模式被缓存（同一模式不重复编译）；
- 合法模式（目录默认规则 ``.+`` / ``[0-9]+(?:\\.[0-9]+)?``）行为不变；
- 规则编译层（``compile_rule``）对不安全正则报 ``RuleCompileError``。
"""
import time

import pytest

from app.api.v1.module_video.scene.compile import RuleCompileError, compile_rule
from app.utils.re_util import (
    MAX_PATTERN_LENGTH,
    MAX_TEXT_LENGTH,
    RegexSafetyError,
    safe_regex_search,
    validate_regex_pattern,
)


def test_catastrophic_nested_quantifier_is_rejected():
    """灾难性模式必须被静态拒绝（不得进入 re 引擎）。"""
    with pytest.raises(RegexSafetyError):
        validate_regex_pattern("(a+)+$")
    with pytest.raises(RegexSafetyError):
        validate_regex_pattern("(a*)*")
    with pytest.raises(RegexSafetyError):
        validate_regex_pattern("(?:\\w+)+")


def test_catastrophic_pattern_does_not_hang_and_is_handled():
    """已知灾难性模式 + 超长非匹配串：必须立即返回 False（不挂起）。"""
    text = "a" * 100_000 + "!"
    start = time.perf_counter()
    result = safe_regex_search("(a+)+$", text)
    elapsed = time.perf_counter() - start
    assert result is False
    assert elapsed < 1.0, f"疑似发生灾难性回溯，耗时 {elapsed:.3f}s"


def test_safe_patterns_keep_working():
    """合法正则行为不变（向后兼容目录默认规则）。"""
    assert safe_regex_search(".+", "hello") is True
    assert safe_regex_search(".+", "") is False
    assert safe_regex_search("[0-9]+(?:\\.[0-9]+)?", "12.5") is True
    assert safe_regex_search("[0-9]+(?:\\.[0-9]+)?", "abc") is False
    # 有界量词包裹无界量词不是灾难性结构，应放行
    assert validate_regex_pattern("[0-9]+(?:\\.[0-9]+)?") is not None
    assert validate_regex_pattern("(a+)?") is not None


def test_overlong_pattern_rejected():
    with pytest.raises(RegexSafetyError):
        validate_regex_pattern("a" * (MAX_PATTERN_LENGTH + 1))


def test_invalid_regex_handled_as_no_match():
    """非法正则视为不命中，不抛异常。"""
    assert safe_regex_search("(unclosed", "any") is False


def test_input_text_is_bounded():
    """待匹配文本超过上限即截断；上限之后的命中不算命中（限制最坏规模）。"""
    long_text = "a" * (MAX_TEXT_LENGTH + 1000) + "z"
    start = time.perf_counter()
    assert safe_regex_search("z", long_text) is False
    assert time.perf_counter() - start < 1.0


def test_compiled_patterns_are_cached():
    """同一模式重复使用应命中 LRU 缓存，避免每事件现编译。"""
    from app.utils import re_util

    pattern = "__cache_probe_[0-9]+__"
    re_util._compile_cached.cache_clear()
    assert safe_regex_search(pattern, "x1") is False
    before = re_util._compile_cached.cache_info().misses
    assert safe_regex_search(pattern, "x2") is False
    info = re_util._compile_cached.cache_info()
    assert info.misses == before  # 第二次未再编译
    assert info.hits >= 1


def test_compile_rule_rejects_unsafe_regex():
    """规则编译层对灾难性正则报错（保存即拒绝）。"""
    cond = {"op": "and", "children": [{"subject": "text_match", "regex": "(a+)+$"}]}
    with pytest.raises(RuleCompileError):
        compile_rule("OCR_TEXT", {}, cond)

    ok = compile_rule("OCR_TEXT", {"pattern": "[0-9]+"}, cond)
    assert ok["children"][0]["regex"] == "[0-9]+"
