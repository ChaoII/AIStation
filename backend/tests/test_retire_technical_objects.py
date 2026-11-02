"""技术表停用规则（纯逻辑）。

本体里混进平台自身元数据（ai_*）、备份表（*_BAK）、系统表（sys_*）。
它们的 name 就是表名、没有绑定指标 —— 既匹配不上问句，又会在检索里占坑。

这里只钉「什么算技术表」，**故意不收** view_* / annotation_* / train_*：
视图是专为问数建的，后两者是平台业务表（缺的是中文名，不是该被停用）。
"""

import pytest

from scripts.retire_technical_objects import _reason


@pytest.mark.parametrize("code,expect_prefix", [
    ("ai_pipeline", "前缀"),
    ("ai_query_concept", "前缀"),
    ("sys_user_notification", "前缀"),
    ("FUEL_CMCS_INFURNACE_BAK", "后缀"),
    ("fOO_bak", "后缀"),
])
def test_technical_tables_are_matched(code, expect_prefix):
    assert _reason(code).startswith(expect_prefix)


@pytest.mark.parametrize("code", [
    "view_aikb_infactorybatchinfo",   # 专为问数建的视图
    "VIEW_INFURNACEQUALITY",          # 源库业务视图
    "annotation_image",               # 平台业务表
    "train_tasks",
    "FUEL_CMCS_ASSAY",
    "coal_assay",
])
def test_business_objects_are_not_matched(code):
    assert _reason(code) == ""
