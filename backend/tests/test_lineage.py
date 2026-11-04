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

def test_rebuild_is_idempotent_and_safe_without_datasource(db_run):
    """空库/数据源不存在时：不崩、可重复跑（幂等）。

    ⚠️ 与计划里的差异：原计划断言"total > 500"，但 pytest 用的是**空的 SQLite
    测试库**，没有 ds:4 的 schema/指标，也没有可连的远端库，断言不出来。
    "> 500" 属于**对 dev 库的验收**，在 Task 3 用真实库跑过：
        {'fk': 16, 'view': 328, 'name': 250, 'usage': 3706, 'total': 4300}
    这里保留可自动化的部分：远端取不到时四路都要**静默降级**而不是抛异常。
    """
    from app.plugin.module_ai.query import lineage as L

    first = db_run(L.rebuild_lineage(4))
    second = db_run(L.rebuild_lineage(4))
    assert first == second                      # 幂等
    assert set(first) == {"fk", "view", "name", "usage", "total"}
    # 远端不可用 → fk/view 为 0，但函数必须正常返回（不能抛）
    assert first["fk"] == 0 and first["view"] == 0

def test_impact_lineage_off_by_default(db_run):
    """开关默认关：返回固定空结构，旧字段一个不少（不破坏既有消费方）。"""
    from app.plugin.module_ai.query.service import AiQueryService as S

    d = db_run(S.impact_analysis("FUEL_CMCS_INFACTORYBATCH"))
    assert d["lineage"] == {"upstream": [], "downstream": [], "used_by": [],
                            "sensitive_columns": []}
    for k in ("table", "metrics", "incoming_relations", "object_links"):
        assert k in d


def test_lineage_for_table_shape(db_run):
    """按表查询永远返回四个键（空库也不能是 None/异常）。"""
    from app.plugin.module_ai.query import lineage as L

    d = db_run(L.lineage_for_table("ds:4", "FUEL_CMCS_INFACTORYBATCH"))
    assert set(d) == {"upstream", "downstream", "used_by", "sensitive_columns"}
    assert isinstance(d["upstream"], list) and isinstance(d["sensitive_columns"], list)

def test_coverage_shape(db_run):
    from app.plugin.module_ai.query import lineage as L

    c = db_run(L.lineage_coverage("ds:4"))
    assert set(c) == {"tables_total", "tables_with_edges", "columns_total",
                      "columns_with_edges", "by_kind"}
    assert c["tables_total"] >= 0 and c["columns_with_edges"] >= 0


def test_routes_registered():
    """两条路由必须真在 app.routes 里（防止被别的路径参数路由吃掉/漏注册）。"""
    from main import create_app

    paths = {getattr(r, "path", "") for r in create_app().routes}
    # 注册路径不含 ROOT_PATH（/api/v1 是 include 时加的）
    assert "/ai/query/lineage/coverage" in paths
    assert "/ai/query/lineage/rebuild" in paths
