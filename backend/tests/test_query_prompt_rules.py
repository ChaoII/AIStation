"""生成规则（可配置提示词规则）的纯逻辑测试：编号 / 开关 / 作用域 / 兜底。

为什么要这些用例
----------------
规则从代码搬到表里，最大的风险是「搬完之后拼出来的提示词变了」——而这种回归
**单测之外看不出来**（问数照样能答，只是口径悄悄变了）。所以这里锁三件事：

1. 默认渲染与改造前**逐字一致**（只差行首编号，编号由渲染生成）；
2. 停用/改顺序后编号**连续**（老实现把编号写死在文案里，停用一条就会跳号）；
3. 作用域与设置开关的过滤语义，以及「读库失败回退代码默认」的兜底。

用 ``PYTEST_NO_APP=1`` 可快跑（不构造应用，约 2 秒）。
"""
from __future__ import annotations

from app.plugin.module_ai.query.dialect import CORE_RULES, build_system_prompt
from app.plugin.module_ai.query.prompt_rules import (
    DEFAULT_RULES,
    _render,
    default_rows,
)


def _by_code() -> dict[str, dict]:
    return {r["code"]: r for r in default_rows()}


def test_default_render_matches_legacy_text():
    """默认配置（enum_hint 关）渲染 7 条，文案与历史实现逐字一致。"""
    rules = _render(default_rows(), {}, "ds:6", "PostgreSQL")
    assert len(rules) == 7
    assert rules[0].startswith("（1）问题要求按实体（摄像头/设备/算法/数据集/规则等）展示时")
    assert "占比用“COUNT(*) * 100.0 / 总数”" in rules[1]
    assert rules[2] == "（3）多行 SQL 直接换行输出即可，不要加注释。"
    assert rules[3].startswith("（4）**所有聚合列和计算列必须起中文别名**")
    assert rules[4].startswith("（5）先判断问题属于「单表聚合 / 多表联查 / 嵌套子查询」")
    assert rules[5].startswith("（6）先看要的是「明细」还是「汇总」")
    assert rules[6].startswith("（7）按某个数值列排序取 Top N")


def test_enum_hint_follows_setting_switch():
    """枚举提示由设置开关控制：关（默认）不出现，开则插到第 2 位并重排编号。"""
    off = _render(default_rows(), {"enum_hint_enabled": "false"}, "ds:6", "PostgreSQL")
    on = _render(default_rows(), {"enum_hint_enabled": "true"}, "ds:6", "PostgreSQL")
    assert len(off) == 7 and len(on) == 8
    assert on[1].startswith("（2）status/framework/severity/task_type")
    assert off[1].startswith("（2）占比用")


def test_disabled_rule_does_not_leave_number_gap():
    """停用一条后编号必须连续（老实现把编号写进文案，停用会跳号）。"""
    rows = default_rows()
    for r in rows:
        if r["code"] == "ratio_formula":
            r["enabled"] = False
    rules = _render(rows, {}, "ds:6", "PostgreSQL")
    prefixes = [r.split("）")[0] + "）" for r in rules]
    assert prefixes == [f"（{i}）" for i in range(1, len(rules) + 1)]
    assert all("占比用" not in r for r in rules)


def test_priority_controls_order():
    rows = default_rows()
    for r in rows:
        if r["code"] == "topn_null":
            r["priority"] = 1
    rules = _render(rows, {}, "ds:6", "PostgreSQL")
    assert rules[0].startswith("（1）按某个数值列排序取 Top N")


def test_scope_datasource_and_dialect():
    rows = default_rows()
    for r in rows:
        if r["code"] == "topn_null":
            r["scope"] = "datasource"
            r["scope_value"] = "ds:6"
    assert any("Top N" in r for r in _render(rows, {}, "ds:6", "PostgreSQL"))
    assert not any("Top N" in r for r in _render(rows, {}, "ds:4", "PostgreSQL"))

    for r in rows:
        if r["code"] == "topn_null":
            r["scope"] = "dialect"
            r["scope_value"] = "MySQL"
    assert any("Top N" in r for r in _render(rows, {}, "ds:6", "MySQL"))
    assert not any("Top N" in r for r in _render(rows, {}, "ds:6", "PostgreSQL"))


def test_core_rules_are_not_part_of_configurable_set():
    """核心安全约束必须留在代码里（不进规则表、不可被停用）。"""
    codes = {r["code"] for r in DEFAULT_RULES}
    assert "core_readonly" not in codes
    prompt = build_system_prompt({"name": "PostgreSQL"}, [], "", "")
    assert "".join(CORE_RULES) in prompt
    assert "不要使用 DELETE/UPDATE/INSERT/DDL" in prompt


def test_render_is_empty_when_all_disabled():
    rows = default_rows()
    for r in rows:
        r["enabled"] = False
    assert _render(rows, {}, "ds:6", "PostgreSQL") == []
