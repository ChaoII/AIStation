"""策略判定引擎：把 ``ai_policy`` 行 + 访问主体算成「放/拒 + 怎么改」。

设计稿：``docs/superpowers/specs/2026-11-06-query-permission-model-design.md`` §3.2。

本模块是**纯逻辑**：不读库、不解析 SQL、不生成 SQL 改写。输入的 ``Policy`` 由
调用方（QueryGuard / 迁移器 / explain 接口）从库里读好再传进来，因此可以脱离
应用与数据库单测（``PYTEST_NO_APP=1``）。

判定规则（与 spec 逐条对应）：

1. ``deny`` > ``mask`` > ``allow``（表级 deny 短路；列级 deny 只影响对应列）；
2. 同一 effect 内按**主体具体性** ``user > attr > role > domain > everyone``；
3. 同具体性按 ``priority`` 降序；仍并列时按 ``id`` 升序（保证结果稳定可复现）；
   ``allow`` 并列取**并集**（多条行条件用 ``OR`` 连接，policy_ids 全带上）；
4. 超管绕过一切策略，``reason="superuser bypass"``、``policy_ids=()``；
5. **表级默认拒绝**：没有任何适用的 ``allow`` 就拒绝；
6. **列级默认继承**：表的 ``allow``（``columns=[]`` 即整表可读）覆盖所有列，
   列的限制**只来自显式** ``deny`` / ``mask``。这里刻意**不实现**"列默认拒绝"——
   ``allow.columns`` 是「按列的额外授予」（如允许对敏感列做聚合），不是列白名单。

两个容易踩的语义边界：

- ``condition`` 只有 ``allow`` 用（行级过滤）。表达式里的 ``$attr.<name>`` 在
  ``principal.attrs`` 里缺失（或为空）时视为**条件不成立** → 该 allow 不适用；
  若所有 allow 都不适用 → 该表 deny（fail-closed，不是"忽略条件放行"）。
- ``mask`` / ``deny`` **不是授权**：只有 mask 而没有 allow 时，表仍然默认拒绝。

``Decision.sql`` 的语义：表级判定时放行策略的行条件（多条以 ``OR`` 并集连接，
原样保留 ``$attr.*`` / ``$user.id`` 占位符，由编译器做参数命名空间隔离）；
列级判定时为空串；掩码改写放在 ``applied[0]["mask"]``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 运行时不依赖 principal（它要连库），保持纯逻辑与可单测
    from .principal import Principal

__all__ = ["Decision", "Policy", "decide_column", "decide_table"]

#: 主体具体性：数值越大越具体（spec §3.2 第 2 条，brief 把 domain 排在 role 之后）。
_SUBJECT_SPECIFICITY: dict[str, int] = {
    "user": 5,
    "attr": 4,
    "role": 3,
    "domain": 2,
    "everyone": 1,
}

#: effect 的裁决顺序：先看有没有 deny，再看 mask，最后才是 allow。
_EFFECT_ORDER: dict[str, int] = {"deny": 0, "mask": 1, "allow": 2}

#: 行条件里的属性引用：``$attr.dept_id``。
_ATTR_REF = re.compile(r"\$attr\.([A-Za-z_][A-Za-z0-9_]*)")

#: 行条件里的用户 id 引用：``$user.id``。
_USER_ID_REF = re.compile(r"\$user\.id\b")

#: ``attr`` 主体的写法：``dept_id == 3`` / ``dept_id=3`` / ``dept_id:3``。
_ATTR_SUBJECT = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:==|=|:)\s*(.+?)\s*$")

#: 数据域成员（``domain`` 主体）在 Principal 里暂时借 ``attrs`` 承载：
#: ``attrs["domains"]="hr, finance"``。Principal 没有 domains 字段（Task 2 的接口
#: 不可改），因此这里只认这个约定；没有该属性时 domain 策略不匹配（fail-closed）。
_DOMAIN_ATTR_KEYS = ("domains", "domain")

#: ``domain`` 列表的分隔符（中英文逗号/分号/空白都容忍）。
_DOMAIN_SPLIT = re.compile(r"[,;，；\s]+")


@dataclass(frozen=True)
class Policy:
    """一条策略（``ai_policy`` 行的只读投影）。

    字段与表列一一对应；``columns`` 用元组（可哈希、可比较，JSONB 列表读出来是 list，
    由调用方归一）。``effect`` 取 ``allow`` / ``deny`` / ``mask``；
    ``subject_kind`` 取 ``everyone`` / ``role`` / ``user`` / ``attr`` / ``domain``。
    """

    id: int
    effect: str
    resource_kind: str
    resource_code: str
    subject_kind: str
    subject_value: str
    condition: str
    columns: tuple[str, ...]
    mask_expr: str
    marking: str
    priority: int
    enabled: bool


@dataclass(frozen=True)
class Decision:
    """一次判定的结果。

    - ``permit``：是否放行；
    - ``reason``：给人看的一句话（审计/explain 直接用；超管固定带 ``superuser``）；
    - ``policy_ids``：参与本次裁决的策略 id（超管绕过时为空）；
    - ``sql``：表级行过滤条件（多条 allow 并集，``$attr.*`` 占位符原样保留）；
    - ``applied``：实际施加的改写，目前两种形态：``{"row": 表达式}``、``{"mask": 表达式}``。
    """

    permit: bool
    reason: str = ""
    policy_ids: tuple[int, ...] = ()
    sql: str = ""
    applied: tuple[dict, ...] = ()


# ---------------------------------------------------------------------------
# 小型工具（全部 fail-closed：看不懂就"不匹配/不放行"，绝不猜）
# ---------------------------------------------------------------------------
def _text(value) -> str:
    return str(value or "").strip()


def _table_key(value) -> str:
    """表名归一：小写、去空白、去 schema 前缀（``public.t`` 与 ``t`` 视为同一张表）。"""
    key = _text(value).lower()
    if "." in key:
        key = key.rsplit(".", 1)[1]
    return key


def _subject_specificity(policy: Policy) -> int:
    return _SUBJECT_SPECIFICITY.get(_text(policy.subject_kind).lower(), 0)


def _sort_key(policy: Policy) -> tuple[int, int, int, int]:
    """同 effect 内的裁决顺序：具体性降序 → priority 降序 → id 升序。"""
    return (
        _EFFECT_ORDER.get(_text(policy.effect).lower(), 9),
        -_subject_specificity(policy),
        -int(policy.priority or 0),
        int(policy.id or 0),
    )


def _attr_pairs(principal) -> dict[str, str]:
    attrs = getattr(principal, "attrs", None) or {}
    return {_text(k).lower(): _text(v) for k, v in attrs.items()}


def _subject_matches(policy: Policy, principal) -> bool:
    """主体是否命中。任何无法解析的主体一律**不命中**（fail-closed）。"""
    kind = _text(policy.subject_kind).lower()
    value = _text(policy.subject_value)

    if kind == "everyone":
        return True

    if kind == "user":
        uid = getattr(principal, "user_id", None)
        return uid is not None and str(uid) == value

    if kind == "role":
        if not value:
            return False
        roles = {_text(r).upper() for r in (getattr(principal, "roles", None) or ())}
        return value.upper() in roles

    if kind == "attr":
        m = _ATTR_SUBJECT.match(value)
        if not m:
            return False
        name, expected = m.group(1).lower(), _text(m.group(2))
        actual = _attr_pairs(principal).get(name, "")
        return bool(actual) and actual.lower() == expected.lower()

    if kind == "domain":
        if not value:
            return False
        attrs = _attr_pairs(principal)
        members: set[str] = set()
        for key in _DOMAIN_ATTR_KEYS:
            for item in _DOMAIN_SPLIT.split(attrs.get(key, "")):
                if item:
                    members.add(item.lower())
        return value.lower() in members

    return False


def _condition_state(policy: Policy, principal) -> tuple[bool, tuple[str, ...]]:
    """行条件对该主体是否成立；返回 ``(是否成立, 缺失的属性名)``。

    引擎不执行 SQL，只做**可判定部分**：``$attr.x`` 缺属性、``$user.id`` 缺身份
    → 条件不成立（spec §5.2：缺属性按不成立处理，不是忽略条件）。其余表达式
    （常量比较、列比较）交给编译器下推，这里视为成立。
    """
    condition = _text(policy.condition)
    if not condition:
        return True, ()

    attrs = _attr_pairs(principal)
    missing: list[str] = []
    for name in _ATTR_REF.findall(condition):
        if not attrs.get(name.lower(), ""):
            missing.append(name)
    if _USER_ID_REF.search(condition) and not getattr(principal, "user_id", None):
        missing.append("$user.id")

    # 去重且保持出现顺序：reason 里的提示要稳定
    return (not missing), tuple(dict.fromkeys(missing))


def _candidates(policies, principal, table: str) -> list[Policy]:
    """筛出「启用 + 资源命中 + 主体命中」的策略，并保持稳定顺序。

    资源只比 ``resource_code``（大小写与 schema 前缀不敏感）。``resource_kind``
    不在这里过滤：调用方按需只加载表/视图/对象策略；数据源级策略（``ds:4``）
    与表名不会撞名，交给上层处理。
    """
    target = _table_key(table)
    if not target:
        return []
    out: list[Policy] = []
    for policy in policies or ():
        if policy is None or not getattr(policy, "enabled", True):
            continue
        if _table_key(policy.resource_code) != target:
            continue
        if not _subject_matches(policy, principal):
            continue
        out.append(policy)
    return out


def _by_effect(candidates, effect: str) -> list[Policy]:
    return [p for p in candidates if _text(p.effect).lower() == effect]


def _columns_of(policy: Policy) -> set[str]:
    """策略的列清单（小写）；``columns`` 为空 = 整表。

    兼容 ``columns`` 意外是字符串的情况（例如直接构造 Policy 或上游返回了逗号串）：
    否则 ``tuple("phone")`` 会变成 ``('p','h','o','n','e')``，掩码/deny 会**静默失效**。
    """
    cols = policy.columns
    if cols is None:
        return set()
    items = re.split(r"[,;]", cols) if isinstance(cols, str) else list(cols)
    return {_text(c).lower() for c in items if _text(c)}


def _covers_column(policy: Policy, column: str) -> bool:
    """策略是否作用于该列：``columns`` 为空 = 整表（含所有列）。"""
    cols = _columns_of(policy)
    return not cols or _text(column).lower() in cols


def _ids(policies) -> tuple[int, ...]:
    return tuple(int(p.id or 0) for p in policies)


def _deny_reason(policies, subject: str) -> str:
    return f"{subject} 命中 deny 策略：policy_ids={list(_ids(policies))}"


def _missing_attr_reason(policies, missing: tuple[str, ...], subject: str) -> str:
    return (
        f"{subject} 的行级条件不成立：缺少属性 {', '.join(missing)}"
        f"（policy_ids={list(_ids(policies))}）"
    )


def _default_deny_reason(table: str) -> str:
    return f"默认拒绝：表 {table} 没有任何适用的 allow 策略"


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------
def decide_table(policies: list[Policy], principal: Principal, table: str) -> Decision:
    """表级判定：**能不能查这张表** + 要用什么行过滤条件。

    - 显式表级 ``deny``（``columns`` 为空）短路 → 拒绝；列级 deny 不影响表级放行；
    - 没有任何适用的 ``allow`` → 拒绝（默认拒绝），缺属性导致的 allow 不适用也拒绝；
    - 放行时 ``sql`` 是多条行条件的并集（``OR``），``applied`` 逐条记录。
    """
    if principal is None:
        return Decision(False, "missing principal")
    if getattr(principal, "is_superuser", False):
        return Decision(True, "superuser bypass")

    candidates = _candidates(policies, principal, table)

    table_denies = [p for p in _by_effect(candidates, "deny") if not _columns_of(p)]
    if table_denies:
        table_denies.sort(key=_sort_key)
        return Decision(False, _deny_reason(table_denies, f"表 {table}"), _ids(table_denies))

    allows = _by_effect(candidates, "allow")
    applicable: list[Policy] = []
    missing: list[str] = []
    for policy in allows:
        ok, lacked = _condition_state(policy, principal)
        if ok:
            applicable.append(policy)
        else:
            missing.extend(lacked)

    if not applicable:
        if allows:
            return Decision(
                False,
                _missing_attr_reason(allows, tuple(dict.fromkeys(missing)), f"表 {table}"),
                _ids(sorted(allows, key=_sort_key)),
            )
        return Decision(False, _default_deny_reason(table))

    applicable.sort(key=_sort_key)
    rows = [c for c in (_text(p.condition) for p in applicable) if c]
    sql = " OR ".join(f"({c})" for c in rows) if len(rows) > 1 else (rows[0] if rows else "")
    return Decision(
        True,
        f"允许：表 {table} 命中 {len(applicable)} 条 allow 策略",
        _ids(applicable),
        sql,
        tuple({"row": c} for c in rows),
    )


def decide_column(
    policies: list[Policy], principal: Principal, table: str, column: str
) -> Decision:
    """列级判定：**这一列能不能读 / 要不要脱敏**。

    裁决顺序（spec §3.2）：

    1. 显式列 ``deny``（``columns`` 为空或包含该列）→ 拒绝；
    2. 没有任何适用的表 ``allow`` → 拒绝（列级默认**继承**表 allow，不是列默认拒绝）；
    3. 列 ``mask``（``columns`` 为空或包含该列）→ 放行但 ``applied=[{"mask": ...}]``；
       多条命中时取「主体最具体 → priority 最高 → id 最小」的那条；
    4. 否则放行（继承表 allow，``applied`` 为空）。

    ``allow.columns`` 只表示按列的额外授予，**不会**把其它列变成不可读。
    """
    if principal is None:
        return Decision(False, "missing principal")
    if getattr(principal, "is_superuser", False):
        return Decision(True, "superuser bypass")

    candidates = _candidates(policies, principal, table)

    column_denies = [p for p in _by_effect(candidates, "deny") if _covers_column(p, column)]
    if column_denies:
        column_denies.sort(key=_sort_key)
        return Decision(False, _deny_reason(column_denies, f"列 {column}"), _ids(column_denies))

    allows = _by_effect(candidates, "allow")
    applicable: list[Policy] = []
    missing: list[str] = []
    for policy in allows:
        ok, lacked = _condition_state(policy, principal)
        if ok:
            applicable.append(policy)
        else:
            missing.extend(lacked)

    if not applicable:
        if allows:
            return Decision(
                False,
                _missing_attr_reason(allows, tuple(dict.fromkeys(missing)), f"列 {column}"),
                _ids(sorted(allows, key=_sort_key)),
            )
        return Decision(False, _default_deny_reason(table))

    masks = [p for p in _by_effect(candidates, "mask") if _covers_column(p, column)]
    if masks:
        masks.sort(key=_sort_key)
        chosen = masks[0]
        expr = _text(chosen.mask_expr)
        if not expr:
            # 配了 mask 却没表达式：不能退化成"明文放行"，fail-closed。
            return Decision(
                False,
                f"列 {column} 的掩码策略 {chosen.id} 缺少掩码表达式，拒绝访问",
                _ids(masks),
            )
        return Decision(
            True,
            f"允许但脱敏：列 {column} 命中 mask 策略 {chosen.id}",
            _ids([chosen]) + _ids(sorted(applicable, key=_sort_key)),
            "",
            ({"mask": expr},),
        )

    return Decision(
        True,
        f"允许：列 {column} 继承表 {table} 的 allow",
        _ids(sorted(applicable, key=_sort_key)),
    )
