"""问句语言规则：词表可配（默认行为不变）+ 开关 + 预览。

原则（AGENTS.md）：说法/词表放界面维护，算法结构留代码。
这组用例锁两件事：① 默认词表与改造前判定一致；② 配置能真正改变判定。
纯逻辑，`PYTEST_NO_APP=1` 可快跑。
"""
from __future__ import annotations

from app.plugin.module_ai.query import language_rules as LR
from app.plugin.module_ai.query.metric_rules import match_metric, wants_grouping
from app.plugin.module_ai.query.question_rules import is_listing_question


def _rules(**over):
    base = LR.merge_rules(None)
    base.update(over)
    return base


def test_defaults_judge_like_before():
    p = LR.probe("燃煤合同一共有多少份")
    assert p["count_intent"] is True
    p = LR.probe("当前煤场的存煤量是多少")
    assert p["physical_qty"] is True
    p = LR.probe("入厂煤批次有多少条")
    assert p["rowcount_ask"] is True
    p = LR.probe("按煤种统计平均收到基低位发热量")
    assert p["grouping"] is True
    p = LR.probe("列出所有供应商")
    assert p["listing"] is True and p["all_list"] is True


def test_switch_disables_rule():
    rules = _rules(switches={**LR.DEFAULT_LANGUAGE_RULES["switches"], "count_intent": False})
    assert LR.probe("燃煤合同一共有多少份", rules)["count_intent"] is False
    # 关掉「列举」后，列举问句不再被判成列举
    rules2 = _rules(switches={**LR.DEFAULT_LANGUAGE_RULES["switches"], "listing": False})
    assert is_listing_question("列出所有供应商") is True  # 默认仍生效
    LR.set_rules(rules2)
    try:
        assert is_listing_question("列出所有供应商") is False
    finally:
        LR.reset()


def test_word_list_override():
    rules = _rules(count_units=["票", "单"], count_quantifiers=["多少"])
    assert LR.probe("这个月开了多少票", rules)["count_intent"] is True
    # 默认词表里没有「票」
    assert LR.probe("这个月开了多少票")["count_intent"] is False


def test_invalid_json_falls_back():
    assert LR.effective("{bad json") ["count_units"] == LR.DEFAULT_LANGUAGE_RULES["count_units"]
    assert LR.effective("")["switches"] == LR.DEFAULT_LANGUAGE_RULES["switches"]


def test_grouping_and_metric_routing_use_config():
    # 默认：含「每个」判分组
    assert wants_grouping("每个供应商有多少个矿点") is True
    # 关掉 switches 里的 count_intent 不影响分组；但改词表去掉「每个」后不再分组
    rules = _rules(group_words=["分门别类"])
    LR.set_rules(rules)
    try:
        assert wants_grouping("每个供应商有多少个矿点") is False
    finally:
        LR.reset()


def test_metric_matching_ignores_physical_when_switched_off():
    metric = {
        "key": "stock_record_count", "name": "库存记录数", "description": "", "agg": "count",
        "enabled": True, "datasource": "ds:6", "unit": "", "dimensions": [], "params": [],
        "sql_template": 'SELECT COUNT(*) FROM "T"',
    }
    q = "当前库存是多少"
    # 默认：物理量诉求 → 行数指标不参战（否则把吨数答成条数）
    assert match_metric(q, [metric], [], [], {}) is None
    rules = _rules(switches={**LR.DEFAULT_LANGUAGE_RULES["switches"], "physical_qty": False})
    LR.set_rules(rules)
    try:
        got = match_metric(q, [metric], [], [], {})
        assert got and got["key"] == "stock_record_count"
    finally:
        LR.reset()
