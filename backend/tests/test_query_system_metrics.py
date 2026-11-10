"""系统域（组态/人脸/小程序）计数指标与「明细条数」列举判定回归。

实测 2026-11-10：
- 「原煤仓入煤明细条数是多少」被 `is_listing_question` 的「明细」判成列举 →
  指标已匹配上却被踢去慢路径（多花约 8 秒）。
- ds:4 里 CMMS_CANVAS / FR_PERSONNELINFO 等表一个指标都没有 → 只能走慢路径。
- 「人员信息中男性有多少人」是 WHERE 筛选，不能被「人员总数」指标抢答。
"""
from app.plugin.module_ai.query.metric_rules import match_metric, needs_custom_sql
from app.plugin.module_ai.query.question_rules import is_listing_question


def _m(key, name, desc, agg="count"):
    return {"key": key, "name": name, "description": desc, "enabled": True,
            "agg": agg, "params": [], "dimensions": [], "sql_template": "",
            "object_code": "", "property_code": "", "agg_fn": agg,
            "bound_dimensions": []}


SYSTEM_METRICS = [
    _m("CMMS_CANVAS_count_ID", "组态画面总数", "组态画面（CMMS_CANVAS）的记录数量"),
    _m("CMMS_COMPONENT_count_ID", "组件数量", "组态组件（CMMS_COMPONENT）的记录数量"),
    _m("CMMS_COMPONENTCLASSIFICATION_count_ID", "组件分类总数",
       "组件分类（CMMS_COMPONENTCLASSIFICATION）的记录数量"),
    _m("CMMS_CANVASCOMPONENT_count_ID", "组件引用记录数",
       "组态画面引用组件（CMMS_CANVASCOMPONENT）的记录数量"),
    _m("FR_PERSONNELINFO_count_ID", "人员总数", "人脸识别人员信息（FR_PERSONNELINFO）的记录数量"),
    _m("CMCS_APPVERSION_count_ID", "小程序版本记录数", "小程序版本管理（CMCS_APPVERSION）的记录数量"),
]


def test_listing_count_override():
    """带「明细」但问的是条数时，不算列举。"""
    assert is_listing_question("原煤仓入煤明细条数是多少") is False
    assert is_listing_question("燃煤结算明细表的运损总和是多少") is False


def test_real_listing_stays_listing():
    assert is_listing_question("列出结算明细") is True
    assert is_listing_question("结算明细有哪些") is True
    assert is_listing_question("各煤种的名称分别是什么") is True


def test_system_metrics_match_their_questions():
    cases = {
        "组态画面一共有多少个？": "CMMS_CANVAS_count_ID",
        "当前系统中有多少个组件？": "CMMS_COMPONENT_count_ID",
        "总共有多少个组件分类？": "CMMS_COMPONENTCLASSIFICATION_count_ID",
        "人脸识别人员信息表里一共有多少人员？": "FR_PERSONNELINFO_count_ID",
        "小程序版本管理表中共有多少条版本记录？": "CMCS_APPVERSION_count_ID",
    }
    for q, expected in cases.items():
        got = match_metric(q, SYSTEM_METRICS, [])
        assert got and got["key"] == expected, f"{q} 实际: {got and got['key']}"


def test_gender_filter_never_uses_count_metric():
    """「男性有多少人」是筛选条件，必须让位 NL2SQL。"""
    assert needs_custom_sql("人脸识别人员信息中男性有多少人？") is True
