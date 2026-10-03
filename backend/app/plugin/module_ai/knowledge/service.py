"""知识库 / 数据源 RAG 服务：分块、嵌入、入库、余弦检索、数据源同步。"""
from __future__ import annotations

import math

from sqlalchemy import func, select

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


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """按字符分块（带重叠），保证相邻块有上下文衔接。"""
    text = (text or "").strip()
    if not text:
        return []
    step = max(1, chunk_size - overlap)
    chunks: list[str] = []
    for i in range(0, len(text), step):
        piece = text[i : i + chunk_size].strip()
        if piece:
            chunks.append(piece)
    # 去掉被上一块重叠区域覆盖、内容过短的尾块，避免产生无意义碎片
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
        "created_time": b.created_time,
        "updated_time": b.updated_time,
    }


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
            return [_kb_to_dict(b) for b in rows]

    @classmethod
    async def get_base(cls, kb_id: int) -> dict | None:
        async with async_db_session() as db:
            b = await db.get(AiKnowledgeBaseModel, kb_id)
            if not b or b.is_deleted:
                return None
            return _kb_to_dict(b)

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
        async with async_db_session.begin() as db:
            for kid in ids:
                b = await db.get(AiKnowledgeBaseModel, kid)
                if not b:
                    continue
                await db.delete(b)
                # 级联删除分块
                chunks = (
                    await db.execute(
                        select(AiKnowledgeChunkModel).where(
                            AiKnowledgeChunkModel.knowledge_base_id == kid
                        )
                    )
                ).scalars().all()
                for c in chunks:
                    await db.delete(c)

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
        chunks = chunk_text(data.content, data.chunk_size, data.overlap)
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
    async def search(cls, kb_ids: list[int], query: str, top_k: int = 5, use_graph: bool = True) -> list[dict]:
        """在指定知识库内做余弦检索，返回 top_k 分块；可选并入 GraphRAG 实体扩展。"""
        if not kb_ids or not query:
            return []
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
        results = scored[:top_k]
        if use_graph:
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
                                }
                            )
                            seen.add(c["chunk_id"])
            except Exception:  # noqa: BLE001
                pass
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
            "nodes": [{"id": e.name, "name": e.name, "weight": e.weight or 1} for e in ents],
            "edges": [
                {"source": r.source, "target": r.target, "weight": r.weight or 1}
                for r in rels
            ],
        }

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
        except Exception:  # noqa: BLE001  图谱构建失败不影响主入库
            pass


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
