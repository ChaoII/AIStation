"""时间口径**可配**：周起始日 / 月份口径来自数据源，代码只留默认值。

原则（2026-11-12）：业务口径不该写死。各厂对「本周」「上个月」的定义不同，
所以由 `ai_query_datasources.filter_rules.time` 覆盖，界面上可改。

纯逻辑，`PYTEST_NO_APP=1` 可快跑。
"""
from __future__ import annotations

from app.plugin.module_ai.query.dialect import build_system_prompt, time_rules
from app.plugin.module_ai.query.filtering import effective_filter_rules, time_rules_cfg


def test_defaults_are_monday_natural_month():
    cfg = time_rules_cfg(None)
    assert cfg == {"week_start": "monday", "month_mode": "natural"}
    body = time_rules({"name": "PostgreSQL"})
    assert "date_trunc('week', CURRENT_DATE)" in body
    assert "date_trunc('month', CURRENT_DATE)" in body


def test_sunday_week_start_changes_sql():
    body = time_rules({"name": "PostgreSQL"}, {"week_start": "sunday"})
    assert "date_trunc('week', CURRENT_DATE + INTERVAL '1 day') - INTERVAL '1 day'" in body
    mysql = time_rules({"name": "MySQL"}, {"week_start": "sunday"})
    assert "DAYOFWEEK(CURDATE()) - 1" in mysql


def test_rolling_30_days_changes_month():
    body = time_rules({"name": "PostgreSQL"}, {"month_mode": "rolling30"})
    assert "本月：>= CURRENT_DATE - 30" in body
    assert "上个月：> CURRENT_DATE - 60 AND <= CURRENT_DATE - 30" in body


def test_invalid_values_fall_back_to_defaults():
    cfg = time_rules_cfg({"time": {"week_start": "tuesday", "month_mode": "x"}})
    assert cfg == {"week_start": "monday", "month_mode": "natural"}


def test_effective_rules_expose_time_for_ui():
    eff = effective_filter_rules({"time": {"week_start": "sunday"}})
    assert eff["time"]["week_start"] == "sunday"
    assert eff["time"]["month_mode"] == "natural"


def test_prompt_carries_time_cfg():
    prompt = build_system_prompt(
        {"name": "PostgreSQL"}, [], "", "", time_cfg={"week_start": "sunday"})
    assert "CURRENT_DATE + INTERVAL '1 day'" in prompt
