"""向量与检索文本的统一写入路径。

所有入库 / 重建 / 编辑路径都必须经过 :func:`write_vectors`，避免出现
「只写了 JSONB、pgvector 列没写」「标注改了 search_text 没跟着改」这类不一致：
- ``vector``(jsonb)  —— 权威副本，跨库可移植（SQLite/MySQL 回退用）
- ``embedding``(vector) / ``embedding_hv``(halfvec) —— PG 检索列（2560 维超过
  ``vector`` 的 HNSW 上限 2000，故真正建索引的是半精度列）
- ``search_text`` —— 正文 + 标注，全文检索唯一入口（索引表达式不能含子查询）
"""
from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from typing import Any

from sqlalchemy import text

from app.core.logger import log

from ..config import rag_config

#: PG 向量列默认维度（``smbs/Embedding-4B`` 实测 2560）
PG_DEFAULT_DIM = 2560


def _is_postgres() -> bool:
    """当前连接是否 PostgreSQL（非 PG 只写 JSONB）。"""
    return (os.getenv("DATABASE_TYPE") or "postgresql").lower() in ("postgres", "postgresql")


def build_search_text(content: str, annotations: list | None) -> str:
    """正文 + 标注文本（空白分隔）——全文检索的唯一入口文本。"""
    parts: list[str] = []
    for a in annotations or []:
        if isinstance(a, dict) and a.get("text"):
            parts.append(str(a["text"]))
    return " ".join([(content or "").strip()] + parts).strip()


def vector_literal(vec: Sequence[float]) -> str:
    """格式化为 pgvector 字面量，如 ``[1.0,2.0]``。"""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def chunk_hash(content: str, model: str) -> str:
    """内容哈希（含模型名）：换模型后哈希随之变化，可用于失效判断与去重。"""
    h = hashlib.sha256()
    h.update((model or "").encode("utf-8"))
    h.update(b"\x00")
    h.update((content or "").encode("utf-8"))
    return h.hexdigest()


def _estimate_tokens(value: str) -> int | None:
    """token 估算：``chunking.tokens`` 尚未实现时返回 None（不阻塞入库）。"""
    try:
        from ..chunking.tokens import estimate_tokens
    except Exception:  # noqa: BLE001
        return None
    try:
        return estimate_tokens(value)
    except Exception:  # noqa: BLE001
        return None


async def ensure_pg_vector_columns(db, dim: int | None = None) -> bool:
    """幂等：确保 PG 向量列（vector + halfvec）与 HNSW 索引存在。

    返回是否准备成功；失败（无 pgvector 扩展等）时调用方退回 JSONB + Python 余弦。
    """
    target = int(dim or PG_DEFAULT_DIM)
    try:
        await db.execute(
            text(
                "ALTER TABLE ai_knowledge_chunks "
                f"ADD COLUMN IF NOT EXISTS embedding vector({target})"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE ai_knowledge_chunks "
                f"ADD COLUMN IF NOT EXISTS embedding_hv halfvec({target})"
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_chunk_embedding_hv "
                "ON ai_knowledge_chunks USING hnsw (embedding_hv halfvec_cosine_ops) "
                f"WITH (m = {rag_config.hnsw_m}, "
                f"ef_construction = {rag_config.hnsw_ef_construction})"
            )
        )
        return True
    except Exception as e:  # noqa: BLE001
        log.warning(f"[RAG] 向量列/索引准备失败，退回 JSONB + Python 余弦：{e}")
        return False


async def write_vectors(
    db,
    rows: Sequence[Any],
    vectors: Sequence[Sequence[float]],
    *,
    model_name: str,
    expected_dim: int | None = None,
) -> int:
    """写入向量与检索文本（唯一入口）。

    返回成功写入 PG 检索列的行数；非 PG 或维度与列不一致时返回 0（JSONB 仍已写入）。
    调用前 ``rows`` 必须已 ``flush()``（需要 ``id``）。
    """
    target = int(expected_dim or PG_DEFAULT_DIM)
    pairs: list[tuple[Any, list[float]]] = []
    for row, vec in zip(rows, vectors, strict=False):
        if not vec:
            continue
        values = [float(x) for x in vec]
        row.vector = values
        row.dimension = len(values)
        row.vector_model = model_name
        search_text = build_search_text(row.content or "", getattr(row, "annotations", None))
        row.search_text = search_text
        row.content_hash = chunk_hash(search_text, model_name)
        if getattr(row, "token_count", None) is None:
            row.token_count = _estimate_tokens(row.content or "")
        pairs.append((row, values))
    if not pairs or not _is_postgres():
        return 0
    if not await ensure_pg_vector_columns(db, target):
        return 0
    written = 0
    for row, values in pairs:
        if len(values) != target:
            log.warning(
                f"[RAG] 分块 {getattr(row, 'id', None)} 向量维度 {len(values)} != {target}，仅写 JSONB"
            )
            continue
        try:
            await db.execute(
                text(
                    "UPDATE ai_knowledge_chunks SET embedding = CAST(:v AS vector), "
                    "embedding_hv = CAST(:v AS halfvec) WHERE id = :id"
                ),
                {"v": vector_literal(values), "id": row.id},
            )
            written += 1
        except Exception as e:  # noqa: BLE001
            log.warning(f"[RAG] 写 pgvector 列失败（保留 JSONB）：{e}")
            break
    return written
