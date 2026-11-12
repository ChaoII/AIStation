"""指标护栏（二版）：计数型指标必须有「指标名 / 表名 / 业务别名」证据。

背景：一版护栏在别名为空时上线 → 把「多少份燃煤合同」的正确指标挡掉（105 掉到 98.1%），
已回退。现在别名数据补齐（资产中文名 + 本体对象别名 46 个），同规则重跑并用本用例锁住：
- 误劫持必须挡住（供应商煤质限制 / 配煤方案分仓明细）；
- 正常快路径不能被误伤（燃煤合同、库存这类 sum 指标）。
"""
from __future__ import annotations

import os

import pytest

from app.plugin.module_ai.query.metric_rules import (
    _competitor_alias,
    _metric_table_evidence,
    match_metric,
    set_guard_rules,
)


def _metric(key: str, name: str, table: str, agg: str = "count") -> dict:
    fn = "COUNT(*)" if agg == "count" else 'SUM("X")'
    return {
        "key": key, "name": name, "description": "", "agg": agg,
        "enabled": True, "datasource": "ds:6", "unit": "",
        "sql_template": f'SELECT {fn} AS "值" FROM "{table}"',
        "dimensions": [], "params": [],
    }


SUPPLIER_ALIAS = {"FUEL_CMCS_SUPPLIER": ["供应商", "供应商台账"]}
SCHEME_ALIAS = {"FUEL_MIX_COALSCHEME": ["配煤方案", "掺配方案"]}
CONTRACT_ALIAS = {"FUEL_CB_COALCONTRACT": ["燃煤合同", "采购合同", "合同主表"]}
STOCK_ALIAS = {"FUEL_STG_ALLINMIDDLE": ["煤场进煤记录(流水)"]}


def test_hijack_is_blocked_supplier():
    m = _metric("supplier_count", "供应商数量", "FUEL_CMCS_SUPPLIER")
    assert match_metric("供应商煤质限制一共有多少条？", [m], [], [], {},
                        table_alias=SUPPLIER_ALIAS) is None
    got = match_metric("供应商数量是多少？", [m], [], [], {}, table_alias=SUPPLIER_ALIAS)
    assert got and got["key"] == "supplier_count"


def test_hijack_is_blocked_coalscheme_bunker():
    m = _metric("scheme_count", "配煤方案数量", "FUEL_MIX_COALSCHEME")
    assert match_metric("配煤方案分仓明细一共有多少条？", [m], [], [], {},
                        table_alias=SCHEME_ALIAS) is None
    got = match_metric("配煤方案有多少个？", [m], [], [], {}, table_alias=SCHEME_ALIAS)
    assert got and got["key"] == "scheme_count"


def test_correct_count_metric_not_blocked():
    """别名补上后，「多少份燃煤合同」必须命中合同计数（一版护栏就是在这里误伤）。"""
    m = _metric("contract_count", "燃煤合同数量", "FUEL_CB_COALCONTRACT")
    got = match_metric("咱们一共有多少份燃煤合同？", [m], [], [], {},
                       table_alias=CONTRACT_ALIAS)
    assert got and got["key"] == "contract_count"


def test_sum_metric_not_guarded():
    stock = _metric("coal_storage_qty", "煤场存煤量", "FUEL_STG_ALLINMIDDLE", agg="sum")
    terms = [{"term": "库存量", "metric_key": "coal_storage_qty"}]
    got = match_metric("当前煤场库存量是多少", [stock], terms, [], {},
                       table_alias=STOCK_ALIAS)
    assert got and got["key"] == "coal_storage_qty"


def test_alias_evidence_and_sibling_veto():
    assert _metric_table_evidence("燃煤合同有多少份", "合同数量", "", "FUEL_CB_COALCONTRACT",
                                  ["燃煤合同"])
    assert not _metric_table_evidence("配煤方案分仓明细有多少条", "配煤方案数量", "",
                                     "FUEL_MIX_COALSCHEME", ["配煤方案"])
    assert not _metric_table_evidence("一共有多少条", "供应商数量", "",
                                     "FUEL_CMCS_SUPPLIER", ["供应商"])


def test_competitor_alias_rule():
    """问句点到别的表的业务别名 → 该指标不参战（sum/avg 也拦）。"""
    amap = {
        "FUEL_STG_ALLINMIDDLE": ["煤场进煤记录(流水)", "煤场进煤记录"],
        "FUEL_STG_STORAGEINITIALIZEDETAIL": ["期初库存明细", "初始库存明细"],
        "FUEL_MIX_COALSCHEMEREUSLTDETAIL": ["配煤结果明细"],
        "FUEL_MIX_COALSCHEMERESULT": ["配煤结果", "掺配结果"],
    }
    # 别的表别名命中 → 返回它
    assert _competitor_alias("期初库存明细的库存量合计是多少", "FUEL_STG_ALLINMIDDLE",
                             amap, amap["FUEL_STG_ALLINMIDDLE"]) == "期初库存明细"
    # 只命中自己的别名 → 没有竞争者
    assert _competitor_alias("本月煤场进煤记录有多少条", "FUEL_STG_ALLINMIDDLE",
                             amap, amap["FUEL_STG_ALLINMIDDLE"]) == ""
    # 短别名（<4）不算证据
    assert _competitor_alias("库存有多少", "X", {"T": ["库存"]}, []) == ""


def test_sum_metric_blocked_by_competitor():
    stock = _metric("coal_storage_qty", "煤场存煤量", "FUEL_STG_ALLINMIDDLE", agg="sum")
    amap = {
        "FUEL_STG_ALLINMIDDLE": ["煤场进煤记录(流水)", "煤场进煤记录"],
        "FUEL_STG_STORAGEINITIALIZEDETAIL": ["期初库存明细"],
    }
    assert match_metric("期初库存明细的库存量合计是多少", [stock], [], [], {},
                        table_alias=amap) is None


def test_guard_params_are_configurable():
    """兄弟限定词/最小长度可配：改配置立即生效，复位后回默认。"""
    amap = {"FUEL_STG_ALLINMIDDLE": ["煤场进煤记录"], "T2": ["库存明细"]}
    # 默认 min_alias_len=4：四字别名会被识别为竞争者
    assert _competitor_alias("库存明细有多少", "FUEL_STG_ALLINMIDDLE", amap,
                             amap["FUEL_STG_ALLINMIDDLE"]) == "库存明细"
    try:
        set_guard_rules({"min_alias_len": 6})
        assert _competitor_alias("库存明细有多少", "FUEL_STG_ALLINMIDDLE", amap,
                                 amap["FUEL_STG_ALLINMIDDLE"]) == ""
        # 清空兄弟限定词后，表证据不再被否决
        set_guard_rules({"sibling_qualifiers": []})
        assert _metric_table_evidence("配煤方案分仓明细有多少条", "配煤方案数量", "",
                                      "FUEL_MIX_COALSCHEME", ["配煤方案"])
    finally:
        set_guard_rules(None)


@pytest.mark.skipif(os.environ.get("PYTEST_NO_APP") == "1", reason="需要构造应用（ORM）")
def test_metric_audit_shape():
    """指标体检返回结构（总/可疑/抢答 + 条目字段）。"""
    import asyncio

    from app.plugin.module_ai.query.metric_audit import audit_metrics

    out = asyncio.run(audit_metrics("ds:6", top=5))
    assert set(out) >= {"total_metrics", "suspect", "hijacking", "items"}
    assert isinstance(out["items"], list)
    if out["items"]:
        assert set(out["items"][0]) >= {"key", "name", "reasons", "questions", "action"}


def _mk(key: str, name: str, agg: str, sql: str = "") -> dict:
    return {
        "key": key, "name": name, "agg": agg, "enabled": True, "description": "",
        "sql_template": sql or f'SELECT {agg.upper()}("X") FROM "T"',
        "object_code": "", "params": [], "dimensions": [],
    }


def test_count_question_is_not_hijacked_by_sum_metric():
    """问「多少条」时，SUM 型指标不参战——即使句子里顺带提到灰分/耗用这类物理量词。

    实测翻车：配煤方案主表STANDQTY合计 把「分仓里灰分上限大于20的有多少条」答成了标煤量。
    """
    ms = [_mk("sum_x", "配煤方案标煤量合计", "sum", 'SELECT SUM("ST") FROM "FUEL_MIX_COALSCHEME"')]
    assert match_metric("配煤方案分仓里灰分上限（AD_MAX）大于 20 的有多少条？", ms, [], [], {}) is None
    # 同一句里的物理量问法仍可走指标
    assert match_metric("配煤方案标煤量合计是多少？", ms, [], [], {}) is not None


def test_rowcount_metric_recognised_by_generated_key_shapes():
    """`xxx_count_ID` / 名字带「计数/总数」也算计数指标（自动生成的指标就是这种命名）。"""
    from app.plugin.module_ai.query.metric_rules import is_rowcount_metric

    assert is_rowcount_metric({"key": "FUEL_CMCS_ASSAY_count_ID", "name": "化验主表单据数"})
    assert is_rowcount_metric({"key": "count_dtxy_qyxx", "name": "区域信息条数"})
    assert is_rowcount_metric({"key": "x", "name": "入厂煤批次计数"})
    assert is_rowcount_metric({"key": "x", "name": "人员总数"})
    assert not is_rowcount_metric({"key": "sum_x", "name": "煤场进煤量合计"})
