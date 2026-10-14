"""S4-T2：评测按数据集取题（dataset 过滤透传）。"""
import asyncio


def test_pick_cases_passes_dataset(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import eval_runner as R
        from app.plugin.module_ai.query import eval_set as es

        seen = {}

        async def _fake_list(**kw):
            seen.update(kw)
            return [{"question": "q1", "split": "B"}, {"question": "q2", "split": "A"}]

        monkeypatch.setattr(es, "list_cases", _fake_list)
        return await R._pick_cases({"dataset": "coal_semantic_v1"}, None), seen

    cases, seen = asyncio.run(_go())
    assert seen.get("dataset") == "coal_semantic_v1"
    assert len(cases) == 2


def test_pick_cases_filters_split_and_limit(monkeypatch):
    async def _go():
        from app.plugin.module_ai.query import eval_runner as R
        from app.plugin.module_ai.query import eval_set as es

        async def _fake_list(**kw):
            return [{"question": f"q{i}", "split": "B"} for i in range(5)]

        monkeypatch.setattr(es, "list_cases", _fake_list)
        return await R._pick_cases({"split": "B", "limit": 2}, None)

    cases = asyncio.run(_go())
    assert len(cases) == 2
