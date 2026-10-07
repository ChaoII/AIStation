"""AI 能力评估（影子回归）测试。"""
import asyncio

from app.plugin.module_ai.overview.service import AiOverviewService


class TestAiEval:
    def test_eval_match_true(self):
        assert AiOverviewService.eval_match("订单金额总和是 90500", ["90500"]) is True

    def test_eval_match_case_insensitive(self):
        assert AiOverviewService.eval_match("结果 success", ["SUCCESS"]) is True

    def test_eval_match_all_keywords(self):
        assert AiOverviewService.eval_match("显示 A 和 B", ["a", "b"]) is True

    def test_eval_match_missing_keyword(self):
        assert AiOverviewService.eval_match("显示 A", ["a", "b"]) is False

    def test_run_eval_precision(self):
        samples = [
            {"input": "q1", "expected_keywords": ["90500"], "actual": "90500"},
            {"input": "q2", "expected_keywords": ["abc"], "actual": "xyz"},
        ]
        r = asyncio.run(AiOverviewService.run_eval(samples))
        assert r["total"] == 2 and r["passed"] == 1 and r["precision"] == 0.5

    def test_health_check_shape(self):
        r = asyncio.run(AiOverviewService.health_check(days=7))
        assert "calls" in r and "error_rate" in r and "status" in r and "alerts" in r
        assert r["status"] in ("healthy", "warning", "critical")
