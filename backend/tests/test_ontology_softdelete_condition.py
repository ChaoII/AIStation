"""本体聚合的软删口径：只有表里真有 ``ISDELETED`` 列时才追加条件。

为什么锁这一条：指标快路径走 ``instance_aggregate``，而问数慢路径会补
`"ISDELETED" = false`。缺这一步时「采购计划主表有多少条」指标给 5、实际有效 4
（2026-11 留出集 v2 实测）。这条用例纯逻辑、不连库。
"""
from __future__ import annotations

from app.plugin.module_ai.ontology.service import _deleted_condition


def test_condition_only_when_column_exists():
    assert _deleted_condition({"ID", "NAME", "ISDELETED"}) == '"ISDELETED" = false'
    # 大小写不敏感（元数据里可能是小写）
    assert _deleted_condition(["id", "isdeleted"]) == '"ISDELETED" = false'


def test_condition_empty_without_column():
    assert _deleted_condition({"ID", "NAME"}) == ""
    assert _deleted_condition([]) == ""
    assert _deleted_condition(None) == ""
