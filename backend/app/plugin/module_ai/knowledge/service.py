"""知识库 / 数据源 RAG 服务：分块、嵌入、入库、余弦检索、数据源同步。"""
from __future__ import annotations

import math
import re

from sqlalchemy import func, select, text

from app.core.database import async_db_session

from . import embedding, graphrag
from .model import (
    AiChunkAnnotationLogModel,
    AiDatasourceModel,
    AiKnowledgeBaseModel,
    AiKnowledgeChunkModel,
    AiKnowledgeDocumentModel,
    AiKnowledgeEntityChunkModel,
    AiKnowledgeEntityModel,
    AiKnowledgeRelationModel,
    AiRelationTypeTemplateModel,
    AiSearchLogModel,
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


def _annotation_text(annotations: list | None) -> str:
    """把分块标注文本拼成空白分隔字符串，用于检索。"""
    if not annotations:
        return ""
    parts = []
    for a in annotations:
        if isinstance(a, dict) and a.get("text"):
            parts.append(str(a["text"]))
    return " ".join(parts)


def _searchable_text(content: str, annotations: list | None) -> str:
    """检索用文本：正文 + 标注（提高换说法命中率）。"""
    t = (content or "").strip()
    at = _annotation_text(annotations)
    return (t + " " + at).strip()


# PostgreSQL：把分块标注（JSONB [{text,kind}]）拼成可检索文本的 SQL 表达式
_ANN_SQL = (
    "COALESCE((SELECT string_agg(a->>'text',' ') FROM "
    "jsonb_array_elements(coalesce(annotations,'[]'::jsonb)) a),'')"
)


def _grep_terms(query: str) -> list[str]:
    """把查询拆成检索词元：去标点、按空格/标点切分，保留中英文词与短语。"""
    parts = re.split(r"[\s,，。.．?？!！、；;:：\"'“”‘’|·—\-()（）\[\]]+", query or "")
    return [p.strip() for p in parts if p and p.strip()]


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
        "annotations": c.annotations or [],
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

    @classmethod
    async def count_knowledge_bases(cls) -> int:
        """未删除的知识库数量（控制台跨模块取数入口，不暴露模型）。"""
        async with async_db_session() as db:
            return int(
                (
                    await db.execute(
                        select(func.count())
                        .select_from(AiKnowledgeBaseModel)
                        .where(AiKnowledgeBaseModel.is_deleted.is_(False))
                    )
                ).scalar()
                or 0
            )

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

    @classmethod
    async def copy_kb(cls, kb_id: int, auth) -> dict:
        """复制知识库：新建副本并连同分块内容/向量/溯源一起复制（图谱另同步）。"""
        async with async_db_session.begin() as db:
            src = await db.get(AiKnowledgeBaseModel, kb_id)
            if not src or src.is_deleted:
                raise ValueError("知识库不存在")
            new = AiKnowledgeBaseModel(
                name=f"{src.name}（副本）",
                description=src.description,
                model_id=src.model_id,
                file_type=src.file_type,
                enabled=True,
                chunk_count=0,
                created_id=auth.user.id,
                updated_id=auth.user.id,
            )
            db.add(new)
            await db.flush()
            new_id = new.id
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
            copied = 0
            for c in chunks:
                db.add(
                    AiKnowledgeChunkModel(
                        knowledge_base_id=new_id,
                        file_name=c.file_name,
                        document_id=c.document_id,
                        start_line=c.start_line,
                        page=c.page,
                        chunk_index=c.chunk_index,
                        content=c.content,
                        annotations=c.annotations,
                        meta=c.meta,
                        vector=c.vector,
                        dimension=c.dimension,
                        created_id=auth.user.id,
                        updated_id=auth.user.id,
                    )
                )
                copied += 1
            new.chunk_count = copied
        await cls._rebuild_graph(new_id)
        return {"id": new_id, "name": new.name, "chunks": copied}

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
    async def kb_quality(cls, kb_id: int) -> dict:
        """知识库质量治理：文档数/分块数/分块嵌入率/文档状态 + 健康分 + 需重建标记。

        口径：`chunks` 与 `embedded_rate` 只统计**子块**（父块不生成向量，另计入
        `parents`），避免「父块拉低嵌入率」的假报警。
        """
        from sqlalchemy import func as _f
        from sqlalchemy import select as _sel

        from app.plugin.module_ai.knowledge.model import AiKnowledgeChunkModel

        from .model import AiKnowledgeDocumentModel

        chunk_filter = (
            AiKnowledgeChunkModel.knowledge_base_id == kb_id,
            AiKnowledgeChunkModel.is_deleted.is_(False),
            AiKnowledgeChunkModel.is_parent.is_not(True),
        )
        async with async_db_session() as db:
            docs = (
                await db.execute(
                    _sel(_f.count())
                    .select_from(AiKnowledgeDocumentModel)
                    .where(
                        AiKnowledgeDocumentModel.knowledge_base_id == kb_id,
                        AiKnowledgeDocumentModel.is_deleted.is_(False),
                    )
                )
            ).scalar() or 0
            chunks = (
                await db.execute(
                    _sel(_f.count()).select_from(AiKnowledgeChunkModel).where(*chunk_filter)
                )
            ).scalar() or 0
            parents = (
                await db.execute(
                    _sel(_f.count())
                    .select_from(AiKnowledgeChunkModel)
                    .where(
                        AiKnowledgeChunkModel.knowledge_base_id == kb_id,
                        AiKnowledgeChunkModel.is_deleted.is_(False),
                        AiKnowledgeChunkModel.is_parent.is_(True),
                    )
                )
            ).scalar() or 0
            embedded = (
                await db.execute(
                    _sel(_f.count())
                    .select_from(AiKnowledgeChunkModel)
                    .where(*chunk_filter, AiKnowledgeChunkModel.vector.isnot(None))
                )
            ).scalar() or 0
            status_rows = (
                await db.execute(
                    _sel(AiKnowledgeDocumentModel.doc_status, _f.count())
                    .where(
                        AiKnowledgeDocumentModel.knowledge_base_id == kb_id,
                        AiKnowledgeDocumentModel.is_deleted.is_(False),
                    )
                    .group_by(AiKnowledgeDocumentModel.doc_status)
                )
            ).all()
            stored_model = (
                await db.execute(
                    _sel(AiKnowledgeChunkModel.vector_model)
                    .where(
                        AiKnowledgeChunkModel.knowledge_base_id == kb_id,
                        AiKnowledgeChunkModel.is_deleted.is_(False),
                        AiKnowledgeChunkModel.vector_model.isnot(None),
                    )
                    .order_by(AiKnowledgeChunkModel.id.desc())
                    .limit(1)
                )
            ).scalar()

        current_model: str | None = None
        try:
            resolver = getattr(embedding, "current_model_name", None)
            if callable(resolver):
                current_model = await resolver(model_id=await cls._kb_model_id([kb_id]))
        except Exception:  # noqa: BLE001  解析失败不能拖垮质量接口
            current_model = None

        statuses = {r[0]: int(r[1]) for r in status_rows}
        embedded_rate = round(embedded / chunks, 4) if chunks else 0.0
        failed = int(statuses.get("failed", 0) or 0)
        score = 100.0
        if chunks == 0:
            score = 0.0
        elif embedded_rate < 0.5:
            score = 50.0
        elif failed and failed / max(docs, 1) > 0.2:
            score = 60.0
        needs_rebuild = bool(chunks) and (
            stored_model is None or current_model is None or stored_model != current_model
        )
        return {
            "kb_id": kb_id,
            "docs": docs,
            "chunks": chunks,
            "parents": parents,
            "embedded_rate": embedded_rate,
            "statuses": statuses,
            "score": score,
            "healthy": score >= 80,
            "needs_rebuild": needs_rebuild,
            "vector_model": stored_model,
        }

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

        # grep / 子串全文（WikiLLM 式）：拆词后任一命中即返回（简单问题兜底）
        if mode == "grep":
            try:
                terms = _grep_terms(query)
                if not terms:
                    terms = [query]
                conds = " OR ".join(
                    [f"(content ILIKE :t{i} OR {_ANN_SQL} ILIKE :t{i})" for i in range(len(terms))]
                )
                params: dict = {"ids": kb_ids, "k": top_k}
                for i, t in enumerate(terms):
                    params[f"t{i}"] = f"%{t}%"
                async with async_db_session() as db:
                    rows = (
                        await db.execute(
                            text(
                                "SELECT id, knowledge_base_id, file_name, document_id, start_line, page, content, 1.0 AS score "
                                "FROM ai_knowledge_chunks "
                                "WHERE knowledge_base_id = ANY(:ids) AND is_deleted = false "
                                f"AND ({conds}) "
                                "ORDER BY id LIMIT :k"
                            ),
                            params,
                        )
                    ).mappings().all()
                    for r in rows:
                        results.append(
                            {
                                "chunk_id": int(r["id"]),
                                "knowledge_base_id": int(r["knowledge_base_id"]),
                                "file_name": r["file_name"] or "",
                                "document_id": r["document_id"],
                                "start_line": r["start_line"],
                                "page": r["page"],
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
                                    "SELECT id, knowledge_base_id, file_name, document_id, start_line, page, content, "
                                    "ts_rank(to_tsvector('jiebacfg', content || ' ' || " + _ANN_SQL + "), plainto_tsquery('jiebacfg', :q)) AS score "
                                    "FROM ai_knowledge_chunks "
                                    "WHERE knowledge_base_id = ANY(:ids) AND is_deleted = false "
                                    "AND to_tsvector('jiebacfg', content || ' ' || " + _ANN_SQL + ") @@ plainto_tsquery('jiebacfg', :q) "
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
                                    "document_id": r["document_id"],
                                    "start_line": r["start_line"],
                                    "page": r["page"],
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
                                "SELECT id, knowledge_base_id, file_name, document_id, start_line, page, content, "
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
                                "document_id": r["document_id"],
                                "start_line": r["start_line"],
                                "page": r["page"],
                                "content": r["content"],
                                "score": round(float(r["score"] or 0), 4),
                                "engine": "pgvector",
                            }
                        )
            except Exception:  # noqa: BLE001
                vec_list = await cls._py_search_vector(kb_ids, query, top_k)
            if mode == "vector":
                return vec_list[:top_k]

        # hybrid：向量 + 全文 RRF 融合（各引擎按排名倒数加权，鲁棒且不惩罚缺失引擎）
        if mode == "hybrid":
            results = cls._fuse_rrf(vec_list, ft_list)
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
    def _fuse_rrf(
        cls,
        vec_list: list[dict],
        ft_list: list[dict],
        k: int = 60,
    ) -> list[dict]:
        """RRF（Reciprocal Rank Fusion）：多引擎按排名倒数融合。

        分数 = Σ 1/(k + rank)，不依赖各引擎分数尺度，也不因某引擎缺失而
        惩罚命中项；比加权归一化更鲁棒，是主流混合检索的标准融合法。
        """
        scores: dict[int, float] = {}
        info: dict[int, dict] = {}
        for lst in (vec_list, ft_list):
            for rank, it in enumerate(lst, start=1):
                cid = it["chunk_id"]
                scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
                info.setdefault(cid, it)
        fused = [
            {**info[cid], "engine": "hybrid", "score": round(s, 4)}
            for cid, s in scores.items()
        ]
        fused.sort(key=lambda x: x["score"], reverse=True)
        return fused

    @classmethod
    async def _ensure_vector_col(cls, db, dim: int | None = None) -> None:
        """惰性：为 chunk 表加 pgvector embedding 列 + HNSW 索引（幂等，异常忽略）。

        dim 超过 2000 时 HNSW 无法建索引，退化为顺序扫描（用小库可接受）。
        """
        from . import embedding as _emb

        dim = dim or _emb.EMBED_DIM
        try:
            await db.execute(
                text(
                    f"ALTER TABLE ai_knowledge_chunks "
                    f"ADD COLUMN IF NOT EXISTS embedding vector({dim})"
                )
            )
            if dim <= 2000:
                await db.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS idx_chunk_embedding "
                        "ON ai_knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
                    )
                )
            # 从现有 JSONB vector 迁移一次（<=dim 维才填，避免缩小）
            await db.execute(
                text(
                    "UPDATE ai_knowledge_chunks SET embedding = vector(v.vec::text) "
                    "FROM (SELECT id, vector AS vec FROM ai_knowledge_chunks "
                    "      WHERE vector IS NOT NULL AND embedding IS NULL) v "
                    "WHERE ai_knowledge_chunks.id = v.id AND "
                    f"      jsonb_array_length(v.vec::jsonb) BETWEEN 1 AND {dim}"
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
                if query in _searchable_text(c.content, c.annotations):
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
                if query in _searchable_text(c.content, c.annotations):
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
        """返回知识库图谱（实体 + 关系 + 绑定分块数），供前端可视化。"""
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
        # 实体绑定分块数（图谱节点显示关联度）
        chunk_count: dict[int, int] = {}
        if ents:
            from sqlalchemy import func as _func

            async with async_db_session() as db:
                rows = (
                    await db.execute(
                        select(
                            AiKnowledgeEntityChunkModel.entity_id, _func.count()
                        )
                        .where(
                            AiKnowledgeEntityChunkModel.is_deleted.is_(False),
                            AiKnowledgeEntityChunkModel.entity_id.in_([e.id for e in ents]),
                        )
                        .group_by(AiKnowledgeEntityChunkModel.entity_id)
                    )
                ).all()
            chunk_count = {r[0]: int(r[1]) for r in rows}
        return {
            "nodes": [
                {
                    "id": e.id,
                    "name": e.name,
                    "etype": e.etype or "keyword",
                    "weight": e.weight or 1,
                    "description": e.description or "",
                    "chunk_count": chunk_count.get(e.id, 0),
                    "x": (e.layout or {}).get("x"),
                    "y": (e.layout or {}).get("y"),
                }
                for e in ents
            ],
            "edges": [
                {
                    "id": r.id,
                    "source": r.source,
                    "target": r.target,
                    "weight": r.weight or 1,
                    "rtype": r.rtype or "related",
                }
                for r in rels
            ],
        }

    # ---------- 图谱编辑（实体 / 关系 CRUD + AGE 同步） ----------
    @classmethod
    async def create_graph_entity(cls, kb_id: int, data) -> dict:
        async with async_db_session.begin() as db:
            e = AiKnowledgeEntityModel(
                knowledge_base_id=kb_id, name=data.name, etype=data.etype or "keyword",
                weight=data.weight or 1, description=data.description or "",
            )
            db.add(e)
            await db.flush()
            eid = e.id
        await graphrag.age_sync_graph(kb_id)
        return {"id": eid, "name": data.name, "etype": data.etype or "keyword",
                "weight": data.weight or 1, "description": data.description or ""}

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
            if data.description is not None:
                e.description = data.description
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
        return {
            "id": e.id, "name": e.name, "etype": e.etype or "keyword",
            "weight": e.weight or 1, "description": e.description or "",
        }

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
                weight=data.weight or 1, rtype=data.rtype or "related",
            )
            db.add(r)
            await db.flush()
            rid = r.id
        await graphrag.age_sync_graph(kb_id)
        return {"id": rid, "source": data.source, "target": data.target,
                "weight": data.weight or 1, "rtype": data.rtype or "related"}

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

    # ---------- 分块标注（提升换说法召回命中） ----------
    @classmethod
    async def add_chunk_annotation(
        cls, kb_id: int, chunk_id: int, text: str, kind: str = "alias",
        query: str | None = None, source: str = "manual", user_id: int | None = None,
    ) -> dict:
        """给分块加一条标注，并用正文+标注重新向量化该分块（标注即刻生效于检索）。"""
        async with async_db_session.begin() as db:
            c = await db.get(AiKnowledgeChunkModel, chunk_id)
            if not c or c.knowledge_base_id != kb_id:
                raise ValueError("分块不存在")
            anns = list(c.annotations or [])
            anns.append({"text": text, "kind": kind})
            c.annotations = anns
            model_id = await cls._kb_model_id([kb_id])
            vec = (await embedding.embed_texts([_searchable_text(c.content, anns)], model_id=model_id))[0]
            c.vector = vec
            c.dimension = len(vec) if vec else None
            c.meta = {**(c.meta or {}), "vector_annotated": True}
            db.add(
                AiChunkAnnotationLogModel(
                    knowledge_base_id=kb_id, chunk_id=chunk_id, action="add",
                    text=text, kind=kind, query=query, source=source, user_id=user_id,
                )
            )
        # 标注关键词自动纳入图谱实体并绑定分块
        try:
            await graphrag.sync_annotation_entities(kb_id, chunk_id, [text])
        except Exception:  # noqa: BLE001
            pass
        return {"chunk_id": chunk_id, "annotations": anns}

    @classmethod
    async def remove_chunk_annotation(
        cls, kb_id: int, chunk_id: int, index: int,
        query: str | None = None, source: str = "manual", user_id: int | None = None,
    ) -> dict:
        """删除分块第 index 条标注，并重算向量。"""
        text_removed = ""
        async with async_db_session.begin() as db:
            c = await db.get(AiKnowledgeChunkModel, chunk_id)
            if not c or c.knowledge_base_id != kb_id:
                raise ValueError("分块不存在")
            anns = list(c.annotations or [])
            if index < 0 or index >= len(anns):
                raise ValueError("标注不存在")
            text_removed = anns.pop(index).get("text", "")
            c.annotations = anns
            model_id = await cls._kb_model_id([kb_id])
            vec = (await embedding.embed_texts([_searchable_text(c.content, anns)], model_id=model_id))[0]
            c.vector = vec
            c.dimension = len(vec) if vec else None
            db.add(
                AiChunkAnnotationLogModel(
                    knowledge_base_id=kb_id, chunk_id=chunk_id, action="remove",
                    text=text_removed, kind="", query=query, source=source, user_id=user_id,
                )
            )
        return {"chunk_id": chunk_id, "annotations": anns}

    @classmethod
    async def list_annotation_logs(cls, kb_id: int, limit: int = 50) -> list[dict]:
        """标注台账：按时间倒序返回标注增删历史。"""
        async with async_db_session() as db:
            rows = (
                (
                    await db.execute(
                        select(AiChunkAnnotationLogModel)
                        .where(AiChunkAnnotationLogModel.knowledge_base_id == kb_id)
                        .order_by(AiChunkAnnotationLogModel.id.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
        return [
            {
                "id": r.id,
                "chunk_id": r.chunk_id,
                "action": r.action,
                "text": r.text,
                "kind": r.kind or "alias",
                "query": r.query,
                "source": r.source or "manual",
                "user_id": r.user_id,
                "created_time": r.created_time,
            }
            for r in rows
        ]

    # ---------- 文档管理（wikiLLM / ima 式） ----------
    @staticmethod
    def _extract_doc(filename: str, data: bytes) -> tuple[str, list[int]]:
        """按扩展名提取全文，返回 ``(文本, 每页起始字符偏移)``。

        页码偏移用于引用溯源：把分块定位到原文档的某一页。
        非 PDF 返回 ``[0]``（视为单页，行号仍精确）。
        """
        lower = (filename or "").lower()
        ext = lower.rsplit(".", 1)[-1] if "." in lower else "txt"
        if ext in ("txt", "md", "csv", "json", "log"):
            try:
                return data.decode("utf-8", errors="ignore"), [0]
            except Exception:  # noqa: BLE001
                return data.decode("gbk", errors="ignore"), [0]
        if ext == "docx":
            import io

            from docx import Document

            doc = Document(io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs)
            return text, [0]
        if ext == "pdf":
            import io

            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            parts: list[str] = []
            offsets: list[int] = []
            acc = 0
            for page in reader.pages:
                offsets.append(acc)
                t = page.extract_text() or ""
                parts.append(t)
                acc += len(t) + 1
            return "\n".join(parts), offsets
        # 未知类型退回当作 utf-8 文本
        return data.decode("utf-8", errors="ignore"), [0]

    @staticmethod
    def _chunk_spans(
        text: str, chunks: list[str], page_offsets: list[int] | None = None,
    ) -> tuple[list[int | None], list[int | None]]:
        """根据分块内容在原文中的位置，计算每块的 ``(起始行, 页码)``。

        用 ``text.find`` 定位每块首次出现的起始字符；行号为前缀换行数 +1，
        页码由 ``page_offsets`` 二分确定（默认视为单页）。
        """
        import bisect

        offsets = page_offsets or [0]
        lines: list[int | None] = []
        pages: list[int | None] = []
        pos = 0
        for ch in chunks:
            idx = text.find(ch, pos if pos < len(text) else 0)
            if idx < 0:
                idx = 0
            pos = idx
            lines.append(text[:idx].count("\n") + 1)
            pages.append(bisect.bisect_right(offsets, idx) - 1 if idx >= 0 else 1)
        return lines, pages

    @classmethod
    async def upload_document(
        cls, kb_id: int, filename: str, data: bytes, auth,
        chunk_size: int = 500, overlap: int = 50, strategy: str = "fixed",
    ) -> dict:
        """上传文档→提取全文→分块向量化→入库。"""
        text, page_offsets = cls._extract_doc(filename, data)
        if not text.strip():
            raise ValueError("文档无有效文本")
        ext = (filename or "").lower().rsplit(".", 1)[-1] if "." in (filename or "") else "txt"
        async with async_db_session.begin() as db:
            doc = AiKnowledgeDocumentModel(
                knowledge_base_id=kb_id,
                name=filename or "文档",
                file_type=ext,
                size=len(data),
                content=text,
                doc_status="ready",
            )
            db.add(doc)
            await db.flush()
            doc_id = doc.id
            doc.object_key = await cls._upload_to_rustfs(kb_id, filename or "文档", data)
        # 计算每块的起始行/页码，用于引用溯源
        chunks = chunk_text(text, chunk_size, overlap, strategy)
        start_lines, pages = cls._chunk_spans(text, chunks, page_offsets)
        # 分块向量化入库
        result = await cls.ingest_text(
            kb_id, text, file_name=filename or "文档", auth=auth,
            chunk_size=chunk_size, overlap=overlap, strategy=strategy,
            document_id=doc_id, start_lines=start_lines, pages=pages,
        )
        async with async_db_session.begin() as db:
            d = await db.get(AiKnowledgeDocumentModel, doc_id)
            d.chunk_count = result.get("chunks", 0)
        return {"id": doc_id, "name": filename or "文档", "chunks": result.get("chunks", 0)}

    @staticmethod
    async def _upload_to_rustfs(kb_id: int, filename: str, data: bytes) -> str | None:
        """文档原始文件上传到 RustFS（S3 兼容），返回 object_key。"""
        try:
            import asyncio
            import io
            import uuid

            from app.utils.s3_client import s3_client

            ext = (filename or "doc").rsplit(".", 1)[-1] if "." in (filename or "") else "txt"
            object_key = f"knowledge/{kb_id}/documents/{uuid.uuid4().hex}.{ext}"
            await asyncio.to_thread(
                s3_client.upload_fileobj, io.BytesIO(data), object_key,
            )
            return object_key
        except Exception:  # noqa: BLE001
            return None

    @classmethod
    async def download_document(cls, kb_id: int, doc_id: int) -> dict:
        async with async_db_session() as db:
            d = await db.get(AiKnowledgeDocumentModel, doc_id)
            if not d or d.knowledge_base_id != kb_id or d.is_deleted:
                raise ValueError("文档不存在")
            ok = d.object_key
            name = d.name or "文档"
            file_type = d.file_type or "txt"
        if not ok:
            raise ValueError("文档无原始文件（RustFS）")
        return {"object_key": ok, "name": name, "file_type": file_type}

    @classmethod
    async def export_faq(cls, kb_id: int) -> dict:
        """导出 FAQ：从知识库分块生成问答对（问题=内容前若干字/关键词，答案=内容）。"""
        from app.plugin.module_ai.knowledge.graphrag import extract_keywords

        async with async_db_session() as db:
            rows = (
                (
                    await db.execute(
                        select(AiKnowledgeChunkModel).where(
                            AiKnowledgeChunkModel.knowledge_base_id == kb_id,
                            AiKnowledgeChunkModel.is_deleted.is_(False),
                        ).order_by(AiKnowledgeChunkModel.chunk_index)
                    )
                )
                .scalars()
                .all()
            )
        items = []
        for c in rows:
            kws = extract_keywords(c.content, topk=8)
            q = "；".join(kws[:6]) if kws else (c.content[:30] if c.content else "")
            items.append({
                "id": c.id,
                "file": c.file_name or "",
                "question": q or "知识条目",
                "answer": c.content,
                "keywords": kws[:6],
            })
        return {"count": len(items), "items": items}

    @classmethod
    async def list_documents(cls, kb_id: int) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                (
                    await db.execute(
                        select(AiKnowledgeDocumentModel)
                        .where(
                            AiKnowledgeDocumentModel.knowledge_base_id == kb_id,
                            AiKnowledgeDocumentModel.is_deleted.is_(False),
                        )
                        .order_by(AiKnowledgeDocumentModel.id.desc())
                    )
                )
                .scalars()
                .all()
            )
        return [
            {
                "id": d.id,
                "name": d.name,
                "file_type": d.file_type or "txt",
                "size": d.size or 0,
                "chunk_count": d.chunk_count or 0,
                "status": d.doc_status or "ready",
                "created_time": d.created_time,
                "rustfs_url": (
                    AiKnowledgeService._presigned(d.object_key) if d.object_key else None
                ),
            }
            for d in rows
        ]

    @staticmethod
    def _presigned(object_key: str) -> str | None:
        """生成 RustFS 预签名下载链接。"""
        try:
            from app.utils.s3_client import s3_client

            return s3_client.presigned_url(object_key)
        except Exception:  # noqa: BLE001
            return None

    @classmethod
    async def delete_document(cls, kb_id: int, doc_id: int) -> None:
        import asyncio

        from app.utils.s3_client import s3_client

        async with async_db_session.begin() as db:
            d = await db.get(AiKnowledgeDocumentModel, doc_id)
            if d and d.knowledge_base_id == kb_id:
                ok = d.object_key
                await db.delete(d)
        if ok:
            try:
                await asyncio.to_thread(s3_client.delete_object, ok)
            except Exception:  # noqa: BLE001
                pass

    @classmethod
    async def get_document_content(cls, kb_id: int, doc_id: int) -> dict:
        async with async_db_session() as db:
            d = await db.get(AiKnowledgeDocumentModel, doc_id)
            if not d or d.knowledge_base_id != kb_id or d.is_deleted:
                raise ValueError("文档不存在")
            return {"id": d.id, "name": d.name, "content": d.content or ""}

    @classmethod
    async def reparse_document(cls, kb_id: int, doc_id: int, auth) -> dict:
        """重新解析文档：基于全文重建分块向量化与图谱。"""
        async with async_db_session() as db:
            d = await db.get(AiKnowledgeDocumentModel, doc_id)
            if not d or d.knowledge_base_id != kb_id or d.is_deleted:
                raise ValueError("文档不存在")
            text = d.content or ""
        if not text.strip():
            raise ValueError("文档无有效文本")
        result = await cls.ingest_text(
            kb_id, text, file_name=d.name or "文档", auth=auth,
        )
        async with async_db_session.begin() as db:
            dd = await db.get(AiKnowledgeDocumentModel, doc_id)
            dd.chunk_count = result.get("chunks", 0)
        return {"id": doc_id, "chunks": result.get("chunks", 0)}

    @classmethod
    async def ingest_text(
        cls, kb_id: int, text: str, file_name: str, auth,
        chunk_size: int = 500, overlap: int = 50, strategy: str = "fixed",
        document_id: int | None = None,
        start_lines: list[int] | None = None,
        pages: list[int] | None = None,
    ) -> dict:
        """文本→分块→向量化→入库（文档复用）。支持引用溯源字段。"""
        chunks = chunk_text(text, chunk_size, overlap, strategy)
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
                        file_name=file_name,
                        document_id=document_id,
                        start_line=(start_lines[i - existing - 1] if start_lines and i - existing - 1 < len(start_lines) else None),
                        page=(pages[i - existing - 1] if pages and i - existing - 1 < len(pages) else None),
                        chunk_index=i,
                        content=chunk,
                        meta={"file_name": file_name},
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
    async def ask(cls, kb_id: int, query: str, top_k: int = 6, auth=None, mode: str = "hybrid") -> dict:
        """引用溯源问答：检索→组装带编号的上下文→LLM 生成→返回引用列表。

        ``references`` 每项含 文件/文档ID/起始行/页码/RustFS 链接，供前端
        渲染「角标→弹窗看行页→末尾原文档链接」。
        """
        hits = await cls.search([kb_id], query, top_k=top_k, use_graph=True, mode=mode)
        if not hits:
            # 兜底：混合检索为空时回退子串 grep（简单/口语化问题也能命中）
            hits = await cls.search([kb_id], query, top_k=top_k, use_graph=False, mode="grep")
        if not hits:
            return {"answer": "未检索到相关知识，请换个问法或上传更多文档。", "references": []}
        # 取文档表 + 上下文扩展（父块/相邻片段回填），生成 RustFS 原文档链接
        async with async_db_session() as db:
            doc_ids = {h.get("document_id") for h in hits if h.get("document_id")}
            docs: dict[int, AiKnowledgeDocumentModel] = {}
            if doc_ids:
                rows = (
                    await db.execute(
                        select(AiKnowledgeDocumentModel).where(
                            AiKnowledgeDocumentModel.id.in_(list(doc_ids))
                        )
                    )
                ).scalars().all()
                docs = {d.id: d for d in rows}
            refs: list[dict] = []
            context_parts: list[str] = []
            for i, h in enumerate(hits, start=1):
                did = h.get("document_id")
                doc = docs.get(did) if did else None
                rust = cls._presigned(doc.object_key) if doc and doc.object_key else None
                # 父块回填：拉取同文档相邻 chunk 作为该引用的完整上下文（检索小块、回答用大块）
                ext_ctx = h["content"]
                if did:
                    try:
                        cur = (
                            await db.execute(
                                select(AiKnowledgeChunkModel).where(
                                    AiKnowledgeChunkModel.id == h["chunk_id"]
                                )
                            )
                        ).scalar_one_or_none()
                        if cur is not None:
                            nb = (
                                await db.execute(
                                    select(AiKnowledgeChunkModel.content)
                                    .where(
                                        AiKnowledgeChunkModel.document_id == did,
                                        AiKnowledgeChunkModel.is_deleted.is_(False),
                                        AiKnowledgeChunkModel.chunk_index.between(
                                            (cur.chunk_index or 1) - 1,
                                            (cur.chunk_index or 1) + 1,
                                        ),
                                    )
                                    .order_by(AiKnowledgeChunkModel.chunk_index)
                                )
                            ).scalars().all()
                            if nb:
                                ext_ctx = "\n\n".join(nb)
                    except Exception:  # noqa: BLE001
                        ext_ctx = h["content"]
                refs.append(
                    {
                        "index": i,
                        "chunk_id": h["chunk_id"],
                        "file": h.get("file_name") or (doc.name if doc else "未知"),
                        "document_id": did,
                        "start_line": h.get("start_line"),
                        "page": h.get("page"),
                        "content": h["content"],
                        "context": ext_ctx,
                        "rustfs_url": rust,
                    }
                )
                context_parts.append(f"[{i}] {ext_ctx}")
        answer = await cls._generate_answer(kb_id, query, context_parts, refs)
        return {"answer": answer, "references": refs}

    @classmethod
    async def _generate_answer(cls, kb_id: int, query: str, context_parts: list[str], refs: list[dict]) -> str:
        """用知识库配置的模型生成带引用编号的回答；不可用时回退为引用式摘要。

        回退答案同样在文本中保留 ``[n]`` 编号，前端统一渲染成可点击角标。
        """
        # 先尝试 LLM（Agno Agent 单发生成；不注入工具，仅按系统提示生成带引用编号的回答）
        try:
            from app.plugin.module_ai.agno_tools.agent_factory import build_agent
            from app.plugin.module_ai.models.service import AiModelService

            runtime = await AiModelService.get_runtime_model(usage="chat")
            if runtime:
                system = (
                    "你是知识库问答助手。请仅依据提供的参考资料回答问题；"
                    "引用资料时在对应句子后用[n]标注来源编号，n 与资料编号一致；"
                    "若资料不足则明确说明，不要编造。用中文回答。"
                )
                user = f"问题：{query}\n\n参考资料：\n" + "\n\n".join(context_parts)
                agent = build_agent(
                    model_config=runtime, instructions=[system], tools=[]
                )
                resp = await agent.arun(user, stream=False)
                ans = (
                    resp.get_content_as_string()
                    if hasattr(resp, "get_content_as_string")
                    else str(resp.content or "")
                ).strip()
                if ans:
                    return ans
        except Exception:  # noqa: BLE001
            pass
        # 回退：引用式摘要（保留 [n] 编号供前端渲染角标）
        lines = [f"根据知识库检索到与「{query}」相关的以下资料（点击引用可查看来源位置）："]
        for r in refs:
            loc = ""
            if r.get("page"):
                loc += f"第{r['page']}页"
            if r.get("start_line"):
                loc += (f"，第{r['start_line']}行" if loc else f"第{r['start_line']}行")
            lines.append(
                f"[{r['index']}] 《{r['file']}》{('（' + loc + '）') if loc else ''}"
            )
            lines.append((r["content"] or "").strip()[:400])
        return "\n\n".join(lines)

    @classmethod
    async def suggest_annotate(cls, kb_id: int, query: str, top_n: int = 5) -> list[dict]:
        """检索失败标注引导：向量召回与查询相关但未被全文命中的分块，建议用户标注。"""
        if not query:
            return []
        # 向量召回（含标注）
        try:
            vec = await cls._pg_search([kb_id], query, top_n, False, "vector")
        except Exception:  # noqa: BLE001
            vec = []
        # 全文命中的分块 id
        try:
            ft = await cls._pg_search([kb_id], query, top_n * 3, False, "fulltext")
        except Exception:  # noqa: BLE001
            ft = []
        ft_ids = {r["chunk_id"] for r in ft}
        out = []
        for v in vec:
            out.append(
                {
                    "chunk_id": v["chunk_id"],
                    "file_name": v["file_name"],
                    "content": v["content"],
                    "similarity": v["score"],
                    "hit": v["chunk_id"] in ft_ids,
                }
            )
        return out

    @classmethod
    async def log_search(
        cls, kb_id: int, query: str, mode: str, top_k: int,
        results: list[dict], user_id: int | None = None,
    ) -> None:
        """记录一次检索（供检索趋势统计）。"""
        try:

            async with async_db_session() as db:
                engines = list(
                    dict.fromkeys(r.get("engine") for r in results if r.get("engine"))
                )
                db.add(
                    AiSearchLogModel(
                        knowledge_base_id=kb_id, query=query, mode=mode,
                        top_k=top_k, hit_count=len(results), engines=engines,
                        user_id=user_id,
                    )
                )
                await db.commit()
        except Exception:  # noqa: BLE001  检索日志失败不影响主流程
            pass

    @classmethod
    async def search_stats(cls, kb_id: int, days: int = 30) -> dict:
        """知识库检索统计：总量/命中率/平均命中/引擎分布/近 N 天趋势。"""
        from sqlalchemy import func as _func

        async with async_db_session() as db:
            total = (
                await db.execute(
                    select(_func.count()).where(
                        AiSearchLogModel.knowledge_base_id == kb_id
                    )
                )
            ).scalar() or 0
            hits = (
                await db.execute(
                    select(_func.sum(AiSearchLogModel.hit_count)).where(
                        AiSearchLogModel.knowledge_base_id == kb_id
                    )
                )
            ).scalar() or 0
            zero_hits = (
                await db.execute(
                    select(_func.count()).where(
                        AiSearchLogModel.knowledge_base_id == kb_id,
                        AiSearchLogModel.hit_count == 0,
                    )
                )
            ).scalar() or 0
            # 引擎分布
            en_rows = (
                await db.execute(
                    select(AiSearchLogModel.engines, _func.count()).where(
                        AiSearchLogModel.knowledge_base_id == kb_id
                    ).group_by(AiSearchLogModel.engines)
                )
            ).all()
            engine_dist: dict[str, int] = {}
            for eng, cnt in en_rows:
                for e in (eng or []):
                    engine_dist[e] = engine_dist.get(e, 0) + int(cnt)
            # 按天趋势
            day_rows = (
                await db.execute(
                    select(
                        _func.date(AiSearchLogModel.created_time).label("d"),
                        _func.count().label("n"),
                        _func.sum(AiSearchLogModel.hit_count).label("hits"),
                    )
                    .where(
                        AiSearchLogModel.knowledge_base_id == kb_id,
                        AiSearchLogModel.created_time >= _func.now() - _func.make_interval(0, 0, 0, 0, 0, 0, days),
                    )
                    .group_by("d")
                    .order_by("d")
                )
            ).all()
        avg_hits = round(int(hits) / int(total), 2) if total else 0
        return {
            "total": int(total),
            "hit_count": int(hits),
            "zero_hit_count": int(zero_hits),
            "avg_hits": avg_hits,
            "hit_rate": round(1 - (int(zero_hits) / int(total)), 2) if total else 0,
            "engine_dist": engine_dist,
            "trend": [
                {"date": str(r[0]), "count": int(r[1]), "hits": int(r[2] or 0)}
                for r in day_rows
            ],
        }

    @classmethod
    async def bind_entity_chunks(cls, kb_id: int, entity_id: int, chunk_ids: list[int]) -> dict:
        """把若干分块绑定到实体（图谱检索命中实体可回溯分块）。"""
        imported = 0
        async with async_db_session.begin() as db:
            ent = await db.get(AiKnowledgeEntityModel, entity_id)
            if not ent or ent.is_deleted or ent.knowledge_base_id != kb_id:
                raise ValueError("实体不存在")
            for cid in chunk_ids:
                exists = (
                    await db.execute(
                        select(AiKnowledgeEntityChunkModel).where(
                            AiKnowledgeEntityChunkModel.entity_id == entity_id,
                            AiKnowledgeEntityChunkModel.chunk_id == cid,
                            AiKnowledgeEntityChunkModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if exists:
                    continue
                db.add(AiKnowledgeEntityChunkModel(entity_id=entity_id, chunk_id=cid))
                imported += 1
        return {"entity_id": entity_id, "imported": imported}

    @classmethod
    async def unbind_entity_chunks(cls, kb_id: int, entity_id: int, chunk_ids: list[int]) -> dict:
        """解除实体与若干分块的绑定。"""
        removed = 0
        async with async_db_session.begin() as db:
            ent = await db.get(AiKnowledgeEntityModel, entity_id)
            if not ent or ent.is_deleted or ent.knowledge_base_id != kb_id:
                raise ValueError("实体不存在")
            rows = (
                await db.execute(
                    select(AiKnowledgeEntityChunkModel).where(
                        AiKnowledgeEntityChunkModel.entity_id == entity_id,
                        AiKnowledgeEntityChunkModel.chunk_id.in_(chunk_ids),
                        AiKnowledgeEntityChunkModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            for r in rows:
                await db.delete(r)
                removed += 1
        return {"entity_id": entity_id, "removed": removed}

    @classmethod
    async def get_entity_chunks(cls, kb_id: int, entity_id: int) -> list[dict]:
        """返回实体绑定的分块。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiKnowledgeEntityChunkModel).where(
                        AiKnowledgeEntityChunkModel.entity_id == entity_id,
                        AiKnowledgeEntityChunkModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            chunk_ids = [r.chunk_id for r in rows]
            if not chunk_ids:
                return []
            chunks = (
                (
                    await db.execute(
                        select(AiKnowledgeChunkModel).where(
                            AiKnowledgeChunkModel.id.in_(chunk_ids),
                            AiKnowledgeChunkModel.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return [_chunk_to_dict(c) for c in chunks]

    @classmethod
    async def get_chunk_entities(cls, kb_id: int, chunk_id: int) -> list[dict]:
        """返回绑定到某分块的实体。"""
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiKnowledgeEntityChunkModel).where(
                        AiKnowledgeEntityChunkModel.chunk_id == chunk_id,
                        AiKnowledgeEntityChunkModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            ent_ids = [r.entity_id for r in rows]
            if not ent_ids:
                return []
            ents = (
                (
                    await db.execute(
                        select(AiKnowledgeEntityModel).where(
                            AiKnowledgeEntityModel.id.in_(ent_ids),
                            AiKnowledgeEntityModel.is_deleted.is_(False),
                        )
                    )
                )
                .scalars()
                .all()
            )
        return [{"id": e.id, "name": e.name, "etype": e.etype or "keyword"} for e in ents]

    # ---------- 图谱关系编辑 ----------
    @classmethod
    async def update_graph_relation(cls, kb_id: int, rel_id: int, data) -> dict | None:
        async with async_db_session.begin() as db:
            r = await db.get(AiKnowledgeRelationModel, rel_id)
            if not r or r.is_deleted or r.knowledge_base_id != kb_id:
                return None
            if data.source:
                r.source = data.source
            if data.target:
                r.target = data.target
            if data.weight:
                r.weight = data.weight
            if data.rtype is not None:
                r.rtype = data.rtype
        await graphrag.age_sync_graph(kb_id)
        return {"id": r.id, "source": r.source, "target": r.target,
                "weight": r.weight or 1, "rtype": r.rtype or "related"}

    @classmethod
    async def save_graph_layout(cls, kb_id: int, items: list) -> int:
        """保存图谱布局（节点坐标记忆）。"""
        saved = 0
        async with async_db_session.begin() as db:
            for it in items:
                e = await db.get(AiKnowledgeEntityModel, it.id)
                if not e or e.is_deleted or e.knowledge_base_id != kb_id:
                    continue
                e.layout = {"x": it.x, "y": it.y}
                saved += 1
        return saved

    @classmethod
    async def clear_graph_layout(cls, kb_id: int) -> int:
        """清除全部节点布局记忆（回到自动力导向）。"""
        cleared = 0
        async with async_db_session.begin() as db:
            es = (
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
            for e in es:
                e.layout = None
                cleared += 1
        return cleared

    # ---------- 关系类型模板 ----------
    @classmethod
    async def list_relation_types(cls) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                (
                    await db.execute(
                        select(AiRelationTypeTemplateModel)
                        .where(AiRelationTypeTemplateModel.is_deleted.is_(False))
                        .order_by(AiRelationTypeTemplateModel.id)
                    )
                )
                .scalars()
                .all()
            )
        return [{"id": r.id, "name": r.name, "color": r.color or "#a0a6ad"} for r in rows]

    @classmethod
    async def create_relation_type(cls, name: str, color: str | None = None) -> dict:
        async with async_db_session.begin() as db:
            exists = (
                await db.execute(
                    select(AiRelationTypeTemplateModel).where(
                        AiRelationTypeTemplateModel.name == name,
                        AiRelationTypeTemplateModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if exists:
                raise ValueError("关系类型已存在")
            r = AiRelationTypeTemplateModel(name=name, color=color or "#a0a6ad")
            db.add(r)
            await db.flush()
        return {"id": r.id, "name": r.name, "color": r.color or "#a0a6ad"}

    @classmethod
    async def delete_relation_type(cls, rid: int) -> None:
        async with async_db_session.begin() as db:
            r = await db.get(AiRelationTypeTemplateModel, rid)
            if r:
                await db.delete(r)

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

            # 先删除实体-分块绑定（外键依赖实体），避免 FK 冲突
            ent_ids = select(AiKnowledgeEntityModel.id).where(
                AiKnowledgeEntityModel.knowledge_base_id == kb_id
            )
            await db.execute(
                _delete(AiKnowledgeEntityChunkModel).where(
                    AiKnowledgeEntityChunkModel.entity_id.in_(ent_ids)
                )
            )
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
