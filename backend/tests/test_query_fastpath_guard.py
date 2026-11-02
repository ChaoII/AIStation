"""快路径（指标模板）的**准入检查**。

背景（实测）：「最近一个月平均收到基低位发热量是多少？」命中了 ``avg_rz``，
返回的 SQL 是 ``SELECT AVG("RZ") FROM "DTXY_PMXX"`` —— **一个时间条件都没有**，
但界面上它被标成了「最近一个月」。用户看不出来，这是最坏的一类错误：
不是报错，是自信地答错。

根因不是"又漏了一个词"，而是判定方式是**黑名单**（问句里出现危险词才拦），
永远漏；正确方向是**白名单**：模板必须能解释问句里的每一处限定，解释不了就让位。

这里钉住两条可判定的限定：
1. 时间限定 —— 问句带了时间范围，而模板无法（或没能）把它参数化；
2. 聚合限定 —— 问句说"平均/最大/最小/合计"，而模板算的是另一种聚合。
"""

import pytest

DTY = {
    "key": "avg_rz", "name": "收到基低位发热量", "description": "煤质化验平均发热量",
    "agg": "avg", "enabled": True, "object_code": "", "datasource": "ds:4",
    "sql_template": 'SELECT AVG(CAST("RZ" AS DECIMAL)) AS "收到基低位发热量" FROM "DTXY_PMXX"',
}
RAIL = {
    "key": "fuel_raillost_total", "name": "运损合计", "description": "供应商运损扣吨合计",
    "agg": "sum", "enabled": True, "object_code": "", "datasource": "ds:4",
    "sql_template": 'SELECT SUM(CAST("RAILLOST" AS numeric)) AS "运损合计" FROM "FUEL_CMCS_INFACTORYBATCH"',
}
#: 声明了 days 参数的指标（system 的 alert_by_type 就是这种）
ALERT = {
    "key": "alert_by_type", "name": "各类型告警数", "description": "按告警类型统计",
    "agg": "count", "enabled": True, "object_code": "", "datasource": "system",
    "sql_template": "SELECT alarm_type, COUNT(*) FROM video_alarm_records "
                    "WHERE alarm_time >= CURRENT_DATE - {days} GROUP BY alarm_type",
    "params": [{"key": "days", "type": "value", "label": "最近天数"}],
}


# ---------------------------------------------------------------------------
# 一、时间限定必须被模板消费
# ---------------------------------------------------------------------------
def test_time_window_blocks_fast_path_when_template_has_no_param():
    """「最近一个月」+ 无时间参数的模板 → 必须让位 NL2SQL。"""
    from app.plugin.module_ai.query.service import _fast_path_blockers

    reasons = _fast_path_blockers("最近一个月平均收到基低位发热量是多少？", DTY, [], [])
    assert any("时间" in r for r in reasons), reasons


def test_time_window_blocks_even_when_parseable_but_template_ignores_it():
    """「本月」能被 parse_time_range 解析，但模板没有 {days} → 同样不能用模板答。"""
    from app.plugin.module_ai.query.service import _fast_path_blockers

    reasons = _fast_path_blockers("本月运损合计是多少？", RAIL, [], [])
    assert any("时间" in r for r in reasons), reasons


def test_time_window_allowed_when_template_declares_it():
    """模板真的声明了 {days} 时，时间限定可以被消费，不应拦。"""
    from app.plugin.module_ai.query.service import _fast_path_blockers

    assert _fast_path_blockers("最近7天各类型告警数是多少？", ALERT, [], []) == []


def test_plain_aggregate_question_has_no_blocker():
    """不带任何限定的聚合问句 → 快路径应当放行（不能把快路径调死）。"""
    from app.plugin.module_ai.query.service import _fast_path_blockers

    assert _fast_path_blockers("运损合计是多少？", RAIL, [], []) == []


# ---------------------------------------------------------------------------
# 二、聚合口径必须与模板一致
# ---------------------------------------------------------------------------
def test_agg_word_conflict_blocks_fast_path():
    """问「运损最大」，模板却是 SUM → 让位（否则会把合计当最大值报出去）。"""
    from app.plugin.module_ai.query.service import _fast_path_blockers

    reasons = _fast_path_blockers("运损最大的一次是多少？", RAIL, [], [])
    assert any("聚合" in r for r in reasons), reasons


def test_agg_word_matching_template_passes():
    """问「合计」，模板是 SUM → 口径一致，放行。"""
    from app.plugin.module_ai.query.service import _fast_path_blockers

    assert _fast_path_blockers("运损合计是多少？", RAIL, [], []) == []


def test_bound_count_metric_passes_plain_question():
    """绑定型指标（本体实例层计数）不带限定时应放行。"""
    from app.plugin.module_ai.query.service import _fast_path_blockers

    m = {"key": "coal_assay_count", "name": "化验单数", "description": "化验单数量",
         "agg": "count", "enabled": True, "object_code": "coal_assay",
         "agg_fn": "count", "sql_template": "SELECT 1 AS 数量", "datasource": "ds:4"}
    assert _fast_path_blockers("入厂煤化验单一共有多少条？", m, [], []) == []


def test_avg_intent_blocks_count_template():
    """问「平均每个…有多少条」：要的是除法，count 模板给不了 → 让位。"""
    from app.plugin.module_ai.query.service import _fast_path_blockers

    m = {"key": "coal_assay_count", "name": "化验单数", "description": "化验单数量",
         "agg": "count", "enabled": True, "object_code": "coal_assay",
         "agg_fn": "count", "sql_template": "SELECT 1 AS 数量", "datasource": "ds:4"}
    reasons = _fast_path_blockers("平均每个矿点有多少条化验单？", m, [], [])
    assert any("聚合" in r for r in reasons), reasons


# ---------------------------------------------------------------------------
# 三、排序诉求（模板只出聚合值）
# ---------------------------------------------------------------------------
def test_ordering_question_blocks_fast_path():
    """「按名称排序」要的是有序结果集，聚合模板给不了。"""
    from app.plugin.module_ai.query.service import _fast_path_blockers

    for q in ("煤种按名称排序", "化验单按化验日期降序排列", "运损合计排名前3的供应商"):
        reasons = _fast_path_blockers(q, RAIL, [], [])
        assert any("排序" in r for r in reasons), (q, reasons)


# ---------------------------------------------------------------------------
# 四、实体名匹配：指标名「矿点数」应对得上问句里的「矿点」
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,expect", [
    ("矿点数", "矿点"),
    ("区域数量", "区域"),
    ("化验单数", "化验单"),
    ("运损合计", "运损"),
    ("供应商矿点关系数", "供应商矿点关系"),
    ("化验单", "化验单"),          # 没有可剥的度量词，原样返回
])
def test_metric_name_core_strips_measure_suffix(name, expect):
    """指标名尾部的「数/数量/合计」是度量词，用户不会说（实测「矿点」因此只差 1 分没命中）。"""
    from app.plugin.module_ai.query.service import _metric_name_core

    assert _metric_name_core(name) == expect


def test_match_metric_uses_name_core():
    """「矿点一共有多少个」应命中「矿点数」（裸二元组得分 3 < 门槛 4）。"""
    from app.plugin.module_ai.query.service import _match_metric

    m = {"key": "coal_mine_count", "name": "矿点数", "description": "矿点数量",
         "agg": "count", "enabled": True, "object_code": "coal_mine",
         "agg_fn": "count", "sql_template": "SELECT 1 AS 数量", "datasource": "ds:4"}
    got = _match_metric("矿点一共有多少个？", [m], [], [], {})
    assert got and got["key"] == "coal_mine_count"


def test_match_metric_uses_ontology_object_name():
    """本体桥：指标名是英文 key 时，靠**对象中文名**接上（语义层存在的意义）。"""
    from app.plugin.module_ai.query.service import _match_metric

    m = {"key": "DTXY_QYXX_count_ID", "name": "区域数量", "description": "",
         "agg": "count", "enabled": True, "object_code": "DTXY_QYXX",
         "agg_fn": "count", "sql_template": "SELECT 1 AS 数量", "datasource": "ds:4"}
    objects = {"DTXY_QYXX": {"name": "区域信息", "aliases": ["区域"]}}
    got = _match_metric("区域信息里有多少条？", [m], [], [], objects)
    assert got and got["key"] == "DTXY_QYXX_count_ID"


# ---------------------------------------------------------------------------
# 三、聚合口径以**模板真实表达式**为准，而不是 agg 字段
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("sql,expect", [
    ('SELECT SUM("A") FROM t', "sum"),
    ('SELECT AVG(CAST("A" AS numeric)) FROM t', "avg"),
    ('SELECT MAX("A") FROM t', "max"),
    ('SELECT MIN("A") FROM t', "min"),
    ('SELECT COUNT(*) FROM t', "count"),
])
def test_effective_agg_reads_template_not_metadata(sql, expect):
    """``agg`` 字段是人工维护的，实测有 ``SUM(CHECKQTY)`` 却标成 count 的。

    用错的元数据去校验问句，会把合法问题拦掉（「验收量合计」就是这种）。
    """
    from app.plugin.module_ai.query.service import _effective_agg

    m = dict(RAIL, sql_template=sql)
    assert _effective_agg(m) == expect


def test_effective_agg_uses_agg_fn_for_bound_metric():
    """绑定型指标没有可执行 SQL，聚合口径取 ``agg_fn``。"""
    from app.plugin.module_ai.query.service import _effective_agg

    m = {"agg": "count", "object_code": "coal_assay", "agg_fn": "count",
         "sql_template": "SELECT 1 AS 数量"}
    assert _effective_agg(m) == "count"


# ---------------------------------------------------------------------------
# 四、端到端：_select_metric 真的会因此让位
# ---------------------------------------------------------------------------
def test_select_metric_rejects_time_window_question():
    """整体判定：时间限定无法消费时，_select_metric 返回 None。"""
    import asyncio

    from app.plugin.module_ai.query.service import SYSTEM_DS, AiQueryService

    m = dict(DTY, datasource=SYSTEM_DS)
    assert asyncio.run(AiQueryService._select_metric(
        "最近一个月平均收到基低位发热量是多少？", SYSTEM_DS, [m], [])) is None
    got = asyncio.run(AiQueryService._select_metric(
        "收到基低位发热量是多少？", SYSTEM_DS, [m], []))
    assert got and got["key"] == "avg_rz"


@pytest.mark.parametrize("q", [
    "已删除的入厂煤批次有多少条？",          # 状态修饰 = WHERE 条件
    "矿点名称里带“煤”字的有多少个？",        # 「带…字」= LIKE
    "出现过多少家不同的供应商？",            # 「多少家不同」= COUNT(DISTINCT)
])
def test_condition_words_block_fast_path(q):
    """条件状语必须让位 NL2SQL（实测这几个都被"总数"指标抢答了）。"""
    from app.plugin.module_ai.query.service import _needs_custom_sql

    assert _needs_custom_sql(q) is True


def test_total_amount_is_sum_intent():
    """「总量」是求和，不是计数：实测「煤场进煤总量」被 COUNT(*) 指标答成行数。"""
    from app.plugin.module_ai.query.service import _fast_path_blockers

    m = {"key": "FUEL_STG_ALLINMIDDLE_count_ID", "name": "煤场进煤记录数",
         "agg": "count", "enabled": True, "object_code": "",
         "sql_template": 'SELECT COUNT(*) AS "数量" FROM "FUEL_STG_ALLINMIDDLE"',
         "datasource": "ds:4"}
    reasons = _fast_path_blockers("煤场进煤总量是多少？", m, [], [])
    assert any("聚合" in r for r in reasons), reasons


@pytest.mark.parametrize("q", [
    "化验单里备注不为空的有多少条？",        # 空值判断
    "矿点名称以“煤”字开头的矿点有多少个？",  # 前后缀匹配
    "同一个供应商最多关联了多少个矿点？",    # 极值（max of groups）
    "关联矿点数最多的那家供应商占百分之多少？",
])
def test_operator_words_block_fast_path(q):
    """极值/空值/前后缀/百分比表述，模板都表达不了。

    实测这 4 个措辞都被「总数」类指标抢答（coal_assay.count / coal_mine.count）。
    """
    from app.plugin.module_ai.query.service import _needs_custom_sql

    assert _needs_custom_sql(q) is True


def test_aggregate_object_mismatch_blocks_wrong_metric():
    """问「平均灰分」却被「平均发热量」模板命中 —— 会自信地报出别人的数字。"""
    from app.plugin.module_ai.query.service import _fast_path_blockers

    m = {"key": "avg_rz", "name": "平均收到基低位发热量", "agg": "avg", "enabled": True,
         "object_code": "", "datasource": "ds:4",
         "sql_template": 'SELECT AVG(CAST("RZ" AS numeric)) FROM "DTXY_PMXX"'}
    reasons = _fast_path_blockers("煤质信息的平均灰分是多少？", m, [], [])
    assert any("聚合对象" in r for r in reasons), reasons


def test_aggregate_object_match_passes():
    """问「平均发热量」而模板就是发热量 → 放行。"""
    from app.plugin.module_ai.query.service import _fast_path_blockers

    m = {"key": "avg_rz", "name": "平均收到基低位发热量", "agg": "avg", "enabled": True,
         "object_code": "", "datasource": "ds:4",
         "sql_template": 'SELECT AVG(CAST("RZ" AS numeric)) FROM "DTXY_PMXX"'}
    assert _fast_path_blockers("煤质信息的平均发热量是多少？", m, [], []) == []


@pytest.mark.parametrize("q", ["煤场进煤记录和取煤记录加起来一共多少条？",
                              "煤场进煤记录比取煤记录多多少条？"])
def test_cross_table_comparison_blocks_fast_path(q):
    """跨表加减/比较：单表模板算不出来。"""
    from app.plugin.module_ai.query.service import _needs_custom_sql

    assert _needs_custom_sql(q) is True
