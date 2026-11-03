"""值匹配纠错：把 SQL 里"归一后相等但写法不同"的字面量换成库里的原样写法。

对齐 Databricks Genie 的 entity matching：它的做法是**匹配纠错**（用户说 Florida、
库里存 FL，自动映射），而不是把取值列进提示词让模型自己挑。我们之前做的是后者，
三次实测都没有收益。

这里只做**语义上绝对等价**的归一：去首尾空白、全角→半角、ASCII 大小写。
不做编辑距离/模糊匹配——那会改语义。
"""

from app.plugin.module_ai.query.service import AiQueryService as S

VMAP = {
    ("DTXY_PMXX", "COALTYPE"): ["烟煤", "无烟煤", "褐煤"],
    ("FUEL_CMCS_MINE", "NAME"): ["河曲露天", "FL"],
}


def test_trailing_space_is_fixed():
    sql = "SELECT * FROM \"DTXY_PMXX\" WHERE \"COALTYPE\" = '烟煤 '"
    fixed, fixes = S.fix_sql_literals(sql, VMAP)
    assert "'烟煤'" in fixed and "烟煤 " not in fixed
    assert fixes and "烟煤" in fixes[0]


def test_fullwidth_and_case_are_fixed():
    sql = "SELECT * FROM \"FUEL_CMCS_MINE\" WHERE \"NAME\" = 'ｆｌ'"
    fixed, fixes = S.fix_sql_literals(sql, VMAP)
    assert "'FL'" in fixed
    assert fixes


def test_exact_value_is_left_alone():
    sql = "SELECT * FROM \"DTXY_PMXX\" WHERE \"COALTYPE\" = '烟煤'"
    fixed, fixes = S.fix_sql_literals(sql, VMAP)
    assert fixed == sql
    assert fixes == []


def test_unknown_value_is_not_guessed():
    """库里没有的值一律不动 —— 不能"猜"成最近的值。"""
    sql = "SELECT * FROM \"DTXY_PMXX\" WHERE \"COALTYPE\" = '焦煤'"
    fixed, fixes = S.fix_sql_literals(sql, VMAP)
    assert fixed == sql
    assert fixes == []


def test_escaped_quote_survives():
    sql = "SELECT * FROM \"FUEL_CMCS_MINE\" WHERE \"NAME\" = 'FL' AND 1=1"
    fixed, _ = S.fix_sql_literals(sql, VMAP)
    assert fixed == sql


def test_no_value_map_is_noop():
    sql = "SELECT 1"
    assert S.fix_sql_literals(sql, {}) == (sql, [])
