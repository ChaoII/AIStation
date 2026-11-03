"""SQL 意图校验：拿**问句的措辞**对**生成的 SQL**。

题库对比暴露的失败几乎全是"口径"而不是"能力"：数字都合理，但问的是"按名称"
SQL 却按 ID 分组、问的是"不为空"SQL 没排除空值。结果层面看不出来，
只能靠措辞对——而且要在**重试之前**发现，才有机会改对。
"""

import pytest

from app.plugin.module_ai.query.selfcheck import check_sql_intent, format_sql_intent

SQL_BY_ID = ('SELECT "KDID" AS 矿点, COUNT(*) AS c FROM "DTXY_GYSKDGX" '
             'GROUP BY "KDID" ORDER BY c DESC')
SQL_BY_NAME = ('SELECT "KDNAME" AS 矿点, COUNT(*) AS c FROM "DTXY_GYSKDGX" '
               'GROUP BY "KDNAME" ORDER BY c DESC')


def test_group_key_mismatch_detected():
    """问「按名称」，SQL 按 ID 分组 → 提示。"""
    issues = check_sql_intent("按矿点名称统计供应商数量", SQL_BY_ID)
    assert any(i["kind"] == "group_key" for i in issues), issues


def test_group_key_matching_is_clean():
    assert check_sql_intent("按矿点名称统计供应商数量", SQL_BY_NAME) == []


def test_null_semantics_detected():
    """问「不为空」，SQL 没有任何空值判断。"""
    issues = check_sql_intent(
        "化验单里备注不为空的有多少条？",
        'SELECT COUNT(*) FROM "FUEL_CMCS_ASSAY"')
    assert any(i["kind"] == "null_semantics" for i in issues), issues


def test_null_semantics_satisfied():
    assert check_sql_intent(
        "化验单里备注不为空的有多少条？",
        'SELECT COUNT(*) FROM "FUEL_CMCS_ASSAY" WHERE "REMARK" IS NOT NULL') == []


def test_distinct_detected():
    """问「多少家不同」，SQL 用普通 COUNT。"""
    issues = check_sql_intent(
        "出现过多少家不同的供应商？",
        'SELECT COUNT(*) FROM "DTXY_GYSKDGX"')
    assert any(i["kind"] == "distinct" for i in issues), issues


def test_time_filter_detected():
    """问「最近一个月」，SQL 里一个时间条件都没有。"""
    issues = check_sql_intent(
        "最近一个月平均发热量是多少？",
        'SELECT AVG("RZ") FROM "DTXY_PMXX"')
    assert any(i["kind"] == "time_filter" for i in issues), issues


def test_time_filter_satisfied():
    assert check_sql_intent(
        "最近一个月平均发热量是多少？",
        'SELECT AVG("RZ") FROM "DTXY_PMXX" WHERE "ASSAYDATE" >= CURRENT_DATE - INTERVAL \'1 month\'') == []


@pytest.mark.parametrize("q,sql", [
    ("入厂煤化验单一共有多少条？", 'SELECT COUNT(*) FROM "FUEL_CMCS_ASSAY"'),
    ("运损合计是多少？", 'SELECT SUM("RAILLOST") FROM "FUEL_CMCS_INFACTORYBATCH"'),
])
def test_clean_questions_have_no_issue(q, sql):
    """普通聚合问句不能被误报（误报会白花一次重试）。"""
    assert check_sql_intent(q, sql) == []


def test_format_is_readable():
    issues = check_sql_intent("按矿点名称统计供应商数量", SQL_BY_ID)
    assert "名称" in format_sql_intent(issues)
