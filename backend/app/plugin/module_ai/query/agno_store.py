"""Agno 语义检索存储：用 Agno ``Knowledge`` + ``PgVector`` 承载问数语义索引。

替代原先手写的 ``ai_query_asset_vectors`` + ``retrieval`` 分层检索，
统一走 Agno 框架的向量化 / 索引 / 检索。
"""
from __future__ import annotations

import asyncio

from agno.knowledge import Knowledge
from agno.vectordb.pgvector import PgVector
from sqlalchemy import create_engine

from app.config.setting import settings

from .agno_embedder import SmbsEmbedder

#: Agno PgVector 使用的 schema / 表（与项目库同库，单独 schema 隔离）
_AGNO_SCHEMA = "ai"
_AGNO_TABLE = "ai_query_agno_units"


def _sync_url() -> str:
    """用项目 postgres 配置构造 psycopg 同步串（Agno PgVector 为同步引擎）。"""
    host = getattr(settings, "DATABASE_HOST", "127.0.0.1")
    port = getattr(settings, "DATABASE_PORT", 5432)
    user = getattr(settings, "DATABASE_USER", "root")
    pwd = getattr(settings, "DATABASE_PASSWORD", "")
    name = getattr(settings, "DATABASE_NAME", "aistation")
    return f"postgresql+psycopg://{user}:{pwd}@{host}:{port}/{name}"


class AgnoSemanticStore:
    """进程级单例：Agno Knowledge(PgVector) 语义检索。"""

    _instance: AgnoSemanticStore | None = None

    def __init__(self, engine=None, kb=None):
        self._engine = engine
        self._kb = kb

    @classmethod
    async def get(cls) -> AgnoSemanticStore:
        if cls._instance is None:
            embedder = await SmbsEmbedder.create()
            engine = create_engine(_sync_url(), future=True)
            pv = PgVector(
                table_name=_AGNO_TABLE, schema=_AGNO_SCHEMA, db_engine=engine,
                embedder=embedder, search_type="vector", distance="cosine",
            )
            kb = Knowledge(vector_db=pv)
            cls._instance = cls(engine=engine, kb=kb)
        return cls._instance

    def _ensure(self) -> None:
        if self._kb.vector_db is not None:
            self._kb.vector_db.create()

    async def ensure(self) -> None:
        await asyncio.to_thread(self._ensure)

    def _count(self) -> int:
        from sqlalchemy import text as _t

        with self._engine.connect() as c:
            return int(c.execute(_t(f"SELECT count(*) FROM {_AGNO_SCHEMA}.{_AGNO_TABLE}")).scalar() or 0)

    async def count(self) -> int:
        try:
            return await asyncio.to_thread(self._count)
        except Exception:  # noqa: BLE001
            return 0

    async def seed(self, units: list[dict], reset: bool = False) -> int:
        """把语义单元写入 Agno 向量库。units: [{text, tables}]。"""
        def _do() -> int:
            if reset:
                self._kb.vector_db.delete()
            docs = []
            for u in units:
                if not u.get("text"):
                    continue
                docs.append({
                    "name": u["text"],
                    "text_content": u["text"],
                    "meta_data": {"tables": list(u.get("tables") or [])},
                    "content": u["text"],
                })
            if not docs:
                return 0
            self._kb.insert_many(docs)
            return len(docs)
        return await asyncio.to_thread(_do)

    async def search(self, question: str, top_k: int = 12) -> list[str]:
        """Agno 语义检索，返回命中的单元文本列表。"""
        def _do() -> list[str]:
            out = []
            for doc in self._kb.search(question)[:top_k]:
                out.append(getattr(doc, "name", "") or getattr(doc, "content", "") or "")
            return out
        return await asyncio.to_thread(_do)
