"""反馈闭环：错题 → few-shot 的候选筛选（纯逻辑）。"""
import asyncio


def test_select_candidates_takes_only_failures_with_usable_gold():
    from app.plugin.module_ai.query.eval_curate import select_fewshot_candidates

    results = [
        {"question": "Q1", "gold_match": False, "degenerate": False},   # ✓ 判错
        {"question": "Q2", "gold_match": True, "degenerate": False},    # 答对，不教
        {"question": "Q3", "gold_match": False, "degenerate": True},    # 退化，教了也没用
        {"question": "Q4", "gold_match": False, "degenerate": False},   # 已沉淀过 → 跳过
        {"question": "Q5", "gold_match": False, "degenerate": False},   # 金标缺失 → 跳过
    ]
    gold = {"Q1": "SELECT 1", "Q2": "SELECT 2", "Q3": "SELECT 3", "Q4": "SELECT 4"}
    got = select_fewshot_candidates(results, gold, {"Q4"})
    assert [c["question"] for c in got] == ["Q1"], got
    assert got[0]["gold_sql"] == "SELECT 1"


def test_select_candidates_is_empty_when_all_correct():
    from app.plugin.module_ai.query.eval_curate import select_fewshot_candidates

    got = select_fewshot_candidates(
        [{"question": "Q", "gold_match": True, "degenerate": False}], {"Q": "SELECT 1"}, set()
    )
    assert got == []


def test_curate_from_run_validates_and_skips_degenerate(monkeypatch):
    """沉淀必须**先执行验证**：金标跑不通/退化的不入库（否则教的是错的）。"""
    from app.plugin.module_ai.query import eval_curate as C

    async def _results(run_id):
        return [
            {"question": "Q_OK", "gold_match": False, "degenerate": False},
            {"question": "Q_EMPTY", "gold_match": False, "degenerate": False},
        ]

    async def _cases(**k):
        return [
            {"question": "Q_OK", "gold_sql": "SELECT 1", "datasource": "ds:4"},
            {"question": "Q_EMPTY", "gold_sql": "SELECT 2", "datasource": "ds:4"},
        ]

    async def _fewshots(datasource=None):
        return [{"question": "Q_OLD", "sql": "SELECT 0"}]

    async def _run_gold(sql, ds, auth):
        if sql == "SELECT 2":
            return {"ok": True, "rows": [[0]], "error": ""}      # 单值 0 → 退化
        return {"ok": True, "rows": [[7]], "error": ""}

    added: list[dict] = []

    async def _add(data, auth=None):
        added.append(data)
        return {"id": len(added)}

    monkeypatch.setattr(C, "_load_results", _results)
    monkeypatch.setattr(C, "_list_cases", _cases)
    monkeypatch.setattr(C, "_list_fewshots", _fewshots)
    monkeypatch.setattr(C, "_run_gold", _run_gold)
    monkeypatch.setattr(C, "_add_fewshot", _add)

    out = asyncio.run(C.curate_from_run("run_x", "ds:4"))
    assert out["added"] == 1, out
    assert added[0]["question"] == "Q_OK"
    assert "auto-curated" in (added[0].get("description") or "")
