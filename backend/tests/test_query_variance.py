"""评测方差：纯逻辑测试（`PYTEST_NO_APP=1` 快速跑）。"""
from __future__ import annotations


def _r(q: str, ok: bool, deg: bool = False) -> dict:
    return {"case_id": q, "question": q, "gold_match": ok, "degenerate": deg}


def test_per_question_pass_rate():
    from app.plugin.module_ai.query.eval_variance import per_question

    runs = [
        [_r("q1", True), _r("q2", True)],
        [_r("q1", True), _r("q2", False)],
        [_r("q1", False), _r("q2", False)],
    ]
    pq = per_question(runs)
    assert pq["q1"]["passes"] == 2 and pq["q1"]["runs"] == 3
    assert abs(pq["q1"]["rate"] - 2 / 3) < 1e-9
    assert pq["q2"]["passes"] == 1
    assert pq["q2"]["rate"] == 1 / 3


def test_mcnemar_exact_boundaries():
    from app.plugin.module_ai.query.eval_variance import mcnemar_exact

    # 无翻转 → 不显著
    z = mcnemar_exact([True, False], [True, False])
    assert z["n"] == 0 and z["p"] == 1.0 and z["significant"] is False
    # 1 次翻转 → p=1（样本太小，不能下结论）
    one = mcnemar_exact([True], [False])
    assert one["b10"] == 1 and one["p"] == 1.0 and one["significant"] is False
    # 6 次单向翻转 → 显著
    six = mcnemar_exact([True] * 6, [False] * 6)
    assert six["b10"] == 6 and six["significant"] is True and six["p"] < 0.05


def test_variance_report_measures_spread_and_unstable():
    """同配置三次跑出不同结果 → 必须报出离散度与不稳定题（这正是我们栽过的坑）。"""
    from app.plugin.module_ai.query.eval_variance import variance_report

    runs = [
        [_r("a", True), _r("b", True), _r("c", True)],
        [_r("a", True), _r("b", False), _r("c", True)],
        [_r("a", False), _r("b", True), _r("c", True)],
    ]
    rep = variance_report(runs)
    assert rep["n_runs"] == 3
    assert rep["per_run_accuracy"] == [100.0, 66.67, 66.67]
    assert rep["spread"] == 33.33          # 极差 = 噪声带
    assert rep["noise_band"] == 33.33
    assert rep["n_questions"] == 3
    assert rep["always_pass"] == 1         # c 三次全对
    assert rep["always_fail"] == 0
    assert len(rep["unstable"]) == 2       # a、b 各翻转一次
    assert all(p["n"] >= 0 for p in rep["pairs"])


def test_variance_report_excludes_degenerate():
    from app.plugin.module_ai.query.eval_variance import variance_report

    runs = [[_r("a", True), _r("d", False, deg=True)], [_r("a", True), _r("d", False, deg=True)]]
    rep = variance_report(runs)
    assert rep["n_questions"] == 1         # 退化题不计入
    assert rep["per_run_accuracy"] == [100.0, 100.0]
    assert rep["spread"] == 0.0
