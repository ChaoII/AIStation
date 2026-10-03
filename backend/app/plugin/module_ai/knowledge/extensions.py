"""后端启动时初始化 AI 扩展（pgvector / Apache AGE / pg_jieba）。

仅对 PostgreSQL 数据库执行；非 PostgreSQL 或未安装扩展（如旧 postgres:17 或 SQLite 测试）
时静默跳过，不阻塞启动。每条扩展独立事务提交，避免一条失败回滚掉其它。
"""
from __future__ import annotations

import os

_STMTS = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    "CREATE EXTENSION IF NOT EXISTS age",
    "CREATE EXTENSION IF NOT EXISTS pg_jieba",
]


async def _run_sql(sql: str) -> None:
    """在独立会话执行一条 SQL，失败静默。"""
    try:
        from sqlalchemy import text

        from app.core.database import async_db_session

        async with async_db_session() as db:
            await db.execute(text(sql))
            await db.commit()
    except Exception:  # noqa: BLE001
        pass


async def ensure_extensions() -> None:
    """初始化扩展：创建扩展、LOAD age、确保 jieba 全文配置。"""
    if (os.getenv("DATABASE_TYPE") or "postgresql").lower() not in ("postgres", "postgresql"):
        return
    for stmt in _STMTS:
        await _run_sql(stmt)
    # ARGE 会话内加载（若已 preload 则冗余无害）
    await _run_sql("LOAD 'age'")
    # 确保中文全文检索配置存在（pg_jieba 提供 jiebacfg，缺则按 simple 补建）
    await _run_sql(
        "CREATE TEXT SEARCH CONFIGURATION IF NOT EXISTS jiebacfg (COPY = simple)"
    )
    # 知识库：确保分块标注列 + 实体-分块绑定表存在（幂等）
    await _run_sql("ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS annotations jsonb")
    await _run_sql(
        "CREATE TABLE IF NOT EXISTS ai_knowledge_entity_chunks ("
        "id SERIAL PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(32) DEFAULT '0', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, entity_id INTEGER, chunk_id INTEGER, "
        "UNIQUE (entity_id, chunk_id))"
    )
    await _run_sql(
        "CREATE TABLE IF NOT EXISTS ai_chunk_annotation_logs ("
        "id SERIAL PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(32) DEFAULT '0', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, knowledge_base_id INTEGER, chunk_id INTEGER, "
        "action VARCHAR(16), text TEXT, kind VARCHAR(32), query TEXT, "
        "source VARCHAR(32), user_id INTEGER)"
    )
    await _run_sql(
        "CREATE TABLE IF NOT EXISTS ai_search_logs ("
        "id SERIAL PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(32) DEFAULT '0', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, knowledge_base_id INTEGER, query TEXT, mode VARCHAR(32), "
        "top_k INTEGER, hit_count INTEGER, engines JSONB, user_id INTEGER)"
    )
