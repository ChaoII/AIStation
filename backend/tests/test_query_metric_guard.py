"""指标护栏（二版）：计数型指标必须有「指标名 / 表名 / 业务别名」证据。

背景：一版护栏在别名为空时上线 → 把「多少份燃煤合同」的正确指标挡掉（105 掉到 98.1%），
已回退。现在别名数据补齐（资产中文名 + 本体对象别名 46 个），同规则重跑并用本用例锁住：
- 误劫持必须挡住（供应商煤质限制 / 配煤方案分仓明细）；
- 正常快路径不能被误伤（燃煤合同、库存这类 sum 指标）。
"""
from __future__ import annotations

from app.plugin.module_ai.query.metric_rules import (
    _competitor_alias,
    _metric_table_evidence,
    match_metric,
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
