"""SQL 编译器：把 :class:`AccessPlan` 落实成「行包装 + 列投影 + 掩码」。

设计稿：``docs/superpowers/specs/2026-11-06-query-permission-model-design.md`` §5.1/§5.2/§5.3。

两个入口（纯逻辑，不读库、不接线）::

    plan = build_plan(policies, principal, {"t": ["id", "phone"]})
    decision = rewrite(sql, plan)          # decision.sql 是编译后的可执行 SQL
    if not decision.permit:
        raise CustomException(decision.reason)

编译顺序（**先列改写、后行包装**）：

1. 解析（单条 SELECT，其它一律 deny）；
2. 逐作用域（``traverse_scope``）识别**真实表**：CTE 名不算表，带 schema 限定的引用
   永远是真实表（与 ``star.py`` 同口径）；
3. 表级/列级 deny 判定：deny 列出现在投影/条件/排序/分组都拒绝；
4. 列投影改写：``*`` / ``t.*`` 按 ``allowed_columns`` 展开，``masked`` 列在投影处替换；
5. 行包装：``FROM t AS x`` → ``FROM (SELECT * FROM t WHERE <pred>) AS x``，**逐表**执行；
6. 重新生成 SQL，并把用户的 ``:name`` 占位符恢复成原前缀。

为什么先列改写、后行包装：包装里的 ``SELECT *`` 是编译中间态，**不参与**列策略判定。
若先包装再列改写，那个 ``*`` 会被自己的 ``allowed_columns`` 拦死（自锁）。顺序本身就是
标记，不需要额外打节点属性。

几条硬约定：

- **逐表包装**：``AccessPlan.row_filters`` 是「表名 → 条件」，编译器绝不把不同表的条件
  ``OR`` 到一起（T6 评审：``union_condition`` 遇到任一空串会把整组吸收，另一张表的行过滤
  就被静默丢掉，用户看到的是"过滤没生效"）；
- **行条件先过 AST 白名单**：``Policy.condition`` 是管理员配置的字符串。只允许
  列/字面量/比较/``AND OR NOT``/``IN``/``LIKE``/``IS NULL``/括号；子查询、函数、
  ``;``、DDL/DML 关键字、注释一律 deny。条件里的 ``$attr.*`` / ``$user.id`` 由
  :func:`build_plan` 在编译期绑定为**安全转义的字面量**（``Decision`` 没有参数通道，
  ``:p_policy_<n>`` 的参数化留给接线时再改；绑定失败会留一个 ``$`` 占位符让本模块拒绝）；
- **CTE 名不是表**：``with x as (select * from t) select * from x`` 不能把给 ``x`` 的
  策略套到 CTE 引用上，也不能把 ``x`` 当成未覆盖的表拒绝；
- **fail-closed**：解析失败 / 非 SELECT / 多语句 / 条件或掩码表达式不合法 / 查询里的表
  不在计划内 → ``Decision(False, reason=...)``，**不抛异常**；``applied`` 记录实际施加的
  改写（``{"row": ...}`` / ``{"mask": ...}`` / ``{"star": "unexpanded"}``）。

``Decision.policy_ids`` 恒为空：``AccessPlan`` 的接口没有策略 id（签名不可改），审计用的
策略 id 由 ``build_plan`` 的调用方（网关）自行合并。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .engine import (
    Decision,
    _attr_values,
    _is_enabled,
    _table_key,
    decide_column,
    decide_table,
)

if TYPE_CHECKING:  # 运行时不依赖 principal（它要连库），保持纯逻辑与可单测
    from .engine import Policy
    from .principal import Principal

try:  # sqlglot 是硬依赖；缺失时按 deny 处理，不炸整站
    import sqlglot
    from sqlglot import exp
    from sqlglot.optimizer.scope import traverse_scope
except Exception:  # noqa: BLE001 # pragma: no cover - 依赖缺失只在极端环境发生
    sqlglot = None  # type: ignore[assignment]
    exp = None  # type: ignore[assignment]
    traverse_scope = None  # type: ignore[assignment]

__all__ = ["DENIED_ALL", "AccessPlan", "build_plan", "rewrite"]

#: ``denied[table]`` 里的整表拒绝哨兵。
#:
#: ``AccessPlan`` 的字段是接口固定的（没有"表级拒绝"字段），而"表没有任何适用的
#: allow"必须能被表达出来。列名不可能是 ``*``，因此用它作哨兵：
#: 出现即表示**整张表不可读**（包括 ``select 1 from t`` 这种不带列引用的查询）。
DENIED_ALL = "*"

#: 行条件里的属性引用（与 ``engine`` 同口径）。
_ATTR_REF = re.compile(r"\$attr\.([A-Za-z_][A-Za-z0-9_]*)\b")
#: 行条件里的用户 id 引用。
_USER_ID_REF = re.compile(r"\$user\.id\b")
#: ``col = $attr.x``：属性是多值时改写成 ``col IN (...)`。
_EQ_ATTR_REF = re.compile(
    r"(?P<col>[A-Za-z_][A-Za-z0-9_.]*)\s*=\s*\$attr\.(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b"
)
#: 条件/掩码里禁止出现的写操作与 DDL 关键字（词边界，避免误伤 created/updated 之类）。
_DDL_WORDS = re.compile(
    r"\b(alter|call|copy|create|delete|do|drop|execute|grant|insert|merge|revoke|"
    r"truncate|update|vacuum)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AccessPlan:
    """一次查询的访问计划（``build_plan`` 产出，``rewrite`` 消费）。

    - ``row_filters``：表名（归一化小写裸名）→ 行过滤条件，**按表**；
    - ``allowed_columns``：表名 → 可读列（星号展开的来源）。``None`` = 无列元数据
      （无法展开，保留星号）；空元组 = 一列都不可读；
    - ``masked``：表名 → {列名（小写）: 掩码表达式}；
    - ``denied``：表名 → 不可读列（小写）；含 :data:`DENIED_ALL` 表示整表拒绝。

    冻结点只防字段重绑，dict 本身仍可读；调用方不要改它。
    """

    row_filters: dict[str, str]
    allowed_columns: dict[str, tuple[str, ...] | None]
    masked: dict[str, dict[str, str]]
    denied: dict[str, frozenset[str]]


# ---------------------------------------------------------------------------
# 条件绑定（build_plan 侧）
# ---------------------------------------------------------------------------
def _sql_literal(value) -> str:
    """把属性值转成 SQL 字面量。

    字符串**一律加引号**（即使看起来是数字）：``dept_id = '3'`` 在 PG 里是 unknown
    字面量、会按列类型隐式转换，对 int 与 text 列都成立；反过来把 ``'3'`` 当数字内联，
    遇到 text 列会直接报类型错。引号内的 ``'`` 双写转义。
    """
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def _attr_literal(attrs: dict, name: str):
    """单值属性 → 字面量；多值返回 ``None``（调用方决定能否表达）。"""
    values = _attr_values(attrs.get(name.lower()))
    return values[0] if len(values) == 1 else None


def _bind_condition(condition: str, principal: Principal) -> str:
    """把 ``$attr.*`` / ``$user.id`` 绑定成字面量（只处理引擎判定为"条件成立"的策略）。

    多值属性：只在 ``col = $attr.x`` 的位置改写成 ``col IN (v1, v2)``；其它位置无法用
    单个字面量表达，**原样保留占位符**——:func:`rewrite` 会因条件里残留 ``$`` 而拒绝
    （fail-closed，不猜、不丢条件）。

    缺属性/缺身份：引擎的 ``applicable_condition`` 已经把这些 ``allow`` 排除了，正常
    不会走到这里；真出现时以 ``1 = 0`` / ``NULL`` 兜底（宁可查不到行，也不放宽）。
    """
    attrs = {
        str(k).lower(): v
        for k, v in (getattr(principal, "attrs", None) or {}).items()
    }

    def _eq_repl(m: re.Match) -> str:
        values = _attr_values(attrs.get(m.group("name").lower()))
        if not values:
            return "1 = 0"
        col = m.group("col")
        if len(values) == 1:
            return f"{col} = {_sql_literal(values[0])}"
        return f"{col} IN ({', '.join(_sql_literal(v) for v in values)})"

    out = _EQ_ATTR_REF.sub(_eq_repl, condition or "")

    def _attr_repl(m: re.Match) -> str:
        literal = _attr_literal(attrs, m.group(1))
        # 多值/缺失 → 保留原占位符，交给 rewrite 拒绝
        return m.group(0) if literal is None else _sql_literal(literal)

    out = _ATTR_REF.sub(_attr_repl, out)

    uid = getattr(principal, "user_id", None)
    out = _USER_ID_REF.sub(str(int(uid)) if uid else "NULL", out)
    return out


def _table_marking(policies, table: str) -> str:
    """该表是否带标记（如 ``sensitive``）。

    标记是**表属性**，不是主体属性：只看启用 + 资源命中 + ``resource_kind in
    {"table","view"}``，不要求主体命中（否则换个角色就能把"带标记"变成"无标记"）。
    """
    for policy in policies or ():
        if policy is None or not _is_enabled(getattr(policy, "enabled", True)):
            continue
        kind = str(getattr(policy, "resource_kind", "") or "").strip().lower()
        if kind not in {"table", "view"}:
            continue
        if _table_key(getattr(policy, "resource_code", "")) != table:
            continue
        marking = str(getattr(policy, "marking", "") or "").strip()
        if marking:
            return marking
    return ""


def _metadata_columns(columns) -> list[str]:
    """列元数据归一：去空、去重（保序）、保留原始大小写（展开时要按真实标识符输出）。"""
    out: list[str] = []
    seen: set[str] = set()
    if isinstance(columns, dict):  # 兼容“列名 → 类型”的元数据写法
        columns = list(columns)
    if not isinstance(columns, (list, tuple, set, frozenset)):
        return out
    for raw in columns:
        name = str(raw or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
    return out


# ---------------------------------------------------------------------------
# 计划构建
# ---------------------------------------------------------------------------
def build_plan(
    policies: list[Policy], principal: Principal, tables: dict[str, list[str]]
) -> AccessPlan:
    """把策略 + 主体 + 表/列元数据算成 :class:`AccessPlan`（纯函数）。

    参数 ``tables`` 是**查询涉及的全部真实表** → 列清单（空列表 = 没有列元数据）。
    每张输入表都会在计划里留下一条记录（``allowed_columns`` 或 ``denied``），
    ``rewrite`` 据此对"计划没覆盖的表"fail-closed。

    逐表复用引擎，不另写一套并集/缺属性判断：

    - ``decide_table`` → 表级 allow/deny + 行条件并集（``union_condition`` 语义）；
    - ``decide_column`` → 列级 deny / mask / 继承；
    - 行条件在此处绑定主体属性（见 :func:`_bind_condition`）。
    """
    row_filters: dict[str, str] = {}
    allowed_columns: dict[str, tuple[str, ...] | None] = {}
    masked: dict[str, dict[str, str]] = {}
    denied: dict[str, frozenset[str]] = {}

    for raw_table, raw_columns in (tables or {}).items():
        table = _table_key(raw_table)
        if not table:
            continue

        table_decision = decide_table(policies, principal, table)
        if not table_decision.permit:
            # 表级拒绝（含"没有任何适用的 allow"）：用哨兵表达整表不可读
            denied[table] = frozenset({DENIED_ALL})
            continue

        if table_decision.sql:
            row_filters[table] = _bind_condition(table_decision.sql, principal)

        columns = _metadata_columns(raw_columns)
        if not columns:
            # 无列元数据：带标记 → 拒绝（不放未知列）；否则保留星号并记审计
            if _table_marking(policies, table):
                denied[table] = frozenset({DENIED_ALL})
            else:
                allowed_columns[table] = None
            continue

        blocked: set[str] = set()
        masks: dict[str, str] = {}
        readable: list[str] = []
        for column in columns:
            column_decision = decide_column(policies, principal, table, column)
            if not column_decision.permit:
                blocked.add(column.lower())
                continue
            readable.append(column)
            for item in column_decision.applied:
                expr = str(item.get("mask") or "").strip()
                if expr:
                    masks[column.lower()] = expr

        allowed_columns[table] = tuple(readable)
        if blocked:
            denied[table] = frozenset(blocked)
        if masks:
            masked[table] = masks

    return AccessPlan(
        row_filters=row_filters,
        allowed_columns=allowed_columns,
        masked=masked,
        denied=denied,
    )


# ---------------------------------------------------------------------------
# 条件/掩码表达式校验
# ---------------------------------------------------------------------------
def _allowed_condition_nodes() -> tuple:
    """行条件允许的 AST 节点（spec §5.2 的安全子集）。"""
    return (
        exp.Column,
        exp.Identifier,
        exp.Literal,
        exp.Boolean,
        exp.Null,
        exp.Neg,
        exp.Paren,
        exp.And,
        exp.Or,
        exp.Not,
        exp.EQ,
        exp.NEQ,
        exp.GT,
        exp.GTE,
        exp.LT,
        exp.LTE,
        exp.In,
        exp.Like,
        exp.ILike,
        exp.Is,
        exp.Between,
        exp.Tuple,
    )


def _compile_condition(raw: str, dialect: str):
    """校验并解析管理员行条件；返回 ``(表达式, 错误原因)``，成功时错误原因为空串。

    只在 AST 层放行白名单节点：子查询/函数/``CASE``/``CAST`` 等一律拒绝——
    管理员输入视为可信，但**先过 AST**，避免"配置错误"变成注入面。
    """
    text = str(raw or "").strip()
    if not text:
        return None, ""
    if "$" in text:
        return None, "条件里残留未绑定的策略参数（如 $attr.* / $user.id）"
    if ";" in text:
        return None, "条件里不允许分号（防多条语句）"
    if "--" in text or "/*" in text or "*/" in text:
        return None, "条件里不允许注释"
    if _DDL_WORDS.search(text):
        return None, "条件里不允许 DDL/DML 关键字"
    try:
        parsed = sqlglot.parse_one(text, read=dialect)
    except Exception as e:  # noqa: BLE001 - 脏条件按拒绝处理
        return None, f"条件无法解析：{e}"
    if parsed is None or isinstance(parsed, (exp.Select, exp.Subquery, exp.Command)):
        return None, "条件只允许布尔表达式（不允许子查询/语句）"
    allowed = _allowed_condition_nodes()
    for node in parsed.walk():
        if not isinstance(node, allowed):
            return None, f"条件包含不允许的语法：{type(node).__name__}"
    return parsed, ""


def _compile_mask(raw: str, dialect: str, alias: str | None):
    """校验并解析掩码表达式；返回 ``(表达式, 错误原因)``。

    掩码表达式与行条件同源（管理员配置），同样不允许子查询/多条语句/DDL；函数不设
    白名单（spec §5.3 的白名单属于配置侧校验，编译器只保证不会变成取数旁路）。
    给出 ``alias`` 时把表达式里未限定的列挂到该表上（join 下避免歧义）。
    """
    text = str(raw or "").strip()
    if not text:
        return None, "掩码表达式为空"
    if ";" in text:
        return None, "掩码表达式里不允许分号"
    if _DDL_WORDS.search(text):
        return None, "掩码表达式里不允许 DDL/DML 关键字"
    try:
        parsed = sqlglot.parse_one(text, read=dialect)
    except Exception as e:  # noqa: BLE001
        return None, f"掩码表达式无法解析：{e}"
    if parsed is None or isinstance(parsed, (exp.Select, exp.Subquery, exp.Command)):
        return None, "掩码表达式不允许子查询/语句"
    for node in parsed.walk():
        if isinstance(node, (exp.Select, exp.Subquery, exp.Command)):
            return None, "掩码表达式不允许子查询"
    if alias:
        for column in parsed.find_all(exp.Column):
            if not column.table:
                column.set("table", exp.to_identifier(alias))
    return parsed, ""


# ---------------------------------------------------------------------------
# 编译（rewrite 侧）
# ---------------------------------------------------------------------------
def _norm_ident(name) -> str:
    """标识符归一（去引号/反引号、小写）；表的 schema 前缀用 ``_table_key`` 处理。"""
    return str(name or "").strip().strip('"').strip("`").strip().lower()


def _real_tables(scope) -> list[tuple[object, str]]:
    """该作用域的**真实表**：``(Table 节点, 归一化表名)``。

    CTE 名不是表：``scope.cte_sources`` 是该作用域真正可见的 CTE（本 SELECT 的 WITH +
    祖先链，CTE 体内看不到自身），带 schema 限定的引用永远是真实表。
    """
    cte_names = {_norm_ident(name) for name in scope.cte_sources}
    out: list[tuple[object, str]] = []
    for table in scope.tables:
        name = str(table.name or "").strip()
        if not name:
            continue
        if not (table.db or table.catalog) and _norm_ident(name) in cte_names:
            continue
        out.append((table, _table_key(name)))
    return out


def _covered(plan: AccessPlan, table: str) -> bool:
    """计划是否覆盖该表（每张输入表都会在四个字典之一留下记录）。"""
    return (
        table in plan.row_filters
        or table in plan.allowed_columns
        or table in plan.masked
        or table in plan.denied
    )


def _scope_own_columns(scope, scope_roots: set[int]) -> list[object]:
    """该作用域**自己**的列引用（不进入嵌套子查询作用域）。

    不能用 ``scope.columns``：它不含 ``HAVING`` / ``QUALIFY`` 里的列（实测
    ``having count(phone) > 1`` 的 ``phone`` 缺失），会把 deny 列藏起来。
    嵌套作用域的根整棵跳过，交给它自己的作用域判定。
    """
    out: list[object] = []
    stack: list[object] = [scope.expression]
    while stack:
        node = stack.pop()
        if isinstance(node, exp.Column):
            out.append(node)
        for child in node.iter_expressions():
            if id(child) in scope_roots:
                continue
            stack.append(child)
    return out


def _mask_for(plan: AccessPlan, table: str, column: str) -> str:
    return str((plan.masked.get(table) or {}).get(column.lower()) or "")


def _mask_touches_denied(expr, plan: AccessPlan, table: str) -> bool:
    """掩码表达式是否引用了本表的 deny 列。

    掩码只改显示形态，不该变成"用 deny 列拼一个新值"的取数旁路：
    ``mask phone = left(salary, 3)`` 会把 salary 透出来，按拒绝处理。
    """
    denied = plan.denied.get(table) or frozenset()
    if not denied:
        return False
    for column in expr.find_all(exp.Column):
        if _norm_ident(column.name) in denied:
            return True
    return False


def _expand_star(
    plan: AccessPlan,
    table: str,
    dialect: str,
    qualifier: str | None,
):
    """展开一张表的全部可读列；返回 ``(表达式列表, 无法展开的原因)``。

    ``allowed_columns[table] is None`` = 没有列元数据 → 无法展开，调用方保留星号并记
    ``star_unexpanded``（保可用性，spec §5.3 第 3 种情况）。
    """
    allowed = plan.allowed_columns.get(table)
    if allowed is None:
        # 没有列元数据就不能展开；若该表还有列级限制（deny/mask），保留星号会直接
        # 把受限列读出来，必须拒绝（fail-closed）。
        if (plan.denied.get(table) or frozenset()) or (plan.masked.get(table) or {}):
            return [], "restricted-no-metadata"
        return [], "no-metadata"

    out = []
    for column in allowed:
        mask = _mask_for(plan, table, column)
        if mask:
            expr, error = _compile_mask(mask, dialect, qualifier)
            if error:
                return [], error
            if _mask_touches_denied(expr, plan, table):
                return [], "掩码表达式引用了 deny 列"
            out.append(expr.as_(column))
        else:
            out.append(exp.column(column, table=qualifier) if qualifier else exp.column(column))
    return out, ""


def _wrap_table(table, condition) -> None:
    """把表引用换成 ``(SELECT * FROM t WHERE <cond>) AS <原别名>`` 并原地替换。

    内部 ``SELECT *`` 是编译中间态：本模块先做列改写、最后才包装，因此它不会被
    列策略再检查一遍。别名优先沿用原别名（``from t x`` → ``as x``），没别名则用表名，
    保证 ``t.col`` 这类限定列引用继续有效。
    """
    inner_table = table.copy()
    inner_table.set("alias", None)
    inner = exp.select("*").from_(inner_table).where(condition.copy())

    alias_node = table.args.get("alias")
    alias = alias_node.copy() if alias_node is not None else exp.TableAlias(this=table.this.copy())
    table.replace(exp.Subquery(this=inner, alias=alias))


def rewrite(sql: str, plan: AccessPlan, *, dialect: str = "postgres") -> Decision:
    """把 SQL 按访问计划改写；返回 :class:`Decision`，**任何异常都转成 deny**。

    处理顺序见模块 docstring。成功时 ``Decision.sql`` 是可直接执行的 SQL（用户的
    ``:name`` 占位符保持原前缀），``applied`` 列出实际施加的改写。
    """
    if exp is None or sqlglot is None or traverse_scope is None:  # pragma: no cover
        return Decision(False, "sqlglot 不可用，按拒绝处理（fail-closed）")
    if not isinstance(plan, AccessPlan):
        return Decision(False, "缺少访问计划，按拒绝处理（fail-closed）")

    text = str(sql or "").strip()
    if not text:
        return Decision(False, "空 SQL，按拒绝处理（fail-closed）")

    # ① 解析：只允许单条 SELECT
    try:
        trees = sqlglot.parse(text, read=dialect)
    except Exception as e:  # noqa: BLE001 - 脏 SQL 一律 fail-closed
        return Decision(False, f"SQL 解析失败，按拒绝处理（fail-closed）：{e}")
    if len(trees) != 1 or trees[0] is None:
        return Decision(False, "只允许单条查询语句，按拒绝处理（fail-closed）")
    tree = trees[0]
    if isinstance(tree, exp.Command) or not isinstance(tree, exp.Query):
        return Decision(
            False, f"只允许 SELECT 查询，按拒绝处理（fail-closed）：{type(tree).__name__}"
        )
    if tree.args.get("into"):
        return Decision(False, "不允许 SELECT INTO，按拒绝处理（fail-closed）")
    with_node = tree.args.get("with")
    if with_node is not None and with_node.args.get("recursive"):
        return Decision(False, "不允许递归 CTE（WITH RECURSIVE），按拒绝处理（fail-closed）")

    # 用户/模板参数（:name）先记下来，生成后恢复原前缀（PG 方言会输出 %(name)s）
    placeholders = {p.name for p in tree.find_all(exp.Placeholder) if p.name}

    try:
        scopes = list(traverse_scope(tree))
    except Exception as e:  # noqa: BLE001
        return Decision(False, f"查询作用域解析失败，按拒绝处理（fail-closed）：{e}")

    # 逐作用域收集真实表与别名映射（CTE 名不算表）
    entries: list[tuple[object, list[tuple[object, str]], dict[str, str]]] = []
    for scope in scopes:
        real = _real_tables(scope)
        alias_to_table = {
            _norm_ident(table.alias_or_name): table_id for table, table_id in real
        }
        entries.append((scope, real, alias_to_table))

    # ② 表级/列级 deny（包装前，此时树里只有用户自己的引用）
    scope_roots = {id(scope.expression) for scope in scopes}
    scope_meta = {id(scope): (real, aliases) for scope, real, aliases in entries}

    for scope, real, _alias_to_table in entries:
        for _table, table_id in real:
            if not _covered(plan, table_id):
                return Decision(
                    False, f"表 {table_id} 不在访问计划内，按拒绝处理（fail-closed）"
                )
            if DENIED_ALL in (plan.denied.get(table_id) or frozenset()):
                return Decision(False, f"表 {table_id} 被策略拒绝（deny）")

        # 作用域链：相关子查询里的列可能属于外层真实表（无别名时无法精确判定，
        # 保守地把外层表也算进候选——宁可误拒，也不放过 deny 列）。
        chain: list[object] = []
        node = scope
        while node is not None:
            chain.append(node)
            node = getattr(node, "parent", None)
        visible: list[str] = []
        for item in chain:
            meta = scope_meta.get(id(item))
            if not meta:
                continue
            for _table, table_id in meta[0]:
                if table_id not in visible:
                    visible.append(table_id)

        # CTE / 派生表作用域不能引用外层查询（非 LATERAL），无别名列只可能是本地表；
        # 其余作用域（EXISTS / 标量子查询等）可能相关引用外层，保守地把外层也算进候选。
        visible_candidates = (
            [table_id for _table, table_id in real]
            if getattr(scope, "is_cte", False) or getattr(scope, "is_derived_table", False)
            else visible
        )

        for column in _scope_own_columns(scope, scope_roots):
            if isinstance(column.this, exp.Star):  # t.* 星号另行处理
                continue
            column_name = _norm_ident(column.name)
            if not column_name:
                continue
            qualifier = _norm_ident(column.table)
            if qualifier:
                table_id = None
                for item in chain:
                    meta = scope_meta.get(id(item))
                    if meta and qualifier in meta[1]:
                        table_id = meta[1][qualifier]
                        break
                # 派生表 / CTE 列：真实表由内层作用域处理，这里不猜
                candidates = [table_id] if table_id else []
            else:
                candidates = visible_candidates
            for table_id in candidates:
                if column_name in (plan.denied.get(table_id) or frozenset()):
                    return Decision(
                        False,
                        f"列 {table_id}.{column_name} 被策略拒绝（deny，不可用于"
                        "投影/条件/排序/分组）",
                    )

    # ③ 行条件校验（只校验真正被引用的表）
    conditions: dict[str, object] = {}
    for _scope, real, _alias_to_table in entries:
        for _table, table_id in real:
            if table_id in conditions:
                continue
            raw = str(plan.row_filters.get(table_id) or "").strip()
            if not raw:
                continue
            parsed, error = _compile_condition(raw, dialect)
            if error:
                return Decision(
                    False, f"表 {table_id} 的行策略条件不合法，按拒绝处理：{error}"
                )
            conditions[table_id] = parsed

    applied: list[dict] = []

    def _record(item: dict) -> None:
        item = dict(item)
        if item not in applied:
            applied.append(item)

    # ④ 列投影改写（先列、后行，避免包装内的 * 被自己拦死）
    for scope, real, alias_to_table in entries:
        expression = scope.expression
        if not isinstance(expression, exp.Select):
            continue
        projections: list[object] = []
        changed = False
        for projection in expression.expressions:
            # 裸 *：展开本作用域所有真实表；任一表无元数据则整体保留
            if isinstance(projection, exp.Star):
                if not real:
                    # 只来自 CTE/派生表的星号：真实表由内层作用域判定，这里原样保留
                    projections.append(projection)
                    continue
                expanded: list[object] = []
                blocked: list[str] = []
                pending_masks: list[dict] = []
                # 同作用域还有 CTE/派生表（sources 里不是 Table）时，它们的列未知，
                # 裸星号不能"只展开真实表"——否则会把 CTE/派生表的列整段丢掉。
                has_unknown_source = any(
                    not isinstance(source, exp.Table) for source in scope.sources.values()
                )
                for table, table_id in real:
                    if has_unknown_source:
                        if (plan.denied.get(table_id) or frozenset()) or (
                            plan.masked.get(table_id) or {}
                        ):
                            return Decision(
                                False,
                                f"表 {table_id} 的星号无法展开（同作用域还有 CTE/派生表）"
                                "且存在列级限制，按拒绝处理（fail-closed）",
                            )
                        blocked.append(table_id)
                        continue
                    qualifier = table.alias_or_name if len(real) > 1 else None
                    columns, why = _expand_star(plan, table_id, dialect, qualifier)
                    if why == "no-metadata":
                        blocked.append(table_id)
                    elif why == "restricted-no-metadata":
                        return Decision(
                            False,
                            f"表 {table_id} 无列元数据但存在列级限制，无法安全展开"
                            "星号，按拒绝处理（fail-closed）",
                        )
                    elif why:
                        return Decision(
                            False, f"表 {table_id} 的掩码表达式不合法，按拒绝处理：{why}"
                        )
                    else:
                        expanded.extend(columns)
                        for column in plan.allowed_columns.get(table_id) or ():
                            mask = _mask_for(plan, table_id, column)
                            if mask:
                                pending_masks.append(
                                    {
                                        "mask": mask,
                                        "table": table_id,
                                        "column": column.lower(),
                                    }
                                )
                if blocked:
                    # 无法完整展开 = 只能保留用户的星号：此时任何列级限制（deny/mask）
                    # 都会被原样读出来（掩码没施加），必须拒绝。
                    for _table, table_id in real:
                        if (plan.denied.get(table_id) or frozenset()) or (
                            plan.masked.get(table_id) or {}
                        ):
                            return Decision(
                                False,
                                f"表 {table_id} 的星号无法完整展开（存在无列元数据/"
                                "CTE/派生表的同级来源）且该作用域存在列级限制，按拒绝"
                                "处理（fail-closed）",
                            )
                    # 记审计（每张无法展开的表一条）
                    for table_id in blocked:
                        _record({"star": "unexpanded", "table": table_id})
                    projections.append(projection)
                    continue
                if not expanded:
                    return Decision(
                        False, "星号展开后没有可读列，按拒绝处理（fail-closed）"
                    )
                for item in pending_masks:  # 确认真的展开后才记（整段保留时不算施加）
                    _record(item)
                projections.extend(expanded)
                changed = True
                continue

            # 限定星号 t.*：按别名映射还原真实表
            if isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star):
                qualifier = _norm_ident(projection.table)
                table_id = alias_to_table.get(qualifier)
                if not table_id:
                    projections.append(projection)  # 派生表/CTE 的星号，内层已判定
                    continue
                columns, why = _expand_star(
                    plan, table_id, dialect, qualifier or None
                )
                if why == "no-metadata":
                    _record({"star": "unexpanded", "table": table_id})
                    projections.append(projection)
                    continue
                if why == "restricted-no-metadata":
                    return Decision(
                        False,
                        f"表 {table_id} 无列元数据但存在列级限制，无法安全展开星号，"
                        "按拒绝处理（fail-closed）",
                    )
                if why:
                    return Decision(
                        False, f"表 {table_id} 的掩码表达式不合法，按拒绝处理：{why}"
                    )
                if not columns:
                    return Decision(
                        False, f"表 {table_id} 的星号展开后没有可读列，按拒绝处理（fail-closed）"
                    )
                for column in plan.allowed_columns.get(table_id) or ():
                    mask = _mask_for(plan, table_id, column)
                    if mask:
                        _record(
                            {"mask": mask, "table": table_id, "column": column.lower()}
                        )
                projections.extend(columns)
                changed = True
                continue

            # 直接列投影（含 `col as alias`）：mask 只作用于投影，保留输出列名
            inner = projection.this if isinstance(projection, exp.Alias) else projection
            if isinstance(inner, exp.Column) and not isinstance(inner.this, exp.Star):
                column_name = _norm_ident(inner.name)
                qualifier = _norm_ident(inner.table)
                if qualifier:
                    table_id = alias_to_table.get(qualifier)
                elif len(real) == 1:
                    table_id = real[0][1]
                else:
                    hits = [
                        table_id
                        for _table, table_id in real
                        if _mask_for(plan, table_id, column_name)
                    ]
                    table_id = hits[0] if len(hits) == 1 else None
                mask = _mask_for(plan, table_id, column_name) if table_id else ""
                if mask:
                    expr, error = _compile_mask(mask, dialect, qualifier or None)
                    if error:
                        return Decision(
                            False, f"表 {table_id} 的掩码表达式不合法，按拒绝处理：{error}"
                        )
                    if _mask_touches_denied(expr, plan, table_id):
                        return Decision(
                            False,
                            f"表 {table_id} 的掩码表达式引用了 deny 列，按拒绝处理"
                            "（fail-closed）",
                        )
                    out_name = projection.alias or inner.name
                    projections.append(expr.as_(out_name))
                    _record({"mask": mask, "table": table_id, "column": column_name})
                    changed = True
                    continue

            projections.append(projection)

        if changed:
            expression.set("expressions", projections)

    # ⑤ 行包装（逐表，绝不把不同表的条件合并成一个字符串）
    for _scope, real, _alias_to_table in entries:
        for table, table_id in real:
            condition = conditions.get(table_id)
            if condition is None:
                continue
            _wrap_table(table, condition)
            _record({"row": str(plan.row_filters.get(table_id) or ""), "table": table_id})

    # ⑥ 生成 SQL，恢复用户参数前缀
    try:
        compiled = tree.sql(dialect=dialect)
    except Exception as e:  # noqa: BLE001
        return Decision(False, f"SQL 生成失败，按拒绝处理（fail-closed）：{e}")
    for name in placeholders:
        compiled = compiled.replace(f"%({name})s", f":{name}")

    if applied:
        reason = f"SQL 编译完成：{len(applied)} 处策略改写"
    else:
        reason = "SQL 编译完成：没有需要施加的策略"
    # policy_ids 恒为空：AccessPlan 没有策略 id 字段（接口固定），由调用方合并
    return Decision(True, reason, (), compiled, tuple(applied))
