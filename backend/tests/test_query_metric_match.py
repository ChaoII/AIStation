"""指标匹配（快路径语义匹配）收紧：纯逻辑，可 ``PYTEST_NO_APP=1`` 快速跑。

实测误命中：`所有燃煤合同的合同数量合计是多少？` 命中 `total_settlement_qty`（结算总量）
——因为通用词「数量」出现在该指标描述里就加分了。合同**数量** ≠ 结算**量**。
"""
from app.plugin.module_ai.query.service import _match_metric


def _m(key, name, desc, **kw):
    d = {"key": key, "name": name, "description": desc, "enabled": True,
         "params": [], "dimensions": []}
    d.update(kw)
    return d


def test_does_not_match_on_generic_word_only():
    """通用词（数量/多少/合计）不能单独把指标拉出来。"""
    metrics = [
        _m("total_settlement_qty", "结算总量", "结算总量（结算数量）"),
        _m("avg_contract_price", "平均合同单价", "合同单价平均值"),
    ]
    got = _match_metric("所有燃煤合同的合同数量合计是多少？", metrics, [])
    assert got is None, f"不该命中任何指标，实际命中: {got and got['key']}"


def test_matches_when_metric_own_words_appear():
    metrics = [_m("avg_contract_price", "平均合同单价", "合同单价平均值")]
    got = _match_metric("燃煤采购结算的平均合同单价是多少？", metrics, [])
    assert got and got["key"] == "avg_contract_price"


def test_distribution_metric_beats_count_metric_for_type_question():
    """「按类型分布」类问句要选分布指标，而不是「今日告警数」。"""
    metrics = [
        _m("alert_by_type", "按告警类型的分布", "按告警类型分组的告警数量，可过滤最近N天"),
        _m("alert_count_today", "今日告警数", "今天产生的视频告警总数"),
    ]
    terms = [{"term": "告警", "metric_key": "alert_count_today"}]
    got = _match_metric("各种告警类型分别有多少条？", metrics, terms)
    assert got and got["key"] == "alert_by_type", f"实际: {got and got['key']}"


def test_time_frame_month_prefers_month_metric():
    metrics = [
        _m("alert_count_today", "今日告警数", "今天产生的视频告警总数"),
        _m("alert_count_month", "本月告警数", "本自然月产生的视频告警总数"),
    ]
    terms = [{"term": "报警", "metric_key": "alert_count_today"}]
    got = _match_metric("这个月总共有多少条报警？", metrics, terms)
    assert got and got["key"] == "alert_count_month", f"实际: {got and got['key']}"


def test_disabled_metric_never_matches():
    metrics = [_m("avg_contract_price", "平均合同单价", "合同单价平均值", enabled=False)]
    assert _match_metric("平均合同单价是多少？", metrics, []) is None


def test_count_intent_skips_average_metric():
    """计数意图（多少份/多少条）下，平均值指标不该被抢答。

    实测 2026-11-10：「燃煤合同一共有多少份」与「平均合同单价」都含「合同」，
    平均单价以 4 分压线命中（名称二元组 3 + 描述 1）→ 快路径答成 539.75，gold 是 COUNT。
    """
    metrics = [_m("avg_contract_price", "平均合同单价", "燃煤结算主表中的合同单价平均值", agg="avg")]
    assert _match_metric("燃煤合同一共有多少份？", metrics, []) is None


def test_count_question_prefers_count_metric_over_avg():
    """有「合同数量」指标时，计数题要选它而不是平均单价。"""
    metrics = [
        _m("avg_contract_price", "平均合同单价", "燃煤结算主表中的合同单价平均值", agg="avg"),
        _m("contract_count", "合同数量", "燃煤采购合同主表中的合同记录数", agg="count",
           sql_template='SELECT COUNT(*) FROM "FUEL_CB_COALCONTRACT"'),
    ]
    for q in ("燃煤合同一共有多少份？", "咱们一共有多少份燃煤合同？"):
        got = _match_metric(q, metrics, [])
        assert got and got["key"] == "contract_count", f"{q} 实际: {got and got['key']}"


def test_physical_quantity_skips_rowcount_metric():
    """「存煤量是多少」问的是吨数，不能被「…条数」指标答成行数（实测返回 370）。"""
    rowcount = _m("count_fuel_report_dayinoutstorage", "每日耗用量及存煤量条数",
                  "每日耗用量及存煤量（FUEL_REPORT_DAYINOUTSTORAGE）的记录条数", agg="count")
    storage = _m("coal_storage_qty", "煤场存煤量",
                 "按进煤流水剩余量汇总的当前存煤量（吨）", agg="sum")
    terms = [{"term": "存煤量", "metric_key": "coal_storage_qty"}]
    got = _match_metric("当前煤场的存煤量是多少", [rowcount, storage], terms)
    assert got and got["key"] == "coal_storage_qty", f"实际: {got and got['key']}"
    # 没有正确的存煤指标时，也不该退化成行数
    assert _match_metric("当前煤场的存煤量是多少", [rowcount], []) is None


def test_explicit_rowcount_question_still_uses_count_metric():
    """用户明确问「条数」时，行数指标仍然是对的。"""
    rowcount = _m("count_fuel_report_dayinoutstorage", "每日耗用量及存煤量条数",
                  "每日耗用量及存煤量（FUEL_REPORT_DAYINOUTSTORAGE）的记录条数", agg="count")
    got = _match_metric("每日耗用量及存煤量条数是多少", [rowcount], [])
    assert got and got["key"] == "count_fuel_report_dayinoutstorage"
    # 术语「存煤量」命中也不许把它改判走
    from app.plugin.module_ai.query.metric_rules import prefers_rowcount
    assert prefers_rowcount("每日耗用量及存煤量条数是多少", rowcount) is True
    assert prefers_rowcount("当前煤场的存煤量是多少", rowcount) is False


def test_term_only_question_matches_metric():
    """问句只有术语（「热值是多少」）也要能选中指标。

    实测 2026-11-10：术语绑定只 +3 分，低于 MIN_METRIC_SCORE=4 → 匹配不到，
    最终走慢路径且模型返回空 SQL（答案直接失败）。术语是人工绑定，权重按 +6 算。
    """
    metrics = [
        {"key": "avg_rz", "name": "平均收到基低位发热量", "description": "煤质信息中收到基低位发热量的平均值",
         "enabled": True, "dimensions": [], "sql_template": 'SELECT AVG("RZ") FROM t', "agg": "avg"},
        {"key": "avg_lf", "name": "平均干基全硫", "description": "煤质信息中干基全硫的平均值",
         "enabled": True, "dimensions": [], "sql_template": 'SELECT AVG("LF") FROM t', "agg": "avg"},
    ]
    terms = [{"term": "热值", "metric_key": "avg_rz"}, {"term": "硫分", "metric_key": "avg_lf"}]
    got = _match_metric("热值是多少", metrics, terms)
    assert got and got["key"] == "avg_rz", f"实际: {got and got['key']}"
    got2 = _match_metric("硫分是多少", metrics, terms)
    assert got2 and got2["key"] == "avg_lf", f"实际: {got2 and got2['key']}"
