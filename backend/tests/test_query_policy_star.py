"""Task 5 星号止血（P0 安全修复）：含敏感列的表禁止未展开星号。

背景（真实漏洞）：``select * from 表`` 在 sqlglot 里解析出 ``columns=[]``，
现有列级 ACL 用 ``c in cols`` 判定 → 星号绕过敏感列检查，数据被整行读出来。

语义约定（``unexpanded_star``）：

1. 只看**未展开**的星号（``*`` / ``t.*``），``count(*)`` 这类聚合里的星号不算取列；
2. 返回**命中的真实表名**（别名要还原：``select f.* from fuel_price f`` → ``fuel_price``；
   返回值归一化为小写裸表名）；
3. 表名比较**大小写不敏感**，``public.fuel_price`` 的 schema 前缀不算表名的一部分 ——
   星号展开的是整张表的所有列，带不带 schema 都是同一个风险；
4. CTE 识别是**作用域感知**的：只有本作用域真正可见的 CTE 名才遮蔽真表，**带 schema 限定
   的引用永远是真实表**，CTE 体内的引用看不到自身名字（非递归）；子查询别名不是真实表，
   星号落到它们身上时由**内层** select 的星号判定覆盖；
5. 无风险返回 ``None``；**解析失败返回 ``"*"``**（调用方据此拒绝，fail-closed）。

全部是纯逻辑，``PYTEST_NO_APP=1`` 可跑（不需要应用与数据库）。
"""

from __future__ import annotations

from app.plugin.module_ai.query.policy.star import unexpanded_star

SENSITIVE = {"fuel_price"}


# ---------------------------------------------------------------------------
# brief 的 4 条必须覆盖
# ---------------------------------------------------------------------------


def test_plain_star_on_sensitive_table_is_flagged():
    assert unexpanded_star("select * from fuel_price", {"fuel_price"}) == "fuel_price"


def test_qualified_star_is_flagged():
    assert unexpanded_star("select t.* from fuel_price t", {"fuel_price"}) == "fuel_price"


def test_star_on_safe_table_is_allowed():
    assert unexpanded_star("select * from dim_city", {"fuel_price"}) is None


def test_parse_failure_is_treated_as_risk():
    assert unexpanded_star("select * from ((((", {"fuel_price"}) == "*"


# ---------------------------------------------------------------------------
# 别名还原 / 大小写 / schema 前缀
# ---------------------------------------------------------------------------


def test_qualified_star_resolves_alias_to_real_table():
    assert unexpanded_star("select f.* from fuel_price f", SENSITIVE) == "fuel_price"


def test_schema_qualified_star_is_resolved():
    sql = "select public.fuel_price.* from public.fuel_price"
    assert unexpanded_star(sql, SENSITIVE) == "fuel_price"


def test_table_name_comparison_is_case_insensitive():
    # 返回值也是归一化（小写）的裸表名；T6 拿它去查敏感列时需按库内写法再归一
    assert unexpanded_star("select * from FUEL_PRICE", {"fuel_price"}) == "fuel_price"
    assert unexpanded_star("select * from fuel_price", {"FUEL_PRICE"}) == "fuel_price"


def test_schema_prefix_does_not_hide_the_table():
    assert unexpanded_star("select * from public.fuel_price", SENSITIVE) == "fuel_price"
    assert unexpanded_star("select p.* from public.fuel_price p", SENSITIVE) == "fuel_price"


def test_schema_prefixed_sensitive_name_is_also_matched():
    assert unexpanded_star("select * from fuel_price", {"public.fuel_price"}) == "fuel_price"


def test_quoted_schema_qualified_table_is_unwrapped():
    sql = 'select * from "public"."Fuel_Price"'
    assert unexpanded_star(sql, SENSITIVE) == "fuel_price"


def test_quoted_schema_qualified_sensitive_name_is_normalized_per_segment():
    # 整体 strip('"') 会残留引号（'"fuel_price'）导致永不匹配（fail-open）
    sql = 'select * from "public"."Fuel_Price"'
    assert unexpanded_star(sql, {'"public"."Fuel_Price"'}) == "fuel_price"


# ---------------------------------------------------------------------------
# 聚合里的星号不是取列（否则 count(*) 会被一律拒绝）
# ---------------------------------------------------------------------------


def test_count_star_is_not_a_column_read():
    assert unexpanded_star("select count(*) from fuel_price", SENSITIVE) is None
    sql = "select c.city_id, count(*) from dim_city c join fuel_price f on c.city_id = f.city_id"
    assert unexpanded_star(sql, SENSITIVE) is None


def test_trailing_statement_star_is_not_silently_dropped():
    # sqlglot.parse_one 会丢弃第二条语句 —— 这里必须用 parse 全查（真实绕过写法）
    assert unexpanded_star("select 1; select * from fuel_price", SENSITIVE) == "fuel_price"


# ---------------------------------------------------------------------------
# join / 子查询 / CTE
# ---------------------------------------------------------------------------


def test_bare_star_over_join_flags_the_sensitive_side():
    sql = "select * from dim_city c join fuel_price f on c.city_id = f.city_id"
    assert unexpanded_star(sql, SENSITIVE) == "fuel_price"


def test_qualified_star_over_join_only_flags_that_table():
    sql = "select c.* from dim_city c join fuel_price f on c.city_id = f.city_id"
    assert unexpanded_star(sql, SENSITIVE) is None


def test_bare_star_over_comma_join_flags_the_sensitive_side():
    assert unexpanded_star("select * from dim_city, fuel_price", SENSITIVE) == "fuel_price"


def test_multiple_qualified_stars_over_comma_join():
    sql = "select a.*, b.* from dim_city a, fuel_price b"
    assert unexpanded_star(sql, SENSITIVE) == "fuel_price"


def test_star_inside_subquery_is_flagged():
    assert unexpanded_star("select * from (select * from fuel_price) t", SENSITIVE) == "fuel_price"


def test_star_inside_cte_is_flagged():
    sql = "with x as (select * from fuel_price) select * from x"
    assert unexpanded_star(sql, SENSITIVE) == "fuel_price"


def test_schema_qualified_reference_is_never_treated_as_cte():
    # CTE 不能被 schema 限定：public.fuel_price 永远是真实表
    sql = "with fuel_price as (select 1 as x) select * from public.fuel_price"
    assert unexpanded_star(sql, SENSITIVE) == "fuel_price"


def test_cte_named_like_sensitive_table_does_not_mask_real_table():
    assert (
        unexpanded_star(
            "with fuel_price as (select * from public.fuel_price) select * from fuel_price",
            {"fuel_price"},
        )
        == "fuel_price"
    )


def test_nested_cte_shadow_does_not_mask_outer_real_table():
    assert (
        unexpanded_star(
            "select * from fuel_price where 1 in (with fuel_price as (select 1) select 1 from fuel_price)",
            {"fuel_price"},
        )
        == "fuel_price"
    )


def test_star_over_real_cte_is_allowed():
    # PG 非递归语义：CTE 在本作用域内确实遮蔽同名真表，星号只展开 CTE 的 x
    sql = "with fuel_price as (select 1 as x) select * from fuel_price"
    assert unexpanded_star(sql, SENSITIVE) is None


def test_star_over_safe_cte_is_allowed():
    sql = "with x as (select city_id from fuel_price) select * from x"
    assert unexpanded_star(sql, SENSITIVE) is None


def test_union_branch_is_checked():
    sql = "select * from dim_city union all select * from fuel_price"
    assert unexpanded_star(sql, SENSITIVE) == "fuel_price"


# ---------------------------------------------------------------------------
# 边界：空 SQL / 没有敏感表
# ---------------------------------------------------------------------------


def test_empty_sql_has_no_risk():
    assert unexpanded_star("", SENSITIVE) is None
    assert unexpanded_star("   ", SENSITIVE) is None


def test_no_sensitive_tables_means_no_risk():
    assert unexpanded_star("select * from fuel_price", set()) is None


def test_unsupported_statement_command_is_treated_as_risk():
    # sqlglot 把不支持的语法退化成 exp.Command，此时遍历不到 star → 必须 fail-closed
    assert unexpanded_star("vacuum fuel_price", SENSITIVE) == "*"
