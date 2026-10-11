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
