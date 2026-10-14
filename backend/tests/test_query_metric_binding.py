"""S1-T1：指标绑定列 + 评测 dataset 列。"""
import asyncio


def test_metric_columns_exist():
    async def _go():
        from sqlalchemy import inspect

        from app.core.database import async_db_session

        async with async_db_session() as db:
            cols = await db.run_sync(
                lambda s: {
                    c["name"] for c in inspect(s.connection()).get_columns("ai_query_metrics")
                }
            )
        return cols

    cols = asyncio.run(_go())
    for c in ("object_code", "property_code", "agg_fn", "bound_dimensions"):
        assert c in cols


def test_case_dataset_roundtrip():
    async def _go():
        from sqlalchemy import text

        from app.core.database import async_db_session
        from app.plugin.module_ai.query import eval_set as es

        await es.upsert_case(
            {
                "question": "__t_ds__?",
                "gold_sql": "SELECT 1",
                "datasource": "system",
                "dataset": "coal_semantic_v1",
            }
        )
        rows = await es.list_cases(dataset="coal_semantic_v1")
        hit = [r for r in rows if r["question"] == "__t_ds__?"]
        assert hit and hit[0]["dataset"] == "coal_semantic_v1"
        # 清理：按 question 直删（SQLite 下 testcase 的 BIGSERIAL id 不自增，不能用 id）
        async with async_db_session.begin() as db:
            await db.execute(
                text("UPDATE ai_query_testcase SET is_deleted=true WHERE question='__t_ds__?'")
            )

    asyncio.run(_go())
