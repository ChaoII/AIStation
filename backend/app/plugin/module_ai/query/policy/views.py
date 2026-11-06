"""视图权限按血缘**三级降级**（P2 §5.4）：列映射 → 表级 → 不可映射。

为什么需要降级
--------------
血缘覆盖率不足以支撑"映射不了就全拒"（实测 ds:4 表级 66.5%、列级仅 11.3%），
但**也不能假装过滤**：视图没有暴露行策略的条件列时，往 ``WHERE`` 上写那个列名
要么是非法 SQL、要么过滤的是别的东西（更糟：看起来"已过滤"）。

三级语义
--------
=========  ============================================  ==============================
tier       触发条件                                       施加到视图上的限制
=========  ============================================  ==============================
``column`` 受约束基表都能定位到「基表.列」                   行条件（列全部暴露时）+ 列 deny/mask
``table``  受约束基表只能定位到「基表」                       只有表级 allow/deny（**不加**行条件；
                                                        基表有列级限制/标记时拒绝）
``none``   完全映射不到 / 血缘只有推断失败的占位              无限制放行（记审计）；有受保护表则拒绝
=========  ============================================  ==============================

``tier`` 记录的是**血缘映射能到达的粒度**（能力），不是"最终是否拒绝"：列级映射的视图
也可能因为条件列没被暴露而拒绝，此时 ``tier`` 仍是 ``column`` —— 运维据此区分
"映射不到"（``none``）与"映射到了但条件不满足"（``column``/``table`` + deny）。

``lineage`` 条目格式（``dict[视图, list[str]]``）
------------------------------------------------
- ``"表"``：只映射到表（tier=table）；``public.表`` 同样按表处理；
- ``"表.列"``：视图暴露该基表的**同名列**（tier=column）；
- ``"表.*"``：该基表所有同名列都暴露（列清单不可枚举，星号保留）；
- ``"unknown"`` / ``"?"`` / 空段：血缘推断失败的占位，**不是真实表名**（tier=none）；
- ``dict`` 条目：取 ``table`` 字段（``lineage.py`` 的 ``upstream`` 就是这个形状），
  按**表级**处理；缺 ``table`` / 非字符串 / 其它类型 → 不可解析（同占位处理）。

⚠️ ``lineage.py`` 的 ``upstream`` 只有表级信息（``{"table": ...}``），直传只能到
``table``；列级映射需要调用方另外提供「基表.列」条目（列级血缘）。

返回值
------
``AccessPlan`` 是**补充片段**：只包含从基表推导出的限制，调用方叠加到"视图自身"的
计划条目上（视图自己的策略仍由 ``build_plan`` 判定）。``tier == "none"`` 且放行时
片段为空（不改变调用方判定）；拒绝时 ``denied[视图] = {"*"}`` —— 键是**视图**，
因为最终 SQL 引用的是视图名；拒绝原因写进 ``AccessPlan.deny_reason``，
``compiler.rewrite`` 会把它并入 ``Decision.reason``（审计/explain 可直接读）。

几条硬约定
----------
- **不做主体判定**：签名没有 ``Principal``。调用方必须传入"已按主体筛过的候选策略"
  （与 :func:`engine.decide_table` 的输入同口径）；本模块只做血缘映射。
- **行条件原样透传**：``$attr.*`` / ``$user.id`` 的绑定仍由 :func:`build_plan`
  （编译期）负责；未绑定的占位符会被 :func:`compiler.rewrite` 拒绝（fail-closed）。
- **多基表行条件不合并**：一份视图条件表达不了两张表各自的过滤（T9 Ruling：
  跨表 ``OR`` 会静默丢表）→ 拒绝。
- **混合粒度不施加行条件**：一张基表到了列、另一张只到表时，``tier`` 只能是 ``table``
  （三值里没有 mixed），而 table 级按约定**不出现行条件** → 整视图拒绝，原因
  ``REASON_MIXED``（不伪造、也不把表级 allow 当行过滤放行）。
- **列冲突按拒绝**：同一视图列被两张基表映射成不同掩码 → 无法判定归属 → 拒绝；
  deny 优先于 mask（跨基表也一样，不会再给 deny 列挂掩码）。
- 纯逻辑：不读库、不解析真实视图定义，``PYTEST_NO_APP=1`` 可单测。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .compiler import DENIED_ALL, AccessPlan
from .engine import _columns_of, _is_enabled, _sort_key, _table_key, union_condition

if TYPE_CHECKING:  # 运行时不依赖策略对象之外的东西
    from .engine import Policy

__all__ = ["resolve_view_policies"]

try:  # 与编译器同一依赖；缺失时按"无法证明"处理（fail-closed）
    from sqlglot import exp as _exp
    from sqlglot import parse_one as _parse_one
except Exception:  # noqa: BLE001 # pragma: no cover - 依赖缺失只在极端环境发生
    _exp = None  # type: ignore[assignment]
    _parse_one = None  # type: ignore[assignment]

#: 血缘推断失败的占位（不是真实表名）。``lineage.py`` 目前不产出它们，
#: 保留给人工录入 / 上游降级数据 —— 见到即"这视图依赖什么不可知"。
_UNKNOWN_UPSTREAM = frozenset({"", "?", "unknown", "n/a", "none", "unresolved", "null"})

#: 常见 schema 前缀：``public.fuel_price`` 按**表**处理（不是 ``表.列``）。
_SCHEMA_PREFIXES = frozenset({"public", "dbo", "ai", "information_schema", "pg_catalog"})

#: 本模块只处理表/视图策略（与 engine 的 Ruling 一致）。
_RESOURCE_KINDS = frozenset({"table", "view"})

#: 整视图拒绝的原因：写进 ``AccessPlan.deny_reason``，``rewrite`` 会并入 ``Decision.reason``
#: （审计/explain 直接可读，不靠人猜为什么拒）。
REASON_UNRESOLVABLE = "视图血缘不可解析，无法证明不依赖受保护的表"
REASON_MIXED = "混合粒度无法安全套用行条件"
REASON_TABLE_ROW = "视图只映射到表，无法安全套用行条件"
REASON_TABLE_COLUMN = "视图只映射到表，无法排除列级限制/标记列被暴露"
REASON_MULTI_ROW = "多张基表的行条件无法合并成一份视图条件"


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _clean(value) -> str:
    """标识符归一：去空白、去两端引号/反引号（不做小写，列名要保留写法）。"""
    return str(value or "").strip().strip('"').strip("`").strip()


def _lower(value) -> str:
    return _clean(value).lower()


def _empty_plan(policy_ids=()) -> AccessPlan:
    """空片段：不改变调用方对视图自身的判定。"""
    return AccessPlan(
        row_filters={},
        allowed_columns={},
        masked={},
        denied={},
        policy_ids=tuple(policy_ids),
    )


def _deny_plan(view_key: str, policy_ids=(), reason: str = "") -> AccessPlan:
    """整视图拒绝：键是视图名（SQL 里引用的就是它）。"""
    return AccessPlan(
        row_filters={},
        allowed_columns={},
        masked={},
        denied={view_key: frozenset({DENIED_ALL})},
        policy_ids=tuple(policy_ids),
        deny_reason=reason,
    )


def _unique_ids(policies) -> tuple[int, ...]:
    out: list[int] = []
    for policy in policies or ():
        try:
            pid = int(getattr(policy, "id", 0) or 0)
        except (TypeError, ValueError):
            continue
        if pid and pid not in out:
            out.append(pid)
    return tuple(out)


def _entry_policies(policies) -> list[Policy]:
    """过滤出本模块会用的策略：启用 + ``resource_kind in {table,view}``。"""
    out = []
    for policy in policies or ():
        if policy is None or not _is_enabled(getattr(policy, "enabled", True)):
            continue
        if _lower(getattr(policy, "resource_kind", "")) not in _RESOURCE_KINDS:
            continue
        out.append(policy)
    return out


def _parse_entry(entry) -> tuple[str, str | None] | None:
    """解析一条血缘条目。

    Returns:
        ``None`` = 定位不到基表（占位/空段）；
        ``(表, None)`` = 表级；``(表, "*")`` = 整表列；``(表, 列)`` = 列级。
    """
    text = _clean(entry)
    if not text:
        return None
    parts = [_clean(part) for part in text.split(".")]
    if not parts or not parts[0]:
        return None  # ".dept_id"：基表不可知
    if all(part.lower() in _UNKNOWN_UPSTREAM for part in parts):
        return None  # "unknown" / "?"

    if len(parts) == 1:
        return (_table_key(parts[0]), None)

    if len(parts) == 2 and parts[0].lower() in _SCHEMA_PREFIXES:
        return (_table_key(parts[1]), None)  # public.表

    column = parts[-1]
    if not column:  # "fuel_price."：只到表
        return (_table_key(parts[0]), None)
    table = _table_key(".".join(parts[:-1]))
    if not table or table in _UNKNOWN_UPSTREAM:
        return None
    if column == "*":
        return (table, "*")
    if column.lower() in _UNKNOWN_UPSTREAM:
        return None
    return (table, _lower(column))


def _entry_text(item) -> str | None:
    """血缘条目归一：

    - ``str`` → 原样；
    - ``dict`` → 取 ``table`` 字段（``lineage.py`` 的 ``upstream`` 就是这个形状）；
    - 其它 / 缺 ``table`` / 非字符串 → ``None``（不可解析，按"上游存在但认不出"处理）。
    """
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        table = item.get("table")
        return table if isinstance(table, str) and table.strip() else None
    return None


def _lineage_entries(view_key: str, lineage) -> list[str | None]:
    """取该视图的血缘条目（键按 ``_table_key`` 归一：大小写 / schema 不敏感）。

    条目只做"取出"，不做解析 —— ``None`` 表示这条无法归一（见 :func:`_entry_text`）。
    """
    for key, value in (lineage or {}).items():
        if _table_key(key) != view_key:
            continue
        if isinstance(value, str) or isinstance(value, dict):
            value = [value]
        return [_entry_text(item) for item in (value or ())]
    return []


def _expr_columns(text: str) -> list[tuple[str, str]] | None:
    """表达式里的列引用 ``[(限定名, 列名)]``；解析失败返回 ``None``（fail-closed）。"""
    if _exp is None or _parse_one is None:  # pragma: no cover - 依赖缺失
        return None
    try:
        parsed = _parse_one(str(text or "").strip(), read="postgres")
    except Exception:  # noqa: BLE001 - 脏表达式按"不可证明"处理
        return None
    if parsed is None:
        return None
    return [(_lower(column.table), _lower(column.name)) for column in parsed.find_all(_exp.Column)]


def _check_expr_columns(text: str, exposed: set[str] | None) -> bool:
    """行条件 / 掩码表达式能否安全挪到视图上。

    视图列与基表列**同名**（这是血缘能映射的前提），所以要求：

    - 不带基表限定（``fuel_price.dept_id`` 在视图上不存在这个别名）；
    - 每个列都被视图暴露（``exposed is None`` = 整表列都暴露，全部放行）。
    """
    columns = _expr_columns(text)
    if columns is None:
        return False
    for qualifier, name in columns:
        if qualifier:
            return False
        if exposed is not None and name not in exposed:
            return False
    return True


def _covers(policy, column_lower: str) -> bool:
    """该策略是否作用于这一列（``columns`` 为空 = 整表，调用方已单独处理）。"""
    cols = _columns_of(policy)
    return bool(cols) and column_lower in cols


def _effect(policy) -> str:
    return _lower(getattr(policy, "effect", ""))


# ---------------------------------------------------------------------------
# 血缘解析
# ---------------------------------------------------------------------------
def _parse_lineage(
    view_key: str, lineage
) -> tuple[list[str], dict[str, list[str]], set[str], bool]:
    """把该视图的血缘拆成「已知基表」「列级映射」「整表列映射」「有无不可解析条目」。

    Returns:
        ``(tables, column_map, wildcard, has_unresolvable)``；

        - ``tables``：血缘里出现过的基表（保持条目顺序、去重）；
        - ``column_map``：表 → 视图暴露的**同名列**（只含列级条目）；
        - ``wildcard``：声明了 ``表.*`` 的表（列清单不可枚举）；
        - ``has_unresolvable``：出现了占位 / 空段条目（说明"上游存在但认不出"）。

    只有表级条目的表不会出现在 ``column_map``/``wildcard`` 里 —— 调用方据此判定
    "只能套表级 allow/deny"。
    """
    tables: list[str] = []
    column_map: dict[str, list[str]] = {}
    wildcard: set[str] = set()
    unresolvable = False
    for raw in _lineage_entries(view_key, lineage):
        parsed = _parse_entry(raw)
        if parsed is None:
            unresolvable = True
            continue
        table, column = parsed
        if table not in tables:
            tables.append(table)
        if column is None:
            continue
        if column == "*":
            wildcard.add(table)
            continue
        names = column_map.setdefault(table, [])
        if column not in {name.lower() for name in names}:
            names.append(column)
    return tables, column_map, wildcard, unresolvable


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------
def resolve_view_policies(
    view: str,
    lineage: dict[str, list[str]],
    policies: list[Policy],
) -> tuple[AccessPlan, str]:
    """把基表策略按血缘映射到视图上（三级降级），返回 ``(补充片段, tier)``。

    参数
    ----
    view:
        视图名（大小写 / schema 前缀不敏感）。
    lineage:
        视图 → 血缘条目列表，条目格式见模块 docstring。
    policies:
        **已按主体筛过**的候选策略（调用方负责；本函数不做主体判定）。

    返回
    ----
    ``tier`` 取 ``"column"`` / ``"table"`` / ``"none"``；``AccessPlan`` 是补充片段
    （拒绝时 ``denied[视图]`` 含 :data:`DENIED_ALL`）。
    """
    view_key = _table_key(view)
    if not view_key:
        return _empty_plan(), "none"

    entries = _entry_policies(policies)
    tables, column_map, wildcard, unresolvable = _parse_lineage(view_key, lineage)

    if unresolvable:
        # 「上游存在但认不出来」≠「没有上游」：只要库里有策略，就无法证明视图不依赖
        # 受保护的表 → fail-closed（审计 tier=none 可见）。
        if entries:
            return _deny_plan(view_key, _unique_ids(entries), REASON_UNRESOLVABLE), "none"
        return _empty_plan(), "none"

    # 基表顺序按血缘出现顺序（稳定输出，便于测试与审计）
    if not tables:
        return _empty_plan(), "none"

    by_table: dict[str, list[Policy]] = {}
    for policy in entries:
        by_table.setdefault(_table_key(getattr(policy, "resource_code", "")), []).append(policy)

    protected = [table for table in tables if by_table.get(table)]
    if not protected:
        # 血缘指向的表都没有策略 → 没有可施加的映射（放行，审计记 none）
        return _empty_plan(), "none"

    # tier 是**映射能力**：所有受约束基表都能到列 → column；否则只到表。
    column_capable = all(table in column_map or table in wildcard for table in protected)
    tier = "column" if column_capable else "table"

    row_conditions: list[tuple[str, str]] = []
    denied_columns: set[str] = set()
    masked_columns: dict[str, str] = {}
    used: list[Policy] = []
    deny_view = False
    deny_reason = ""

    for table in protected:
        base_policies = by_table[table]
        exposed = None if table in wildcard else column_map.get(table) or []
        exposed_set = None if exposed is None else {name.lower() for name in exposed}
        capable = table in column_map or table in wildcard

        table_denies = [
            policy
            for policy in base_policies
            if _effect(policy) == "deny" and not _columns_of(policy)
        ]
        if table_denies:
            used.extend(table_denies)
            deny_view = True
            deny_reason = f"基表 {table} 被表级 deny 拒绝"
            continue

        allows = [policy for policy in base_policies if _effect(policy) == "allow"]
        if not allows:
            # 没有任何适用的 allow → 默认拒绝（引擎口径），视图同样不可用。
            used.extend(base_policies)
            deny_view = True
            deny_reason = f"基表 {table} 没有任何适用的 allow 策略（默认拒绝）"
            continue

        used.extend(allows)
        conditions = [str(getattr(policy, "condition", "") or "").strip() for policy in allows]

        if not capable:
            # 只映射到表：表级 allow 可用，但行条件**不在这一级施加** ——
            # 无法证明视图暴露了条件列，写上去就是"假装过滤"。
            if any(conditions):
                deny_view = True
                deny_reason = REASON_TABLE_ROW
                continue
            # 基表带标记（敏感）+ 映射不到列 → 无法证明视图没暴露标记列
            marking = next(
                (
                    str(getattr(policy, "marking", "") or "").strip()
                    for policy in base_policies
                    if str(getattr(policy, "marking", "") or "").strip()
                ),
                "",
            )
            # 列级 deny/mask 同理：视图可能把敏感列换个名字暴露出来，映射不到列就
            # 证明不了没暴露 → fail-closed（与"不许假装过滤"同一口径）。
            column_restricted = any(
                _effect(policy) in {"deny", "mask"} and _columns_of(policy)
                for policy in base_policies
            )
            if marking or column_restricted:
                deny_view = True
                deny_reason = REASON_TABLE_COLUMN
            continue

        # 一级：列可映射
        if any(condition == "" for condition in conditions):
            pass  # 无条件 allow 吸收条件（与 union_condition 语义一致）
        else:
            condition = union_condition(conditions)
            if not _check_expr_columns(condition, exposed_set):
                deny_view = True  # 条件列没被视图暴露 / 带基表限定 → 不伪造
                deny_reason = f"基表 {table} 的行条件无法映射到视图列"
                continue
            row_conditions.append((table, condition))

        column_policies = [
            policy
            for policy in base_policies
            if _effect(policy) in {"deny", "mask"} and _columns_of(policy)
        ]
        if not column_policies:
            continue
        used.extend(column_policies)
        if exposed is None:
            # 整表列映射（``表.*``）但列清单不可枚举：列级限制无法精确落地 → 拒绝。
            deny_view = True
            deny_reason = f"基表 {table} 的列级限制无法在整表列映射下落地"
            continue
        for name in exposed:
            low = name.lower()
            denies = [
                policy
                for policy in column_policies
                if _effect(policy) == "deny" and _covers(policy, low)
            ]
            if denies:
                denied_columns.add(name)
                masked_columns.pop(name, None)  # deny 优先于 mask
                continue
            if name in denied_columns:
                # 别的基表已把这一视图列 deny 了：deny 优先，不再挂掩码
                # （否则会出现 allowed_columns 里没有它、masked 里却有它的自相矛盾）。
                continue
            masks = [
                policy
                for policy in column_policies
                if _effect(policy) == "mask" and _covers(policy, low)
            ]
            if not masks:
                continue
            masks.sort(key=_sort_key)  # 主体越具体 → priority 越高 → id 越小
            expr = str(getattr(masks[0], "mask_expr", "") or "").strip()
            if not expr or not _check_expr_columns(expr, exposed_set):
                deny_view = True  # 空掩码 / 引用未暴露列 → 不能生成非法 SQL
                deny_reason = f"基表 {table} 的掩码表达式无法安全套用到视图"
                break
            previous = masked_columns.get(name)
            if previous and previous != expr:
                deny_view = True  # 同一视图列被两张基表配了不同掩码，无法判定
                deny_reason = f"视图列 {name} 来自多张基表且掩码不一致"
                break
            masked_columns[name] = expr

    policy_ids = _unique_ids(used)

    if not deny_view and row_conditions and tier != "column":
        # 混合粒度：一张基表到了列、另一张只到表。tier 三值里没有 mixed，
        # 而"table 级只套 allow/deny"又要求不出现行条件 → 整视图拒绝（不许假装过滤）。
        deny_view = True
        deny_reason = REASON_MIXED

    if deny_view:
        return _deny_plan(view_key, policy_ids, deny_reason), tier

    # 不同基表的行条件不能 OR 到一起（会把另一张表的过滤整段丢掉）
    if len(row_conditions) > 1:
        return _deny_plan(view_key, policy_ids, REASON_MULTI_ROW), tier

    row_filters: dict[str, str] = {}
    if row_conditions:
        row_filters[view_key] = row_conditions[0][1]

    masked: dict[str, dict[str, str]] = {}
    if masked_columns:
        masked[view_key] = dict(masked_columns)

    denied: dict[str, frozenset[str]] = {}
    if denied_columns:
        denied[view_key] = frozenset(denied_columns)

    allowed_columns: dict[str, tuple[str, ...] | None] = {}
    if tier == "column" and not any(table in wildcard for table in protected):
        # 列白名单 = 视图暴露的列（去 deny）；星号按它展开，掩码列在展开时替换
        ordered: list[str] = []
        seen: set[str] = set()
        for table in protected:
            for name in column_map.get(table) or []:
                if name.lower() in seen:
                    continue
                if name in denied_columns:
                    continue
                seen.add(name.lower())
                ordered.append(name)
        allowed_columns[view_key] = tuple(ordered)

    return (
        AccessPlan(
            row_filters=row_filters,
            allowed_columns=allowed_columns,
            masked=masked,
            denied=denied,
            policy_ids=policy_ids,
        ),
        tier,
    )
