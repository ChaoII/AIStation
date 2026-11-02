"""本体对象名回填脚本的取名规则（纯逻辑，不需要数据库）。

背景：422 个对象里 162 个 ``name == code``（自动导入时没带中文名），
导致「区域一共有多少个？」这种问法匹配不上「区域数量」这个指标。
脚本从三个来源回填：数据源表注释 → 平台资产别名 → 绑定指标名（剥度量词）。
这里钉住"什么算一个合格的候选名"，避免把半截注释或表名写进本体。
"""

from scripts.fill_ont_object_names import _clean


def test_keeps_real_chinese_comment():
    assert _clean("  区域信息  ", "DTXY_QYXX") == "区域信息"


def test_takes_first_clause_of_long_comment():
    assert _clean("化验单主表。含水分、灰分等指标", "FUEL_CMCS_ASSAY") == "化验单主表"


def test_rejects_comment_equal_to_table_name():
    assert _clean("FUEL_CMCS_ASSAY", "FUEL_CMCS_ASSAY") == ""


def test_rejects_comment_containing_table_name():
    """实测踩过：资产描述里带表名（"数据 ai_access_rule"），那不是中文名。"""
    assert _clean("数据 ai_access_rule", "ai_access_rule") == ""


def test_rejects_empty_and_overlong_ascii():
    assert _clean("", "t") == ""
    assert _clean("a very long english only description " * 3, "t") == ""
