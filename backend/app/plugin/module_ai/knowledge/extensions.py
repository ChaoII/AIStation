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
    await _run_sql("ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS document_id integer")
    await _run_sql("ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS start_line integer")
    await _run_sql("ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS page integer")
    await _run_sql("ALTER TABLE ai_knowledge_relations ADD COLUMN IF NOT EXISTS rtype varchar(64)")
    await _run_sql("ALTER TABLE ai_knowledge_entities ADD COLUMN IF NOT EXISTS description text")
    await _run_sql("ALTER TABLE ai_knowledge_entities ADD COLUMN IF NOT EXISTS layout jsonb")
    await _run_sql(
        "CREATE TABLE IF NOT EXISTS ai_relation_types ("
        "id SERIAL PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(32) DEFAULT '0', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, name VARCHAR(64) UNIQUE, color VARCHAR(16))"
    )
    for rt in ("属于", "包含", "依赖", "相关", "引用", "位于", "用于", "关联"):
        await _run_sql(
            f"INSERT INTO ai_relation_types (name,color) SELECT '{rt}','#a0a6ad' "
            "WHERE NOT EXISTS (SELECT 1 FROM ai_relation_types WHERE name='" + rt + "')"
        )
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
    await _run_sql(
        "CREATE TABLE IF NOT EXISTS ai_knowledge_documents ("
        "id SERIAL PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(32) DEFAULT '0', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, knowledge_base_id INTEGER, name VARCHAR(256), "
        "file_type VARCHAR(16), size INTEGER, content TEXT, chunk_count INTEGER, "
        "doc_status VARCHAR(16), file_path VARCHAR(512), object_key VARCHAR(512))"
    )
    await _run_sql("ALTER TABLE ai_knowledge_documents ADD COLUMN IF NOT EXISTS file_path VARCHAR(512)")
    await _run_sql("ALTER TABLE ai_knowledge_documents ADD COLUMN IF NOT EXISTS object_key VARCHAR(512)")

    # ---- 检索链路 v2：分块新列（幂等；非 PG 会静默跳过） ----
    for col, ddl in (
        ("parent_id", "integer"),
        ("is_parent", "boolean DEFAULT false"),
        ("content_hash", "varchar(64)"),
        ("vector_model", "varchar(128)"),
        ("token_count", "integer"),
        ("char_start", "integer"),
        ("char_end", "integer"),
        ("search_text", "text"),
    ):
        await _run_sql(f"ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS {col} {ddl}")
    # 半精度向量列 + HNSW（2560 维超过 vector 的 2000 上限，故用 halfvec）
    await _run_sql(
        "ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_hv halfvec(2560)"
    )
    await _run_sql(
        "CREATE INDEX IF NOT EXISTS idx_chunk_embedding_hv "
        "ON ai_knowledge_chunks USING hnsw (embedding_hv halfvec_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
    # search_text 回填（正文 + 标注；索引表达式不能含子查询，故落列）
    await _run_sql(
        "UPDATE ai_knowledge_chunks SET search_text = trim("
        "coalesce(content, '') || ' ' || "
        "COALESCE((SELECT string_agg(a->>'text', ' ') FROM "
        "jsonb_array_elements(coalesce(annotations, '[]'::jsonb)) a), '')) "
        "WHERE search_text IS NULL"
    )
    await _run_sql(
        "CREATE INDEX IF NOT EXISTS idx_chunk_fts "
        "ON ai_knowledge_chunks USING gin (to_tsvector('jiebacfg', search_text))"
    )
    # ---- RAG 后台任务表（幂等；ORM 会建，这里为存量库补） ----
    await _run_sql(
        "CREATE TABLE IF NOT EXISTS ai_rag_tasks ("
        "id SERIAL PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(16) DEFAULT 'pending', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, created_id INTEGER, updated_id INTEGER, deleted_id INTEGER, "
        "kind VARCHAR(32), kb_id INTEGER, document_id INTEGER, payload JSONB, "
        "progress INTEGER DEFAULT 0, step VARCHAR(64), message TEXT, error TEXT, "
        "cancel_requested BOOLEAN DEFAULT false, started_time TIMESTAMP, finished_time TIMESTAMP)"
    )
    # ---- 检索评测表（幂等） ----
    await _run_sql(
        "CREATE TABLE IF NOT EXISTS ai_eval_sets ("
        "id SERIAL PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(16) DEFAULT '0', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, created_id INTEGER, updated_id INTEGER, deleted_id INTEGER, "
        "name VARCHAR(128), description TEXT, kb_ids JSONB)"
    )
    await _run_sql(
        "CREATE TABLE IF NOT EXISTS ai_eval_items ("
        "id SERIAL PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(16) DEFAULT '0', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, set_id INTEGER, query TEXT, "
        "expected_chunk_ids JSONB, expected_files JSONB, note TEXT)"
    )
    await _run_sql(
        "CREATE TABLE IF NOT EXISTS ai_eval_runs ("
        "id SERIAL PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(16) DEFAULT 'running', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, created_id INTEGER, updated_id INTEGER, deleted_id INTEGER, "
        "set_id INTEGER, kb_id INTEGER, config JSONB, metrics JSONB, error TEXT)"
    )
