"""星号止血（P0 安全修复）：含敏感列的表禁止**未展开的星号**。

漏洞背景：``select * from 表`` 在 sqlglot 解析后 ``columns=[]``，既有列级 ACL 用
``c in cols`` 判定命中列 → 星号把敏感列一起读了出来，却一条都没被拦。

本模块只做"发现"：给定 SQL 与敏感表清单，回答"这次查询有没有星号落在敏感表上"。
真正的接线（拒绝 / 展开 / 审计）在 T6/T7，本模块**不修改任何 ACL 逻辑**。

判定语义：

1. 只看**未展开**的星号：裸 ``*`` 与限定 ``t.*``；``count(*)`` 这类函数里的星号
   不算取列（否则所有计数查询都会被拒）；
2. 别名要还原成真实表名：``select f.* from fuel_price f`` → ``fuel_price``；
3. 裸 ``*`` 会展开**该 SELECT 作用域内全部表**的列，只要其中任一张敏感即算命中
   （join / 逗号连接都按此处理）；
4. 表名比较**大小写不敏感**；``public.fuel_price`` 的 schema 前缀不参与比较 ——
   带不带 schema 展开的是同一张表的全部列；
5. CTE / 子查询别名**不是真实表**：星号落在它们身上不算命中，真正的风险由**内层**
   SELECT 的星号判定覆盖（``with x as (select * from fuel_price) select * from x``
   命中 ``fuel_price``）；
6. **解析失败返回 ``"*"``**（fail-closed）：调用方据此拒绝。空 SQL / 没有敏感表
   返回 ``None``——没有敏感列可泄漏。

纯逻辑、无 IO，``PYTEST_NO_APP=1`` 可单测。
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = ["unexpanded_star"]


def _normalize(name: str | None) -> str:
    """标识符归一化：去引号/反引号、去空白、转小写（大小写不敏感比较）。"""
    return (name or "").strip().strip('"').strip("`").strip().lower()


def _sensitive_names(sensitive_tables: Iterable[str]) -> set[str]:
    """敏感表清单 → 归一化后的**裸表名**集合（``public.t`` 只取 ``t``）。"""
    out: set[str] = set()
    for raw in sensitive_tables or ():
        parts = [p for p in _normalize(raw).split(".") if p]
        if parts:
            out.add(parts[-1])
    return out


def _inside_function(star, sel, exp) -> bool:
    """星号是否位于函数调用内（``count(*)`` 不取列，必须放过）。

    只看 star 到所属 SELECT 之间的祖先链：链上出现 ``exp.Func`` 即视为聚合/函数。
    """
    node = star.parent
    while node is not None and node is not sel:
        if isinstance(node, exp.Func):
            return True
        node = node.parent
    return False


def unexpanded_star(
    sql: str,
    sensitive_tables: set[str],
    dialect: str = "postgres",
) -> str | None:
    """返回星号命中的**真实表名**；无风险返回 ``None``；解析失败返回 ``"*"``。

    Args:
        sql: 待检查的查询（单条 SELECT；其它语句也能解析，只是同样检查其内部 SELECT）。
        sensitive_tables: 含敏感列的表名集合（大小写不敏感，可带 schema 前缀）。
        dialect: sqlglot 的读方言，与 ``service.py`` 保持一致（默认 postgres）。
    """
    if not sql or not sql.strip():
        return None
    sensitive = _sensitive_names(sensitive_tables)
    if not sensitive:
        # 没有敏感列 → 星号泄漏不了任何东西，直接放过（也避免无谓的解析开销）
        return None
    try:
        import sqlglot
        from sqlglot import exp
    except Exception:  # noqa: BLE001 - 依赖缺失按风险处理
        return "*"
    try:
        # 用 parse 而不是 parse_one：parse_one 会**静默丢弃**后续语句，
        # ``select 1; select * from fuel_price`` 就查不到星号了（真实绕过写法）。
        trees = sqlglot.parse(sql, read=dialect)
    except Exception:  # noqa: BLE001 - 脏 SQL 一律按风险处理（fail-closed）
        return "*"
    if not trees:  # 非空 SQL 解析不出语法树 → 同样按风险处理
        return "*"

    for tree in trees:
        if tree is None:
            return "*"
        hit = _star_hit(tree, exp, sensitive)
        if hit:
            return hit
    return None


def _star_hit(tree, exp, sensitive: set[str]) -> str | None:
    """在单条语句的语法树里找落在敏感表上的未展开星号。"""
    # CTE 名不是真实表；内层 SELECT 会各自被检查，这里只用来排除"假表"
    cte_names = {_normalize(c.alias_or_name) for c in tree.find_all(exp.CTE)}

    for sel in tree.find_all(exp.Select):
        tables: list[str] = []
        alias_to_table: dict[str, str] = {}
        for t in sel.find_all(exp.Table):
            # 只算**直接**属于本 SELECT 的表；子查询/CTE 内部的表归属内层 SELECT
            if t.find_ancestor(exp.Select) is not sel:
                continue
            name = (t.name or "").strip()
            if not name or _normalize(name) in cte_names:
                continue
            tables.append(name)
            alias_to_table[_normalize(t.alias_or_name)] = name
        if not tables:
            continue

        for star in sel.find_all(exp.Star):
            if star.find_ancestor(exp.Select) is not sel:
                continue  # 内层 SELECT 的星号交给内层判定
            if _inside_function(star, sel, exp):
                continue  # count(*) 之类不是取列

            if isinstance(star.parent, exp.Column):
                # 限定星号 t.* / schema.table.* → 用别名映射还原真实表名
                qualifier = _normalize(star.parent.table)
                if not qualifier:
                    continue
                real = alias_to_table.get(qualifier)
                if real and _normalize(real) in sensitive:
                    return real
                continue

            # 裸星号：展开本 SELECT 作用域内所有表的全部列，任一敏感即命中
            for name in tables:
                if _normalize(name) in sensitive:
                    return name

    return None
