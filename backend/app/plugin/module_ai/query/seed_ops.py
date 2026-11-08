"""种子与初始化：语义层预置、向量表、分享表、数据保留（2026-11-08 从 service.py 拆出）。

``ensure_system_seed`` 幂等写入预置指标/术语/实体映射（首次启动与升级后都跑）；
``_ensure_vector_table`` / ``_seed_vectors`` / ``_agno_seed_units`` 保证向量检索可用
（agno 表与旧 pgvector 表都建）；``_ensure_share_table`` / ``_ensure_data_lifetime`` 建
分享与数据保留所需的附属表。全部 ``CREATE ... IF NOT EXISTS``，失败只记降级。
"""
from __future__ import annotations

import json

from app.core.database import async_db_session
from app.core.logger import log

from . import service as _svc
from .model import AiQueryDictionaryModel, AiQueryFewshotModel, AiQueryMetricModel


class SeedOps:
    @classmethod
    async def ensure_system_seed(cls) -> None:
        """首次执行时写入系统数据源预置指标与术语；之后跳过（避免拖慢快路径）。"""
        if _svc._SEED_DONE:
            return
        async with async_db_session.begin() as db:
            from sqlalchemy import select

            for m in _svc._SYSTEM_METRICS:
                existing = (
                    await db.execute(
                        select(AiQueryMetricModel).where(
                            AiQueryMetricModel.datasource == _svc.SYSTEM_DS,
                            AiQueryMetricModel.key == m["key"],
                            AiQueryMetricModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.name = m["name"]
                    existing.description = m.get("description", "")
                    existing.sql_template = m["sql_template"]
                    existing.params = m.get("params") or []
                    existing.dimensions = m.get("dimensions") or []
                    existing.agg = m.get("agg", "count")
                    existing.unit = m.get("unit", "")
                    existing.cache_ttl = m.get("cache_ttl", 0)
                else:
                    db.add(
                        AiQueryMetricModel(
                            datasource=_svc.SYSTEM_DS, key=m["key"], name=m["name"],
                            description=m.get("description", ""),
                            sql_template=m["sql_template"], params=m.get("params") or [],
                            dimensions=m.get("dimensions") or [], agg=m.get("agg", "count"),
                            unit=m.get("unit", ""), permission_tag=m.get("permission_tag", ""),
                            enabled=True, sort=0, cache_ttl=m.get("cache_ttl", 0),
                        )
                    )
            for t in _svc._SYSTEM_TERMS:
                existing = (
                    await db.execute(
                        select(AiQueryDictionaryModel).where(
                            AiQueryDictionaryModel.datasource == _svc.SYSTEM_DS,
                            AiQueryDictionaryModel.term == t["term"],
                            AiQueryDictionaryModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.metric_key = t.get("metric_key", "")
                    existing.type = t.get("type", "term")
                else:
                    db.add(
                        AiQueryDictionaryModel(
                            datasource=_svc.SYSTEM_DS, term=t["term"],
                            metric_key=t.get("metric_key", ""), field_path="",
                            type=t.get("type", "term"),
                        )
                    )
            for eg in _svc._NL2SQL_FEWSHOT:
                exists_fs = (
                    await db.execute(
                        select(AiQueryFewshotModel).where(
                            AiQueryFewshotModel.question == eg["q"],
                            AiQueryFewshotModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if not exists_fs:
                    db.add(
                        AiQueryFewshotModel(
                            datasource=_svc.SYSTEM_DS, question=eg["q"], sql=eg["sql"], enabled=True
                        )
                    )
        _svc._SEED_DONE = True

    @classmethod
    async def _ensure_share_table(cls, db) -> None:
        from sqlalchemy import text as _t
        dialect = (db.bind.dialect.name if db.bind else "")
        if dialect == "postgresql":
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_dataset_share ("
                "id BIGSERIAL PRIMARY KEY, table_name VARCHAR(255), token VARCHAR(64), "
                "user_id INTEGER, is_deleted INTEGER DEFAULT 0, created_time TIMESTAMP)"))
        else:
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_dataset_share ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, token TEXT, "
                "user_id INTEGER, is_deleted INTEGER DEFAULT 0, created_time TEXT)"))

    @staticmethod
    async def _ensure_data_lifetime(db) -> None:
        """幂等创建数据生命周期表（按方言选择自增主键，避免 SQLite 的 AUTOINCREMENT 在 PG 报错）。"""
        from sqlalchemy import text as _t
        dialect = (db.bind.dialect.name if db.bind else "") or ""
        if dialect == "postgresql":
            ddl = ("CREATE TABLE IF NOT EXISTS ai_data_lifetime "
                   "(id BIGSERIAL PRIMARY KEY, table_name VARCHAR(255), retention_days INTEGER, "
                   "enabled BOOLEAN DEFAULT true, is_deleted BOOLEAN DEFAULT false)")
        elif dialect == "mysql":
            ddl = ("CREATE TABLE IF NOT EXISTS ai_data_lifetime "
                   "(id BIGINT AUTO_INCREMENT PRIMARY KEY, table_name VARCHAR(255), retention_days INT, "
                   "enabled TINYINT(1) DEFAULT 1, is_deleted TINYINT(1) DEFAULT 0)")
        else:
            ddl = ("CREATE TABLE IF NOT EXISTS ai_data_lifetime "
                   "(id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, retention_days INTEGER, "
                   "enabled INTEGER DEFAULT 1, is_deleted INTEGER DEFAULT 0)")
        await db.execute(_t(ddl))

    @classmethod
    async def _ensure_vector_table(cls) -> None:
        """确保 pgvector 资产向量表存在（vector 扩展需已启用）。

        HNSW 索引上限 2000 维，本库 2560 维 → 用顺序余弦扫描（数百行足够快），
        仅当维度≤2000 才尝试建 HNSW 索引。
        """
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _text

            await db.execute(
                _text(
                    "CREATE TABLE IF NOT EXISTS ai_query_asset_vectors ("
                    "id BIGSERIAL PRIMARY KEY, asset_type VARCHAR(32), ref VARCHAR(256) UNIQUE, "
                    "txt TEXT, tables JSONB, embedding vector(2560))"
                )
            )

    @classmethod
    async def _seed_vectors(cls) -> int:
        """把资产单元向量写入 pgvector（幂等：按 ref upsert）。"""
        try:
            await cls._ensure_vector_table()
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 创建 pgvector 表失败: {e}")
            return 0
        index = await cls._semantic_index()
        if not index:
            return 0
        # 只保留带 tables 的单元
        rows = [u for u in index if u.get("tables")]
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _text

            for u in rows:
                ref = u["text"][:220]
                vec = str(u["vector"])
                tables = list(u["tables"])
                await db.execute(
                    _text(
                        "INSERT INTO ai_query_asset_vectors(asset_type, ref, txt, tables, embedding) "
                        "VALUES ('unit', :ref, :txt, CAST(:tables AS jsonb), CAST(:vec AS vector)) "
                        "ON CONFLICT (ref) DO UPDATE SET txt=EXCLUDED.txt, tables=EXCLUDED.tables, embedding=EXCLUDED.embedding"
                    ),
                    {"ref": ref, "txt": u["text"], "tables": json.dumps(tables, ensure_ascii=False), "vec": vec},
                )
        return len(rows)

    @classmethod
    async def _agno_seed_units(cls, schema: dict) -> None:
        """后台把 schema 单元播种进 Agno 向量库（不阻塞请求）。"""
        global _AGNO_SEEDED, _AGNO_SEEDING
        try:
            from .agno_store import AgnoSemanticStore

            store = await AgnoSemanticStore.get()
            await store.ensure()
            if (await store.count()) == 0:
                units: list[dict] = []
                for t in schema:
                    units.append({"text": f"数据表 {t}", "tables": {t}})
                    for col in schema[t]:
                        cname = col.split("(")[0]
                        units.append({"text": f"表 {t} 的字段 {cname}", "tables": {t}})
                n = await store.seed(units, reset=True)
                log.info(f"[query] Agno 语义单元后台入库: {n} 条")
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] Agno 后台播种失败: {e}")
        finally:
            _AGNO_SEEDED = True
            _AGNO_SEEDING = False
