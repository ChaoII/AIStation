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
4. **作用域感知的 CTE 识别**（``sqlglot.optimizer.scope.traverse_scope``）：
   只有**本作用域真正可见**的 CTE 名才算"假表"——本 SELECT 的 WITH（按 PG 语义
   定义在前的才可见）+ 祖先作用域链；CTE 体内的引用**看不到自身名字**（非递归）；
   **带 schema 限定的引用永远是真实表**（``with fuel_price as (...) select * from
   public.fuel_price`` 必须命中）。不能用"全语句 CTE 名集合"，那会把同名真表误判成
   假表而静默放行；
5. 表名比较**大小写不敏感**：``public.fuel_price`` / ``"public"."Fuel_Price"`` 都归成
   裸表名 ``fuel_price``；返回的也是**归一化（小写、去 schema）的真实表名**；
6. **解析失败返回 ``"*"``**（fail-closed）：调用方据此拒绝。空 SQL / 没有敏感表
   返回 ``None``——没有敏感列可泄漏。

⚠️ T6 接线注意口径差异：本模块**大小写不敏感**且**去掉 schema**，而
``service._sensitive_asset_cols`` 是 ``table_name == table`` 的**精确匹配**、敏感表清单
也来自字段资产目录的原始写法。调用方拿返回值去查敏感列时需自行归一（例如
``table.split(".")[-1]`` 后按库内实际写法比对），否则混合大小写/带 schema 的表名会失配。

纯逻辑、无 IO，``PYTEST_NO_APP=1`` 可单测。
"""

from __future__ import annotations

from collections.abc import Iterable

__all__ = ["unexpanded_star"]


def _normalize(name: str | None) -> str:
    """标识符归一化：去引号/反引号、去空白、转小写（大小写不敏感比较）。"""
    return (name or "").strip().strip('"').strip("`").strip().lower()


def _sensitive_names(sensitive_tables: Iterable[str]) -> set[str]:
    """敏感表清单 → 归一化后的**裸表名**集合。

    必须**按 ``.`` 分段后逐段去引号**：整体 ``strip('"')`` 会把
    ``'"public"."Fuel_Price"'`` 变成 ``'"fuel_price'``（残留引号），永不匹配（fail-open）。
    """
    out: set[str] = set()
    for raw in sensitive_tables or ():
        parts = [_normalize(p) for p in (raw or "").split(".")]
        parts = [p for p in parts if p]
        if parts:
            out.add(parts[-1])
    return out


def _inside_function(star, scope_expression, exp) -> bool:
    """星号是否位于函数调用内（``count(*)`` 不取列，必须放过）。

    只看 star 到所属作用域根表达式之间的祖先链：链上出现 ``exp.Func`` 即视为聚合/函数。
    """
    node = star.parent
    while node is not None and node is not scope_expression:
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
        sensitive_tables: 含敏感列的表名集合（大小写不敏感，可带 schema 前缀与引号）。
        dialect: sqlglot 的读方言，与 ``service.py`` 保持一致（默认 postgres）。

    Returns:
        命中的真实表名（**归一化后的小写裸表名**，如 ``fuel_price``）；
        ``None`` = 无风险；``"*"`` = 无法安全判定，调用方应拒绝。
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
        if isinstance(tree, exp.Command):
            # sqlglot 遇到不支持的语法会退化成 Command（stdout 会打一条 warning），
            # 此时遍历不到任何 star，若返回 None 就是静默放行 → fail-closed。
            return "*"
        try:
            hit = _star_hit(tree, sensitive)
        except Exception:  # noqa: BLE001 - 遍历阶段意外抛错不能冒泡（fail-closed）
            return "*"
        if hit:
            return hit
    return None


def _star_hit(tree, sensitive: set[str]) -> str | None:
    """在单条语句的语法树里找落在敏感表上的未展开星号（按作用域判定）。"""
    from sqlglot import exp
    from sqlglot.optimizer.scope import traverse_scope

    for scope in traverse_scope(tree):
        # ``scope.cte_sources`` 就是"该作用域真正可见的 CTE"：本 SELECT 的 WITH
        # （CTE 体内只有定义在前的兄弟 CTE，非递归时不含自身）+ 祖先作用域链。
        # 绝不能用全语句的 CTE 名集合 —— 那会把同名真表一起遮住（Critical 绕过）。
        cte_names = {_normalize(name) for name in scope.cte_sources}

        tables: list[str] = []
        alias_to_table: dict[str, str] = {}
        for t in scope.tables:
            name = (t.name or "").strip()
            if not name:
                continue
            # schema 限定（public.t）不可能是 CTE 引用，永远是真实表
            if not (t.db or t.catalog) and _normalize(name) in cte_names:
                continue
            tables.append(name)
            alias_to_table[_normalize(t.alias_or_name)] = name
        if not tables:
            continue

        for star in scope.find_all(exp.Star):
            if _inside_function(star, scope.expression, exp):
                continue  # count(*) 之类不是取列

            if isinstance(star.parent, exp.Column):
                # 限定星号 t.* / schema.table.* → 用别名映射还原真实表名
                qualifier = _normalize(star.parent.table)
                if not qualifier:
                    continue
                real = alias_to_table.get(qualifier)
                if real and _normalize(real) in sensitive:
                    return _normalize(real)
                continue

            # 裸星号：展开本作用域内所有表的全部列，任一敏感即命中
            for name in tables:
                if _normalize(name) in sensitive:
                    return _normalize(name)

    return None
