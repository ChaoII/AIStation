"""大小写敏感数据源的标识符加引号。

背景（实测）：ds:4 是**大小写敏感**的 PostgreSQL，表名/列名是大写，必须加双引号。
指标模板写成 `SELECT SUM(BALANCEQTY) FROM FUEL_CB_COALBALANCE` 时，PG 会把
未加引号的标识符**折成小写**（`fuel_cb_coalbalance`）→ `UndefinedTableError: 关系不存在`。

这里用 sqlglot 解析后按 schema 把标识符改写成**真实大小写 + 双引号**；
未匹配的标识符（函数名、别名、未知表）原样保留。
"""
from __future__ import annotations

from typing import Any


def _norm(name: Any) -> str:
    return str(name or "").upper()


def _identifier(name: str):
    """构造一个「已加引号」的标识符节点（兼容不同 sqlglot 版本）。"""
    from sqlglot import exp

    to_identifier = getattr(exp, "to_identifier", None)
    if to_identifier is not None:
        return to_identifier(name, quoted=True)
    return exp.Identifier(this=name, quoted=True)


def quote_schema_identifiers(sql: str, schema: dict[str, list[str]] | None) -> str:
    """把 SQL 中命中 schema 的表名/列名改写为「真实大小写 + 双引号」。

    ``schema``：``{真实表名: [真实列名, ...]}``。
    schema 为空、SQL 解析失败时**原样返回**（不猜、不破坏）。
    """
    if not sql or not schema:
        return sql
    try:
        import sqlglot
        from sqlglot import exp
    except Exception:  # noqa: BLE001 - 没装 sqlglot 就退化为原样
        return sql
    try:
        tree = sqlglot.parse_one(sql, read="postgres")
    except Exception:  # noqa: BLE001 - 解析不了就交给下游报错，别在这里改写
        return sql
    if tree is None:
        return sql

    tables: dict[str, str] = {_norm(t): t for t in schema}
    # 列池用「大写键 → 真实名列表」：**不能覆盖**。实测真库里别的表有小写同名列
    # （如 `contractprice`），一旦覆盖就会把已写对的 `CONTRACTPRICE` 改坏。
    cols_by_table: dict[str, dict[str, list[str]]] = {}
    all_cols: dict[str, list[str]] = {}

    def _add(pool: dict[str, list[str]], real: str) -> None:
        pool.setdefault(_norm(real), []).append(real)

    for t, cols in schema.items():
        pool: dict[str, list[str]] = {}
        for c in cols or []:
            if c:
                _add(pool, str(c))
        cols_by_table[_norm(t)] = pool
        for k, vs in pool.items():
            for v in vs:
                _add(all_cols, v)

    def _pick(pool: dict[str, list[str]], name: str) -> str | None:
        """按真实列名解析：**写对了（精确大小写）就别动**，否则取大小写不敏感命中。"""
        cands = pool.get(_norm(name))
        if not cands:
            return None
        if name in cands:
            return name
        return cands[0]

    # 本查询用到的表（去重）
    q_tables: list[str] = []
    for t in tree.find_all(exp.Table):
        real = tables.get(_norm(t.name))
        if real and real not in q_tables:
            q_tables.append(real)
    single_pool = cols_by_table.get(_norm(q_tables[0])) if len(q_tables) == 1 else None
    # 无限定/别名限定的列名：只用**本查询涉及的表的列**解析。
    # 用全局列池会撞到"别的表的小写同名列"，把 `FACILITYID` 引号成 `"facilityid"` →
    # PG 找不到该列（实测 ds:4 窗口函数题因此整题报错）。
    q_pool: dict[str, list[str]] = {}
    for t in q_tables:
        for vs in cols_by_table.get(_norm(t), {}).values():
            for v in vs:
                _add(q_pool, v)

    def _fix_table(node) -> None:
        real = tables.get(_norm(node.name))
        if real:
            node.set("this", _identifier(real))

    def _fix_column(node) -> None:
        qual = node.table
        if qual:
            real_t = tables.get(_norm(qual))
            if real_t:
                real_c = _pick(cols_by_table.get(_norm(real_t), {}), node.name)
                if real_c:
                    node.set("this", _identifier(real_c))
                return
        real_c = _pick(single_pool or q_pool or all_cols, node.name)
        if real_c:
            node.set("this", _identifier(real_c))

    for node in list(tree.walk()):
        if isinstance(node, exp.Table):
            _fix_table(node)
        elif isinstance(node, exp.Column):
            _fix_column(node)

    try:
        return tree.sql(dialect="postgres")
    except Exception:  # noqa: BLE001
        return sql
