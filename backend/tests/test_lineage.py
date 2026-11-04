"""血缘（第一步：表级）测试。

设计见 `docs/superpowers/specs/2026-11-04-ontology-lineage-design.md`，
实现计划见 `docs/superpowers/plans/2026-11-04-ontology-lineage.md`。

纯逻辑用例用 `PYTEST_NO_APP=1` 跑（约 2 秒）；需要应用的用例在文件后半段。
"""
from __future__ import annotations

import asyncio

from app.plugin.module_ai.query.lineage import (
    Edge,
    columns_used,
    infer_name_edges,
    tables_in_sql,
)


def _run(coro):
    """在测试里跑协程（项目没有 pytest-asyncio）。"""
    return asyncio.run(coro)


def test_name_edges_only_unique_match():
    """`XXXID` → 表 `*XXX`，**只收唯一匹配**。"""
    cols = {
        "FUEL_CMCS_INFACTORYBATCH": {"ID", "INFACTORYBATCHID", "MINENAME"},
        "FUEL_CMCS_ASSAY": {"ID", "INFACTORYBATCHID", "USERID"},
        "SYS_USER": {"ID"},
    }
    edges = infer_name_edges(cols)
    got = {(e.src_table, e.src_column, e.dst_table) for e in edges}
    # INFACTORYBATCHID 唯一匹配 FUEL_CMCS_INFACTORYBATCH
    assert ("FUEL_CMCS_ASSAY", "INFACTORYBATCHID", "FUEL_CMCS_INFACTORYBATCH") in got
    # USERID：没有唯一候选表（SYS_USER 不以 USER 结尾？它确实以 USER 结尾）
    # —— 此例中 SYS_USER 是唯一候选，故允许连；这里断言的是"不连到自己"
    assert all(e.dst_table != e.src_table for e in edges)
    # 自身 ID 不连自己
    assert all(e.src_column != "ID" for e in edges)
    assert all(e.kind == "name" and e.confidence == 0.6 for e in edges)
    assert all(e.dst_column == "ID" for e in edges)


def test_name_edges_skip_ambiguous_columns():
    """多候选（两表都以同一前缀结尾）时一律丢弃 —— 宁可少连。"""
    cols = {
        "T1": {"ORDERID"},
        "A_ORDER": {"ID"},
        "B_ORDER": {"ID"},
    }
    edges = infer_name_edges(cols)
    assert all(e.src_column != "ORDERID" for e in edges)


def test_edge_defaults():
    e = Edge("usage", "T", "C", None, None, ref_kind="metric", ref_key="k")
    assert e.confidence == 1.0 and e.dst_table is None


def test_tables_and_columns_from_sql():
    sql = (
        'SELECT "MINENAME", COUNT(*) FROM "FUEL_CMCS_INFACTORYBATCH" b '
        'JOIN "FUEL_CMCS_ASSAY" a ON a."INFACTORYBATCHID" = b."ID" '
        'WHERE b."ISDELETED" = false'
    )
    assert tables_in_sql(sql) == {"FUEL_CMCS_INFACTORYBATCH", "FUEL_CMCS_ASSAY"}
    cols = columns_used(sql, "FUEL_CMCS_INFACTORYBATCH",
                        {"ID", "MINENAME", "ISDELETED", "REMARK"})
    assert cols == {"ID", "MINENAME", "ISDELETED"}


def test_bad_sql_returns_empty():
    """脏 SQL 不能打断重算：解析失败一律返回空集。"""
    assert tables_in_sql("this is not sql") == set()
    assert columns_used("this is not sql", "T", {"A"}) == set()
    assert tables_in_sql("") == set()
