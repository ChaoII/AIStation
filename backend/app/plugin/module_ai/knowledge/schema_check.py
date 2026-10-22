"""知识库模块缺失表/列的启动幂等补齐。

用于旧库升级：与 `module_train.schema_check` 同模式——插件表自建/补列，**不走 alembic autogenerate**
（dev 库有大量历史影子表，autogenerate 会把它们判成待 DROP）。

每条 DDL 独立事务：PostgreSQL 中一条语句失败会中止当前事务，独立事务可隔离单条失败。
"""

#: 知识库分类表（左侧分类树）
CREATE_KNOWLEDGE_CATEGORIES_DDL = """
CREATE TABLE IF NOT EXISTS ai_knowledge_categories (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,
    name VARCHAR(64) NOT NULL UNIQUE,
    parent_id INTEGER,
    owner VARCHAR(64),
    remark TEXT,
    sort INTEGER DEFAULT 0,
    status VARCHAR(1) DEFAULT '0',
    description TEXT,
    created_time TIMESTAMP DEFAULT NOW(),
    updated_time TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_time TIMESTAMP,
    created_id INTEGER,
    updated_id INTEGER,
    deleted_id INTEGER
)
"""

#: 缺失列清单：表名 → [(列名, 类型)]
MISSING_KNOWLEDGE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "ai_knowledge_bases": [
        ("category_id", "INTEGER"),
    ],
}


async def ensure_knowledge_schema(engine) -> None:
    """建知识库分类表 + 补 `ai_knowledge_bases.category_id`（幂等，失败仅告警）。"""
    from sqlalchemy import text

    from app.core.logger import log

    try:
        async with engine.begin() as conn:
            await conn.execute(text(CREATE_KNOWLEDGE_CATEGORIES_DDL))
    except Exception as e:  # noqa: BLE001
        log.warning(f"knowledge schema: 建 ai_knowledge_categories 失败: {e}")

    for table, columns in MISSING_KNOWLEDGE_COLUMNS.items():
        for name, col_type in columns:
            try:
                async with engine.begin() as conn:
                    await conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {col_type}")
                    )
            except Exception as e:  # noqa: BLE001
                log.warning(f"knowledge backfill skipped {table}.{name}: {e}")

    # agno 向量层：启动即惰性构建（建表 + HNSW 向量索引）并清孤儿行（分块已删/软删的残留）
    if not _is_sqlite():
        try:
            from .search.agno_engine import purge_orphans

            await purge_orphans()
        except Exception as e:  # noqa: BLE001
            log.warning(f"agno 向量层启动维护跳过: {str(e)[:160]}")


def _is_sqlite() -> bool:
    # DATABASE_TYPE 由 settings 注入；SQLite 测试环境跳过 agno 维护（回退路径生效）
    import os

    return (os.getenv("DATABASE_TYPE") or "postgresql").lower() == "sqlite"
