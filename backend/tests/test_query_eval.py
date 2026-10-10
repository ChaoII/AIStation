"""问数评测模块单测：表/CRUD、指标纯函数、生成解析与校验、执行器与消融。

纯逻辑部分可 ``PYTEST_NO_APP=1`` 快速跑；涉及 DB/HTTP 的按默认模式跑。
"""
import asyncio


# ===========================================================================
# 批次1：三表 + 测试集 CRUD
# ===========================================================================
def test_ensure_eval_tables_is_idempotent():
    async def _run():
        from app.plugin.module_ai.query.eval_set import ensure_eval_tables

        await ensure_eval_tables()
        await ensure_eval_tables()  # 第二次不得报错

    asyncio.run(_run())


def test_upsert_case_is_idempotent_and_filterable():
    async def _run():
        from app.plugin.module_ai.query.eval_set import list_cases, upsert_case

        await upsert_case({
            "question": "Q_IDEMPOTENT", "gold_sql": "SELECT 1", "datasource": "system",
            "difficulty": "简单", "scenario": "安防", "form": "单维统计",
        })
        await upsert_case({
            "question": "Q_IDEMPOTENT", "gold_sql": "SELECT 1", "datasource": "system",
            "difficulty": "困难", "scenario": "安防", "form": "联表",
        })
        rows = [c for c in await list_cases(datasource="system") if c["question"] == "Q_IDEMPOTENT"]
        assert len(rows) == 1, "同 (datasource,question) 必须只有一条"
        assert rows[0]["difficulty"] == "困难"  # 后写覆盖
        assert await list_cases(difficulty="不存在的难度") == []

    asyncio.run(_run())


def test_import_cases_skips_invalid():
    async def _run():
        from app.plugin.module_ai.query.eval_set import import_cases

        out = await import_cases([
            {"question": "Q_OK", "gold_sql": "SELECT 1", "datasource": "system"},
            {"question": "", "gold_sql": "SELECT 1"},
            {"question": "Q_NO_SQL"},
        ])
        assert out == {"saved": 1, "skipped": 2}

    asyncio.run(_run())


# ===========================================================================
# 批次2：指标纯函数（可 PYTEST_NO_APP=1 快速跑）
# ===========================================================================
def test_gold_tables_and_recall_at_k():
    from app.plugin.module_ai.query.eval_metrics import gold_tables, recall_at_k

    schema = {"FUEL_CB_COALBALANCE": [], "FUEL_CMCS_ASSAY": [], "OTHER": []}
    sql = 'SELECT * FROM "FUEL_CB_COALBALANCE" a JOIN FUEL_CMCS_ASSAY b ON a.id=b.id'
    assert gold_tables(sql, schema) == {"FUEL_CB_COALBALANCE", "FUEL_CMCS_ASSAY"}
    assert recall_at_k({"A", "B"}, ["A", "B", "C"], k=8) == 1.0
    assert recall_at_k({"A", "B"}, ["X", "Y"], k=8) == 0.0
    assert recall_at_k({"A", "B"}, ["B", "X", "Y", "A"], k=2) == 0.5  # 只看前 2
    assert recall_at_k(set(), ["X"], k=8) == 1.0


def test_summarize_and_group_by_dimension():
    from app.plugin.module_ai.query.eval_metrics import group_by, summarize

    results = [
        {"gold_match": True, "metric_key": "m1", "expected_metric": "m1", "path": "fast",
         "is_error": False, "took_ms": 100, "recall": 1.0, "difficulty": "简单"},
        {"gold_match": False, "metric_key": "m2", "expected_metric": "m1", "path": "slow",
         "is_error": True, "took_ms": 300, "recall": 0.0, "difficulty": "困难"},
    ]
    s = summarize(results)
    assert s["total"] == 2
    assert s["data_accuracy"] == 0.5
    assert s["semantic_accuracy"] == 0.5  # 2 题都带期望，命中 1 题
    assert s["fast_rate"] == 0.5
    assert s["error_rate"] == 0.5
    assert s["avg_ms"] == 200.0
    assert s["recall_at_k"] == 0.5
    g = group_by(results, "difficulty")
    assert g["简单"]["accuracy"] == 1.0 and g["困难"]["accuracy"] == 0.0
    assert summarize([])["total"] == 0
