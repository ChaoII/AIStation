"""Task 9：SQL 编译器（行包装 / 列投影 / mask），纯逻辑不接线。

覆盖两层：

1. ``rewrite``（brief 的 4 条 + addendum 的作用域/多表/条件校验）：
   - 行过滤按表包装成 ``(SELECT * FROM t WHERE <cond>) AS t``，**逐表**，不把多表条件并成
     一个字符串（T6 评审：``union_condition`` 遇到任一空条件会把整组吸收成空串）；
   - 星号按 ``allowed_columns`` 展开；``None`` = 无元数据 → 保留星号并记
     ``{"star": "unexpanded"}``；
   - deny 列出现在投影/条件/排序/分组都拒绝；mask 只替换投影并保留输出列名；
   - CTE 名不是真实表（``traverse_scope`` + ``cte_sources``），不能把给同名真表的策略套到
     CTE 引用上；内部包装产生的 ``*`` 不参与列判定（先列改写、后包装）；
   - 解析失败 / 非 SELECT / 多语句 / 管理员条件含子查询、函数、``;``、DDL → deny，不抛异常。

2. ``build_plan``（策略 → 计划）：
   - 逐表 ``decide_table``：无 allow → 整表拒绝（``denied[t]`` 里的 ``"*"`` 哨兵）；
   - 行条件用 ``decide_table`` 的并集（复用 engine 的 union/缺属性语义），
     ``$attr.*`` / ``$user.id`` 在**编译期**按 AST 替换为安全转义的字面量
     （Decision 没有参数通道；字符串字面量内的 ``$`` 不动）；
   - 逐列 ``decide_column``：deny 进 ``denied``、mask 进 ``masked``、其余进 ``allowed_columns``；
   - 无列元数据且表带 ``marking`` → 整表拒绝；无元数据无标记 → ``allowed_columns[t] = None``。

评审修复（Critical 1-4）另有一组回归：括号表 ``(t) AS j``、括号 join、整行引用
（``select t`` / ``(t).phone`` / ``row_to_json(t)`` / ``count(t)`` / ``t::text``）、
mask 列出现在任意投影表达式/条件/排序/聚合，以及系统表与系统函数。

全部用例 ``PYTEST_NO_APP=1`` 可跑（不需要应用与数据库）。
"""

from __future__ import annotations

import itertools

import pytest

from app.plugin.module_ai.query.policy.compiler import (
    DENIED_ALL,
    AccessPlan,
    build_plan,
    rewrite,
)
from app.plugin.module_ai.query.policy.engine import Policy
from app.plugin.module_ai.query.policy.principal import Principal

_ids = itertools.count(1)


# ---------------------------------------------------------------------------
# 构造辅助
# ---------------------------------------------------------------------------
def plan(**kw) -> AccessPlan:
    """测试用简写：allowed -> allowed_columns。"""
    kw["allowed_columns"] = kw.pop("allowed", {})
    kw.setdefault("row_filters", {})
    kw.setdefault("masked", {})
    kw.setdefault("denied", {})
    return AccessPlan(**kw)


def P(*, user_id=7, is_superuser=False, roles=("USER",), attrs=None, entry="ask") -> Principal:
    return Principal(
        user_id=user_id,
        is_superuser=is_superuser,
        roles=tuple(roles),
        attrs=dict(attrs or {}),
        entry=entry,
    )


def pol(
    effect,
    *,
    table="t",
    subject_kind="everyone",
    subject_value="",
    columns=(),
    condition="",
    mask_expr="",
    marking="",
    priority=100,
    enabled=True,
    pid=None,
    kind="table",
) -> Policy:
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
        marking=marking,
        priority=priority,
        enabled=enabled,
    )


def norm(sql: str) -> str:
    """生成 SQL 的比对口径：小写 + 折叠空白（不比对引号/大小写风格）。"""
    return " ".join((sql or "").lower().split())


# ---------------------------------------------------------------------------
# brief 的 4 条
# ---------------------------------------------------------------------------
def test_row_filter_wraps_table():
    d = rewrite("select id from t", plan(row_filters={"t": "dept_id = 3"}))
    assert d.permit and "dept_id = 3" in d.sql


def test_star_expands_to_allowed_columns():
    d = rewrite("select * from t", plan(allowed={"t": ("a", "b")}))
    assert "a" in d.sql and "b" in d.sql and "*" not in d.sql


def test_denied_column_is_rejected():
    assert not rewrite("select phone from t", plan(denied={"t": {"phone"}})).permit


def test_internal_wrapper_star_is_not_rechecked():
    d = rewrite("select a from t", plan(row_filters={"t": "1=1"}, allowed={"t": ("a",)}))
    assert d.permit


# ---------------------------------------------------------------------------
# addendum：CTE 名不能当表
# ---------------------------------------------------------------------------
def test_cte_name_is_not_treated_as_table():
    """给同名 CTE 配置的策略不能生效；基表的行过滤要在 CTE 体内生效。"""
    d = rewrite(
        "with x as (select * from t) select * from x",
        plan(row_filters={"x": "1 = 0", "t": "dept_id = 3"}, allowed={"t": ("id", "dept_id")}),
    )
    assert d.permit
    text = norm(d.sql)
    assert "1 = 0" not in text  # x 是 CTE，不是真实表
    assert "dept_id = 3" in text  # 基表 t 的策略照旧
    assert "select * from x" in text  # CTE 引用原样保留


def test_star_with_cte_sibling_is_not_partially_expanded():
    """同作用域有 CTE 时不能只展开真实表，否则 CTE 的列会被整段丢掉。"""
    d = rewrite(
        "with x as (select phone from u) select * from x join t on t.id = x.id",
        plan(allowed={"u": None, "t": ("id",)}),
    )
    assert d.permit
    assert "*" in d.sql


def test_star_with_cte_sibling_and_restricted_real_table_is_denied():
    d = rewrite(
        "with x as (select phone from u) select * from x join t on t.id = x.id",
        plan(allowed={"u": None, "t": ("id",)}, denied={"t": {"phone"}}),
    )
    assert not d.permit


def test_blocked_star_does_not_leak_sibling_mask():
    """星号因 u 无元数据而保留时，同作用域 t 的掩码列会被明文读出 → 必须拒绝。"""
    d = rewrite(
        "select * from t join u on u.id = t.id",
        plan(
            allowed={"t": ("id", "phone"), "u": None},
            masked={"t": {"phone": "left(phone, 3)"}},
        ),
    )
    assert not d.permit


def test_cte_body_same_named_column_is_not_false_denied():
    """CTE 体内另一张表的同名列，不能因外层表的 deny 被误拒。"""
    d = rewrite(
        "with x as (select phone from u) select x.phone from x join t on t.id = x.id",
        plan(allowed={"u": None, "t": ("id",)}, denied={"t": {"phone"}}),
    )
    assert d.permit


# ---------------------------------------------------------------------------
# addendum：多表逐表包装
# ---------------------------------------------------------------------------
def test_multi_table_row_filters_are_wrapped_per_table():
    d = rewrite(
        "select a.id from a join b on b.id = a.id",
        plan(row_filters={"a": "dept_id = 3", "b": "dept_id = 4"}),
    )
    assert d.permit
    text = norm(d.sql)
    assert "(select * from a where dept_id = 3) as a" in text
    assert "(select * from b where dept_id = 4) as b" in text


def test_one_table_without_filter_does_not_absorb_other():
    """addendum 1 的回归：任一张表无条件，不能把另一张表的行过滤吞掉。"""
    d = rewrite(
        "select a.id, b.id from a join b on b.id = a.id",
        plan(row_filters={"a": "dept_id = 3"}, allowed={"a": None, "b": None}),
    )
    assert d.permit
    text = norm(d.sql)
    assert "dept_id = 3" in text
    assert "(select * from a where dept_id = 3) as a" in text


def test_alias_is_preserved_when_wrapping():
    d = rewrite(
        "select x.id from t x",
        plan(row_filters={"t": "dept_id = 3"}),
    )
    assert d.permit
    assert "(select * from t where dept_id = 3) as x" in norm(d.sql)


# ---------------------------------------------------------------------------
# addendum：行条件 AST 校验（子查询 / 函数 / ; / DDL 一律 deny）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "condition",
    [
        "(select 1) = 1",           # 子查询
        "exists (select 1 from u)",  # 相关子查询
        "lower(dept_id) = 'x'",      # 函数调用
        "dept_id = 3; drop table t",  # 多条语句 / DDL
        "dept_id = (delete from t)",  # DDL 关键字
        "dept_id = 3 -- and 1=1",     # 注释夹带（AST 校验后仍只剩合法节点也要拒绝）
    ],
)
def test_unsafe_policy_condition_is_denied(condition):
    d = rewrite("select id from t", plan(row_filters={"t": condition}))
    assert not d.permit
    assert "条件" in d.reason or "策略" in d.reason


def test_safe_policy_condition_is_allowed():
    for cond in (
        "dept_id = 3",
        "dept_id in (1, 2, 3)",
        "dept_id is null",
        "dept_id like 'x%'",
        "(dept_id = 3 or dept_id = 4) and not deleted",
        "dept_id between 1 and 5",
    ):
        d = rewrite("select id from t", plan(row_filters={"t": cond}))
        assert d.permit, f"{cond} 应放行：{d.reason}"


# ---------------------------------------------------------------------------
# 列投影 / mask
# ---------------------------------------------------------------------------
def test_mask_replaces_projection_and_keeps_output_name():
    d = rewrite(
        "select phone from t",
        plan(masked={"t": {"phone": "left(phone, 3)"}}),
    )
    assert d.permit
    assert "left(phone, 3) as phone" in norm(d.sql)
    assert any("mask" in item for item in d.applied)


def test_mask_keeps_explicit_alias():
    d = rewrite(
        "select phone as p from t",
        plan(masked={"t": {"phone": "left(phone, 3)"}}),
    )
    assert d.permit
    assert "left(phone, 3) as p" in norm(d.sql)


def test_mask_in_star_expansion():
    d = rewrite(
        "select * from t",
        plan(allowed={"t": ("id", "phone")}, masked={"t": {"phone": "left(phone, 3)"}}),
    )
    assert d.permit
    text = norm(d.sql)
    assert "left(phone, 3) as phone" in text
    assert "*" not in text
    # 星号展开时的掩码也要落进 applied（审计要看得到"哪些列被掩了"）
    assert any(item.get("mask") for item in d.applied)


def test_mask_referencing_denied_column_is_denied():
    d = rewrite(
        "select phone from t",
        plan(denied={"t": {"salary"}}, masked={"t": {"phone": "left(salary, 3)"}}),
    )
    assert not d.permit


def test_denied_column_in_where_order_group_is_denied():
    for sql in (
        "select id from t where phone = 'x'",
        "select id from t order by phone",
        "select id from t group by phone",
    ):
        d = rewrite(sql, plan(denied={"t": {"phone"}}))
        assert not d.permit, sql


def test_unexpanded_star_is_recorded_when_no_metadata():
    d = rewrite("select * from t", plan(allowed={"t": None}))
    assert d.permit
    assert any(item.get("star") == "unexpanded" for item in d.applied)


def test_star_with_empty_allowlist_is_denied():
    d = rewrite("select * from t", plan(allowed={"t": ()}))
    assert not d.permit


def test_star_with_deny_but_no_metadata_is_denied():
    """无元数据 + 有 deny 列：保留星号会把 deny 列一起读出来，必须拒绝。"""
    d = rewrite("select * from t", plan(denied={"t": {"phone"}}))
    assert not d.permit


def test_star_with_mask_but_no_metadata_is_denied():
    d = rewrite("select * from t", plan(masked={"t": {"phone": "left(phone, 3)"}}))
    assert not d.permit


def test_denied_column_in_order_by_with_star_is_denied():
    d = rewrite("select * from t order by phone", plan(allowed={"t": ("id",)}, denied={"t": {"phone"}}))
    assert not d.permit


def test_denied_column_in_join_condition_is_denied():
    d = rewrite(
        "select a.id from a join b on b.id = a.phone",
        plan(allowed={"a": ("id",), "b": ("id",)}, denied={"a": {"phone"}}),
    )
    assert not d.permit


def test_denied_column_in_having_is_denied():
    """``scope.columns`` 不含 HAVING 列（实测），编译器必须自己收集。"""
    d = rewrite(
        "select id from t group by id having count(phone) > 1",
        plan(allowed={"t": ("id",)}, denied={"t": {"phone"}}),
    )
    assert not d.permit


def test_denied_column_in_correlated_subquery_is_denied():
    d = rewrite(
        "select id from t where exists (select 1 from u where u.id = t.phone)",
        plan(allowed={"t": ("id",), "u": ("id",)}, denied={"t": {"phone"}}),
    )
    assert not d.permit


def test_recursive_cte_is_denied():
    d = rewrite(
        "with recursive x as (select id from t union all select id from x) select * from x",
        plan(allowed={"t": ("id",)}),
    )
    assert not d.permit


def test_all_denied_table_is_denied_even_without_columns():
    d = rewrite("select 1 from t", plan(denied={"t": {DENIED_ALL}}))
    assert not d.permit


def test_table_missing_from_plan_is_denied():
    """计划必须覆盖查询涉及的每张表（build_plan 会对每张输入表出一条记录）。"""
    d = rewrite("select id from t", plan(allowed={"other": ("id",)}))
    assert not d.permit


# ---------------------------------------------------------------------------
# 解析 / 语句类型
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "sql",
    [
        "select * from ((((",           # 解析失败
        "",                             # 空 SQL
        "select 1; select 2",           # 多语句
        "drop table t",                 # DDL
        "insert into t values (1)",     # 写操作
        "delete from t",                # 写操作
    ],
)
def test_unparsable_or_non_select_is_denied(sql):
    d = rewrite(sql, plan())
    assert not d.permit


# ---------------------------------------------------------------------------
# 参数占位符保持原前缀（不把用户的 :name 变成 psycopg 的 %(name)s）
# ---------------------------------------------------------------------------
def test_user_placeholders_keep_colon_prefix():
    d = rewrite(
        "select id from t where owner = :u",
        plan(row_filters={"t": "dept_id = 3"}),
    )
    assert d.permit
    assert ":u" in d.sql
    assert "%(u)s" not in d.sql


# ---------------------------------------------------------------------------
# build_plan
# ---------------------------------------------------------------------------
def test_build_plan_binds_attr_condition():
    principal = P(attrs={"dept_id": "3"})
    allow = pol("allow", condition="dept_id = $attr.dept_id")
    built = build_plan([allow], principal, {"t": ["id", "dept_id"]})

    assert built.row_filters["t"] == "dept_id = '3'"
    assert built.allowed_columns["t"] == ("id", "dept_id")

    d = rewrite("select id from t", built)
    assert d.permit
    assert "dept_id = '3'" in norm(d.sql)


def test_build_plan_binds_user_id_and_multivalue_attr():
    principal = P(user_id=7, attrs={"dept_id": ["3", "4"]})
    allow = pol("allow", condition="owner = $user.id and dept_id = $attr.dept_id")
    built = build_plan([allow], principal, {"t": ["id"]})
    d = rewrite("select id from t", built)
    assert d.permit
    text = norm(d.sql)
    assert "owner = 7" in text
    assert "dept_id in ('3', '4')" in text


def test_build_plan_collects_denied_and_masked_columns():
    allow = pol("allow")
    mask = pol("mask", columns=("phone",), mask_expr="left(phone, 3)")
    denied = pol("deny", columns=("salary",))
    built = build_plan(
        [allow, mask, denied], P(), {"t": ["id", "phone", "salary"]}
    )

    assert built.allowed_columns["t"] == ("id", "phone")
    assert built.masked["t"] == {"phone": "left(phone, 3)"}
    assert built.denied["t"] == frozenset({"salary"})


def test_build_plan_denies_table_without_allow():
    built = build_plan([], P(), {"t": ["id"]})
    assert built.denied["t"] == frozenset({DENIED_ALL})
    assert not rewrite("select id from t", built).permit


def test_build_plan_denies_marked_table_without_metadata():
    allow = pol("allow", marking="sensitive")
    built = build_plan([allow], P(), {"t": []})
    assert DENIED_ALL in built.denied["t"]
    assert not rewrite("select * from t", built).permit


def test_build_plan_allows_unmarked_table_without_metadata():
    allow = pol("allow")
    built = build_plan([allow], P(), {"t": []})
    assert built.allowed_columns["t"] is None
    d = rewrite("select * from t", built)
    assert d.permit
    assert any(item.get("star") == "unexpanded" for item in d.applied)


def test_build_plan_superuser_has_no_filters():
    built = build_plan([pol("deny")], P(is_superuser=True), {"t": ["id"]})
    assert built.row_filters == {}
    assert built.denied == {}
    assert rewrite("select id from t", built).permit


def test_build_plan_normalizes_schema_qualified_table_names():
    allow = pol("allow", table="public.t", condition="dept_id = 3")
    built = build_plan([allow], P(), {"public.T": ["id"]})
    assert "t" in built.row_filters
    d = rewrite("select id from public.t", built)
    assert d.permit
    assert "dept_id = 3" in norm(d.sql)


# ===========================================================================
# 评审修复回归（Critical 1-4 + Important）
# ===========================================================================
MASKED = {
    "allowed": {"t": ("id", "phone")},
    "masked": {"t": {"phone": "left(phone, 3)"}},
}


def masked_plan() -> AccessPlan:
    return plan(**MASKED)


# ---------------------------------------------------------------------------
# Critical 1：FROM (t) AS j 绕过全部策略
# ---------------------------------------------------------------------------
def test_parenthesized_table_alias_denies_column():
    assert not rewrite("select j.phone from (t) as j", plan(denied={"t": {"phone"}})).permit


def test_parenthesized_table_alias_denies_table():
    assert not rewrite(
        "select j.phone from (t) as j", plan(denied={"t": {DENIED_ALL}})
    ).permit


def test_parenthesized_table_alias_applies_row_filter():
    d = rewrite(
        "select * from (t) as j",
        plan(row_filters={"t": "dept = 1"}, allowed={"t": ("id", "dept")}),
    )
    assert d.permit
    text = norm(d.sql)
    assert "dept = 1" in text
    # 括号表的列元数据是已知的：星号要展开，不能走 star_unexpanded
    assert text.startswith("select id, dept from")
    assert not any(item.get("star") == "unexpanded" for item in d.applied)
    assert any(item.get("row") == "dept = 1" for item in d.applied)


def test_parenthesized_table_alias_masks_projection():
    d = rewrite(
        "select j.phone from (t) as j",
        plan(allowed={"t": ("phone",)}, masked={"t": {"phone": "left(phone, 3)"}}),
    )
    assert d.permit
    assert "left(j.phone, 3)" in norm(d.sql)


def test_parenthesized_table_alias_whole_row_denied():
    assert not rewrite("select j from (t) as j", masked_plan()).permit


# ---------------------------------------------------------------------------
# Critical 2：括号 join 丢行过滤还伪造 applied
# ---------------------------------------------------------------------------
def test_parenthesized_join_applies_both_row_filters_and_keeps_joins():
    d = rewrite(
        "select * from (t join u on t.id = u.id)",
        plan(row_filters={"t": "a = 1", "u": "b = 2"}, allowed={"t": None, "u": None}),
    )
    assert d.permit
    text = norm(d.sql)
    assert text.count("a = 1") == 1
    assert text.count("b = 2") == 1
    # join 结构保留（两张表各自包装后仍在同一条 join 上）
    assert "join" in text and "on t.id = u.id" in text
    rows = [item["row"] for item in d.applied if "row" in item]
    assert set(rows) == {"a = 1", "b = 2"}
    for row in rows:  # applied 必须与最终 SQL 一致
        assert row in text


def test_join_applied_entries_all_appear_in_sql():
    d = rewrite(
        "select * from t join u on t.id = u.id",
        plan(row_filters={"t": "a = 1", "u": "b = 2"}, allowed={"t": None, "u": None}),
    )
    assert d.permit
    text = norm(d.sql)
    for item in d.applied:
        if "row" in item:
            assert item["row"] in text


def test_union_level_order_by_denied_column_is_denied():
    d = rewrite(
        "select id from t union select id from t order by phone",
        plan(allowed={"t": ("id",)}, denied={"t": {"phone"}}),
    )
    assert not d.permit


def test_union_level_order_by_masked_column_is_denied():
    d = rewrite(
        "select id from t union select id from t order by phone",
        plan(allowed={"t": ("id", "phone")}, masked={"t": {"phone": "left(phone, 3)"}}),
    )
    assert not d.permit


# ---------------------------------------------------------------------------
# Critical 3：整行 / 整表引用绕过 deny 与 mask
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "sql",
    [
        "select t from t",
        "select (t).phone from t",
        "select row_to_json(t) from t",
        "select to_jsonb(t) from t",
        "select json_agg(t) from t",
        "select count(t) from t",
        "select t::text from t",
        "select row_to_json(t.*) from t",
    ],
)
def test_whole_row_reference_is_denied_when_restricted(sql):
    d = rewrite(sql, masked_plan())
    assert not d.permit, sql


def test_whole_row_reference_allowed_without_restrictions():
    d = rewrite("select t from t", plan(allowed={"t": ("id",)}))
    assert d.permit


# ---------------------------------------------------------------------------
# Critical 4：mask 只挡最外层裸列
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "sql",
    [
        "select max(phone) from t",
        "select min(phone) from t",
        "select avg(phone) from t",
        "select sum(phone) from t",
    ],
)
def test_aggregate_over_masked_column_is_denied(sql):
    assert not rewrite(sql, masked_plan()).permit, sql


@pytest.mark.parametrize(
    "sql,needle",
    [
        ("select substring(phone, 1, 2) from t", "substring(left(phone, 3)"),
        ("select phone || '' from t", "left(phone, 3) ||"),
        (
            "select case when phone is null then 1 else 0 end from t",
            "case when left(phone, 3) is null",
        ),
    ],
)
def test_masked_column_inside_projection_expression_is_wrapped(sql, needle):
    d = rewrite(sql, masked_plan())
    assert d.permit, d.reason
    assert needle in norm(d.sql)
    assert any("mask" in item for item in d.applied)


@pytest.mark.parametrize(
    "sql",
    [
        "select id from t where phone like '1%'",
        "select id from t order by phone",
        "select id from t group by phone",
        "select id from t group by id having max(phone) > 1",
        "select id from t join u on u.id = t.phone",
    ],
)
def test_masked_column_outside_projection_is_denied(sql):
    p = plan(
        allowed={"t": ("id", "phone"), "u": ("id",)},
        masked={"t": {"phone": "left(phone, 3)"}},
    )
    assert not rewrite(sql, p).permit, sql


# ---------------------------------------------------------------------------
# Important：policy_ids 透传
# ---------------------------------------------------------------------------
def test_build_plan_collects_policy_ids_and_rewrite_passes_through():
    allow = pol("allow", pid=11)
    mask = pol("mask", columns=("phone",), mask_expr="left(phone, 3)", pid=12)
    built = build_plan([allow, mask], P(), {"t": ["id", "phone"]})
    assert set(built.policy_ids) == {11, 12}
    d = rewrite("select phone from t", built)
    assert d.permit
    assert set(d.policy_ids) == {11, 12}


# ---------------------------------------------------------------------------
# Important：行条件按 AST 绑定
# ---------------------------------------------------------------------------
def test_condition_dollar_inside_string_literal_is_not_substituted():
    allow = pol("allow", condition="note = '$attr.dept_id'")
    built = build_plan([allow], P(attrs={"dept_id": "3"}), {"t": ["id"]})
    assert built.row_filters["t"] == "note = '$attr.dept_id'"
    d = rewrite("select id from t", built)
    assert d.permit
    assert "$attr.dept_id" in d.sql  # 字符串字面量原样保留


def test_binding_failure_denies_without_raising():
    allow = pol("allow", condition="dept_id = $attr.dept_id")
    built = build_plan([allow], P(attrs={"dept_id": {"nested": 1}}), {"t": ["id"]})
    d = rewrite("select id from t", built)
    assert not d.permit


# ---------------------------------------------------------------------------
# Important：系统表 / 系统函数
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "sql",
    [
        "select * from pg_class",
        "select * from pg_catalog.pg_class",
        "select * from information_schema.tables",
    ],
)
def test_system_table_is_denied(sql):
    d = rewrite(sql, plan(allowed={"pg_class": None, "tables": None}))
    assert not d.permit, sql


@pytest.mark.parametrize(
    "sql",
    [
        "select pg_read_file('/etc/passwd')",
        "select id from t where id = pg_ls_dir('.')",
    ],
)
def test_system_function_is_denied(sql):
    d = rewrite(sql, plan(allowed={"t": ("id",)}))
    assert not d.permit, sql


# ===========================================================================
# 复审修复轮（round 2）
# ===========================================================================
def test_paren_join_alias_denies_join_side_column():
    d = rewrite(
        "select u.phone from (t join u on t.id = u.id) as j",
        plan(
            allowed={"t": ("id",), "u": ("id", "phone")},
            denied={"u": {"phone"}},
        ),
    )
    assert not d.permit


def test_paren_join_alias_denies_join_side_table():
    d = rewrite(
        "select u.phone from (t join u on t.id = u.id) as j",
        plan(
            allowed={"t": ("id",), "u": ("id",)},
            denied={"u": {DENIED_ALL}},
        ),
    )
    assert not d.permit


def test_paren_join_group_alias_checks_all_group_tables():
    """`j.phone` 属于多表括号组：组内任一表命中 deny/mask 就拒绝（不能当别名不存在）。"""
    d = rewrite(
        "select j.phone from (t join u on t.id = u.id) as j",
        plan(
            allowed={"t": ("id", "phone"), "u": ("id",)},
            denied={"t": {"phone"}},
        ),
    )
    assert not d.permit


@pytest.mark.parametrize(
    "sql",
    [
        "select * from (t join u on t.id = u.id) as j",
        "select * from ((t join u on t.id = u.id)) as j",
    ],
)
def test_paren_join_alias_applies_both_row_filters(sql):
    d = rewrite(
        sql,
        plan(row_filters={"t": "a = 1", "u": "b = 2"}, allowed={"t": None, "u": None}),
    )
    assert d.permit
    text = norm(d.sql)
    assert text.count("a = 1") == 1
    assert text.count("b = 2") == 1
    for item in d.applied:  # applied 与最终 SQL 一致
        if "row" in item:
            assert item["row"] in text


def test_nested_paren_join_applies_all_row_filters():
    """`((t join u) join v)`：外层 join 挂在括号 Subquery 上，v 也要被包装。"""
    d = rewrite(
        "select * from ((t join u on t.id = u.id) join v on v.id = t.id) as j",
        plan(
            row_filters={"t": "a = 1", "u": "b = 2", "v": "c = 3"},
            allowed={"t": None, "u": None, "v": None},
        ),
    )
    assert d.permit
    text = norm(d.sql)
    for cond in ("a = 1", "b = 2", "c = 3"):
        assert text.count(cond) == 1, text
    rows = [item["row"] for item in d.applied if "row" in item]
    assert set(rows) == {"a = 1", "b = 2", "c = 3"}
    for row in rows:
        assert row in text


def test_paren_join_alias_uncovered_join_side_is_denied():
    d = rewrite(
        "select * from (t join u on t.id = u.id) as j",
        plan(allowed={"t": None}),
    )
    assert not d.permit


def test_paren_join_alias_star_expands_both_tables():
    d = rewrite(
        "select * from (t join u on t.id = u.id) as j",
        plan(allowed={"t": ("t_id",), "u": ("u_id", "u_phone")}),
    )
    assert d.permit
    text = norm(d.sql)
    assert "t_id" in text and "u_id" in text and "u_phone" in text


@pytest.mark.parametrize(
    "sql",
    [
        "select (select phone) from t",
        "select id from t where id in (select 1 where phone like '1%')",
        "select id from t where exists (select 1 from u where u.id = phone)",
        "select * from t, lateral (select phone as p) x",
        "select t.id from t, lateral (select phone as p) x",
    ],
)
def test_masked_column_in_subquery_is_denied(sql):
    p = plan(
        allowed={"t": ("id", "phone"), "u": ("id",)},
        masked={"t": {"phone": "left(phone, 3)"}},
    )
    assert not rewrite(sql, p).permit, sql


# ===========================================================================
# round 3：括号 join 的**组别名**（`(t JOIN u) AS j` 后用 `j.col` / `j.*` / `j`）
# ===========================================================================
JOIN_GROUPS = [
    ("(t join u on t.id = u.id) as j", ("t", "u")),
    ("(t left join u on t.id = u.id) as j", ("t", "u")),
    ("(t cross join u) as j", ("t", "u")),
    ("(t, u) as j", ("t", "u")),
    ("((t join u on t.id = u.id)) as j", ("t", "u")),
    ("((t join u on t.id = u.id) join v on v.id = t.id) as j", ("t", "u", "v")),
]


@pytest.mark.parametrize("group,tables", JOIN_GROUPS)
def test_group_alias_column_deny_checks_whole_group(group, tables):
    d = rewrite(
        f"select j.phone from {group}",
        plan(
            allowed=dict.fromkeys(tables, ("id", "phone")),
            denied={tables[-1]: {"phone"}},
        ),
    )
    assert not d.permit, group


@pytest.mark.parametrize("group,tables", JOIN_GROUPS)
def test_group_alias_table_deny_checks_whole_group(group, tables):
    d = rewrite(
        f"select j.phone from {group}",
        plan(
            allowed=dict.fromkeys(tables, ("id", "phone")),
            denied={tables[-1]: {DENIED_ALL}},
        ),
    )
    assert not d.permit, group


@pytest.mark.parametrize("group,tables", JOIN_GROUPS)
def test_group_alias_mask_is_not_plaintext(group, tables):
    d = rewrite(
        f"select j.phone from {group}",
        plan(
            allowed=dict.fromkeys(tables, ("id", "phone")),
            masked={tables[-1]: {"phone": "left(phone, 3)"}},
        ),
    )
    assert not d.permit, group  # 投影位置无法判定归属 → deny（不是明文放行）


@pytest.mark.parametrize("group,tables", JOIN_GROUPS)
def test_group_alias_whole_row_denied(group, tables):
    d = rewrite(
        f"select j from {group}",
        plan(
            allowed=dict.fromkeys(tables, ("id", "phone")),
            masked={tables[-1]: {"phone": "left(phone, 3)"}},
        ),
    )
    assert not d.permit, group


@pytest.mark.parametrize("group,tables", JOIN_GROUPS)
def test_group_alias_star_expands_all_group_tables(group, tables):
    d = rewrite(
        f"select j.* from {group}",
        plan(allowed=dict.fromkeys(tables, ("id", "phone"))),
    )
    assert d.permit, d.reason
    text = norm(d.sql)
    for table in tables:
        assert f"{table}.id" in text, f"{group} 丢掉了 {table} 的列：{text}"


def test_group_alias_star_without_metadata_is_denied():
    d = rewrite(
        "select j.* from (t join u on t.id = u.id) as j",
        plan(allowed={"t": ("id",), "u": None}),
    )
    assert not d.permit  # 无法展开就拒绝，不能静默丢 u 的列


@pytest.mark.parametrize("group,tables", JOIN_GROUPS)
def test_group_alias_mask_in_predicate_is_denied(group, tables):
    d = rewrite(
        f"select t.id from {group} where j.phone like '1%'",
        plan(
            allowed=dict.fromkeys(tables, ("id", "phone")),
            masked={tables[-1]: {"phone": "left(phone, 3)"}},
        ),
    )
    assert not d.permit, group


def test_group_alias_join_side_row_filter_still_applied():
    d = rewrite(
        "select j.id from (t join u on t.id = u.id) as j",
        plan(
            row_filters={"t": "a = 1", "u": "b = 2"},
            allowed={"t": ("id",), "u": ("id",)},
        ),
    )
    assert d.permit
    text = norm(d.sql)
    assert "a = 1" in text and "b = 2" in text
