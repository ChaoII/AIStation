"""向量检索/写入的 agno 原生实现（agno.vectordb.pgvector.PgVector）。

遵循 AGENTS.md「AI 调用一律走 agno、能用成熟库不手撸」：

- **生产主路径**：agno PgVector（``ai_kb_vectors`` 原生表：content / meta_data / embedding，
  schema 与 HNSW 索引由 agno 自管）；Embedder 复用 ``embeddings.dims.resolve_embedder``
  （平台网关的 embedding 模型）→ ``OpenAILikeEmbedder``；
- **降级保留**：旧实现（pgvector SQL 近邻 / Python 手算余弦）仅在非 PG 环境、agno 不可用
  或连接失败时回退（SQLite 测试环境天然走回退，不影响既有 pytest）；
- 存量数据迁移：点一次「重建索引」即可（入库链路已双写）。
"""
from __future__ import annotations

import asyncio
import os
from hashlib import md5
from typing import Any

from app.core.logger import log

#: agno 自管的向量表
TABLE = "ai_kb_vectors"

#: 进程内单例（构建失败不缓存，下次重试）
_DB: Any = None


def _is_postgres() -> bool:
    return (os.getenv("DATABASE_TYPE") or "postgresql").lower() in ("postgres", "postgresql")


async def _vectordb():
    """惰性构建 agno PgVector；非 PG / 构建失败返回 None（调用方回退旧实现）。"""
    global _DB
    if _DB is not None:
        return _DB
    if not _is_postgres():
        return None
    try:
        from agno.knowledge.embedder.openai_like import OpenAILikeEmbedder
        from agno.vectordb.pgvector import PgVector
        from agno.vectordb.search import SearchType
        from openai import AsyncOpenAI

        from app.config.setting import settings

        from ..embeddings.dims import get_dimension, resolve_embedder

        resolved = await resolve_embedder()
        dim = await get_dimension()
        client = AsyncOpenAI(
            base_url=resolved.base_url,
            api_key=resolved.api_key,
            default_headers=resolved.headers or None,
            timeout=resolved.timeout,
            max_retries=2,
        )
        embedder = OpenAILikeEmbedder(id=resolved.model, async_client=client, dimensions=int(dim))
        _DB = PgVector(
            table_name=TABLE,
            schema="public",
            db_url=settings.DB_URI,
            embedder=embedder,
            search_type=SearchType.vector,
            create_schema=True,
            # agno 的自动建索引在 PG 会因 SET 参数化语法报错，且有 2000 维 HNSW 上限：
            # 显式禁用( vector_index=None )，改由下方 _create_vector_index 手动补建(幂等)。
            # 若维度>2000 或建索引失败，则退化为顺序扫描(当前语料量级 <10ms 级可接受)。
            # 语料上万后需评估：halfvec 索引(需改 agno 查询列)或换 ≤2000 维 embedding 模型。
            vector_index=None,
        )
        # agno 构造只存配置：建表需显式调用（IF NOT EXISTS，幂等）
        await _DB.async_create()
        # agno 不在 create() 里建向量索引：此处显式补建 HNSW（幂等，已存在即跳过；
        # 维度>2000 超出 HNSW 上限或建索引失败时，由下方 except 兜底退化为顺序扫描）。
        try:
            await asyncio.to_thread(_DB._create_vector_index)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[RAG] agno 向量索引创建失败（检索仍可用，语料大时会退化）：{str(e)[:160]}")
        log.info(f"[RAG] agno PgVector 就绪（表 public.{TABLE}，维度 {dim}）")
        return _DB
    except Exception as e:  # noqa: BLE001
        log.warning(f"[RAG] agno PgVector 初始化失败（回退旧实现）：{str(e)[:200]}")
        return None


async def upsert_chunks(rows: list[dict]) -> int:
    """批量写入/替换向量行（入库链路双写；失败仅告警，旧列仍可用）。

    rows: ``[{chunk_id, content, meta_data, vector}]`` —— vector 直接复用已算好的嵌入，
    不重复调 embedding。
    """
    if not rows:
        return 0
    db = await _vectordb()
    if db is None:
        return 0
    try:
        from agno.knowledge.document import Document

        docs = []
        for r in rows:
            vec = r.get("vector") or []
            docs.append(
                Document(
                    id=str(r["chunk_id"]),
                    content=r.get("content") or "",
                    meta_data=r.get("meta_data") or {},
                    embedding=[float(x) for x in vec] or None,
                )
            )
        content_hash = md5(
            (f"{(rows[0].get('meta_data') or {}).get('kb_id')}:"
             + ",".join(str(r["chunk_id"]) for r in rows)).encode("utf-8")
        ).hexdigest()
        await db.async_upsert(content_hash, docs)
        return len(docs)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[RAG] agno 向量写入失败（跳过；旧列仍可检索）：{str(e)[:200]}")
        return 0


async def search_chunks(query: str, kb_ids: list[int], top_n: int) -> list[dict] | None:
    """agno 近邻检索。

    返回 ``[{id, content, meta_data, score}]``；非 PG / 失败返回 ``None``（调用方回退旧实现）。
    """
    db = await _vectordb()
    if db is None:
        return None
    try:
        docs = await db.async_search(
            query,
            limit=max(int(top_n) * 4, int(top_n)),
            filters={
                "op": "AND",
                "conditions": [
                    {"op": "IN", "key": "kb_id", "values": [str(k) for k in kb_ids]}
                ],
            },
        )
        out: list[dict] = []
        for d in docs:
            meta = getattr(d, "meta_data", None) or {}
            try:
                kb_id = int(meta.get("kb_id"))
            except (TypeError, ValueError):
                continue
            if kb_id not in set(kb_ids):
                continue
            score = getattr(d, "score", None)
            out.append(
                {
                    "chunk_id": int(meta.get("chunk_id") or 0),
                    "content": getattr(d, "content", "") or "",
                    "meta_data": meta,
                    "score": float(score) if score is not None else None,
                }
            )
            if len(out) >= top_n:
                break
        return out
    except Exception as e:  # noqa: BLE001
        log.warning(f"[RAG] agno 向量检索失败（回退旧实现）：{str(e)[:200]}")
        return None


async def delete_chunk_ids(chunk_ids: list[int]) -> int:
    """删除指定分块的向量行（分块删除/知识库级联删除时同步，避免脏命中）。"""
    if not chunk_ids:
        return 0
    db = await _vectordb()
    if db is None:
        return 0
    try:
        from sqlalchemy import text as _text

        with db.db_engine.begin() as conn:
            result = conn.execute(
                _text(
                    f"DELETE FROM public.{TABLE} "
                    "WHERE (meta_data->>'chunk_id')::int = ANY(:ids)"
                ),
                {"ids": [int(c) for c in chunk_ids]},
            )
            return int(result.rowcount or 0)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[RAG] agno 向量行删除失败：{str(e)[:200]}")
        return 0


async def delete_kb_vectors(kb_id: int) -> int:
    """删除某知识库的全部向量行（知识库删除/重建前清残留）。"""
    db = await _vectordb()
    if db is None:
        return 0
    try:
        from sqlalchemy import text as _text

        with db.db_engine.begin() as conn:
            result = conn.execute(
                _text(
                    f"DELETE FROM public.{TABLE} WHERE meta_data->>'kb_id' = :kb"
                ),
                {"kb": str(kb_id)},
            )
            return int(result.rowcount or 0)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[RAG] agno 知识库向量清理失败：{str(e)[:200]}")
        return 0


async def purge_orphans() -> int:
    """启动幂等清理：删除对应分块已不存在/已软删的向量行（防重建残留脏行）。"""
    db = await _vectordb()
    if db is None:
        return 0
    try:
        from sqlalchemy import text as _text

        with db.db_engine.begin() as conn:
            result = conn.execute(
                _text(
                    f"DELETE FROM public.{TABLE} v WHERE NOT EXISTS ("
                    "SELECT 1 FROM ai_knowledge_chunks c "
                    "WHERE c.id = (v.meta_data->>'chunk_id')::int AND c.is_deleted = false)"
                )
            )
            n = int(result.rowcount or 0)
        if n:
            log.info(f"[RAG] agno 孤儿向量清理：{n} 行")
        return n
    except Exception as e:  # noqa: BLE001
        log.warning(f"[RAG] agno 孤儿清理失败：{str(e)[:200]}")
        return 0
