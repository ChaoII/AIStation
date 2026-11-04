"""血缘（第一步：表级）：从四种来源自动推断"谁依赖谁"。

为什么不复用 `ai_query_asset_columns.related_table`
--------------------------------------------------
那个字段是**人工维护的外键配置**，是权威数据。把自动推断写回去，人工配置和
机器猜测就混在一起，以后分不清谁对。本模块只读产出到 `ai_query_lineage`，
人工字段一个都不碰。

四种来源（见 `docs/superpowers/specs/2026-11-04-ontology-lineage-design.md`）：

    fk     真外键            置信度 1.0
    view   视图 → 基表同名列  置信度 0.9
    name   XXXID → 表 *XXX    置信度 0.6（**只收唯一匹配**）
    usage  表.列被谁使用       置信度 1.0（指标 / 报表 / 历史问数）

原则：**宁缺勿错**。解析失败返回空集、只记 warning，绝不让一条脏 SQL 把整次重算打断。
"""
from __future__ import annotations

import re
from typing import NamedTuple


class Edge(NamedTuple):
    """一条血缘边：`src → dst`。`usage` 边没有 dst，用 ref_kind/ref_key 表示"被谁用"。"""

    kind: str                     # fk | view | name | usage
    src_table: str
    src_column: str | None = None
    dst_table: str | None = None
    dst_column: str | None = None
    ref_kind: str | None = None   # usage: metric | report | ask
    ref_key: str | None = None
    confidence: float = 1.0


#: 开关关闭时返回的固定空结构（避免调用方各自造 dict）
EMPTY_LINEAGE: dict = {
    "upstream": [],
    "downstream": [],
    "used_by": [],
    "sensitive_columns": [],
}


def infer_name_edges(columns_by_table: dict[str, set[str]]) -> list[Edge]:
    """列 `XXXID` → 表名以 `XXX` 结尾的表。

    **只收唯一匹配**：`ID`、`USERID`、`CREATEDID` 这类列在多张表上都可能成立，
    连错了比不连更糟（影响分析会给出假答案）。真外键（`fk`）不受此限。
    """
    table_names = sorted(columns_by_table)
    edges: list[Edge] = []
    for table, cols in columns_by_table.items():
        for col in cols:
            if col == "ID" or not col.endswith("ID") or len(col) <= 3:
                continue
            base = col[:-2].rstrip("_")
            if not base:
                continue
            cands = [tn for tn in table_names if tn.endswith(base) and tn != table]
            if len(cands) != 1:
                continue
            edges.append(Edge("name", table, col, cands[0], "ID", confidence=0.6))
    return edges


def tables_in_sql(sql: str) -> set[str]:
    """SQL 里出现的表名（大写）。解析失败返回空集 —— 脏 SQL 不该打断重算。"""
    if not sql or not sql.strip():
        return set()
    try:
        import sqlglot
        from sqlglot import exp
    except ImportError:  # pragma: no cover - 依赖缺失时降级
        return set()
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:  # noqa: BLE001
        return set()
    return {t.name.upper() for t in tree.find_all(exp.Table) if t.name}


def columns_used(sql: str, table: str, columns: set[str]) -> set[str]:
    """SQL 文本里出现过的、属于 `table` 的列名（大写）。

    第一步接受这种**粗粒度**匹配（列名以单词边界出现即算）。真正的列级解析
    （`SELECT *` 展开、别名、CTE）是第二步，等这里的数字出来再决定值不值得做。
    """
    if not sql or not columns:
        return set()
    up = sql.upper()
    return {c for c in columns if re.search(rf"\b{re.escape(c)}\b", up)}
