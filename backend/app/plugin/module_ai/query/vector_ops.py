"""向量检索与答案缓存（2026-11-08 从 service.py 拆出）。

- ``_agno_search_tables`` / ``_pgv_search`` / ``_embedding_mid``：agno Knowledge 优先，
  失败回退旧 pgvector（两套都可用，回退只在降级/测试路径）；
- ``_asset_tmeta``：资产元数据投影（表名 → 别名/域/描述），带短时缓存；
- ``_cache_*``：单条回答的 Redis 缓存（key 含用户，指标结果是按权限算的）。

三个进程级标志（``_AGNO_SEEDED`` / ``_AGNO_SEEDING`` / ``_ASSET_TMETA``）仍归
``service.py``，这里用 ``_svc.`` 读写。
"""
from __future__ import annotations

from app.core.database import async_db_session
from app.core.logger import log

from . import service as _svc
from .model import AiQueryAssetModel


class VectorOps:
    @classmethod
    async def _pgv_search(cls, question: str, top_k: int = 12) -> list[str]:
        """pgvector 向量检索：返回最相关表（HNSW 余弦）。"""
        try:
            await cls._ensure_vector_table()
        except Exception:  # noqa: BLE001
            return []
        try:
            from app.plugin.module_ai.knowledge.embedding import embed_texts

            qvec = (await embed_texts([question], model_id=await cls._embedding_mid()))[0]
        except Exception:  # noqa: BLE001
            return []
        async with async_db_session() as db:
            from sqlalchemy import text as _text

            r = await db.execute(
                _text(
                    "SELECT tables FROM ai_query_asset_vectors "
                    "ORDER BY embedding <-> CAST(:q AS vector) LIMIT :k"
                ),
                {"q": str(qvec), "k": top_k},
            )
            rows = r.fetchall()
        tables: set[str] = set()
        for row in rows:
            t = row[0]
            if t:
                tables.update(t)
        return list(tables)

    @staticmethod
    async def _embedding_mid() -> int | None:
        """解析 usage='embedding' 的模型 id（供 embed_texts 使用），无则 None。"""
        try:
            from sqlalchemy import text as _t

            async with async_db_session() as db:
                m = (
                    await db.execute(
                        _t(
                            "SELECT id FROM ai_models "
                            "WHERE usage=:usage AND enabled=true AND is_deleted=false "
                            "ORDER BY is_default DESC, id DESC LIMIT 1"
                        ),
                        {"usage": "embedding"},
                    )
                ).scalar_one_or_none()
                return int(m) if m else None
        except Exception:  # noqa: BLE001
            return None

    @classmethod
    async def _agno_search_tables(cls, question: str, schema: dict, top_k: int) -> list[str]:
        """用 Agno Knowledge(PgVector) 语义检索，返回命中的表集合。

        首次调用触发**后台播种**（不阻塞当前请求，回退 pgvector），
        播种完成后走 Agno 检索。
        """
        from .agno_store import AgnoSemanticStore

        store = await AgnoSemanticStore.get()
        await store.ensure()
        if not _svc._AGNO_SEEDED and (await store.count()) == 0 and not _svc._AGNO_SEEDING:
            _svc._AGNO_SEEDING = True
            import asyncio as _asyncio

            _asyncio.ensure_future(cls._agno_seed_units(schema))
            return []  # 本次回退到 pgvector，播种完成后走 Agno
        texts = await store.search(question, top_k=top_k)
        tables: set[str] = set()
        for txt in texts:
            for t in schema:
                if t in txt:
                    tables.add(t)
        return list(tables)

    @classmethod
    async def _auto_index(cls, object_code: str) -> None:
        """后台按建议为某对象建索引（失败不阻断、允许重试）。"""
        from app.plugin.module_ai.ontology import indexing as _idx

        try:
            r = await _idx.apply_suggestions(object_code, only_high=True)
            log.warning("[query] 自动建索引 object={} -> {}", object_code, r.get("msg"))
        except Exception as e:  # noqa: BLE001
            _svc._OQ_INDEXED.discard(object_code)   # 失败回滚占位，下次可再试
            log.warning(f"[query] 自动建索引失败（忽略）object={object_code}: {str(e)[:120]}")

    @staticmethod
    async def _asset_tmeta() -> dict:
        """表级资产元数据（中文名/业务域/描述/业务场景），进程级缓存。"""
        if _svc._ASSET_TMETA is not None:
            return _svc._ASSET_TMETA
        async with async_db_session() as db:
            from sqlalchemy import select

            rows = (
                await db.execute(
                    select(AiQueryAssetModel).where(AiQueryAssetModel.is_deleted.is_(False))
                )
            ).scalars().all()
        _svc._ASSET_TMETA = {
            a.table_name: {
                "alias": a.alias or "", "domain": a.domain or "",
                "description": a.description or "",
                "business_scenarios": a.business_scenarios or "",
            }
            for a in rows
        }
        return _svc._ASSET_TMETA

    @staticmethod
    def _cache_key(metric: dict, params: dict, user_id: int | None = None) -> str:
        import hashlib
        import json

        raw = json.dumps(
            {"ds": metric.get("datasource"), "key": metric.get("key"),
             "params": sorted(params.items()),
             # 安全补丁（2026-10-19）：缓存 key 必须含 user。指标结果是**按调用者
             # 权限**算出来的（行/列策略已下推），不含 user ⇒ A 按自己权限算出的
             # 结果会在 TTL（30~120s）内被 B 直接拿到 —— 越权读。
             "uid": int(user_id or 0)},
            ensure_ascii=False, sort_keys=True, default=str,
        )
        return f"ai:query:{hashlib.md5(raw.encode()).hexdigest()}"

    @staticmethod
    async def _cache_get(redis, key: str):
        try:
            val = await redis.get(key)
            if not val:
                return None
            import json

            return json.loads(val)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    async def _cache_set(redis, key: str, res: dict, ttl: int) -> None:
        try:
            import json

            await redis.set(key, json.dumps(res, ensure_ascii=False, default=str), ex=max(ttl, 1))
        except Exception:  # noqa: BLE001
            pass
