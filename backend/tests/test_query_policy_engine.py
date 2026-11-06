"""Task 4：策略判定引擎（纯逻辑，不碰数据库）。

覆盖设计稿 §3.2 的六条硬规则：

1. ``deny`` > ``mask`` > ``allow``；
2. 同 effect 内主体具体性 ``user > attr > role > domain > everyone``；
3. 同具体性按 ``priority`` 降序；``allow`` 并列取并集；
4. 超管绕过但 reason 带 ``superuser``；
5. 表级默认拒绝（没有 allow 就拒）；
6. 列级默认继承表 allow（``columns=[]`` = 整表可读），列的限制只来自显式 deny/mask。

外加边界：禁用策略、大小写、缺主体、缺属性、空掩码、并列取哪条。

全部用例都是纯逻辑（``PYTEST_NO_APP=1`` 可跑，不需要应用/数据库）。
"""

from __future__ import annotations

import itertools

from app.plugin.module_ai.query.policy.engine import (
    Decision,
    Policy,
    applicable_condition,
    decide_column,
    decide_table,
    union_condition,
)
from app.plugin.module_ai.query.policy.principal import Principal

_ids = itertools.count(1)


def P(*, user_id=7, is_superuser=False, roles=("USER",), attrs=None, entry="ask") -> Principal:
    """构造访问主体（默认普通 USER 角色，无属性）。"""
    return Principal(
        user_id=user_id,
        is_superuser=is_superuser,
        roles=tuple(roles),
        attrs=dict(attrs or {}),
        entry=entry,
    )


def pol(
    effect,
    subject_kind="role",
    subject_value="USER",
    *,
    table="t",
    columns=(),
    condition="",
    mask_expr="",
    priority=100,
    enabled=True,
    pid=None,
    kind="table",
) -> Policy:
    """构造一条策略；``id`` 自动递增，断言时用对象自己的 id 比较。"""
    return Policy(
        id=next(_ids) if pid is None else pid,
        effect=effect,
        resource_kind=kind,
        resource_code=table,
        subject_kind=subject_kind,
        subject_value=subject_value,
        condition=condition,
        columns=(columns,) if isinstance(columns, str) else tuple(columns),
        mask_expr=mask_expr,
        marking="",
        priority=priority,
        enabled=enabled,
    )


def allow(table="t", subject_kind="role", subject_value="USER", **kw) -> Policy:
    return pol("allow", subject_kind, subject_value, table=table, **kw)


def deny(table="t", subject_kind="role", subject_value="USER", **kw) -> Policy:
    return pol("deny", subject_kind, subject_value, table=table, **kw)


def mask(
    table="t",
    subject_kind="role",
    subject_value="USER",
    columns=("phone",),
    mask_expr="LEFT(phone,3)",
    **kw,
) -> Policy:
    return pol(
        "mask",
        subject_kind,
        subject_value,
        table=table,
        columns=columns,
        mask_expr=mask_expr,
        **kw,
    )


# ---------------------------------------------------------------------------
# 规则 5：表级默认拒绝
# ---------------------------------------------------------------------------
def test_default_deny_without_allow():
    assert not decide_table([], P(roles=("USER",)), "t").permit


def test_allow_for_other_table_does_not_help():
    d = decide_table([allow(table="other")], P(), "t")
    assert not d.permit
    assert "t" in d.reason


def test_deny_alone_denies():
    d = decide_table([deny()], P(), "t")
    assert not d.permit
    assert d.policy_ids and len(d.policy_ids) == 1
    assert "deny" in d.reason


# ---------------------------------------------------------------------------
# 规则 4：超管绕过（reason 必须可识别），且没有命中策略
# ---------------------------------------------------------------------------
def test_superuser_bypasses_but_reports_reason():
    d = decide_table([], P(is_superuser=True), "t")
    assert d.permit and "superuser" in d.reason
    assert d.policy_ids == ()

    # 超管连显式 deny 都绕过（策略列表照传）
    d2 = decide_table([deny()], P(is_superuser=True), "t")
    assert d2.permit and "superuser" in d2.reason
    assert decide_column([deny(columns=("phone",))], P(is_superuser=True), "t", "phone").permit


# ---------------------------------------------------------------------------
# 规则 1：deny > mask > allow
# ---------------------------------------------------------------------------
def test_deny_beats_allow():
    pols = [allow("t", "role", "USER"), deny("t", "role", "USER")]
    d = decide_table(pols, P(roles=("USER",)), "t")
    assert not d.permit
    assert d.policy_ids == (pols[1].id,)


def test_mask_beats_allow_but_not_deny():
    pols = [
        allow("t", "role", "USER"),
        mask("t", "role", "USER", "phone", "LEFT(phone,3)"),
    ]
    d = decide_column(pols, P(roles=("USER",)), "t", "phone")
    assert d.permit and d.applied[0]["mask"] == "LEFT(phone,3)"

    # 再加一条 deny：mask 不能再"放行"，deny 赢
    pols.append(deny("t", "role", "USER", columns=("phone",)))
    d2 = decide_column(pols, P(roles=("USER",)), "t", "phone")
    assert not d2.permit
    assert d2.policy_ids == (pols[2].id,)


def test_mask_alone_does_not_grant_the_table():
    """mask 不是授权：没有 allow 时表仍按默认拒绝。"""
    assert not decide_table([mask()], P(), "t").permit
    assert not decide_column([mask()], P(), "t", "phone").permit


def test_mask_without_expression_denies():
    """配了 mask 却没写表达式：fail-closed，不能当放行。"""
    d = decide_column([allow(), mask(mask_expr="")], P(), "t", "phone")
    assert not d.permit
    assert "掩码" in d.reason


def test_string_columns_are_not_split_into_characters():
    """``columns`` 意外是字符串时仍按「一个列名」处理，绝不让 mask 静默失效。"""
    pols = [
        allow(),
        pol("mask", columns="phone", mask_expr="LEFT(phone,3)"),
    ]
    d = decide_column(pols, P(), "t", "phone")
    assert d.permit and d.applied[0]["mask"] == "LEFT(phone,3)"


# ---------------------------------------------------------------------------
# 规则 2 + 3：具体性与 priority
# ---------------------------------------------------------------------------
def test_most_specific_subject_wins():
    pols = [
        allow("t", "everyone", "", columns=("a", "b")),
        deny("t", "role", "USER", columns=("b",)),
    ]
    assert decide_column(pols, P(roles=("USER",)), "t", "a").permit
    assert not decide_column(pols, P(roles=("USER",)), "t", "b").permit


def test_specificity_beats_priority_within_same_effect():
    """同 effect 内先比具体性，再比 priority：user 低优先级也压过 role 高优先级。"""
    pols = [
        mask("t", "role", "USER", "phone", "LEFT(phone,1)", priority=999),
        mask("t", "user", "7", "phone", "LEFT(phone,2)", priority=1),
    ]
    d = decide_column(pols + [allow()], P(user_id=7), "t", "phone")
    assert d.permit and d.applied[0]["mask"] == "LEFT(phone,2)"
    assert d.policy_ids[0] == pols[1].id


def test_priority_breaks_ties_within_same_specificity():
    pols = [
        mask("t", "role", "USER", "phone", "LEFT(phone,1)", priority=10),
        mask("t", "role", "USER", "phone", "LEFT(phone,9)", priority=500),
    ]
    d = decide_column(pols + [allow()], P(), "t", "phone")
    assert d.applied[0]["mask"] == "LEFT(phone,9)"


def test_allow_conditions_are_unioned():
    """allow 并列取并集：多条行条件以 OR 连接，policy_ids 全含。"""
    pols = [
        allow(condition="dept_id = $attr.dept_id", priority=200),
        allow(condition="owner_id = $user.id", priority=10),
    ]
    d = decide_table(pols, P(user_id=7, attrs={"dept_id": "3"}), "t")
    assert d.permit
    assert "dept_id = $attr.dept_id" in d.sql and "owner_id = $user.id" in d.sql
    assert " OR " in d.sql and d.sql.count("(") == 2
    assert set(d.policy_ids) == {pols[0].id, pols[1].id}
    assert len(d.applied) == 2


def test_unconditional_allow_absorbs_conditional_union():
    """无条件授权吸收有条件授权：整表可读，绝不能缩窄成行过滤（否则用户被静默藏行）。

    T8 backfill 后 ``legacy_default_allow``（无条件）与域/行策略同时命中时会真实发生。
    """
    pols = [
        allow(subject_kind="everyone", subject_value="", condition=""),
        allow("t", "role", "USER", condition="dept_id = $attr.dept_id"),
    ]
    d = decide_table(pols, P(roles=("USER",), attrs={"dept_id": "3"}), "t")
    assert d.permit
    assert d.sql == "", f"无条件 allow 必须吸收条件，实际得到 {d.sql!r}"
    assert d.applied == ()
    assert set(d.policy_ids) == {pols[0].id, pols[1].id}, "两条 allow 都参与裁决"


def test_unconditional_allow_not_downgraded_by_missing_attr():
    """无条件 allow 在场时，缺属性的有条件 allow 只是"不适用"，不影响整表放行。"""
    pols = [
        allow(subject_kind="everyone", subject_value="", condition=""),
        allow(condition="dept_id = $attr.dept_id"),
    ]
    d = decide_table(pols, P(attrs={}), "t")
    assert d.permit and d.sql == "" and d.applied == ()
    assert d.policy_ids == (pols[0].id,)


def test_union_condition_helper():
    assert union_condition([]) == ""
    assert union_condition([""]) == ""
    assert union_condition(["a = 1"]) == "a = 1"
    assert union_condition(["a = 1", "b = 2"]) == "(a = 1) OR (b = 2)"
    # 任一空串 = 无条件授权 → 整组吸收
    assert union_condition(["a = 1", ""]) == ""


def test_applicable_condition_helper():
    p_ok = allow(condition="owner_id = $user.id")
    assert applicable_condition(p_ok, P(user_id=7)) == "owner_id = $user.id"
    assert applicable_condition(p_ok, P(user_id=None)) is None

    p_attr = allow(condition="dept_id = $attr.dept_id")
    assert applicable_condition(p_attr, P(attrs={})) is None
    assert applicable_condition(p_attr, P(attrs={"dept_id": "3"})) == "dept_id = $attr.dept_id"

    assert applicable_condition(allow(condition=""), P()) == ""


# ---------------------------------------------------------------------------
# 规则「缺属性 → 条件不成立 → 该表 deny」（不是忽略条件）
# ---------------------------------------------------------------------------
def test_missing_attr_makes_row_policy_deny():
    pols = [allow("t", "role", "USER", condition="dept_id = $attr.dept_id")]
    d = decide_table(pols, P(roles=("USER",), attrs={}), "t")
    assert not d.permit
    assert "dept_id" in d.reason
    assert d.policy_ids == (pols[0].id,)

    # 属性存在时同一策略就是放行，且把行条件带出来供编译器下推
    ok = decide_table(pols, P(roles=("USER",), attrs={"dept_id": "3"}), "t")
    assert ok.permit and "$attr.dept_id" in ok.sql


def test_empty_attr_value_is_treated_as_missing():
    pols = [allow(condition="dept_id = $attr.dept_id")]
    assert not decide_table(pols, P(attrs={"dept_id": ""}), "t").permit


def test_missing_user_id_makes_user_condition_deny():
    pols = [allow(condition="owner_id = $user.id")]
    assert not decide_table(pols, P(user_id=None), "t").permit


# ---------------------------------------------------------------------------
# 规则 6：列级默认继承（不要实现"列默认拒绝"）
# ---------------------------------------------------------------------------
def test_columns_empty_allow_covers_every_column():
    d = decide_column([allow(columns=())], P(), "t", "any_col")
    assert d.permit and d.applied == () and d.sql == ""


def test_column_scoped_allow_does_not_restrict_other_columns():
    """allow.columns 是「按列的额外授予」，不是列白名单（spec §3.2-6）。"""
    pols = [allow(columns=("a",))]
    assert decide_table(pols, P(), "t").permit
    assert decide_column(pols, P(), "t", "b").permit


def test_deny_with_columns_does_not_block_the_table():
    """只 deny 了 phone：表本身仍可查，其它列不受影响。"""
    pols = [allow(), deny(columns=("phone",))]
    assert decide_table(pols, P(), "t").permit
    assert decide_column(pols, P(), "t", "name").permit
    assert not decide_column(pols, P(), "t", "phone").permit


def test_column_without_any_allow_is_denied():
    assert not decide_column([], P(), "t", "name").permit


# ---------------------------------------------------------------------------
# 边界：禁用、大小写、缺主体、空策略、主体类型
# ---------------------------------------------------------------------------
def test_disabled_policy_is_ignored():
    assert not decide_table([allow(enabled=False)], P(), "t").permit
    # 禁用的 deny 不生效：列照常可读（只剩 allow 起作用）
    d = decide_column([allow(), deny(columns=("phone",), enabled=False)], P(), "t", "phone")
    assert d.permit and d.applied == ()


def test_enabled_accepts_config_strings():
    """``enabled`` 是配置串时也要认得 "false"/"0"/"no"，不能一律当启用。"""
    for raw in ("false", "FALSE", "0", "no", "off", " n ", ""):
        assert not decide_table([allow(enabled=raw)], P(), "t").permit, raw
    for raw in ("true", "1", "yes", "on"):
        assert decide_table([allow(enabled=raw)], P(), "t").permit, raw


def test_only_table_and_view_policies_are_processed():
    """Ruling：同名的 object/datasource 策略不能给物理表放行（对象权限另有引擎）。"""
    for kind in ("object", "datasource", "OBJECT", ""):
        d = decide_table([allow(subject_kind="everyone", subject_value="", kind=kind)], P(), "t")
        assert not d.permit, f"resource_kind={kind!r} 不应参与表判定"

    # view 与 table 同等处理
    assert decide_table([allow(kind="view")], P(), "t").permit
    assert decide_table([allow(kind="TABLE")], P(), "t").permit
    assert decide_column([allow(kind="view")], P(), "t", "phone").permit


def test_zero_attr_value_is_not_treated_as_missing():
    """属性值 0 是合法值（``str(value or \"\")`` 会误判成缺失）。"""
    pols = [allow(condition="dept_id = $attr.dept_id")]
    d = decide_table(pols, P(attrs={"dept_id": 0}), "t")
    assert d.permit and d.sql == "dept_id = $attr.dept_id"


def test_role_and_table_match_are_case_insensitive():
    d = decide_table([allow(table="  T ", subject_value="user")], P(roles=("user",)), "t")
    assert d.permit


def test_schema_qualified_table_matches_bare_name():
    assert decide_table([allow(table="public.t")], P(), "t").permit
    assert decide_table([allow(table="t")], P(), "public.t").permit


def test_user_subject_matches_user_id():
    assert decide_table([allow(subject_kind="user", subject_value="7")], P(user_id=7), "t").permit
    assert not decide_table(
        [allow(subject_kind="user", subject_value="8")], P(user_id=7), "t"
    ).permit


def test_attr_subject_matches_principal_attrs():
    pols = [allow(subject_kind="attr", subject_value="dept_id == 3")]
    assert decide_table(pols, P(attrs={"dept_id": "3"}), "t").permit
    assert not decide_table(pols, P(attrs={"dept_id": "4"}), "t").permit
    assert not decide_table(pols, P(attrs={}), "t").permit
    # 写错格式的属性主体：fail-closed，绝不匹配
    assert not decide_table([allow(subject_kind="attr", subject_value="???")], P(), "t").permit


def test_domain_subject_matches_domain_membership():
    pols = [allow(subject_kind="domain", subject_value="finance")]
    assert decide_table(pols, P(attrs={"domains": "hr, finance"}), "t").permit
    assert not decide_table(pols, P(attrs={"domains": "hr"}), "t").permit
    assert not decide_table(pols, P(attrs={}), "t").permit


def test_domain_subject_accepts_container_attrs():
    """T6 可能注入 list/tuple/set：容器里的任一元素命中即匹配（不能 str() 化成 "['hr']"）。"""
    pols = [allow(subject_kind="domain", subject_value="finance")]
    for domains in (
        ["hr", "finance"],
        ("finance",),
        {"finance", "hr"},
        frozenset({"FINANCE"}),
        ["", " finance "],
    ):
        assert decide_table(pols, P(attrs={"domains": domains}), "t").permit, domains
    assert not decide_table(pols, P(attrs={"domains": []}), "t").permit
    assert not decide_table(pols, P(attrs={"domains": ["hr"]}), "t").permit
    # 兼容单数键 domain
    assert decide_table(pols, P(attrs={"domain": "finance"}), "t").permit


def test_unknown_subject_kind_never_matches():
    assert not decide_table([allow(subject_kind="team", subject_value="x")], P(), "t").permit


def test_missing_principal_denies():
    d = decide_table([allow()], None, "t")
    assert not d.permit and "principal" in d.reason
    assert not decide_column([allow()], None, "t", "name").permit


def test_empty_policy_list_and_decision_shape():
    d = decide_table([], P(), "t")
    assert d == Decision(False, d.reason), "未命中时没有 policy_ids/sql/applied"
    assert isinstance(d.policy_ids, tuple) and isinstance(d.applied, tuple)
