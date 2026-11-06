"""Task 11：权限绕过回归集（12 条），只走 ``compiler.rewrite``。

为什么是这 12 条
----------------
P0 的星号止血只回答"有没有未展开星号"，P2 编译器才是执行边界。历史漏洞与评审现场
发现的绕过写花样集中在：裸星号 / 限定星号 / CTE / UNION / 标量子查询 / 引号 /
大小写 / 注释 / 敏感列函数包装。**``count(*)`` 必须允许**（它不是取列），
其余"含敏感列的星号或敏感列引用"必须拒绝。

测试口径
--------
计划模拟**生产上最常见的形态**：表 ``t`` 有敏感列 ``phone``，但字段资产还没同步
（``allowed_columns["t"] is None``）。此时：

- 星号**无法安全展开**（不知道还有哪些列）→ 只能拒绝（spec §5.3 第 2 种情况，
  fail-closed，不允许"保留星号当没看见"）；
- 显式引用 ``phone``（含函数包装）→ 列 deny 拒绝；
- 不涉及 ``phone`` 的显式列 / ``count(*)`` → 放行，且放行的 SQL 里不能出现 ``phone``。

不在这里放宽任何预期：用例失败就回编译器修（本轮结论：12 条全部按预期）。
"""

from __future__ import annotations

import pytest

from app.plugin.module_ai.query.policy.compiler import AccessPlan, rewrite

#: 有敏感列 ``phone``、但无列元数据的表 ``t``。
PLAN = AccessPlan(
    row_filters={},
    allowed_columns={"t": None},
    masked={},
    denied={"t": frozenset({"phone"})},
)

#: ``(SQL, 是否应放行)``。
BYPASS_CASES: list[tuple[str, bool]] = [
    ("select * from t", False),
    ("select t.* from t", False),
    ("select a from t", True),
    ("with x as (select * from t) select * from x", False),
    ("select * from t union select * from t", False),
    ("select (select phone from t limit 1) from t", False),
    ('select * from "t"', False),
    ("SELECT * FROM T", False),
    ("select /*x*/ * from t", False),
    ("select * from t -- tail", False),
    ("select coalesce(phone,'') from t", False),
    ("select count(*) from t", True),
]


def test_case_table_is_complete():
    """回归集就是这 12 条；少了任何一条都说明有人删用例而不是修漏洞。"""
    assert len(BYPASS_CASES) == 12


@pytest.mark.parametrize(("sql", "expected"), BYPASS_CASES)
def test_bypass_matrix(sql: str, expected: bool):
    decision = rewrite(sql, PLAN)

    assert decision.permit is expected, f"{sql} → {decision.reason}"

    if not expected:
        # 拒绝必须带人话原因（审计/explain 直接用），而不是靠"解析失败"蒙对
        assert decision.reason, f"{sql} 被拒绝但没给出原因"
        assert "SQL 解析失败" not in decision.reason, f"{sql} 应是策略拒绝：{decision.reason}"
    else:
        # 放行路径也不能把敏感列带出来
        assert "phone" not in decision.sql.lower(), decision.sql


def test_star_is_not_silently_kept_when_unexpandable():
    """有列级限制却无法展开星号时，绝不能"保留星号 + 记一句审计"就放行。"""
    decision = rewrite("select * from t", PLAN)

    assert not decision.permit
    assert decision.sql == ""  # 拒绝时没有可执行 SQL
    assert decision.applied == ()


def test_explicit_safe_projection_keeps_no_row_filter():
    """没有行策略时不做无谓包装（避免每次查询多一层子查询）。"""
    decision = rewrite("select a from t", PLAN)

    assert decision.permit
    assert "where" not in decision.sql.lower()
    assert decision.applied == ()
