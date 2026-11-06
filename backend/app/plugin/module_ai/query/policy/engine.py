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
   **无条件 allow 吸收条件**：只要有一条无条件的 allow，整表可读、``sql=""``；
4. 超管绕过一切策略，``reason="superuser bypass"``、``policy_ids=()``；
5. **表级默认拒绝**：没有任何适用的 ``allow`` 就拒绝；
6. **列级默认继承**：表的 ``allow``（``columns=[]`` 即整表可读）覆盖所有列，
   列的限制**只来自显式** ``deny`` / ``mask``。这里刻意**不实现**"列默认拒绝"——
   ``allow.columns`` 是「按列的额外授予」（如允许对敏感列做聚合），不是列白名单。

资源范围（Ruling）：**本引擎只吃 ``resource_kind in {"table","view"}`` 的策略**，
``object`` / ``datasource`` 等 kind 在 ``decide_table`` / ``decide_column`` 内直接忽略
（对象权限走 ``ontology/security.py``；对象行策略由 T8 迁成物理表的 table 策略）。

三个容易踩的语义边界：

- ``condition`` 只有 ``allow`` 用（行级过滤）。表达式里的 ``$attr.<name>`` 在
  ``principal.attrs`` 里缺失（或为空）时视为**条件不成立** → 该 allow 不适用；
  若所有 allow 都不适用 → 该表 deny（fail-closed，不是"忽略条件放行"）。
  保守之处：``$attr.x`` 出现在**字符串字面量**里也会被当成属性引用（宁可误拒）。
- ``mask`` / ``deny`` **不是授权**：只有 mask 而没有 allow 时，表仍然默认拒绝。
- ``attr`` 主体的写法是 ``dept_id == 3``，值**不要加引号**（``"3"`` / ``'3'`` 不匹配）；
  属性值可以是标量，也可以是 list/tuple/set（任一元素命中即匹配）。
- ``domain`` 主体读 ``attrs["domains"]``（或 ``attrs["domain"]``），值可以是逗号串
  或容器。**T6 接线时必须注入该属性**（``load_principal`` 现在只读 ``dept_id``），
  否则域策略在 enforce 下永远不匹配。

``Decision.sql`` 的语义：表级判定时放行策略的行条件（多条以 ``OR`` 并集连接，
原样保留 ``$attr.*`` / ``$user.id`` 占位符，由编译器做参数命名空间隔离）；
**有一条无条件 allow 时为空串**（无条件授权吸收条件）；列级判定时为空串；
掩码改写放在 ``applied[0]["mask"]``。

T9 ``build_plan`` 复用 :func:`applicable_condition` 与 :func:`union_condition`，
不要另写一套并集/缺属性判断（两套实现会 drift，shadow diff 抓不到）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # 运行时不依赖 principal（它要连库），保持纯逻辑与可单测
    from .principal import Principal

__all__ = [
    "Decision",
    "Policy",
    "applicable_condition",
    "decide_column",
    "decide_table",
    "matched_policies",
    "missing_attributes",
    "union_condition",
]

#: 本引擎处理的资源类型（Ruling）：对象权限走 ``ontology/security.py``，
#: 数据源级策略不落到具体表。其它 kind 在判定时**直接忽略**。
_POLICY_RESOURCE_KINDS = frozenset({"table", "view"})

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
    """转成去空白字符串；只有 ``None`` 算"没有值"。

    不能写 ``str(value or "")``：``0`` / ``False`` 会被误判成缺失（属性值 0 是合法值，
    按缺失处理会让行条件被误拒）。
    """
    return "" if value is None else str(value).strip()


def _is_enabled(value) -> bool:
    """``enabled`` 归一：数据库 bool 之外，也容忍配置串（``"false"`` / ``"0"`` / ``"no"``）。"""
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off", "n"}
    return bool(value)


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


def _raw_attrs(principal) -> dict[str, object]:
    """主体属性（键小写），**保留原始类型**（可能是 str，也可能是 list/tuple/set）。"""
    attrs = getattr(principal, "attrs", None) or {}
    return {_text(k).lower(): v for k, v in attrs.items()}


def _attr_values(value) -> list[str]:
    """把一个属性值摊平成文本列表；容器（list/tuple/set）逐元素摊平。

    字符串保持**整体**（不按空白/逗号切分）——``attr`` 主体的 ``dept_name == East China``
    这类值本身可能带空格。需要切分成多个记号的是域成员，见 :func:`_domain_tokens`。
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple, set, frozenset)):
        out: list[str] = []
        for item in value:
            out.extend(_attr_values(item))
        return out
    text = _text(value)
    return [text] if text else []


def _domain_tokens(value) -> list[str]:
    """域成员记号：在 :func:`_attr_values` 基础上再按逗号/分号/空白切分。"""
    out: list[str] = []
    for item in _attr_values(value):
        out.extend(v for v in (tok.strip() for tok in _DOMAIN_SPLIT.split(item)) if v)
    return out


def _attr_present(value) -> bool:
    """属性是否有可用值；容器要求至少一个非空元素，空串视为缺失（fail-closed）。"""
    return bool(_attr_values(value))


def _attr_matches(value, expected: str) -> bool:
    """属性值是否等于期望值；容器任一元素命中即可（大小写不敏感）。"""
    want = _text(expected).lower()
    if not want:
        return False
    return any(v.lower() == want for v in _attr_values(value))


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
        # 约定：subject_value 写成 ``dept_id == 3``，值**不要加引号**（``"3"`` / `'3'` 都不匹配）。
        m = _ATTR_SUBJECT.match(value)
        if not m:
            return False
        name, expected = m.group(1).lower(), _text(m.group(2))
        return _attr_matches(_raw_attrs(principal).get(name), expected)

    if kind == "domain":
        if not value:
            return False
        attrs = _raw_attrs(principal)
        members: set[str] = set()
        for key in _DOMAIN_ATTR_KEYS:
            members.update(v.lower() for v in _domain_tokens(attrs.get(key)))
        return value.lower() in members

    return False


def _missing_conditions(policy: Policy, principal) -> tuple[str, ...]:
    """行条件里**无法在本主体上判定**的引用；空元组 = 条件对主体成立。

    引擎不执行 SQL，只做**可判定部分**：``$attr.x`` 缺属性、``$user.id`` 缺身份
    → 条件不成立（spec §5.2：缺属性按不成立处理，不是忽略条件）。其余表达式
    （常量比较、列比较）交给编译器下推，这里视为成立。

    保守之处：``$attr.x`` 出现在**字符串字面量**里（如 ``note = '$attr.dept_id'``）
    也会被当成属性引用；属性缺失时该策略不适用。这偏向误拒而非误放，可接受。
    """
    condition = _text(policy.condition)
    if not condition:
        return ()

    attrs = _raw_attrs(principal)
    missing: list[str] = []
    for name in _ATTR_REF.findall(condition):
        if not _attr_present(attrs.get(name.lower())):
            missing.append(name)
    if _USER_ID_REF.search(condition) and not getattr(principal, "user_id", None):
        missing.append("$user.id")

    # 去重且保持出现顺序：reason 里的提示要稳定
    return tuple(dict.fromkeys(missing))


def applicable_condition(policy: Policy, principal: Principal) -> str | None:
    """公开 helper（T9 ``build_plan`` 复用）：该 allow 策略对这个主体的行条件。

    - ``None``：**不适用**（缺属性 / 缺 ``$user.id``）；
    - ``""``：适用且**无条件**（整表可读）；
    - 其它：适用，返回条件表达式（``$attr.*`` / ``$user.id`` 占位符原样保留，
      由编译器做参数命名空间隔离）。
    """
    missing = _missing_conditions(policy, principal)
    if missing:
        return None
    return _text(policy.condition)


def union_condition(conditions: list[str]) -> str:
    """公开 helper（T9 ``build_plan`` 复用）：多条行条件取**并集**。

    - 任一为空串（无条件授权）→ 整组吸收，返回 ``""``（否则会把无条件授权缩窄成
      有条件过滤，用户被静默藏行——T8 backfill 后 ``legacy_default_allow`` 与域/行策略
      同命中时会真实发生）；
    - 空列表 → ``""``（没有约束）；
    - 多条 → ``(a) OR (b)``；单条原样返回。
    """
    rows = list(conditions or ())
    if not rows or any(row == "" for row in rows):
        return ""
    if len(rows) == 1:
        return rows[0]
    return " OR ".join(f"({row})" for row in rows)


def _candidates(policies, principal, table: str) -> list[Policy]:
    """筛出「启用 + 资源命中 + 主体命中」的策略，并保持稳定顺序。

    只处理 ``resource_kind in {"table","view"}`` 的策略（Ruling）：对象权限走
    ``ontology/security.py``，数据源级策略与表名不是同一层资源。否则同一个 code 的
    ``object`` 策略会意外给同名物理表放行。

    资源只比 ``resource_code``（大小写与 schema 前缀不敏感）。
    """
    target = _table_key(table)
    if not target:
        return []
    out: list[Policy] = []
    for policy in policies or ():
        if policy is None or not _is_enabled(getattr(policy, "enabled", True)):
            continue
        kind = _text(getattr(policy, "resource_kind", "")).lower()
        if kind not in _POLICY_RESOURCE_KINDS:
            continue
        if _table_key(policy.resource_code) != target:
            continue
        if not _subject_matches(policy, principal):
            continue
        out.append(policy)
    return out


def _by_effect(candidates, effect: str) -> list[Policy]:
    return [p for p in candidates if _text(p.effect).lower() == effect]


def matched_policies(policies, principal, table: str) -> list[Policy]:
    """**explain 接口用**：命中「资源 + 主体」的策略，按裁决顺序返回。

    只是 :func:`_candidates` 的公开镜像（再按 ``_sort_key`` 排序），供治理页展示
    「这次判定看到了哪些策略」。判定本身仍只走 :func:`decide_table` /
    :func:`decide_column`，这里不参与放行/拒绝。
    """
    if principal is None or getattr(principal, "is_superuser", False):
        # 超管绕过一切策略：展示"没有策略参与"比列一堆会误导人。
        return []
    out = _candidates(policies, principal, table)
    out.sort(key=_sort_key)
    return out


def missing_attributes(policies, principal, table: str) -> tuple[str, ...]:
    """**explain 接口用**：命中的 ``allow`` 策略里，本主体缺失的属性名。

    与 :func:`applicable_condition` 同一套判断（缺属性 → allow 不适用 → 该表拒绝），
    只是把"缺了什么"单独摊出来给运维看。没有缺失时返回空元组。
    """
    if principal is None or getattr(principal, "is_superuser", False):
        return ()
    missing: list[str] = []
    for policy in _candidates(policies, principal, table):
        if _text(policy.effect).lower() != "allow":
            continue
        missing.extend(_missing_conditions(policy, principal))
    return tuple(dict.fromkeys(missing))


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


def _split_allows(
    allows: list[Policy], principal
) -> tuple[list[Policy], list[str], tuple[str, ...]]:
    """把 allow 分成「适用」与「不适用」，并带回适用的行条件与缺失属性。

    条件返回值语义见 :func:`applicable_condition`：``None`` = 不适用，``""`` = 无条件。
    """
    applicable: list[Policy] = []
    conditions: list[str] = []
    missing: list[str] = []
    for policy in allows:
        condition = applicable_condition(policy, principal)
        if condition is None:
            missing.extend(_missing_conditions(policy, principal))
            continue
        applicable.append(policy)
        conditions.append(condition)
    return applicable, conditions, tuple(dict.fromkeys(missing))


# ---------------------------------------------------------------------------
# 对外接口
# ---------------------------------------------------------------------------
def decide_table(policies: list[Policy], principal: Principal, table: str) -> Decision:
    """表级判定：**能不能查这张表** + 要用什么行过滤条件。

    - 显式表级 ``deny``（``columns`` 为空）短路 → 拒绝；列级 deny 不影响表级放行；
    - 没有任何适用的 ``allow`` → 拒绝（默认拒绝），缺属性导致的 allow 不适用也拒绝；
    - 放行时 ``sql`` 是行条件的并集；**只要有一条无条件的 allow，``sql`` 就是空串**
      （无条件授权吸收所有条件，整表可读，``applied`` 也为空）。
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
    applicable, conditions, missing = _split_allows(allows, principal)

    if not applicable:
        if allows:
            return Decision(
                False,
                _missing_attr_reason(allows, missing, f"表 {table}"),
                _ids(sorted(allows, key=_sort_key)),
            )
        return Decision(False, _default_deny_reason(table))

    applicable.sort(key=_sort_key)
    sql = union_condition(conditions)
    return Decision(
        True,
        f"允许：表 {table} 命中 {len(applicable)} 条 allow 策略",
        _ids(applicable),
        sql,
        tuple({"row": c} for c in conditions) if sql else (),
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
    applicable, _conditions, missing = _split_allows(allows, principal)

    if not applicable:
        if allows:
            return Decision(
                False,
                _missing_attr_reason(allows, missing, f"列 {column}"),
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
