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
    #: 实际参与本次计划的策略 id（``build_plan`` 填，``rewrite`` 透传进 ``Decision``）。
    policy_ids: tuple[int, ...] = ()
    #: 整表/整视图拒绝的原因（仅审计与提示用，不参与判定）。视图血缘三级降级会填
    #: 「混合粒度无法安全套用行条件」这类说明；``rewrite`` 拒绝时并入 ``Decision.reason``。
    deny_reason: str = ""


# ---------------------------------------------------------------------------
# 条件绑定（build_plan 侧）
# ---------------------------------------------------------------------------
def _placeholder_ref(node):
    """``$attr.x`` / ``$user.id`` 在 sqlglot 里是 ``Dot(Parameter(Var), Identifier)``。

    返回 ``(命名空间, 字段)``；不是占位符返回 ``None``。
    """
    if not isinstance(node, exp.Dot):
        return None
    left = node.this
    if isinstance(left, exp.Parameter):
        left = left.this
    if not isinstance(left, exp.Var):
        return None
    field = node.expression
    name = field.name if isinstance(field, exp.Identifier) else ""
    return (_norm_ident(left.this), _norm_ident(name))


def _bind_condition(condition: str, principal: Principal) -> str:
    """把 ``$attr.*`` / ``$user.id`` 按 **AST** 绑定成安全字面量。

    必须先解析再替换：正则替换会命中**字符串字面量内部**（
    ``note = '$attr.dept_id'`` 是"拿这个字符串做比较"，不是属性引用），改成按
    ``Dot(Parameter(Var(...)))`` 节点替换就没有这个问题。

    规则：
    - ``$user.id`` → 数字字面量；
    - ``$attr.x`` 单值 → 字符串字面量（引号双写转义）；
    - ``$attr.x`` 多值且位置是 ``col = $attr.x`` → ``col IN (v1, v2)``；
    - 其余情况（类型不符 / 多值出现在别的比较里 / 未知命名空间如 ``$role``）→
      **原样返回条件**（里面还带占位符节点）→ :func:`rewrite` 的条件校验会拒绝，
      fail-closed，不猜、不放宽。

    缺属性：引擎的 ``applicable_condition`` 已把这类 ``allow`` 排除了，正常不会走到；
    真出现时同样原样返回 → 拒绝。
    """
    text = str(condition or "").strip()
    if not text:
        return ""
    try:
        parsed = sqlglot.parse_one(text, read="postgres")
    except Exception:  # noqa: BLE001 - 解析失败交给 rewrite 拒绝
        return text
    if parsed is None:
        return text

    attrs = {
        str(k).lower(): v
        for k, v in (getattr(principal, "attrs", None) or {}).items()
    }
    ok = True

    for dot in list(parsed.find_all(exp.Dot)):
        ref = _placeholder_ref(dot)
        if ref is None:
            continue  # 普通 Dot（如 (x).y）不在这里处理，交给条件白名单
        namespace, field = ref

        if namespace == "user" and field == "id":
            try:
                uid = int(getattr(principal, "user_id", None))
            except (TypeError, ValueError):
                ok = False
                continue
            dot.replace(exp.Literal.number(uid))
            continue

        if namespace == "attr":
            raw = attrs.get(field)
            if isinstance(raw, (dict, bytes, bytearray)):
                ok = False
                continue
            values = _attr_values(raw)
            if not values:
                ok = False
                continue
            if len(values) == 1:
                dot.replace(exp.Literal.string(values[0]))
                continue
            parent = dot.parent
            if isinstance(parent, exp.EQ) and parent.args.get("expression") is dot:
                parent.replace(
                    exp.In(
                        this=parent.this.copy(),
                        expressions=[exp.Literal.string(v) for v in values],
                    )
                )
                continue
            ok = False
            continue

        ok = False  # $role.* 等暂不支持 → 拒绝

    if not ok:
        return text  # 保留占位符，rewrite 会以"未绑定的策略参数"拒绝
    try:
        return parsed.sql(dialect="postgres")
    except Exception:  # noqa: BLE001
        return text


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
    policy_ids: list[int] = []

    def _add_ids(ids) -> None:
        for pid in ids or ():
            if pid not in policy_ids:
                policy_ids.append(int(pid))

    for raw_table, raw_columns in (tables or {}).items():
        table = _table_key(raw_table)
        if not table:
            continue

        table_decision = decide_table(policies, principal, table)
        _add_ids(table_decision.policy_ids)
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
                # 标记本身也是"生效的策略"，审计要能追到
                for policy in policies or ():
                    if policy is None or not _is_enabled(getattr(policy, "enabled", True)):
                        continue
                    if str(getattr(policy, "marking", "") or "").strip() and _table_key(
                        getattr(policy, "resource_code", "")
                    ) == table:
                        _add_ids([getattr(policy, "id", 0)])
            else:
                allowed_columns[table] = None
            continue

        blocked: set[str] = set()
        masks: dict[str, str] = {}
        readable: list[str] = []
        for column in columns:
            column_decision = decide_column(policies, principal, table, column)
            _add_ids(column_decision.policy_ids)
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
        policy_ids=tuple(policy_ids),
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
    for node in parsed.walk():
        if isinstance(node, (exp.Parameter, exp.Var, exp.Placeholder)):
            # 不是"文本里出现 $"，而是真的留下占位符节点（字符串字面量里的 $ 不算）
            return None, "条件里存在未绑定的策略参数（$attr.* / $user.id/$role.*）"
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
    for func in parsed.find_all(exp.Func):
        if _is_system_function(func):
            return None, "掩码表达式里不允许调用系统函数"
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


#: 系统 schema：这些 schema 下的表一律拒绝（编译器是执行边界）。
_SYSTEM_SCHEMAS = frozenset({"pg_catalog", "information_schema", "pg_toast"})

#: 系统函数（``pg_*`` 之外、需要单独点名的）。``pg_*`` 前缀统一拒绝。
_SYSTEM_FUNCTIONS = frozenset(
    {
        "lo_import",
        "lo_export",
        "dblink",
        "dblink_connect",
        "dblink_exec",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "pg_sleep",
    }
)


def _func_name(func) -> str:
    """函数名归一（``Anonymous`` 的 ``this`` 是字符串，其余走 ``sql_name``）。"""
    if isinstance(func, exp.Anonymous):
        return _norm_ident(func.this)
    try:
        return _norm_ident(func.sql_name())
    except Exception:  # noqa: BLE001
        return ""


def _is_system_function(func) -> bool:
    name = _func_name(func)
    return bool(name) and (name.startswith("pg_") or name in _SYSTEM_FUNCTIONS)


def _is_system_table(table) -> bool:
    """``pg_*`` / ``pg_catalog`` / ``information_schema`` / ``pg_toast`` 一律拒绝。"""
    name = _norm_ident(table.name)
    db = _norm_ident(table.db)
    catalog = _norm_ident(table.catalog)
    if name.startswith("pg_"):
        return True
    return db in _SYSTEM_SCHEMAS or catalog in _SYSTEM_SCHEMAS


def _group_members(subquery, cte_names: set[str]):
    """括号组里的真实表 + 是否含未知来源（派生表/CTE）。

    从 ``Subquery`` 出发遍历整棵 FROM 项（含 ``joins``），遇到 ``SELECT`` 就标记
    unknown 并跳过（派生表自己的作用域会判定它的基表）。CTE 引用同样记 unknown。
    不能沿 ``table.parent`` 的 Subquery 链走：``(t JOIN u) AS j`` 里 u 的 parent 是
    ``Join``，第一层就断了（round 3 的根因）。
    """
    members: list[object] = []
    unknown = False
    stack: list[object] = [subquery]
    while stack:
        node = stack.pop()
        if isinstance(node, exp.Select):
            unknown = True
            continue
        if isinstance(node, exp.Table):
            name = str(node.name or "").strip()
            if not name:
                continue
            if not (node.db or node.catalog) and _norm_ident(name) in cte_names:
                # CTE 基项：列未知，但**不能 continue**——它的 joins 里可能有真实表
                # （`(c join u on true) AS j`），漏掉 u 会让整组策略失效。
                unknown = True
            else:
                members.append(node)
        for child in node.iter_expressions():
            if isinstance(child, exp.Select):
                unknown = True
                continue
            stack.append(child)
    return members, unknown


def _real_tables(scope, scope_roots: set[int]) -> list[tuple[object, str, str]]:
    """该作用域的**真实表**：``(Table 节点, 归一化表名, 可见别名)``。

    收集该作用域**自己**的全部 ``exp.Table`` 节点（``_scope_own_nodes`` 只跳过嵌套
    **查询**作用域，不跳过括号表/括号 join 的表作用域）：

    - 普通 FROM / join 两侧 / 括号 join 内部 / ``FROM (t JOIN u) AS j`` 全部覆盖；
      只看 ``scope.tables`` 会漏掉 ``(t) AS j`` 和 join 侧（复审 Critical 1/2）；
    - CTE 引用按 ``scope.cte_sources`` 排除（CTE 名不是表），schema 限定的不算 CTE；
    - 派生表/子查询里的表属于它自己的作用域（那个 SELECT 是作用域根，被跳过）。

    可见别名用表自己的别名/表名；``(t) AS j`` 这类单表括号的外层别名由调用方补进
    别名映射（一个别名只对应一张表时）。
    """
    cte_names = {_norm_ident(name) for name in scope.cte_sources}
    out: list[tuple[object, str, str]] = []
    seen: set[int] = set()
    for node in _scope_own_nodes(scope, scope_roots):
        if not isinstance(node, exp.Table):
            continue
        name = str(node.name or "").strip()
        if not name or id(node) in seen:
            continue
        if not (node.db or node.catalog) and _norm_ident(name) in cte_names:
            continue
        seen.add(id(node))
        out.append((node, _table_key(name), str(node.alias_or_name or name)))
    return out


def _covered(plan: AccessPlan, table: str) -> bool:
    """计划是否覆盖该表（每张输入表都会在四个字典之一留下记录）。"""
    return (
        table in plan.row_filters
        or table in plan.allowed_columns
        or table in plan.masked
        or table in plan.denied
    )


def _scope_own_nodes(scope, scope_roots: set[int]) -> list[object]:
    """该作用域**自己**的节点（不进入嵌套子查询作用域）。"""
    out: list[object] = []
    stack: list[object] = [scope.expression]
    while stack:
        node = stack.pop()
        out.append(node)
        for child in node.iter_expressions():
            if id(child) in scope_roots:
                continue
            stack.append(child)
    return out


def _scope_own_columns(scope, scope_roots: set[int]) -> list[object]:
    """该作用域**自己**的列引用（不进入嵌套子查询作用域）。

    不能用 ``scope.columns``：它不含 ``HAVING`` / ``QUALIFY`` 里的列（实测
    ``having count(phone) > 1`` 的 ``phone`` 缺失），会把 deny 列藏起来。
    嵌套作用域的根整棵跳过，交给它自己的作用域判定。
    """
    return [
        node for node in _scope_own_nodes(scope, scope_roots) if isinstance(node, exp.Column)
    ]


def _scope_clause_nodes(scope, scope_roots: set[int]) -> list[object]:
    """该作用域**非投影**部分的节点（WHERE / GROUP BY / HAVING / ORDER BY / JOIN ON…）。

    mask 只作用于投影；同一列出现在这些位置时必须拒绝（防"用条件反推值"）。
    UNION 作用域没有自己的 SELECT（ORDER BY 挂在 Union 节点上）→ 全部按"非投影"处理。
    """
    expression = scope.expression
    if not isinstance(expression, exp.Select):
        return _scope_own_nodes(scope, scope_roots)
    out: list[object] = []
    for key, value in expression.args.items():
        if key == "expressions":
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            if not isinstance(item, exp.Expression):
                continue
            stack = [item]
            while stack:
                node = stack.pop()
                out.append(node)
                for child in node.iter_expressions():
                    if id(child) in scope_roots:
                        continue
                    stack.append(child)
    return out


def _own_columns_of(node, scope_roots: set[int]) -> list[object]:
    """子树里的列引用（跳过嵌套查询作用域）。"""
    out: list[object] = []
    stack: list[object] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, exp.Column):
            out.append(current)
        for child in current.iter_expressions():
            if id(child) in scope_roots:
                continue
            stack.append(child)
    return out


#: 对掩码列做这些聚合默认拒绝（spec §5.3：mask 只改显示形态，不授予聚合权限）。
_ROW_AGGREGATES = (exp.Sum, exp.Avg, exp.Max, exp.Min)


def _mask_for(plan: AccessPlan, table: str, column: str) -> str:
    return str((plan.masked.get(table) or {}).get(column.lower()) or "")


def _masked_target(column, real, plan: AccessPlan, resolve, fallback=()):
    """该列命中的 masked 表；返回 ``(表名, 是否歧义, 是否跨作用域)``。

    ``resolve`` 把限定名解析成真实表（本作用域 / 作用域链）。无别名列先在本作用域找
    掩码；本地没有时，若列名**不被本地元数据认识**（无 FROM 的子查询、相关子查询、
    LATERAL 等），回退到 ``fallback``（外层作用域的表）。多于一张表命中视为歧义，
    调用方拒绝，绝不猜。

    ``external=True`` 表示引用的是外层表的掩码列：子查询里无法安全替换掩码，
    调用方必须拒绝（复审 Critical 3）。
    """
    local_ids = {table_id for _table, table_id, _alias in real}
    qualifier = _norm_ident(column.table)
    name = _norm_ident(column.name)
    if qualifier:
        table_id = resolve(qualifier)
        if table_id and _mask_for(plan, table_id, name):
            return table_id, False, table_id not in local_ids
        return None, False, False

    hits = [table_id for _table, table_id, _alias in real if _mask_for(plan, table_id, name)]
    if len(hits) > 1:
        return None, True, False
    if hits:
        return hits[0], False, False

    # 本地元数据"认识"这一列 → 它是本作用域的列（只是没配掩码），不要误判成外层引用
    known: set[str] = set()
    for _table, table_id, _alias in real:
        columns = plan.allowed_columns.get(table_id)
        if columns is not None:
            known.update(str(column).lower() for column in columns)
        known.update(plan.denied.get(table_id) or ())
        known.update((plan.masked.get(table_id) or {}).keys())
    if name in known:
        return None, False, False

    outer_hits = [table_id for _table, table_id, _alias in fallback if _mask_for(plan, table_id, name)]
    if len(outer_hits) > 1:
        return None, True, True
    if outer_hits:
        return outer_hits[0], False, True
    return None, False, False


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


def _wrap_table(table, condition, alias: str) -> None:
    """把表引用换成 ``(SELECT * FROM t WHERE <cond>) AS <原别名>`` 并原地替换。

    内部 ``SELECT *`` 是编译中间态：本模块先做列改写、最后才包装，因此它不会被
    列策略再检查一遍。

    **joins 必须摘出来单独处理**（Critical 2）：sqlglot 把 ``t JOIN u`` 的 joins 挂在
    ``t`` 节点上，直接 ``table.copy()`` 会把 u 一起复制进子查询；之后对原 u 的包装
    作用在游离副本上，u 的过滤既不进 SQL、applied 里却写着它。正确做法是把原 join
    节点**移动**到包装结果上（不 copy，保持后续对 join 内表的引用仍有效）。

    别名：``FROM (t) AS j`` 的外层 ``Subquery`` 已经提供别名，内层不再加别名
    （否则是 ``((SELECT ...) AS t) AS j`` 的双重别名）；其余情况沿用原别名/可见别名。
    """
    joins = table.args.get("joins")
    inner_table = table.copy()
    inner_table.set("alias", None)
    inner_table.set("joins", None)
    inner = exp.select("*").from_(inner_table).where(condition.copy())

    parent = table.parent
    covered_by_parent = False
    if not joins:  # 有 join 时必须保留表别名，否则 ON 里的 t.col/u.col 失效
        while isinstance(parent, exp.Subquery):
            if parent.args.get("alias") is not None:
                covered_by_parent = True
                break
            parent = parent.parent

    wrapper = exp.Subquery(this=inner)
    if not covered_by_parent:
        alias_node = table.args.get("alias")
        wrapper.set(
            "alias",
            alias_node.copy()
            if alias_node is not None
            else exp.TableAlias(this=exp.to_identifier(alias)),
        )
    if joins:
        wrapper.set("joins", joins)
        for join in joins:
            join.parent = wrapper

    table.replace(wrapper)


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

    # 系统函数是执行边界：pg_* / 文件读写等直接拒绝（不依赖计划是否覆盖）
    for func in tree.find_all(exp.Func):
        if _is_system_function(func):
            return Decision(
                False,
                f"不允许调用系统函数 {_func_name(func)}，按拒绝处理（fail-closed）",
            )

    # 逐作用域收集真实表与别名映射（CTE / 派生表不是真实表）
    # 作用域根只跳过**查询**作用域；"表作用域"（表达式是 Table）不是查询，不能跳过，
    # 否则 `(t JOIN u) AS j` 里 join 侧的表会整段消失（复审 Critical 1）。
    scope_roots = {
        id(scope.expression)
        for scope in scopes
        if not isinstance(scope.expression, exp.Table)
    }
    entries: list[
        tuple[
            object,
            list[tuple[object, str, str]],
            dict[str, str],
            dict[str, tuple[tuple[str, ...], bool]],
        ]
    ] = []
    for scope in scopes:
        if isinstance(scope.expression, exp.Table):
            # (t) 的"表作用域"：父作用域已经把它当真实表收进来，避免重复判定/包装
            continue
        real = _real_tables(scope, scope_roots)
        alias_to_table = {
            _norm_ident(alias): table_id for _table, table_id, alias in real
        }
        # 括号组的别名：必须按**组内全部真实表**建映射，不能沿 parent 链走
        # （`(t JOIN u) AS j` 的 u 挂在 Join 上，parent 链第一层就断了）。
        # 单表组（`FROM (t) AS j`）补进 1:1 映射；多表/含派生表的组记进 group_aliases，
        # 之后 `j.col` / `j.*` / 整行 `j` 一律按"组内任一表命中"保守处理。
        cte_names = {_norm_ident(name) for name in scope.cte_sources}
        group_aliases: dict[str, tuple[tuple[str, ...], bool]] = {}
        for node in _scope_own_nodes(scope, scope_roots):
            if not isinstance(node, exp.Subquery) or not node.alias:
                continue
            if isinstance(node.args.get("this"), exp.Select):
                continue  # 派生表别名（`(select …) x`）：列由它自己的作用域处理
            members, unknown = _group_members(node, cte_names)
            table_ids = tuple(
                dict.fromkeys(_table_key(table.name) for table in members if table.name)
            )
            if not table_ids:
                continue
            alias_key = _norm_ident(node.alias)
            if len(table_ids) == 1 and not unknown:
                alias_to_table.setdefault(alias_key, table_ids[0])
            else:
                group_aliases[alias_key] = (table_ids, unknown)
        entries.append((scope, real, alias_to_table, group_aliases))

    # ② 表级/列级 deny（包装前，此时树里只有用户自己的引用）
    scope_meta = {id(scope): (real, aliases) for scope, real, aliases, _groups in entries}

    for scope, real, _alias_to_table, group_aliases in entries:
        for table, table_id, _visible in real:
            if _is_system_table(table):
                return Decision(
                    False,
                    f"系统表 {table_id} 不允许查询，按拒绝处理（fail-closed）",
                )
            if not _covered(plan, table_id):
                return Decision(
                    False, f"表 {table_id} 不在访问计划内，按拒绝处理（fail-closed）"
                )
            if DENIED_ALL in (plan.denied.get(table_id) or frozenset()):
                reason = f"表 {table_id} 被策略拒绝（deny）"
                note = str(getattr(plan, "deny_reason", "") or "").strip()
                return Decision(False, f"{reason}：{note}" if note else reason)

        # 作用域链：相关子查询里的列可能属于外层真实表（无别名时无法精确判定，
        # 保守地把外层表也算进候选——宁可误拒，也不放过 deny 列）。
        chain: list[object] = []
        node = scope
        while node is not None:
            chain.append(node)
            node = getattr(node, "parent", None)

        union_branches = list(getattr(scope, "union_scopes", None) or [])

        def _resolve(qualifier: str, chain=chain, union_branches=union_branches):
            """限定名 → 真实表（先本作用域，再沿作用域链，最后 UNION 分支）。"""
            for item in chain:
                meta = scope_meta.get(id(item))
                if meta and qualifier in meta[1]:
                    return meta[1][qualifier]
            for branch in union_branches:
                meta = scope_meta.get(id(branch))
                if meta and qualifier in meta[1]:
                    return meta[1][qualifier]
            return None

        # UNION 的 ORDER BY 挂在外层 Union 节点上，不是任何分支的 SELECT：
        # 列要按**分支表**判定，否则 `... union ... order by phone` 能绕过 deny/mask。
        checked_real = list(real)
        seen_tables = {table_id for _table, table_id, _alias in checked_real}
        for branch in union_branches:
            meta = scope_meta.get(id(branch))
            if not meta:
                continue
            for entry in meta[0]:
                if entry[1] not in seen_tables:
                    checked_real.append(entry)
                    seen_tables.add(entry[1])

        # 外层作用域的真实表（相关子查询 / LATERAL / 无 FROM 子查询里的列可能属于它们）。
        # 用于 mask 列的跨作用域判定：子查询里无法安全替换掩码 → 拒绝。
        ancestor_real: list[tuple[object, str, str]] = []
        ancestor_seen = {table_id for _table, table_id, _alias in checked_real}
        for item in chain[1:]:
            meta = scope_meta.get(id(item))
            if not meta:
                continue
            for entry in meta[0]:
                if entry[1] not in ancestor_seen:
                    ancestor_real.append(entry)
                    ancestor_seen.add(entry[1])

        visible: list[str] = []
        for item in chain:
            meta = scope_meta.get(id(item))
            if not meta:
                continue
            for _table, table_id, _alias in meta[0]:
                if table_id not in visible:
                    visible.append(table_id)
        for _table, table_id, _alias in checked_real:
            if table_id not in visible:
                visible.append(table_id)

        # CTE / 派生表作用域不能引用外层查询（非 LATERAL），无别名列只可能是本地表；
        # 其余作用域（EXISTS / 标量子查询等）可能相关引用外层，保守地把外层也算进候选。
        visible_candidates = (
            [table_id for _table, table_id, _alias in checked_real]
            if getattr(scope, "is_cte", False) or getattr(scope, "is_derived_table", False)
            else visible
        )

        expression = scope.expression
        select_expression = expression if isinstance(expression, exp.Select) else None

        def _under_aggregate(column, expression=expression) -> bool:
            """该列是否位于 SUM/AVG/MAX/MIN 之下（mask 列聚合默认拒绝）。"""
            parent = column.parent
            while parent is not None and parent is not expression:
                if isinstance(parent, _ROW_AGGREGATES):
                    return True
                parent = parent.parent
            return False

        # 整行/整表引用（Critical 3）：select t / (t).phone / row_to_json(t) /
        # count(t) / t::text / row_to_json(t.*) —— 只要表有 deny 或 mask 就拒绝。
        for node in _scope_own_nodes(scope, scope_roots):
            if not isinstance(node, exp.Column):
                continue
            if isinstance(node.this, exp.Star):
                qualifier = _norm_ident(node.table)
                if not qualifier:
                    continue  # 裸星号（含 count(*)）另行处理
                table_id = _resolve(qualifier)
                group = group_aliases.get(qualifier)
                group_ids = group[0] if group else ()
                if not table_id:
                    is_top_projection = node.parent is select_expression and any(
                        node is projection for projection in select_expression.expressions
                    )
                    if group_ids and not is_top_projection and any(
                        (plan.denied.get(tid) or frozenset())
                        or (plan.masked.get(tid) or {})
                        for tid in group_ids
                    ):
                        return Decision(
                            False,
                            f"括号组 {qualifier}.* 涉及 deny/mask 列且无法安全展开，"
                            "按拒绝处理（fail-closed）",
                        )
                    continue
                if not (plan.denied.get(table_id) or plan.masked.get(table_id)):
                    continue
                # 顶层 t.* 投影会被展开；函数参数/条件里的 t.* 是整表引用
                if node.parent is select_expression and any(
                    node is projection for projection in select_expression.expressions
                ):
                    continue
                return Decision(
                    False,
                    f"表 {table_id} 的整表引用（{qualifier}.*）无法安全施加列策略，"
                    "按拒绝处理（fail-closed）",
                )
            if node.table:
                continue  # 限定列：不是整行引用
            name = _norm_ident(node.name)
            # 无别名列指向表别名 → 整行引用（PG 语义：t 表示整行）
            table_id = _alias_to_table.get(name) or _resolve(name)
            group = group_aliases.get(name)
            if not table_id and group:
                if any(
                    (plan.denied.get(tid) or frozenset()) or (plan.masked.get(tid) or {})
                    for tid in group[0]
                ):
                    return Decision(
                        False,
                        f"括号组 {name} 的整行引用涉及 deny/mask 列，按拒绝处理"
                        "（fail-closed）",
                    )
                continue
            if table_id and (plan.denied.get(table_id) or plan.masked.get(table_id)):
                return Decision(
                    False,
                    f"表 {table_id} 的整行引用（{name}）涉及 deny/mask 列，"
                    "按拒绝处理（fail-closed）",
                )

        for column in _scope_own_columns(scope, scope_roots):
            if isinstance(column.this, exp.Star):  # t.* 星号另行处理
                continue
            column_name = _norm_ident(column.name)
            if not column_name:
                continue
            qualifier = _norm_ident(column.table)
            if qualifier:
                table_id = _resolve(qualifier)
                if table_id:
                    candidates = [table_id]
                else:
                    # 括号组别名（`(t JOIN u) AS j`）：按组内所有表检查 deny
                    group = group_aliases.get(qualifier)
                    candidates = list(group[0]) if group else []
            else:
                candidates = visible_candidates
            for table_id in candidates:
                if column_name in (plan.denied.get(table_id) or frozenset()):
                    return Decision(
                        False,
                        f"列 {table_id}.{column_name} 被策略拒绝（deny，不可用于"
                        "投影/条件/排序/分组）",
                    )
            if qualifier and qualifier in group_aliases and not _resolve(qualifier):
                # 组别名 + 掩码列：无法确定是哪张表的列，不能安全替换 → 拒绝
                if any(
                    _mask_for(plan, gid, column_name)
                    for gid in group_aliases[qualifier][0]
                ):
                    return Decision(
                        False,
                        f"列 {qualifier}.{column_name} 属于多表括号组且配置了掩码，"
                        "无法判定归属，按拒绝处理（fail-closed）",
                    )
            masked_table, ambiguous, external = _masked_target(
                column, checked_real, plan, _resolve, ancestor_real
            )
            if ambiguous:
                return Decision(
                    False,
                    f"列 {column_name} 无法确定属于哪张表（多表同名掩码），"
                    "按拒绝处理（fail-closed）",
                )
            if masked_table and external:
                return Decision(
                    False,
                    f"子查询引用了外层表 {masked_table} 的掩码列 {column_name}，"
                    "无法安全替换掩码，按拒绝处理（fail-closed）",
                )
            if masked_table and _under_aggregate(column):
                return Decision(
                    False,
                    f"列 {masked_table}.{column_name} 已配置掩码，不允许做 "
                    "SUM/AVG/MAX/MIN 聚合（需单独 allow），按拒绝处理（fail-closed）",
                )

        # mask 列出现在 WHERE/GROUP BY/ORDER BY/HAVING/JOIN ON → 拒绝（防反推值）
        for node in _scope_clause_nodes(scope, scope_roots):
            if not isinstance(node, exp.Column) or isinstance(node.this, exp.Star):
                continue
            masked_table, ambiguous, _external = _masked_target(
                node, checked_real, plan, _resolve, ancestor_real
            )
            if ambiguous:
                return Decision(
                    False,
                    f"列 {_norm_ident(node.name)} 无法确定属于哪张表（多表同名掩码），"
                    "按拒绝处理（fail-closed）",
                )
            if masked_table:
                return Decision(
                    False,
                    f"列 {masked_table}.{_norm_ident(node.name)} 已配置掩码，不允许"
                    "出现在 WHERE/GROUP BY/ORDER BY/HAVING/JOIN 中（mask 只作用于投影）",
                )

    # ③ 行条件校验（只校验真正被引用的表）
    conditions: dict[str, object] = {}
    for _scope, real, _alias_to_table, _group_aliases in entries:
        for _table, table_id, _visible in real:
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
    for scope, real, alias_to_table, group_aliases in entries:
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
                # 同作用域还有 CTE/派生表（sources 里既不是 Table，也不是"表作用域"）
                # 时，它们的列未知，裸星号不能"只展开真实表"——否则会把 CTE/派生表
                # 的列整段丢掉。`(t) AS j` 是"表作用域"，列已知，不算未知来源。
                has_unknown_source = any(
                    not isinstance(source, exp.Table)
                    and not isinstance(getattr(source, "expression", None), exp.Table)
                    for source in scope.sources.values()
                )
                for _table, table_id, visible_alias in real:
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
                    qualifier = visible_alias if len(real) > 1 else None
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
                    for _table, table_id, _alias in real:
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

            # 限定星号 t.*：按别名映射还原真实表；组别名 j.* 展开整组
            if isinstance(projection, exp.Column) and isinstance(projection.this, exp.Star):
                qualifier = _norm_ident(projection.table)
                table_id = alias_to_table.get(qualifier)
                if not table_id:
                    group = group_aliases.get(qualifier)
                    if group is not None:
                        group_ids, _unknown = group
                        # Ruling（round 4）：组别名会隐藏内层表名，展开成 `t.col` 是
                        # PG 非法 SQL。多表组的 `j.*`：组内任何 deny/mask/row_filter
                        # 无法安全施加 → DENY；否则原样保留 `j.*`（合法）。
                        restricted = any(
                            (plan.denied.get(tid) or frozenset())
                            or (plan.masked.get(tid) or {})
                            or str(plan.row_filters.get(tid) or "").strip()
                            for tid in group_ids
                        )
                        if restricted:
                            return Decision(
                                False,
                                f"括号组 {qualifier}.* 涉及 deny/mask/行过滤，且组别名"
                                "隐藏了内层表名，无法安全展开，按拒绝处理（fail-closed）",
                            )
                        projections.append(projection)
                        continue
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
            # 顶层裸列投影：mask 后保留输出列名；其余表达式在任意位置替换（Critical 4）
            inner = projection.this if isinstance(projection, exp.Alias) else projection
            if isinstance(inner, exp.Column) and not isinstance(inner.this, exp.Star):
                column_name = _norm_ident(inner.name)
                table_id, _ambiguous, _external = _masked_target(
                    inner, real, plan, alias_to_table.get
                )
                mask = _mask_for(plan, table_id, column_name) if table_id else ""
                if mask:
                    qualifier = _norm_ident(inner.table) or None
                    if qualifier is None and len(real) > 1:
                        qualifier = next(
                            (visible for _t, tid, visible in real if tid == table_id),
                            None,
                        )
                    expr, error = _compile_mask(mask, dialect, qualifier)
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
                    projections.append(expr.as_(projection.alias or inner.name))
                    _record({"mask": mask, "table": table_id, "column": column_name})
                    changed = True
                    continue
                projections.append(projection)
                continue

            # 复杂表达式：mask 列出现在任意位置 → 该列替换成掩码表达式
            replaced = False
            for column in _own_columns_of(projection, scope_roots):
                if isinstance(column.this, exp.Star):
                    continue
                table_id, ambiguous, _external = _masked_target(
                    column, real, plan, alias_to_table.get
                )
                if ambiguous:
                    return Decision(
                        False,
                        f"列 {_norm_ident(column.name)} 无法确定属于哪张表（多表同名"
                        "掩码），按拒绝处理（fail-closed）",
                    )
                if not table_id:
                    continue
                column_name = _norm_ident(column.name)
                mask = _mask_for(plan, table_id, column_name)
                if not mask:
                    continue
                qualifier = _norm_ident(column.table) or None
                if qualifier is None and len(real) > 1:
                    qualifier = next(
                        (visible for _t, tid, visible in real if tid == table_id), None
                    )
                expr, error = _compile_mask(mask, dialect, qualifier)
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
                column.replace(expr)
                _record({"mask": mask, "table": table_id, "column": column_name})
                replaced = True
            if replaced:
                changed = True

            projections.append(projection)

        if changed:
            expression.set("expressions", projections)

    # ⑤ 行包装（逐表，绝不把不同表的条件合并成一个字符串）
    for _scope, real, _alias_to_table, _group_aliases in entries:
        for table, table_id, visible in real:
            condition = conditions.get(table_id)
            if condition is None:
                continue
            _wrap_table(table, condition, visible)
            _record({"row": str(plan.row_filters.get(table_id) or ""), "table": table_id})

    # ⑥ 生成 SQL，恢复用户参数前缀
    try:
        # 函数名按小写输出：与管理员配置的掩码/条件文本观感一致（PG 里未加引号的
        # 函数名大小写不敏感），也避免 "LEFT(...)" 与 "left(...)" 的核对歧义。
        compiled = tree.sql(dialect=dialect, normalize_functions="lower")
    except Exception as e:  # noqa: BLE001
        return Decision(False, f"SQL 生成失败，按拒绝处理（fail-closed）：{e}")
    for name in placeholders:
        compiled = compiled.replace(f"%({name})s", f":{name}")

    if applied:
        reason = f"SQL 编译完成：{len(applied)} 处策略改写"
    else:
        reason = "SQL 编译完成：没有需要施加的策略"
    return Decision(True, reason, plan.policy_ids, compiled, tuple(applied))
