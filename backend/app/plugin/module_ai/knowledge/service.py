"""知识库 / 数据源 RAG 服务：分块、嵌入、入库、余弦检索、数据源同步。"""
from __future__ import annotations

import math
import re

from sqlalchemy import func, select, text

from app.core.database import async_db_session

from . import embedding, graphrag
from .model import (
    AiDatasourceModel,
    AiKnowledgeBaseModel,
    AiKnowledgeChunkModel,
    AiKnowledgeEntityModel,
    AiKnowledgeRelationModel,
)


def _cosine(a: list[float], b: list[float]) -> float | None:
    """余弦相似度；维度不一致/零向量返回 None（fail-closed）。"""
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na <= 0 or nb <= 0:
        return None
    sim = dot / (na * nb)
    return max(-1.0, min(1.0, sim))


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50, strategy: str = "fixed") -> list[str]:
    """分块：fixed(定长+重叠) / paragraph(按段落) / sentence(按句子)。"""
    text = (text or "").strip()
    if not text:
        return []
    if strategy == "paragraph":
        paras = re.split(r"\n\s*\n", text)
        out: list[str] = []
        for p in paras:
            p = p.strip()
            if p:
                if len(p) > chunk_size:
                    out.extend(_fixed_chunk(p, chunk_size, overlap))
                else:
                    out.append(p)
        return out
    if strategy == "sentence":
        sents = re.split(r"(?<=[。！？!?；;])", text)
        out = []
        buf = ""
        for s in sents:
            s = s.strip()
            if not s:
                continue
            if len(buf) + len(s) > chunk_size and buf:
                out.append(buf.strip())
                buf = ""
            buf += s
        if buf.strip():
            out.append(buf.strip())
        if len(out) > 1 and len(out[-1]) <= overlap:
            out.pop()
        return out
    return _fixed_chunk(text, chunk_size, overlap)


def _fixed_chunk(text: str, chunk_size: int, overlap: int) -> list[str]:
    step = max(1, chunk_size - overlap)
    chunks: list[str] = []
    for i in range(0, len(text), step):
        piece = text[i : i + chunk_size].strip()
        if piece:
            chunks.append(piece)
    if len(chunks) > 1 and len(chunks[-1]) <= overlap:
        chunks.pop()
    return chunks


def _kb_to_dict(b: AiKnowledgeBaseModel) -> dict:
    return {
        "id": b.id,
        "name": b.name,
        "description": b.description or "",
        "model_id": b.model_id,
        "chunk_count": b.chunk_count or 0,
        "file_type": b.file_type or "text",
        "enabled": b.enabled,
        "graph_nodes": 0,
        "graph_edges": 0,
        "created_time": b.created_time,
        "updated_time": b.updated_time,
    }


async def _attach_graph_stats(items: list[dict]) -> None:
    """给知识库字典附加上下文的图谱规模（实体/关系数）。"""
    from sqlalchemy import func as _func

    from app.plugin.module_ai.knowledge.model import (
        AiKnowledgeEntityModel,
        AiKnowledgeRelationModel,
    )

    ids = [i["id"] for i in items if i.get("id")]
    if not ids:
        return
    try:
        async with async_db_session() as db:
            nrows = (
                await db.execute(
                    select(AiKnowledgeEntityModel.knowledge_base_id, _func.count()).where(
                        AiKnowledgeEntityModel.knowledge_base_id.in_(ids),
                        AiKnowledgeEntityModel.is_deleted.is_(False),
                    ).group_by(AiKnowledgeEntityModel.knowledge_base_id)
                )
            ).all()
            erows = (
                await db.execute(
                    select(AiKnowledgeRelationModel.knowledge_base_id, _func.count()).where(
                        AiKnowledgeRelationModel.knowledge_base_id.in_(ids),
                        AiKnowledgeRelationModel.is_deleted.is_(False),
                    ).group_by(AiKnowledgeRelationModel.knowledge_base_id)
                )
            ).all()
    except Exception:  # noqa: BLE001
        return
    nmap = {r[0]: int(r[1]) for r in nrows}
    emap = {r[0]: int(r[1]) for r in erows}
    for it in items:
        it["graph_nodes"] = nmap.get(it["id"], 0)
        it["graph_edges"] = emap.get(it["id"], 0)


def _chunk_to_dict(c: AiKnowledgeChunkModel) -> dict:
    return {
        "id": c.id,
        "knowledge_base_id": c.knowledge_base_id,
        "file_name": c.file_name or "",
        "chunk_index": c.chunk_index or 0,
        "content": c.content,
        "meta": c.meta,
        "dimension": c.dimension,
    }


def _ds_to_dict(d: AiDatasourceModel) -> dict:
    return {
        "id": d.id,
        "name": d.name,
        "ds_type": d.ds_type or "db",
        "dialect": d.dialect or "",
        "uri": d.uri or "",
        "api_config": d.api_config,
        "knowledge_base_id": d.knowledge_base_id,
        "enabled": d.enabled,
        "created_time": d.created_time,
        "updated_time": d.updated_time,
    }


class AiKnowledgeService:

    # ------------------------------------------------------------ #
    # 知识库 CRUD
    # ------------------------------------------------------------ #
    @classmethod
    async def list_bases(cls) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiKnowledgeBaseModel)
                    .where(AiKnowledgeBaseModel.is_deleted.is_(False))
                    .order_by(AiKnowledgeBaseModel.id.desc())
                )
            ).scalars().all()
            items = [_kb_to_dict(b) for b in rows]
        await _attach_graph_stats(items)
        return items

    @classmethod
    async def get_base(cls, kb_id: int) -> dict | None:
        async with async_db_session() as db:
            b = await db.get(AiKnowledgeBaseModel, kb_id)
            if not b or b.is_deleted:
                return None
            item = _kb_to_dict(b)
        await _attach_graph_stats([item])
        return item

    @classmethod
    async def create_base(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            b = AiKnowledgeBaseModel(
                name=data.name,
                description=data.description or "",
                model_id=data.model_id,
                file_type=data.file_type or "text",
                enabled=data.enabled,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(b)
            await db.flush()
            return _kb_to_dict(b)

    @classmethod
    async def update_base(cls, kb_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            b = await db.get(AiKnowledgeBaseModel, kb_id)
            if not b or b.is_deleted:
                return None
            for key in ("name", "description", "model_id", "file_type", "enabled"):
                if getattr(data, key) is not None:
                    setattr(b, key, getattr(data, key))
            b.updated_id = auth.user.id
            await db.flush()
            return _kb_to_dict(b)

    @classmethod
    async def delete_bases(cls, ids: list[int]) -> None:
        from sqlalchemy import delete as _delete

        async with async_db_session.begin() as db:
            for kid in ids:
                b = await db.get(AiKnowledgeBaseModel, kid)
                if not b:
                    continue
                # 级联删除子数据（分块 / 图谱实体 / 关系），避免外键 IntegrityError
                await db.execute(
                    _delete(AiKnowledgeChunkModel).where(
                        AiKnowledgeChunkModel.knowledge_base_id == kid
                    )
                )
                await db.execute(
                    _delete(AiKnowledgeEntityModel).where(
                        AiKnowledgeEntityModel.knowledge_base_id == kid
                    )
                )
                await db.execute(
                    _delete(AiKnowledgeRelationModel).where(
                        AiKnowledgeRelationModel.knowledge_base_id == kid
                    )
                )
                await db.delete(b)
                # 尝试删除对应 AGE 图（仅 PostgreSQL + AGE 可用时；失败忽略）
                try:
                    await db.execute(
                        text(f"SELECT drop_graph('kb_graph_{kid}', true)")
                    )
                except Exception:  # noqa: BLE001
                    pass

    # ------------------------------------------------------------ #
    # 入库 / 检索
    # ------------------------------------------------------------ #
    @classmethod
    async def _kb_model_id(cls, kb_ids: list[int]) -> int | None:
        """取目标知识库的嵌入模型 ID（取最小 id 的一个，保证检索与入库同模型）。"""
        if not kb_ids:
            return None
        async with async_db_session() as db:
            b = await db.scalar(
                select(AiKnowledgeBaseModel)
                .where(
                    AiKnowledgeBaseModel.id.in_(kb_ids),
                    AiKnowledgeBaseModel.is_deleted.is_(False),
                )
                .order_by(AiKnowledgeBaseModel.id.asc())
                .limit(1)
            )
            return b.model_id if b else None

    @classmethod
    async def ingest(cls, kb_id: int, data, auth) -> dict:
        """文本 → 分块 → 向量化 → 入库，返回写入分块数。"""
        chunks = chunk_text(data.content, data.chunk_size, data.overlap, data.strategy)
        if not chunks:
            return {"chunks": 0}
        model_id = await cls._kb_model_id([kb_id])
        vectors = await embedding.embed_texts(chunks, model_id=model_id)
        saved = 0
        async with async_db_session.begin() as db:
            b = await db.get(AiKnowledgeBaseModel, kb_id)
            if not b or b.is_deleted:
                raise ValueError("知识库不存在")
            existing = (
                await db.execute(
                    select(func.max(AiKnowledgeChunkModel.chunk_index)).where(
                        AiKnowledgeChunkModel.knowledge_base_id == kb_id
                    )
                )
            ).scalar() or 0
            for i, (chunk, vec) in enumerate(zip(chunks, vectors, strict=False), start=existing + 1):
                db.add(
                    AiKnowledgeChunkModel(
                        knowledge_base_id=kb_id,
                        file_name=data.file_name or "文本",
                        chunk_index=i,
                        content=chunk,
                        meta={"file_name": data.file_name or "文本"},
                        vector=vec,
                        dimension=len(vec) if vec else None,
                    )
                )
                saved += 1
            b.chunk_count = (b.chunk_count or 0) + saved
            b.updated_id = auth.user.id
        await cls._rebuild_graph(kb_id)
        return {"chunks": saved}

    @classmethod
    async def search(
        cls,
        kb_ids: list[int],
        query: str,
        top_k: int = 5,
        use_graph: bool = True,
        mode: str = "hybrid",
        vector_weight: float = 0.5,
        fulltext_weight: float = 0.5,
    ) -> list[dict]:
        """知识检索（多模态，自动选路）。mode: vector/fulltext/hybrid/graph/grep。"""
        if not kb_ids or not query:
            return []
        if cls._is_postgres():
            return await cls._pg_search(
                kb_ids, query, top_k, use_graph, mode, vector_weight, fulltext_weight
            )
        return await cls._py_search(kb_ids, query, top_k, use_graph, mode)

    @staticmethod
    def _is_postgres() -> bool:
        import os

        return (os.getenv("DATABASE_TYPE") or "postgresql").lower() in (
            "postgres",
            "postgresql",
        )

    @classmethod
    async def _pg_ext(cls, name: str) -> bool:
        """检测 PostgreSQL 扩展是否存在。"""
        try:
            async with async_db_session() as db:
                return bool(
                    (
                        await db.execute(
                            text("SELECT count(*) FROM pg_extension WHERE extname = :n"),
                            {"n": name},
                        )
                    ).scalar()
                )
        except Exception:  # noqa: BLE001
            return False

    @classmethod
    async def _pg_search(
        cls,
        kb_ids: list[int],
        query: str,
        top_k: int,
        use_graph: bool,
        mode: str = "hybrid",
        vector_weight: float = 0.5,
        fulltext_weight: float = 0.5,
    ) -> list[dict]:
        """PostgreSQL 多模态检索：vector / fulltext(jiebacfg) / hybrid(加权融合) / graph / grep(ILIKE)。"""
        results: list[dict] = []
        seen: set[int] = set()
        do_ft = mode in ("fulltext", "hybrid")
        do_vec = mode in ("vector", "hybrid")
        do_graph = mode == "graph" or (mode == "hybrid" and use_graph)

        # grep / 子串全文（WikiLLM 式，正则/包含）
        if mode == "grep":
            try:
                async with async_db_session() as db:
                    rows = (
                        await db.execute(
                            text(
                                "SELECT id, knowledge_base_id, file_name, content, 1.0 AS score "
                                "FROM ai_knowledge_chunks "
                                "WHERE knowledge_base_id = ANY(:ids) AND is_deleted = false "
                                "AND content ILIKE '%' || :q || '%' ORDER BY id LIMIT :k"
                            ),
                            {"ids": kb_ids, "q": query, "k": top_k},
                        )
                    ).mappings().all()
                    for r in rows:
                        results.append(
                            {
                                "chunk_id": int(r["id"]),
                                "knowledge_base_id": int(r["knowledge_base_id"]),
                                "file_name": r["file_name"] or "",
                                "content": r["content"],
                                "score": round(float(r["score"] or 0), 4),
                                "engine": "grep",
                            }
                        )
            except Exception:  # noqa: BLE001
                pass
            return results[:top_k]

        ft_list: list[dict] = []
        vec_list: list[dict] = []

        # fulltext / jieba 中文全文
        if do_ft:
            try:
                if await cls._pg_ext("pg_jieba"):
                    async with async_db_session() as db:
                        rows = (
                            await db.execute(
                                text(
                                    "SELECT id, knowledge_base_id, file_name, content, "
                                    "ts_rank(to_tsvector('jiebacfg', content), plainto_tsquery('jiebacfg', :q)) AS score "
                                    "FROM ai_knowledge_chunks "
                                    "WHERE knowledge_base_id = ANY(:ids) AND is_deleted = false "
                                    "AND to_tsvector('jiebacfg', content) @@ plainto_tsquery('jiebacfg', :q) "
                                    "ORDER BY score DESC LIMIT :k"
                                ),
                                {"ids": kb_ids, "q": query, "k": top_k},
                            )
                        ).mappings().all()
                        for r in rows:
                            ft_list.append(
                                {
                                    "chunk_id": int(r["id"]),
                                    "knowledge_base_id": int(r["knowledge_base_id"]),
                                    "file_name": r["file_name"] or "",
                                    "content": r["content"],
                                    "score": round(float(r["score"] or 0), 4),
                                    "engine": "jieba_fulltext",
                                }
                            )
            except Exception:  # noqa: BLE001
                pass
            if mode == "fulltext":
                return ft_list[:top_k]

        # vector / pgvector
        if do_vec:
            try:
                qvec = (await embedding.embed_texts([query], model_id=await cls._kb_model_id(kb_ids)))[0]
                async with async_db_session() as db:
                    await cls._ensure_vector_col(db)
                    rows = (
                        await db.execute(
                            text(
                                "SELECT id, knowledge_base_id, file_name, content, "
                                "(1 - (embedding <=> :qv)) AS score "
                                "FROM ai_knowledge_chunks "
                                "WHERE knowledge_base_id = ANY(:ids) AND is_deleted = false AND embedding IS NOT NULL "
                                "ORDER BY embedding <=> :qv LIMIT :k"
                            ),
                            {"ids": kb_ids, "qv": str(qvec), "k": top_k},
                        )
                    ).mappings().all()
                    for r in rows:
                        vec_list.append(
                            {
                                "chunk_id": int(r["id"]),
                                "knowledge_base_id": int(r["knowledge_base_id"]),
                                "file_name": r["file_name"] or "",
                                "content": r["content"],
                                "score": round(float(r["score"] or 0), 4),
                                "engine": "pgvector",
                            }
                        )
            except Exception:  # noqa: BLE001
                vec_list = await cls._py_search_vector(kb_ids, query, top_k)
            if mode == "vector":
                return vec_list[:top_k]

        # hybrid：向量 + 全文加权融合（min-max 归一化后按权重合成）
        if mode == "hybrid":
            results = cls._fuse_weighted(vec_list, ft_list, vector_weight, fulltext_weight)
            seen = {r["chunk_id"] for r in results}
        else:
            results = vec_list + ft_list
            seen = {r["chunk_id"] for r in results}

        # graph 多跳
        if do_graph:
            try:
                gh = await graphrag.graph_retrieve(kb_ids, query, top_k)
                for hit in gh:
                    for c in hit.get("chunks") or []:
                        rid = c.get("chunk_id")
                        if rid in seen:
                            continue
                        seen.add(rid)
                        results.append(
                            {
                                "chunk_id": rid,
                                "knowledge_base_id": kb_ids[0],
                                "file_name": c.get("file_name") or "",
                                "content": c["content"],
                                "score": 0,
                                "graph_entity": hit.get("name"),
                                "engine": "graphrag",
                            }
                        )
            except Exception:  # noqa: BLE001
                pass
        return results[: top_k * 3]

    @staticmethod
    def _minmax_scores(items: list[dict]) -> dict[int, float]:
        """按分块得分清单做 max 归一分（score/max，命中最大者=1，单命中不再归零）。"""
        if not items:
            return {}
        hi = max(it.get("score", 0.0) or 0.0 for it in items)
        if hi <= 0.0:
            return {it["chunk_id"]: 0.0 for it in items}
        return {it["chunk_id"]: ((it.get("score", 0.0) or 0.0) / hi) for it in items}

    @classmethod
    def _fuse_weighted(
        cls,
        vec_list: list[dict],
        ft_list: list[dict],
        vec_w: float,
        ft_w: float,
    ) -> list[dict]:
        """混合检索：向量 + 全文按权重融合（缺失侧贡献 0）。"""
        vn = cls._minmax_scores(vec_list)
        fn = cls._minmax_scores(ft_list)
        info: dict[int, dict] = {}
        for it in vec_list + ft_list:
            info.setdefault(it["chunk_id"], it)
        fused: list[dict] = []
        for cid, it in info.items():
            combined = vn.get(cid, 0.0) * vec_w + fn.get(cid, 0.0) * ft_w
            fused.append({**it, "engine": "hybrid", "score": round(combined, 4)})
        fused.sort(key=lambda x: x["score"], reverse=True)
        return fused

    @classmethod
    async def _ensure_vector_col(cls, db) -> None:
        """惰性：为 chunk 表加 pgvector embedding 列 + HNSW 索引（幂等，异常忽略）。"""
        try:
            await db.execute(
                text(
                    "ALTER TABLE ai_knowledge_chunks "
                    "ADD COLUMN IF NOT EXISTS embedding vector(256)"
                )
            )
            await db.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_chunk_embedding "
                    "ON ai_knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
                )
            )
            # 从现有 JSONB vector 迁移一次（254+ 维才填，避免缩小）
            await db.execute(
                text(
                    "UPDATE ai_knowledge_chunks SET embedding = vector(v.vec::text) "
                    "FROM (SELECT id, vector AS vec FROM ai_knowledge_chunks "
                    "      WHERE vector IS NOT NULL AND embedding IS NULL) v "
                    "WHERE ai_knowledge_chunks.id = v.id AND "
                    "      jsonb_array_length(v.vec::jsonb) BETWEEN 1 AND 256"
                )
            )
            await db.commit()
        except Exception:  # noqa: BLE001
            await db.rollback()

    @classmethod
    async def _py_search_vector(cls, kb_ids: list[int], query: str, top_k: int) -> list[dict]:
        """Python 余弦向量检索回退。"""
        qvec = (await embedding.embed_texts([query], model_id=await cls._kb_model_id(kb_ids)))[0]
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiKnowledgeChunkModel).where(
                        AiKnowledgeChunkModel.knowledge_base_id.in_(kb_ids),
                        AiKnowledgeChunkModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
        scored: list[dict] = []
        for c in rows:
            vec = c.vector or []
            sim = _cosine(qvec, vec) if vec else None
            if sim is None:
                continue
            scored.append(
                {
                    "chunk_id": c.id,
                    "knowledge_base_id": c.knowledge_base_id,
                    "file_name": c.file_name or "",
                    "content": c.content,
                    "score": round(sim, 4),
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    @classmethod
    async def _py_search(cls, kb_ids: list[int], query: str, top_k: int, use_graph: bool, mode: str = "hybrid") -> list[dict]:
        """全可移植回退（SQLite / 无扩展）：子串(grep)/余弦/共现图。"""
        results: list[dict] = []
        if mode == "grep":
            async with async_db_session() as db:
                rows = (
                    await db.execute(
                        select(AiKnowledgeChunkModel).where(
                            AiKnowledgeChunkModel.knowledge_base_id.in_(kb_ids),
                            AiKnowledgeChunkModel.is_deleted.is_(False),
                        )
                    )
                ).scalars().all()
            for c in rows:
                if query in (c.content or ""):
                    results.append(
                        {
                            "chunk_id": c.id,
                            "knowledge_base_id": c.knowledge_base_id,
                            "file_name": c.file_name or "",
                            "content": c.content,
                            "score": 1.0,
                            "engine": "grep",
                        }
                    )
            return results[:top_k]

        if mode in ("vector", "hybrid"):
            results = await cls._py_search_vector(kb_ids, query, top_k)

        if mode == "graph" or (use_graph and mode == "hybrid"):
            try:
                gh = await graphrag.graph_retrieve(kb_ids, query, top_k)
                seen = {r["chunk_id"] for r in results}
                for hit in gh:
                    for c in hit.get("chunks") or []:
                        if c.get("chunk_id") not in seen:
                            results.append(
                                {
                                    "chunk_id": c["chunk_id"],
                                    "knowledge_base_id": kb_ids[0],
                                    "file_name": c.get("file_name") or "",
                                    "content": c["content"],
                                    "score": 0,
                                    "graph_entity": hit.get("name"),
                                    "engine": "graphrag",
                                }
                            )
                            seen.add(c["chunk_id"])
            except Exception:  # noqa: BLE001
                pass
        if mode == "fulltext":
            # 无 pg_jieba 时用 Python jieba 分词做子串命中的近似关键词
            async with async_db_session() as db:
                rows = (
                    await db.execute(
                        select(AiKnowledgeChunkModel).where(
                            AiKnowledgeChunkModel.knowledge_base_id.in_(kb_ids),
                            AiKnowledgeChunkModel.is_deleted.is_(False),
                        )
                    )
                ).scalars().all()
            for c in rows:
                if query in (c.content or ""):
                    results.append(
                        {
                            "chunk_id": c.id,
                            "knowledge_base_id": c.knowledge_base_id,
                            "file_name": c.file_name or "",
                            "content": c.content,
                            "score": 1.0,
                            "engine": "jieba_fulltext",
                        }
                    )
        return results[: top_k * 3]

    @classmethod
    async def get_graph(cls, kb_id: int) -> dict:
        """返回知识库图谱（实体 + 关系），供前端可视化。"""
        async with async_db_session() as db:
            ents = (
                (
                    await db.execute(
                        select(AiKnowledgeEntityModel).where(
                            AiKnowledgeEntityModel.knowledge_base_id == kb_id,
                            AiKnowledgeEntityModel.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )
            rels = (
                (
                    await db.execute(
                        select(AiKnowledgeRelationModel).where(
                            AiKnowledgeRelationModel.knowledge_base_id == kb_id,
                            AiKnowledgeRelationModel.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return {
            "nodes": [
                {"id": e.id, "name": e.name, "etype": e.etype or "keyword", "weight": e.weight or 1}
                for e in ents
            ],
            "edges": [
                {"id": r.id, "source": r.source, "target": r.target, "weight": r.weight or 1}
                for r in rels
            ],
        }

    # ---------- 图谱编辑（实体 / 关系 CRUD + AGE 同步） ----------
    @classmethod
    async def create_graph_entity(cls, kb_id: int, data) -> dict:
        async with async_db_session.begin() as db:
            e = AiKnowledgeEntityModel(
                knowledge_base_id=kb_id, name=data.name, etype=data.etype or "keyword",
                weight=data.weight or 1,
            )
            db.add(e)
            await db.flush()
            eid = e.id
        await graphrag.age_sync_graph(kb_id)
        return {"id": eid, "name": data.name, "etype": data.etype or "keyword", "weight": data.weight or 1}

    @classmethod
    async def update_graph_entity(cls, kb_id: int, entity_id: int, data) -> dict | None:
        async with async_db_session.begin() as db:
            e = await db.get(AiKnowledgeEntityModel, entity_id)
            if not e or e.is_deleted or e.knowledge_base_id != kb_id:
                return None
            old_name = e.name
            if data.name:
                e.name = data.name
            if data.etype:
                e.etype = data.etype
            if data.weight:
                e.weight = data.weight
            # 改名时联动更新关系边的 source/target（保持图谱连边不悬空）
            if data.name and data.name != old_name:
                from sqlalchemy import update as _update

                await db.execute(
                    _update(AiKnowledgeRelationModel)
                    .where(
                        AiKnowledgeRelationModel.knowledge_base_id == kb_id,
                        AiKnowledgeRelationModel.source == old_name,
                    )
                    .values(source=data.name)
                )
                await db.execute(
                    _update(AiKnowledgeRelationModel)
                    .where(
                        AiKnowledgeRelationModel.knowledge_base_id == kb_id,
                        AiKnowledgeRelationModel.target == old_name,
                    )
                    .values(target=data.name)
                )
        await graphrag.age_sync_graph(kb_id)
        return {"id": e.id, "name": e.name, "etype": e.etype or "keyword", "weight": e.weight or 1}

    @classmethod
    async def delete_graph_entities(cls, kb_id: int, ids: list[int]) -> None:
        from sqlalchemy import delete as _delete

        async with async_db_session.begin() as db:
            await db.execute(
                _delete(AiKnowledgeEntityModel).where(
                    AiKnowledgeEntityModel.id.in_(ids),
                    AiKnowledgeEntityModel.knowledge_base_id == kb_id,
                )
            )
        await graphrag.age_sync_graph(kb_id)

    @classmethod
    async def create_graph_relation(cls, kb_id: int, data) -> dict:
        async with async_db_session.begin() as db:
            r = AiKnowledgeRelationModel(
                knowledge_base_id=kb_id, source=data.source, target=data.target,
                weight=data.weight or 1,
            )
            db.add(r)
            await db.flush()
            rid = r.id
        await graphrag.age_sync_graph(kb_id)
        return {"id": rid, "source": data.source, "target": data.target, "weight": data.weight or 1}

    @classmethod
    async def delete_graph_relations(cls, kb_id: int, ids: list[int]) -> None:
        from sqlalchemy import delete as _delete

        async with async_db_session.begin() as db:
            await db.execute(
                _delete(AiKnowledgeRelationModel).where(
                    AiKnowledgeRelationModel.id.in_(ids),
                    AiKnowledgeRelationModel.knowledge_base_id == kb_id,
                )
            )
        await graphrag.age_sync_graph(kb_id)

    @classmethod
    async def list_chunks(cls, kb_id: int) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiKnowledgeChunkModel)
                    .where(
                        AiKnowledgeChunkModel.knowledge_base_id == kb_id,
                        AiKnowledgeChunkModel.is_deleted.is_(False),
                    )
                    .order_by(AiKnowledgeChunkModel.chunk_index.asc())
                )
            ).scalars().all()
            return [_chunk_to_dict(c) for c in rows]

    @classmethod
    async def delete_chunk(cls, chunk_id: int) -> None:
        async with async_db_session.begin() as db:
            c = await db.get(AiKnowledgeChunkModel, chunk_id)
            if c:
                await db.delete(c)

    @classmethod
    async def update_chunk(cls, kb_id: int, chunk_id: int, content: str) -> dict:
        """编辑分块内容并重新向量化该分块。"""
        async with async_db_session.begin() as db:
            c = await db.get(AiKnowledgeChunkModel, chunk_id)
            if not c or c.knowledge_base_id != kb_id:
                raise ValueError("分块不存在")
            model_id = await cls._kb_model_id([kb_id])
            vec = (await embedding.embed_texts([content], model_id=model_id))[0]
            c.content = content
            c.vector = vec
            c.dimension = len(vec) if vec else None
        return {"chunk_id": chunk_id}

    # ------------------------------------------------------------ #
    # 数据源
    # ------------------------------------------------------------ #
    @classmethod
    async def list_datasources(cls) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiDatasourceModel)
                    .where(AiDatasourceModel.is_deleted.is_(False))
                    .order_by(AiDatasourceModel.id.desc())
                )
            ).scalars().all()
            return [_ds_to_dict(d) for d in rows]

    @classmethod
    async def create_datasource(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            d = AiDatasourceModel(
                name=data.name,
                ds_type=data.ds_type or "db",
                dialect=data.dialect or "",
                uri=data.uri or "",
                api_config=data.api_config,
                knowledge_base_id=data.knowledge_base_id,
                enabled=data.enabled,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(d)
            await db.flush()
            return _ds_to_dict(d)

    @classmethod
    async def update_datasource(cls, ds_id: int, data, auth) -> dict | None:
        async with async_db_session.begin() as db:
            d = await db.get(AiDatasourceModel, ds_id)
            if not d or d.is_deleted:
                return None
            for key in (
                "name", "ds_type", "dialect", "uri", "api_config",
                "knowledge_base_id", "enabled",
            ):
                if getattr(data, key) is not None:
                    setattr(d, key, getattr(data, key))
            d.updated_id = auth.user.id
            await db.flush()
            return _ds_to_dict(d)

    @classmethod
    async def delete_datasources(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for ds_id in ids:
                d = await db.get(AiDatasourceModel, ds_id)
                if d:
                    await db.delete(d)

    @classmethod
    async def _db_rows(cls, uri: str, table: str, limit: int) -> list[str]:
        """通过 SQLAlchemy 从数据库取文本行。"""
        from sqlalchemy import create_engine, text

        engine = create_engine(uri)
        with engine.connect() as conn:
            sql = f"SELECT * FROM {table} LIMIT {int(limit)}"
            result = conn.execute(text(sql))
            cols = list(result.keys())
            texts: list[str] = []
            for row in result:
                parts = []
                for col in cols:
                    v = row._mapping.get(col)
                    if v is not None:
                        parts.append(f"{col}: {v}")
                texts.append("\n".join(parts))
        return texts

    @classmethod
    async def _api_rows(cls, uri: str, api_config: dict | None, limit: int) -> list[str]:
        """调用 API 并按字段路径抽取文本。"""
        import httpx

        cfg = api_config or {}
        method = (cfg.get("method") or "GET").upper()
        headers = cfg.get("headers") or {}
        body = cfg.get("body")
        path = cfg.get("data_path") or "data"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.request(method, uri, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
        for key in [p for p in (path or "data").split(".") if p]:
            data = data.get(key, []) if isinstance(data, dict) else []
        if not isinstance(data, list):
            data = [data]
        texts: list[str] = []
        for item in data[:limit]:
            if isinstance(item, dict):
                texts.append("\n".join(f"{k}: {v}" for k, v in item.items()))
            else:
                texts.append(str(item))
        return texts

    @classmethod
    async def test_datasource(cls, ds_id: int) -> dict:
        async with async_db_session() as db:
            d = await db.get(AiDatasourceModel, ds_id)
        if not d or d.is_deleted:
            raise ValueError("数据源不存在")
        try:
            if d.ds_type == "db":
                await _probe_db(d)
                return {"ok": True, "message": "连接成功"}
            rows = await cls._api_rows(d.uri or "", d.api_config, 1)
            return {"ok": True, "message": f"拉取 {len(rows)} 条"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "message": str(e)}

    @classmethod
    async def sync_datasource(cls, ds_id: int, data, auth) -> dict:
        """数据源 → 目标知识库 同步入库。"""
        async with async_db_session() as db:
            d = await db.get(AiDatasourceModel, ds_id)
            kb_id = d.knowledge_base_id if d else None
        if not d or d.is_deleted:
            raise ValueError("数据源不存在")
        if not kb_id:
            raise ValueError("数据源未绑定目标知识库")
        if d.ds_type == "db":
            if not (data.table or "").strip():
                raise ValueError("数据库同步需指定表名/查询")
            texts = await cls._db_rows(d.uri or "", data.table.strip(), data.limit)
        else:
            texts = await cls._api_rows(d.uri or "", d.api_config, data.limit)

        async with async_db_session.begin() as db:
            b = await db.get(AiKnowledgeBaseModel, kb_id)
            if b:
                pass  # 校验存在
        total = 0
        for txt in texts:
            if not txt.strip():
                continue
            # 使用轻量导入：直接按每条入库（避免跨函数 session 复用问题）
            total += await cls._ingest_single(kb_id, d.name, txt, auth)
        return {"rows": len(texts), "chunks": total}

    @classmethod
    async def _ingest_single(cls, kb_id: int, file_name: str, text: str, auth) -> int:
        chunks = chunk_text(text)
        if not chunks:
            return 0
        vectors = await embedding.embed_texts(chunks, model_id=await cls._kb_model_id([kb_id]))
        async with async_db_session.begin() as db:
            b = await db.get(AiKnowledgeBaseModel, kb_id)
            if not b:
                return 0
            existing = (
                await db.execute(
                    select(func.max(AiKnowledgeChunkModel.chunk_index)).where(
                        AiKnowledgeChunkModel.knowledge_base_id == kb_id
                    )
                )
            ).scalar() or 0
            for i, (chunk, vec) in enumerate(zip(chunks, vectors, strict=False), start=existing + 1):
                db.add(
                    AiKnowledgeChunkModel(
                        knowledge_base_id=kb_id,
                        file_name=file_name,
                        chunk_index=i,
                        content=chunk,
                        meta={"source": "datasource", "file_name": file_name},
                        vector=vec,
                        dimension=len(vec) if vec else None,
                    )
                )
            b.chunk_count = (b.chunk_count or 0) + len(chunks)
        await cls._rebuild_graph(kb_id)
        return len(chunks)

    @classmethod
    async def _rebuild_graph(cls, kb_id: int) -> None:
        """重算知识库图谱（删除旧实体/关系后重建）。"""
        async with async_db_session.begin() as db:
            from sqlalchemy import delete as _delete

            await db.execute(
                _delete(AiKnowledgeEntityModel).where(
                    AiKnowledgeEntityModel.knowledge_base_id == kb_id
                )
            )
            await db.execute(
                _delete(AiKnowledgeRelationModel).where(
                    AiKnowledgeRelationModel.knowledge_base_id == kb_id
                )
            )
        try:
            await graphrag.build_graph(kb_id)
            await graphrag.age_sync_graph(kb_id)  # AGE 可用则同步图库
        except Exception:  # noqa: BLE001  图谱构建失败不影响主入库
            pass

    @classmethod
    async def rebuild_index(cls, kb_id: int) -> dict:
        """重建索引：重新向量化所有分块 + 重建图谱。"""
        async with async_db_session() as db:
            chunks = (
                (
                    await db.execute(
                        select(AiKnowledgeChunkModel).where(
                            AiKnowledgeChunkModel.knowledge_base_id == kb_id,
                            AiKnowledgeChunkModel.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )
        if not chunks:
            return {"chunks": 0}
        texts = [c.content for c in chunks]
        model_id = await cls._kb_model_id([kb_id])
        vecs = await embedding.embed_texts(texts, model_id=model_id)
        async with async_db_session.begin() as db:
            for c, v in zip(chunks, vecs, strict=False):
                row = await db.get(AiKnowledgeChunkModel, c.id)
                row.vector = v
                row.dimension = len(v) if v else None
        await cls._rebuild_graph(kb_id)
        return {"chunks": len(chunks)}


async def _probe_db(d: AiDatasourceModel) -> list[str]:
    """轻量探测数据库连通性（仅执行 SELECT 1）。"""
    from sqlalchemy import create_engine, text

    engine = create_engine(d.uri or "")
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return []


async def retrieve(knowledge_ids: list[int], query: str, top_k: int = 5, use_graph: bool = True) -> str:
    """供工作流引擎 / Agent 运行注入的检索上下文（拼接返回）。

    检索无结果时返回空串，调用方可跳过注入。开启 ``use_graph`` 时，
    额外用 GraphRAG 扩展实体邻居，把相关实体及其分块注入上下文。
    """
    if not knowledge_ids or not query:
        return ""
    parts: list[str] = []
    results = await AiKnowledgeService.search(knowledge_ids, query, top_k)
    for r in results:
        parts.append(f"[来源: {r.get('file_name') or '未知'}] {r.get('content')}")
    if use_graph:
        try:
            graph_hits = await graphrag.graph_retrieve(knowledge_ids, query, top_k)
            extra: list[str] = []
            for gh in graph_hits:
                for c in gh.get("chunks") or []:
                    extra.append(
                        f"[图谱实体: {gh.get('name')} · {c.get('file_name') or '未知'}] {c.get('content')}"
                    )
            for e in extra:
                if e not in parts:
                    parts.append(e)
        except Exception:  # noqa: BLE001
            pass
    return "\n\n".join(parts)
