"""结果自校验：占比合计/累计单调/排名范围/分组行数（纯逻辑）。"""


def test_ratio_check_flags_bad_total():
    from app.plugin.module_ai.query.selfcheck import check_ratio

    cols = ["类型", "占比"]
    ok = [["A", 60.0], ["B", 40.0]]
    bad = [["A", 6.0], ["B", 4.0]]
    assert check_ratio(cols, ok) == []
    got = check_ratio(cols, bad)
    assert got and got[0]["kind"] == "ratio"


def test_cumulative_check_flags_decrease():
    from app.plugin.module_ai.query.selfcheck import check_cumulative

    cols = ["月份", "累计化验数"]
    ok = [["01", 3], ["02", 7], ["03", 9]]
    bad = [["01", 3], ["02", 1], ["03", 9]]
    assert check_cumulative(cols, ok) == []
    got = check_cumulative(cols, bad)
    assert got and got[0]["kind"] == "cumulative"


def test_rank_check_flags_max_beyond_row_count():
    from app.plugin.module_ai.query.selfcheck import check_rank

    cols = ["名称", "排名"]
    assert check_rank(cols, [["A", 1], ["B", 2]]) == []
    got = check_rank(cols, [["A", 1], ["B", 9]])
    assert got and got[0]["kind"] == "rank"


def test_row_magnitude_flags_single_row_for_grouping_question():
    from app.plugin.module_ai.query.selfcheck import check_row_magnitude

    assert check_row_magnitude("今天有多少条告警", [[5]]) == []
    got = check_row_magnitude("按煤种类型统计各有多少条记录", [["A", 5]])
    assert got and got[0]["kind"] == "rows"


def test_run_selfcheck_aggregates_and_formats():
    from app.plugin.module_ai.query.selfcheck import format_issue, run_selfcheck

    issues = run_selfcheck("按类型统计占比", ["类型", "占比"], [["A", 6.0], ["B", 4.0]])
    assert issues
    assert "占比" in format_issue(issues)


def test_no_false_positive_on_normal_result():
    from app.plugin.module_ai.query.selfcheck import run_selfcheck

    cols = ["煤种类型", "记录数"]
    rows = [["A", 12], ["B", 8], ["C", 5]]
    assert run_selfcheck("按煤种类型统计记录数", cols, rows) == []
