"""PostgreSQL 向量/全文索引存在性校验（仅在 PG 上运行）。"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    (os.getenv("DATABASE_TYPE") or "").lower() not in ("postgres", "postgresql"),
    reason="仅在 PostgreSQL 上验证索引",
)


def test_vector_and_fulltext_indexes_exist():
    import asyncio

    import asyncpg

    dsn = (
        f"postgresql://{os.environ['DATABASE_USER']}:{os.environ['DATABASE_PASSWORD']}"
        f"@{os.environ['DATABASE_HOST']}:{os.environ['DATABASE_PORT']}/{os.environ['DATABASE_NAME']}"
    )

    async def _names() -> set[str]:
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(
                "select indexname from pg_indexes where tablename = 'ai_knowledge_chunks'"
            )
            return {r["indexname"] for r in rows}
        finally:
            await conn.close()

    names = asyncio.run(_names())
    assert "idx_chunk_embedding_hv" in names
    assert "idx_chunk_fts" in names
