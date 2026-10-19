"""召回引擎：向量（PG halfvec / 非 PG 余弦）、全文（jiebacfg）、grep。

统一返回结构（供融合与前端消费）：
``{"chunk_id","knowledge_base_id","file_name","document_id","start_line","page",
"content","score","engine"}``。
"""
from __future__ import annotations

import math
import os

from sqlalchemy import select, text

from app.core.database import async_db_session
from app.core.logger import log

from .. import embedding
from ..config import rag_config
from ..embeddings import persist as vector_store
from ..model import AiKnowledgeChunkModel
from .filters import apply_filters

_COLUMNS = (
    "id, knowledge_base_id, file_name, document_id, start_line, page, content"
)


def _is_postgres() -> bool:
    return (os.getenv("DATABASE_TYPE") or "postgresql").lower() in ("postgres", "postgresql")


def _row_to_item(row, score: float, engine: str) -> dict:
    return {
        "chunk_id": int(row["id"]),
        "knowledge_base_id": int(row["knowledge_base_id"]),
        "file_name": row["file_name"] or "",
        "document_id": row["document_id"],
        "start_line": row["start_line"],
        "page": row["page"],
        "content": row["content"],
        "score": round(float(score or 0.0), 4),
        "engine": engine,
    }


def _cosine(a: list[float], b: list[float]) -> float | None:
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na <= 0 or nb <= 0:
        return None
    return max(-1.0, min(1.0, dot / (na * nb)))


async def ensure_vector_index() -> bool:
    """幂等确保 PG 向量列与 HNSW 索引（非 PG 返回 False）。"""
    if not _is_postgres():
        return False
    async with async_db_session.begin() as db:
        return await vector_store.ensure_pg_vector_columns(db)


async def _py_vector_search(
    kb_ids: list[int], query_vector: list[float], top_n: int, *, min_score: float
) -> list[dict]:
    async with async_db_session() as db:
        rows = (
            (
                await db.execute(
                    select(AiKnowledgeChunkModel).where(
                        AiKnowledgeChunkModel.knowledge_base_id.in_(kb_ids),
                        AiKnowledgeChunkModel.is_deleted.is_(False),
                        AiKnowledgeChunkModel.is_parent.is_not(True),
                        AiKnowledgeChunkModel.vector.isnot(None),
                    )
                )
            )
            .scalars()
            .all()
        )
    scored: list[dict] = []
    for row in rows:
        sim = _cosine(query_vector, list(row.vector or []))
        if sim is None or sim < min_score:
            continue
        scored.append(
            {
                "chunk_id": int(row.id),
                "knowledge_base_id": int(row.knowledge_base_id),
                "file_name": row.file_name or "",
                "document_id": row.document_id,
                "start_line": row.start_line,
                "page": row.page,
                "content": row.content,
                "score": round(sim, 4),
                "engine": "pyvector",
            }
        )
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_n]


async def vector_search(
    kb_ids: list[int],
    query: str,
    top_n: int,
    *,
    model_id: int | None = None,
    filters: dict | None = None,
    min_score: float = 0.0,
) -> list[dict]:
    """向量召回：PG 走 halfvec HNSW；其它库/失败回退 Python 余弦。"""
    if not kb_ids or not query:
        return []
    try:
        qvec = (await embedding.embed_texts([query], model_id=model_id))[0]
    except Exception as e:  # noqa: BLE001
        log.warning(f"[RAG] 查询向量化失败，向量召回跳过：{e}")
        return []

    if _is_postgres():
        try:
            async with async_db_session.begin() as db:
                await db.execute(
                    text(f"SET LOCAL hnsw.ef_search = {int(rag_config.hnsw_ef_search)}")
                )
                rows = (
                    await db.execute(
                        text(
                            f"SELECT {_COLUMNS}, 1 - (embedding_hv <=> CAST(:qv AS halfvec)) AS score "
                            "FROM ai_knowledge_chunks "
                            "WHERE knowledge_base_id = ANY(:ids) AND is_deleted = false "
                            "AND is_parent IS NOT TRUE AND embedding_hv IS NOT NULL "
                            "AND 1 - (embedding_hv <=> CAST(:qv AS halfvec)) >= :min_score "
                            "ORDER BY embedding_hv <=> CAST(:qv AS halfvec) LIMIT :k"
                        ),
                        {
                            "ids": kb_ids,
                            "qv": vector_store.vector_literal(qvec),
                            "k": int(top_n),
                            "min_score": float(min_score),
                        },
                    )
                ).mappings().all()
            return apply_filters(
                [_row_to_item(r, r["score"], "pgvector") for r in rows], filters
            )
        except Exception as e:  # noqa: BLE001  无扩展/无列/维度不符 → 回退
            log.warning(f"[RAG] pgvector 召回失败，回退 Python 余弦：{e}")

    rows = await _py_vector_search(kb_ids, qvec, top_n, min_score=min_score)
    return apply_filters(rows, filters)


async def fulltext_search(
    kb_ids: list[int], query: str, top_n: int, *, filters: dict | None = None
) -> list[dict]:
    """中文全文召回（pg_jieba ``jiebacfg`` + GIN）；不可用时返回空列表。"""
    if not (_is_postgres() and kb_ids and query):
        return []
    try:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    text(
                        f"SELECT {_COLUMNS}, "
                        "ts_rank(to_tsvector('jiebacfg', coalesce(search_text, '')), "
                        "plainto_tsquery('jiebacfg', :q)) AS score "
                        "FROM ai_knowledge_chunks "
                        "WHERE knowledge_base_id = ANY(:ids) AND is_deleted = false "
                        "AND is_parent IS NOT TRUE "
                        "AND to_tsvector('jiebacfg', coalesce(search_text, '')) "
                        "@@ plainto_tsquery('jiebacfg', :q) "
                        "ORDER BY score DESC LIMIT :k"
                    ),
                    {"ids": kb_ids, "q": query, "k": int(top_n)},
                )
            ).mappings().all()
        return apply_filters([_row_to_item(r, r["score"], "jieba_fulltext") for r in rows], filters)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[RAG] 全文召回不可用（将退化为 grep）：{e}")
        return []


async def grep_search(
    kb_ids: list[int], query: str, top_n: int, *, filters: dict | None = None
) -> list[dict]:
    """子串召回（兜底）：按标点/空白拆词，任一命中即返回。"""
    if not kb_ids or not query:
        return []
    terms = [p for p in query.replace("，", " ").replace("。", " ").split() if p] or [query]
    conds = " OR ".join(f"(content ILIKE :t{i} OR coalesce(search_text,'') ILIKE :t{i})"
                        for i in range(len(terms)))
    params: dict = {"ids": kb_ids, "k": int(top_n)}
    for i, term in enumerate(terms):
        params[f"t{i}"] = f"%{term}%"
    try:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    text(
                        f"SELECT {_COLUMNS}, 1.0 AS score FROM ai_knowledge_chunks "
                        "WHERE knowledge_base_id = ANY(:ids) AND is_deleted = false "
                        "AND is_parent IS NOT TRUE "
                        f"AND ({conds}) ORDER BY id LIMIT :k"
                    ),
                    params,
                )
            ).mappings().all()
    except Exception as e:  # noqa: BLE001  非 PG（如 SQLite）用 ORM 兜底
        log.warning(f"[RAG] grep SQL 失败，回退 ORM：{e}")
        async with async_db_session() as db:
            candidates = (
                (
                    await db.execute(
                        select(AiKnowledgeChunkModel).where(
                            AiKnowledgeChunkModel.knowledge_base_id.in_(kb_ids),
                            AiKnowledgeChunkModel.is_deleted.is_(False),
                            AiKnowledgeChunkModel.is_parent.is_not(True),
                        )
                    )
                )
                .scalars()
                .all()
            )
        lowered = query.lower()
        rows = [
            {
                "id": c.id,
                "knowledge_base_id": c.knowledge_base_id,
                "file_name": c.file_name or "",
                "document_id": c.document_id,
                "start_line": c.start_line,
                "page": c.page,
                "content": c.content,
                "score": 1.0,
            }
            for c in candidates
            if lowered in (c.content or "").lower()
            or lowered in (c.search_text or "").lower()
        ][:top_n]
        return apply_filters(
            [_row_to_item(r, r["score"], "grep") for r in rows], filters
        )

    return apply_filters([_row_to_item(r, r["score"], "grep") for r in rows], filters)
