"""检索管线：召回（多路并行）→ 融合 → 过滤 → 重排 → 上下文组装。

对外只暴露 :func:`search`；``AiKnowledgeService.search`` 是薄门面，
负责参数兼容与检索日志埋点（管线本身不关心用户/日志上下文）。
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.logger import log

from .. import embedding, graphrag
from ..config import rag_config
from ..model import AiKnowledgeBaseModel
from .context import assemble
from .engines import fulltext_search, grep_search, vector_search
from .filters import apply_filters
from .fusion import rrf, weighted
from .rerank import rerank as rerank_items


@dataclass
class SearchOptions:
    """一次检索的可选参数（默认值与设计文档 §14 一致）。"""

    mode: str = "hybrid"
    use_graph: bool = True
    min_score: float = 0.0
    use_rerank: bool = True
    vector_weight: float | None = None
    fulltext_weight: float | None = None
    rewrite: str = "off"
    filters: dict | None = None
    context_tokens: int | None = None
    top_n: int | None = None


async def _resolve_model_id(kb_ids: list[int]) -> int | None:
    async with async_db_session() as db:
        return (
            await db.execute(
                select(AiKnowledgeBaseModel.model_id)
                .where(
                    AiKnowledgeBaseModel.id.in_(kb_ids),
                    AiKnowledgeBaseModel.is_deleted.is_(False),
                )
                .order_by(AiKnowledgeBaseModel.id.asc())
                .limit(1)
            )
        ).scalar()


async def _graph_items(kb_ids: list[int], query: str, top_n: int) -> list[dict]:
    """图谱扩展召回（AGE 多跳；失败不影响主链路）。"""
    try:
        hits = await graphrag.graph_retrieve(kb_ids, query, top_n)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[RAG] 图谱召回失败（跳过）：{e}")
        return []
    items: list[dict] = []
    for hit in hits:
        for chunk in hit.get("chunks") or []:
            items.append(
                {
                    "chunk_id": int(chunk["chunk_id"]),
                    "knowledge_base_id": kb_ids[0],
                    "file_name": chunk.get("file_name") or "",
                    "document_id": chunk.get("document_id"),
                    "start_line": chunk.get("start_line"),
                    "page": chunk.get("page"),
                    "chunk_index": chunk.get("chunk_index"),
                    "parent_id": chunk.get("parent_id"),
                    "content": chunk.get("content") or "",
                    "score": 0.0,
                    "engine": "graphrag",
                    "graph_entity": hit.get("name"),
                }
            )
    return items


async def search(
    kb_ids: list[int],
    query: str,
    top_k: int = 5,
    options: SearchOptions | None = None,
    *,
    stats_out: dict | None = None,
) -> list[dict]:
    """执行一次检索，返回带 ``context`` 的结果列表。"""
    opts = options or SearchOptions()
    if not kb_ids or not (query or "").strip():
        return []
    started = time.perf_counter()
    model_id = await _resolve_model_id(kb_ids)
    limit = int(opts.top_n or max(int(top_k) * rag_config.recall_mult, rag_config.recall_min))

    mode = opts.mode if opts.mode in ("vector", "fulltext", "hybrid", "graph", "grep") else "hybrid"
    lists: list[list[dict]] = []
    engine_counts: dict[str, int] = {}
    embed_ms = 0.0

    if mode == "grep":
        rows = await grep_search(kb_ids, query, limit, filters=opts.filters)
        engine_counts["grep"] = len(rows)
        lists.append(rows)
    else:
        need_vector = mode in ("vector", "hybrid")
        need_fulltext = mode in ("fulltext", "hybrid")
        query_vector: list[float] | None = None
        if need_vector:
            t0 = time.perf_counter()
            try:
                query_vector = (await embedding.embed_texts([query], model_id=model_id))[0]
            except Exception as e:  # noqa: BLE001
                log.warning(f"[RAG] 查询向量化失败（退化为纯文本召回）：{e}")
                need_vector = False
                need_fulltext = True if mode == "hybrid" else need_fulltext
            embed_ms = round((time.perf_counter() - t0) * 1000, 1)

        tasks = []
        if need_vector:
            tasks.append(
                (
                    "vector",
                    vector_search(
                        kb_ids,
                        query,
                        limit,
                        model_id=model_id,
                        filters=opts.filters,
                        min_score=opts.min_score,
                        query_vector=query_vector,
                    ),
                )
            )
        if need_fulltext:
            tasks.append(
                ("fulltext", fulltext_search(kb_ids, query, limit, filters=opts.filters))
            )
        if mode == "graph" or (mode == "hybrid" and opts.use_graph):
            tasks.append(("graph", _graph_items(kb_ids, query, top_k)))

        if tasks:
            outcomes = await asyncio.gather(*(coro for _, coro in tasks), return_exceptions=True)
            for (name, _), outcome in zip(tasks, outcomes, strict=False):
                if isinstance(outcome, BaseException):
                    log.warning(f"[RAG] {name} 召回失败（跳过）：{outcome}")
                    engine_counts[name] = 0
                    continue
                engine_counts[name] = len(outcome)  # type: ignore[arg-type]
                lists.append(outcome)  # type: ignore[arg-type]

        # 全文不可用（无 pg_jieba / 非 PG）时自动补 grep，保证关键词问题可召回
        if need_fulltext and engine_counts.get("fulltext", 0) == 0:
            grep_rows = await grep_search(kb_ids, query, limit, filters=opts.filters)
            engine_counts["grep"] = len(grep_rows)
            lists.append(grep_rows)

        if not lists:
            lists = [[]]

    # 融合：默认 RRF；显式给权重时走归一化加权（兼容既有语义）
    if opts.vector_weight is not None or opts.fulltext_weight is not None:
        weights = []
        source = tasks if mode != "grep" else [("grep", None)]
        for name, _ in source:
            if name == "vector":
                weights.append(float(opts.vector_weight or 0.0) or 0.5)
            elif name == "fulltext":
                weights.append(float(opts.fulltext_weight or 0.0) or 0.5)
            else:
                weights.append(0.3)
        fused = weighted(lists, weights)
    else:
        fused = rrf(lists)

    fused = apply_filters(fused, opts.filters)

    rerank_status = "off"
    if opts.use_rerank and fused:
        outcome = await rerank_items(
            query, fused[: int(rag_config.rerank_candidates)], int(top_k), model_id=model_id
        )
        fused = outcome.items
        rerank_status = outcome.status

    assembled = await assemble(fused, top_k=int(top_k), context_tokens=opts.context_tokens)
    total_ms = round((time.perf_counter() - started) * 1000, 1)
    for item in assembled:
        item["timings"] = {
            "embed_ms": embed_ms,
            "total_ms": total_ms,
            "engine_counts": dict(engine_counts),
            "rerank": rerank_status,
        }

    if stats_out is not None:
        stats_out.update(
            {
                "embed_ms": embed_ms,
                "rerank": rerank_status,
                "engine_counts": engine_counts,
                "total_ms": total_ms,
            }
        )
    return assembled
