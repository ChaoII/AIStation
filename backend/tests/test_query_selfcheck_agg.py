"""自校验回归：组上聚合（平均/极值/占比）只返回 1 行是**正确**的，不能报「漏了 GROUP BY」。

背景（2026-11-08 评测）：题 1140「按供应商名称分组，每个供应商平均关联几个矿点」
正确答案就是 1 行（AVG over 每组 COUNT）。旧逻辑只要问句含「每个/按…分组」且结果为
1 行就判可疑 → 触发重试 → 模型改成返回 53 行分组明细，越改越错。
"""
from __future__ import annotations

from app.plugin.module_ai.query.selfcheck import check_row_magnitude, run_selfcheck

ROWS1 = [[12.34]]


def test_avg_over_groups_single_row_is_fine():
    q = "按供应商名称分组，每个供应商平均关联几个矿点"
    assert check_row_magnitude(q, ROWS1) == []


def test_top1_share_single_row_is_fine():
    q = "按供应商名称分组统计关联矿点数，关联最多的那家供应商是谁，它占全部关系的百分之多少"
    assert check_row_magnitude(q, ROWS1) == []


def test_limit_one_sql_is_exempt():
    q = "按矿点统计关系数，取最多的前 3"
    sql = 'SELECT "KDNAME", COUNT(*) AS c FROM "T" GROUP BY 1 ORDER BY c DESC LIMIT 3'
    assert check_row_magnitude(q, ROWS1, sql) == []


def test_outer_aggregate_sql_is_exempt():
    q = "每个供应商关联几个矿点"  # 有分组词，但外层是 AVG
    sql = "SELECT ROUND(AVG(c)::numeric, 2) FROM (SELECT COUNT(*) AS c FROM \"T\" GROUP BY 1) x"
    assert check_row_magnitude(q, ROWS1, sql) == []


def test_plain_grouping_still_flagged():
    """没有聚合/极值语义、也没有 LIMIT 1 时，仍然要报（别把护栏拆了）。"""
    q = "按供应商名称分组，每个供应商关联几个矿点"
    issues = check_row_magnitude(q, ROWS1)
    # 含「平均」必然豁免；换一个不含聚合词的问句验证护栏仍在
    q2 = "按供应商名称分组，每个供应商的关联矿点明细"
    out = check_row_magnitude(q2, ROWS1)
    assert out and out[0]["kind"] == "rows"
    assert isinstance(issues, list)


def test_run_selfcheck_passes_sql_through():
    q = "按矿点统计不同供应商数量，取最多的前 3 个"
    sql = 'SELECT "KDNAME", COUNT(DISTINCT "GYSNAME") c FROM "T" GROUP BY 1 ORDER BY c DESC LIMIT 3'
    assert run_selfcheck(q, ["矿点", "供应商数"], [["A", 9]], sql) == []


# ---------------------------------------------------------------------------
# 「全量列举」与「组上聚合」互斥：判定函数本身也要对
# ---------------------------------------------------------------------------
def test_wants_full_list_excludes_aggregate_questions():
    from app.plugin.module_ai.query.question_rules import wants_full_list

    assert wants_full_list("按供应商名称分组，每个供应商平均关联几个矿点？") is False
    assert wants_full_list(
        "按供应商名称分组统计关联矿点数，关联最多的那家供应商是谁，它占全部关系的百分之多少？"
    ) is False
    assert wants_full_list("各煤种类型的记录占比是多少") is False
    # 真正的列举仍然要走「别截断」
    assert wants_full_list("列出所有摄像头名称") is True
    assert wants_full_list("每个供应商的关联矿点明细") is True
