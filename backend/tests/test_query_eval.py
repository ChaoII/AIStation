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
