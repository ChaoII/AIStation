"""软删口径**可配置**：列名与"问句在问已删除"的词表来自数据源，而不是写死在代码里。

原则（2026-11-12）：业务语义/口径要能在它该在的地方维护 —— 软删列名属于**数据源**的
schema 语义（`ai_query_datasources.filter_rules.softdelete`），不同库叫法不同
（ISDELETED / IS_DELETED / DEL_FLAG），代码只保留默认值。

纯逻辑，`PYTEST_NO_APP=1` 可快跑。
"""
from __future__ import annotations

from app.plugin.module_ai.query.filtering import softdelete_rules
from app.plugin.module_ai.query.softdelete import (
    apply_softdelete_policy,
    asks_about_deletion,
    inject_softdelete,
)


def test_rules_default_and_override():
    d = softdelete_rules(None)
    assert d["column"] == "ISDELETED"
    assert "已删除" in d["deletion_hints"]
    # 旧配置没有 softdelete 段 → 仍然拿到默认（不要求用户重存一遍）
    assert softdelete_rules({"system_table": {}})["column"] == "ISDELETED"
    # 只覆盖列名，词表保持默认
    r = softdelete_rules({"softdelete": {"column": "DEL_FLAG"}})
    assert r["column"] == "DEL_FLAG"
    assert "作废" in r["deletion_hints"]


def test_inject_uses_configured_column():
    sql = 'SELECT COUNT(*) FROM "T1"'
    out, hit = apply_softdelete_policy(
        "一共有多少条", sql, {"T1": ["ID(bigint)", "DEL_FLAG(bool)"]},
        {"softdelete": {"column": "DEL_FLAG"}})
    assert hit == ["T1"]
    assert '"DEL_FLAG" = FALSE' in out.upper()


def test_no_injection_when_question_asks_deleted():
    sql = 'SELECT COUNT(*) FROM "T1"'
    out, hit = apply_softdelete_policy(
        "已删除的记录有多少条", sql, {"T1": ["ISDELETED(bool)"]}, None)
    assert hit == [] and out == sql


def test_no_injection_when_sql_already_has_condition():
    sql = 'SELECT COUNT(*) FROM "T1" WHERE "ISDELETED" = TRUE'
    out, hit = apply_softdelete_policy(
        "已作废的记录有多少条", sql, {"T1": ["ISDELETED(bool)"]}, None)
    assert hit == [] and out == sql


def test_table_without_column_is_untouched():
    sql = 'SELECT COUNT(*) FROM "T1"'
    out, hit = apply_softdelete_policy("一共有多少条", sql, {"T1": ["ID(bigint)"]}, None)
    assert hit == [] and out == sql


def test_custom_hints_are_honoured():
    sql = 'SELECT COUNT(*) FROM "T1"'
    rules = {"softdelete": {"column": "ISDELETED", "deletion_hints": ["销账"]}}
    assert asks_about_deletion("销账的有多少条", rules["softdelete"]["deletion_hints"])
    out, hit = apply_softdelete_policy("销账的有多少条", sql, {"T1": ["ISDELETED(bool)"]}, rules)
    assert hit == [] and out == sql


def test_inject_softdelete_signature_still_backward_compatible():
    out, hit = inject_softdelete('SELECT * FROM "A"', {"A"})
    assert hit == ["A"] and '"ISDELETED" = FALSE' in out.upper()


def test_effective_rules_show_defaults_in_ui():
    """界面回显必须是**生效值**：库里没存 softdelete 时也要看到默认列名与词表。"""
    from app.plugin.module_ai.query.filtering import effective_filter_rules

    eff = effective_filter_rules(None)
    assert eff["softdelete"]["column"] == "ISDELETED"
    assert "作废" in eff["softdelete"]["deletion_hints"]
    # 已保存的覆盖要生效
    eff2 = effective_filter_rules({
        "softdelete": {"column": "IS_DELETED", "deletion_hints": ["注销"]},
        "system_table": {"prefixes": ["TMP_"]},
    })
    assert eff2["softdelete"]["column"] == "IS_DELETED"
    assert eff2["softdelete"]["deletion_hints"] == ["注销"]
    assert eff2["system_table"]["prefixes"] == ["TMP_"]
    # 旧配置（无 system_table）→ 默认前缀仍在
    assert effective_filter_rules({"enabled": True})["system_table"]["prefixes"]
