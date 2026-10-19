"""RAG 检索链路 v2：分块新列 + 向量/全文索引 + 后台任务表 + 评测表

Revision ID: b1c2d3e4f5a6
Revises: f6b7c8d9e0a1
Create Date: 2026-10-19 22:50:00.000000

说明（**手写迁移**，本项目禁用 autogenerate：dev 库有 400+ 历史/影子表，
autogenerate 会把它们判成待 DROP）：

- `ai_knowledge_chunks` 增列：parent_id / is_parent / content_hash / vector_model /
  token_count / char_start / char_end / search_text（检索链路 v2，见设计文档 §5.1）。
- PG 专有：`embedding_hv halfvec(2560)`（2560 维超过 vector 的 HNSW 上限 2000，
  故真正建索引的是半精度列）、`idx_chunk_embedding_hv`（HNSW）、
  `idx_chunk_fts`（`to_tsvector('jiebacfg', search_text)` 的 GIN）——非 PG 一律跳过。
- `search_text` 回填：**索引表达式不能含子查询**，所以落成实体列；PG 下用 jsonb 函数
  拼「正文 + 标注」，其它方言退化为 `content`。
- 新增 4 张表：`ai_rag_tasks`（后台任务）、`ai_eval_sets` / `ai_eval_items` / `ai_eval_runs`（评测）。
- 知识库各表是**插件表**，不由迁移链创建：空库全链重放（SQLite 回归）时可能不存在 →
  所有操作先 `sa.inspect(bind).has_table()` 判定；建表/建索引失败只打印并跳过
  （启动期 `knowledge/extensions.py` 会幂等补齐，确保存量库与空库都能落地）。
- `downgrade()` 删表 + 删列 + 删索引；列删除在 SQLite 上会失败（不支持 DROP COLUMN IF EXISTS），
  逐条 try/except 跳过。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "f6b7c8d9e0a1"
branch_labels = None
depends_on = None

_TABLE = "ai_knowledge_chunks"

#: 新增列 -> 类型（PG 之外的方言用同样的类型名，均被 PG/SQLite/MySQL 接受）
_NEW_COLUMNS: tuple[tuple[str, str], ...] = (
    ("parent_id", "INTEGER"),
    ("is_parent", "BOOLEAN DEFAULT false"),
    ("content_hash", "VARCHAR(64)"),
    ("vector_model", "VARCHAR(128)"),
    ("token_count", "INTEGER"),
    ("char_start", "INTEGER"),
    ("char_end", "INTEGER"),
    ("search_text", "TEXT"),
)

_TABLES_SQL: tuple[tuple[str, str], ...] = (
    (
        "ai_rag_tasks",
        "id {serial} PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(16) DEFAULT 'pending', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, created_id INTEGER, updated_id INTEGER, deleted_id INTEGER, "
        "kind VARCHAR(32), kb_id INTEGER, document_id INTEGER, payload {json}, "
        "progress INTEGER DEFAULT 0, step VARCHAR(64), message TEXT, error TEXT, "
        "cancel_requested BOOLEAN DEFAULT false, started_time TIMESTAMP, finished_time TIMESTAMP",
    ),
    (
        "ai_eval_sets",
        "id {serial} PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(16) DEFAULT '0', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, created_id INTEGER, updated_id INTEGER, deleted_id INTEGER, "
        "name VARCHAR(128), description TEXT, kb_ids {json}",
    ),
    (
        "ai_eval_items",
        "id {serial} PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(16) DEFAULT '0', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, set_id INTEGER, query TEXT, "
        "expected_chunk_ids {json}, expected_files {json}, note TEXT",
    ),
    (
        "ai_eval_runs",
        "id {serial} PRIMARY KEY, uuid VARCHAR(64), status VARCHAR(32) DEFAULT 'running', "
        "created_time TIMESTAMP, updated_time TIMESTAMP, is_deleted BOOLEAN DEFAULT false, "
        "deleted_time TIMESTAMP, created_id INTEGER, updated_id INTEGER, deleted_id INTEGER, "
        "set_id INTEGER, kb_id INTEGER, config {json}, metrics {json}, error TEXT",
    ),
)


def _dialect() -> str:
    return op.get_bind().dialect.name


def _exec(sql: str, label: str) -> None:
    """执行一条 DDL/DML；失败只打印（启动期 extensions 会幂等补齐）。"""
    try:
        op.execute(sql)
    except Exception as e:  # noqa: BLE001
        print(f"[migrate] {label} 跳过：{type(e).__name__}: {e}")


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    dialect = _dialect()
    pg = dialect == "postgresql"
    if not _has_table(_TABLE):
        print(f"[migrate] {_TABLE} 不存在，整段跳过（由 knowledge/extensions.py 启动期补齐）")
    else:
        existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(_TABLE)}
        for col, ddl in _NEW_COLUMNS:
            if col in existing:
                continue
            _exec(f"ALTER TABLE {_TABLE} ADD COLUMN {col} {ddl}", f"加列 {col}")
        if pg:
            _exec(
                f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS embedding_hv halfvec(2560)",
                "加列 embedding_hv",
            )
        # search_text 回填
        if pg:
            _exec(
                f"UPDATE {_TABLE} SET search_text = trim(coalesce(content, '') || ' ' || "
                "COALESCE((SELECT string_agg(a->>'text', ' ') FROM "
                "jsonb_array_elements(coalesce(annotations, '[]'::jsonb)) a), '')) "
                "WHERE search_text IS NULL",
                "回填 search_text(PG)",
            )
            _exec(
                "CREATE INDEX IF NOT EXISTS idx_chunk_embedding_hv ON "
                f"{_TABLE} USING hnsw (embedding_hv halfvec_cosine_ops) "
                "WITH (m = 16, ef_construction = 64)",
                "建索引 idx_chunk_embedding_hv",
            )
            _exec(
                "CREATE INDEX IF NOT EXISTS idx_chunk_fts ON "
                f"{_TABLE} USING gin (to_tsvector('jiebacfg', search_text))",
                "建索引 idx_chunk_fts",
            )
        else:
            _exec(
                f"UPDATE {_TABLE} SET search_text = trim(coalesce(content, '')) "
                "WHERE search_text IS NULL",
                "回填 search_text(非PG)",
            )

    serial = "SERIAL" if pg else "INTEGER"
    json_type = "JSONB" if pg else "TEXT"
    for name, body in _TABLES_SQL:
        if _has_table(name):
            continue
        _exec(
            f"CREATE TABLE {name} ({body.format(serial=serial, json=json_type)})",
            f"建表 {name}",
        )


def downgrade() -> None:
    for name, _body in reversed(_TABLES_SQL):
        if not _has_table(name):
            continue
        _exec(f"DROP TABLE IF EXISTS {name}", f"删表 {name}")

    if _has_table(_TABLE):
        if _dialect() == "postgresql":
            _exec("DROP INDEX IF EXISTS idx_chunk_fts", "删索引 idx_chunk_fts")
            _exec("DROP INDEX IF EXISTS idx_chunk_embedding_hv", "删索引 idx_chunk_embedding_hv")
        for col, _ddl in reversed(_NEW_COLUMNS):
            _exec(f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS {col}", f"删列 {col}")
        if _dialect() == "postgresql":
            _exec(
                f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS embedding_hv",
                "删列 embedding_hv",
            )
