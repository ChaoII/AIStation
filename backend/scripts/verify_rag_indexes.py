"""校验 RAG 检索索引是否真实可用（在 dev/生产库上手工执行）。

用途：
1. 幂等补齐向量列（``embedding`` / ``embedding_hv``）与两个索引；
2. 打印向量查询的 ``EXPLAIN`` 计划，确认走 ``Index Scan``（而不是全表顺序扫描）。

用法：
    cd backend && uv run python scripts/check_rag_indexes.py [--dim 2560]

退出码：0 = 两个索引都存在且 EXPLAIN 走索引；1 = 未达标或数据库不可用。
"""
from __future__ import annotations

import argparse
import os
import sys

os.environ.setdefault("ENVIRONMENT", "dev")
# 手工执行脚本时把 backend/ 加入 sys.path（直接运行 scripts/ 下的文件不会自动加）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import psycopg  # noqa: E402

from app.config.setting import settings  # noqa: E402

_ALTERS = (
    "ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS parent_id integer",
    "ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS is_parent boolean DEFAULT false",
    "ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS content_hash varchar(64)",
    "ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS vector_model varchar(128)",
    "ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS token_count integer",
    "ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS char_start integer",
    "ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS char_end integer",
    "ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS search_text text",
    "ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS embedding vector({dim})",
    "ALTER TABLE ai_knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_hv halfvec({dim})",
    "UPDATE ai_knowledge_chunks SET search_text = trim("
    "coalesce(content, '') || ' ' || "
    "COALESCE((SELECT string_agg(a->>'text', ' ') FROM "
    "jsonb_array_elements(coalesce(annotations, '[]'::jsonb)) a), '')) "
    "WHERE search_text IS NULL",
    "CREATE INDEX IF NOT EXISTS idx_chunk_embedding_hv ON ai_knowledge_chunks "
    "USING hnsw (embedding_hv halfvec_cosine_ops) WITH (m = 16, ef_construction = 64)",
    "CREATE INDEX IF NOT EXISTS idx_chunk_fts ON ai_knowledge_chunks "
    "USING gin (to_tsvector('jiebacfg', search_text))",
    # 存量分块从 JSONB 回填向量列（维度必须严格等于列维度）
    "UPDATE ai_knowledge_chunks SET embedding = CAST(v.vec::text AS vector), "
    "embedding_hv = CAST(v.vec::text AS halfvec) "
    "FROM (SELECT id, vector AS vec FROM ai_knowledge_chunks "
    "      WHERE vector IS NOT NULL AND embedding_hv IS NULL) v "
    "WHERE ai_knowledge_chunks.id = v.id AND jsonb_array_length(v.vec::jsonb) = {dim}",
)

_EXPLAIN_VECTOR = (
    "EXPLAIN (COSTS OFF) SELECT id FROM ai_knowledge_chunks "
    "WHERE knowledge_base_id = ANY(ARRAY[1]) AND is_deleted = false "
    "AND embedding_hv IS NOT NULL "
    "ORDER BY embedding_hv <=> CAST('{zero}' AS halfvec({dim})) LIMIT 5"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="校验知识库 RAG 索引")
    parser.add_argument("--dim", type=int, default=2560, help="向量维度（默认 2560）")
    args = parser.parse_args()

    dsn = (
        f"postgresql://{settings.DATABASE_USER}:{settings.DATABASE_PASSWORD}"
        f"@{settings.DATABASE_HOST}:{settings.DATABASE_PORT}/{settings.DATABASE_NAME}"
    )
    try:
        conn = psycopg.connect(dsn, autocommit=True)
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] 无法连接数据库 {settings.DATABASE_HOST}:{settings.DATABASE_PORT}: {e}")
        return 1

    ok = True
    with conn:
        for stmt in _ALTERS:
            try:
                conn.execute(stmt.format(dim=args.dim))
            except Exception as e:  # noqa: BLE001
                print(f"[WARN] 补列/建索引失败（跳过）：{e}")

        rows = conn.execute(
            "select indexname from pg_indexes where tablename = 'ai_knowledge_chunks'"
        ).fetchall()
        names = {r[0] for r in rows}
        for idx in ("idx_chunk_embedding_hv", "idx_chunk_fts"):
            if idx in names:
                print(f"[OK]   索引存在：{idx}")
            else:
                print(f"[FAIL] 索引缺失：{idx}")
                ok = False

        zero = "[" + ",".join("0" for _ in range(args.dim)) + "]"
        # 小表（本机 dev 库仅数十行）规划器会合法地选择「全表扫描 + 排序」，
        # 因此关掉 seqscan/bitmapscan/sort 来证明**索引本身可用**。
        conn.execute("SET enable_seqscan = off")
        conn.execute("SET enable_bitmapscan = off")
        conn.execute("SET enable_sort = off")
        plan = conn.execute(_EXPLAIN_VECTOR.format(zero=zero, dim=args.dim)).fetchall()
        conn.execute("RESET enable_seqscan")
        conn.execute("RESET enable_bitmapscan")
        conn.execute("RESET enable_sort")
        plan_text = "\n".join(r[0][:120] for r in plan)
        print("EXPLAIN 向量查询计划（enable_seqscan/bitmapscan/sort = off）：")
        print(plan_text)
        if "idx_chunk_embedding_hv" in plan_text:
            print("[OK]   向量检索索引可用（Index Scan using idx_chunk_embedding_hv）")
        else:
            print("[FAIL] 向量检索索引不可用")
            ok = False

        filled = conn.execute(
            "select count(*), count(embedding_hv) from ai_knowledge_chunks"
        ).fetchone()
        print(f"分块总数 {filled[0]}，其中 embedding_hv 非空 {filled[1]}")
    conn.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
