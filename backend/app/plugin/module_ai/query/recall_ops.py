"""语义召回：单元构建、四通道并行、RRF 融合（2026-11-08 从 service.py 拆出）。

- 召回单元（`ai_query_recall_unit`）由表/指标/术语/概念/对象拼成，`rebuild_recall_units` 重建；
- 四通道：向量 / 关键词 / 本体 / 实体，**并行不短路**，用 RRF 融合（只看排名，免跨通道归一化）；
- `recall_enabled=false` 时退回 `_semantic_tables_legacy`，便于灰度回滚；
- 检索结果按「问题 + 数据源 + 配置指纹」缓存（`_svc._retrieval_cache_key`）。
"""
from __future__ import annotations

import time

from app.core.database import async_db_session
from app.core.logger import log

from . import service as _svc


class RecallOps:
    @classmethod
    async def _semantic_index(cls) -> list | None:
        """把表/列/指标/术语编码成向量索引（进程级缓存，仅首次构建）。"""
        global _SEMANTIC_INDEX
        if _SEMANTIC_INDEX is not None:
            return _SEMANTIC_INDEX
        schema = await cls._system_schema()
        metrics = await cls.list_metrics(_svc.SYSTEM_DS)
        terms = await cls.list_terms(_svc.SYSTEM_DS)
        units: list[dict] = []
        for t in schema:
            units.append({"text": f"数据表 {t}", "tables": {t}})
            for col in schema[t]:
                cname = col.split("(")[0]
                units.append({"text": f"表 {t} 的字段 {cname}", "tables": {t}})
        for m in metrics:
            units.append(
                {"text": f"统计指标 {m['name']}：{m['description']}", "tables": _svc._tables_in_sql(m.get("sql_template", ""))}
            )
        for tm in terms:
            units.append(
                {"text": f"业务术语 {tm['term']} 对应 {tm.get('metric_key') or tm.get('field_path')}", "tables": set()}
            )
        try:
            from app.plugin.module_ai.knowledge.embedding import embed_texts

            vecs = await embed_texts([u["text"] for u in units], model_id=await cls._embedding_mid())
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] schema 向量化失败，退化为关键字: {e}")
            return []
        if not vecs:
            return []
        _SEMANTIC_INDEX = [
            {"text": u["text"], "tables": u["tables"], "vector": v}
            for u, v in zip(units, vecs, strict=False)
        ]
        return _SEMANTIC_INDEX

    @classmethod
    async def _ensure_recall_units_table(cls) -> None:
        """建语义单元表（幂等）。

        ``embedding`` 列**只在 PostgreSQL 上创建**——测试用 SQLite，没有 pgvector。
        """
        cols = cls._RECALL_UNITS_COLS
        from app.config.setting import settings

        if settings.DATABASE_TYPE == "postgres":
            cols = cols.replace("meta JSONB,", "meta JSONB, embedding vector(2560),")
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            await db.execute(
                _t(f"CREATE TABLE IF NOT EXISTS ai_query_recall_units ({cols})")
            )

    @classmethod
    async def _collect_recall_units(cls) -> list[dict]:
        """收集召回单元：表 / 本体对象 / 概念 / 指标 / 术语。"""
        from app.plugin.module_ai.ontology import semantic as _sem

        from .recall import (
            build_concept_unit,
            build_metric_unit,
            build_object_unit,
            build_table_unit,
            build_term_unit,
        )

        units: list[dict] = []
        try:
            schema = await cls._system_schema()
            assets = {a.get("table_name"): a for a in await cls.list_assets()}
            for table, labels in (schema or {}).items():
                cols = [cls._parse_col_label(x) for x in (labels or [])]
                units.append(build_table_unit(table, assets.get(table) or {}, cols))
        except Exception as e:  # noqa: BLE001 - 单个来源失败不阻断整体重建
            log.warning(f"[query][recall] 表单元构建失败: {e}")
        try:
            ctx = await _sem.semantic_context(include_properties=True)
            rels = ctx.get("relations") or []
            props = ctx.get("properties") or {}
            for o in ctx.get("objects") or []:
                code, table = o.get("code"), o.get("table")
                mine = [
                    r for r in rels
                    if r.get("source") in (code, table) or r.get("target") in (code, table)
                ]
                units.append(build_object_unit(o, props.get(code) or [], mine))
            # semantic_context 的 concepts 已合并「本体别名 + ai_query_concept」
            for c in ctx.get("concepts") or []:
                units.append(build_concept_unit(c))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 本体单元构建失败: {e}")
        try:
            for m in await cls.list_metrics(_svc.SYSTEM_DS):
                units.append(build_metric_unit(m))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 指标单元构建失败: {e}")
        try:
            for t in await cls.list_terms(_svc.SYSTEM_DS):
                units.append(build_term_unit(t))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 术语单元构建失败: {e}")

        # 同一 (kind, ref) 只保留一条，保证幂等
        seen: set[tuple[str, str]] = set()
        out: list[dict] = []
        for u in units:
            key = (u.get("kind") or "", u.get("ref") or "")
            if not key[1] or key in seen:
                continue
            seen.add(key)
            out.append(u)
        return out

    @classmethod
    async def rebuild_recall_units(cls) -> dict:
        """重建语义召回单元（幂等，可重复执行）。

        返回 ``{"units": 条数, "embedded": 已向量化条数, "version": 批次}``。
        非 PostgreSQL 环境不写 ``embedding``（无 pgvector），只存文本。
        """
        import json as _json

        from sqlalchemy import text as _t

        from app.config.setting import settings
        from app.plugin.module_ai.knowledge.embedding import embed_texts

        await cls._ensure_recall_units_table()
        units = await cls._collect_recall_units()
        is_pg = settings.DATABASE_TYPE == "postgres"

        vecs: list[list[float] | None] = [None] * len(units)
        embedded = 0
        if is_pg and units:
            try:
                got = await embed_texts([u["text"] for u in units])
                for i, v in enumerate(got):
                    if i < len(vecs):
                        vecs[i] = v
                embedded = len(got)
            except Exception as e:  # noqa: BLE001 - 向量化失败仍保留文本单元
                log.warning(f"[query][recall] 单元向量化失败（仅存文本）: {e}")

        version = int(time.time())
        async with async_db_session.begin() as db:
            for u, v in zip(units, vecs, strict=False):
                params = {
                    "kind": u["kind"],
                    "ref": u["ref"],
                    "text": u["text"],
                    "meta": _json.dumps(u.get("meta") or {}, ensure_ascii=False),
                    "ver": version,
                }
                if is_pg:
                    params["emb"] = _json.dumps(v) if v is not None else None
                    await db.execute(
                        _t(
                            "INSERT INTO ai_query_recall_units"
                            "(kind,ref,text,meta,embedding,version,is_deleted,"
                            "created_time,updated_time) VALUES "
                            "(:kind,:ref,:text,CAST(:meta AS jsonb),CAST(:emb AS vector),"
                            ":ver,false,now(),now()) "
                            "ON CONFLICT (kind,ref) DO UPDATE SET text=EXCLUDED.text, "
                            "meta=EXCLUDED.meta, "
                            "embedding=COALESCE(EXCLUDED.embedding, "
                            "ai_query_recall_units.embedding), "
                            "version=EXCLUDED.version, is_deleted=false, updated_time=now()"
                        ),
                        params,
                    )
                else:
                    await db.execute(
                        _t(
                            "INSERT INTO ai_query_recall_units"
                            "(kind,ref,text,meta,version,is_deleted,created_time,updated_time) "
                            "VALUES (:kind,:ref,:text,:meta,:ver,false,now(),now()) "
                            "ON CONFLICT (kind,ref) DO UPDATE SET text=EXCLUDED.text, "
                            "meta=EXCLUDED.meta, version=EXCLUDED.version, "
                            "is_deleted=false, updated_time=now()"
                        ),
                        params,
                    )
        log.info(f"[query][recall] 语义单元重建完成: {len(units)} 条（向量化 {embedded}）")
        return {"units": len(units), "embedded": embedded, "version": version}

    @classmethod
    async def _recall_vector(cls, question: str, top_n: int) -> list[str]:
        """向量召回通道：**直查 pgvector**（绕过 Agno 的同步引擎与默认 10 条限制）。

        非 PostgreSQL / 未装 pgvector / 单元未重建时**优雅降级为空列表**，由其余通道兜底
        （测试库是 SQLite，走的正是这条路径）。
        """
        import json as _json

        from app.config.setting import settings

        if settings.DATABASE_TYPE != "postgres":
            return []
        try:
            from sqlalchemy import text as _t

            from app.plugin.module_ai.knowledge.embedding import embed_texts

            vecs = await embed_texts([question])
            if not vecs or not vecs[0]:
                return []
            async with async_db_session() as db:
                rows = (
                    await db.execute(
                        _t(
                            "SELECT meta FROM ai_query_recall_units "
                            "WHERE is_deleted = false AND embedding IS NOT NULL "
                            "ORDER BY embedding <=> CAST(:q AS vector) LIMIT :n"
                        ),
                        {"q": _json.dumps(vecs[0]), "n": int(top_n)},
                    )
                ).fetchall()
            out: list[str] = []
            for (meta,) in rows:
                m = meta if isinstance(meta, dict) else _json.loads(meta or "{}")
                for t in m.get("tables") or []:
                    if t and t not in out:
                        out.append(t)
            return out
        except Exception as e:  # noqa: BLE001 - 向量通道失败不得阻断召回
            log.warning(f"[query][recall] 向量通道失败，已降级: {e}")
            return []

    @classmethod
    async def _recall_keyword(cls, question: str, schema: dict | None = None) -> list[str]:
        """关键词通道（薄包装：取数据后调纯函数 ``recall_keyword``）。

        ⚠️ 必须用**调用方传入的 schema**：外部数据源（如 ds:4 燃煤库）的表不在
        ``_svc._system_schema()`` 里，固定用系统 schema 会让该通道对外部源完全失效。
        """
        from .recall import recall_keyword

        try:
            schemas = schema if schema is not None else await cls._system_schema()
            return recall_keyword(
                question, schemas,
                await cls.list_metrics(_svc.SYSTEM_DS), await cls.list_terms(_svc.SYSTEM_DS),
            )
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 关键词通道失败: {e}")
            return []

    @classmethod
    async def _recall_ontology(cls, question: str) -> list[str]:
        """本体强信号通道：别名 > 同义词 > 属性名 > 对象名。"""
        from app.plugin.module_ai.ontology import semantic as _sem

        from .recall import recall_ontology

        try:
            ctx = await _sem.semantic_context(include_properties=True)
            tmap = await _sem.object_table_map()
            props = ctx.get("properties") or {}
            objs: list[dict] = []
            for o in ctx.get("objects") or []:
                oo = dict(o)
                oo["properties"] = [
                    (p.get("name") or p.get("code"))
                    for p in (props.get(o.get("code")) or [])
                ]
                objs.append(oo)
            return recall_ontology(question, objs, tmap)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 本体通道失败: {e}")
            return []

    @classmethod
    async def _recall_entity(cls, question: str, schema: dict | None = None) -> list[str]:
        """实体名词通道（薄包装）；同样必须用传入的 schema（外部数据源场景）。"""
        from .recall import recall_entity

        try:
            cfg = await cls._cfg()
            schemas = schema if schema is not None else await cls._system_schema()
            return recall_entity(question, cls._cfg_entity_map(cfg), schemas)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 实体通道失败: {e}")
            return []

    @classmethod
    async def _semantic_tables(cls, question: str, schema: dict | None = None,
                               metrics: list[dict] | None = None,
                               terms: list[dict] | None = None,
                               datasource: str | None = None) -> list[str]:
        """分层检索（带**记忆缓存**）。

        同一个问题在一次问答里会被问两次——`_build_schema_context` 拼 prompt、
        `_recall_grounding` 做溯源——而这条路径会走向量检索。
        不缓存就是白跑一次检索（实测收尾阶段因此花掉 1.2~1.8 秒）。
        缓存 key **含数据源**：否则两个数据源互相串结果。
        key 还要含**配置签名**：`_semantic_tables_uncached` 返回的是**已经按
        `recall_top_k` 截断**的列表，只按「数据源|问题」缓存的话，
        管理员把 top_k 从 12 调到 6，10 分钟内（TTL=600s）拿到的还是 12 张表的旧结果
        —— 正好把"调参实验"变成"调了没变化"。
        """
        key = f"{_svc._retrieval_cache_key(question, datasource)}|{_svc._cfg_sig(await cls._cfg())}"
        if _svc._BYPASS_CACHE.get():
            # 评测：召回结果与消融开关（recall_enabled 等）强相关，缓存会让消融失真
            return await cls._semantic_tables_uncached(question, schema, metrics, terms)
        hit = _svc._RETRIEVAL_CACHE.get(key)
        if hit and time.time() - hit[0] <= _svc._RETRIEVAL_CACHE_TTL:
            return list(hit[1])
        out = await cls._semantic_tables_uncached(question, schema, metrics, terms)
        if len(_svc._RETRIEVAL_CACHE) >= _svc._RETRIEVAL_CACHE_MAX:
            for k in list(_svc._RETRIEVAL_CACHE)[: max(1, _svc._RETRIEVAL_CACHE_MAX // 10)]:
                _svc._RETRIEVAL_CACHE.pop(k, None)
        _svc._RETRIEVAL_CACHE[key] = (time.time(), list(out))
        return out

    @classmethod
    async def _semantic_tables_uncached(cls, question: str, schema: dict | None = None,
                                        metrics: list[dict] | None = None,
                                        terms: list[dict] | None = None) -> list[str]:
        """多路并行召回 + RRF 融合 + 阈值 + **按分数取 top_k**（阶段1）。

        取代旧实现的「分级短路 + 字典序截断」：四个通道**并行**执行、互不短路，
        用 RRF（只用排名，免跨通道归一化）融合后按分数截断。
        ``recall_enabled=false`` 时退回 ``_semantic_tables_legacy``，便于灰度回滚。
        """
        import asyncio

        cfg = await cls._cfg()
        if not cls._cfg_bool(cfg, "recall_enabled", True):
            return await cls._semantic_tables_legacy(question, schema, metrics, terms)

        from .recall import CORE_TABLES, DEFAULT_WEIGHTS, fuse_rrf

        top_k = cls._cfg_int(cfg, "recall_top_k", 12)
        top_n = max(8, top_k * 2)
        # schema 是**本次问答的数据源**的表结构（外部源时由调用方传入）：
        # 关键词/实体通道必须用它，否则对外部数据源（如 ds:4 燃煤库）失效。
        try:
            schema_map = schema if schema is not None else await cls._system_schema()
        except Exception as e:  # noqa: BLE001 - 取不到 schema 不阻断召回
            log.warning(f"[query][recall] 取 schema 失败（通道将为空）: {e}")
            schema_map = schema or {}

        async def _timed(name: str, coro):
            t0 = time.perf_counter()
            try:
                return name, await coro, (time.perf_counter() - t0) * 1000
            except Exception as e:  # noqa: BLE001
                return name, e, (time.perf_counter() - t0) * 1000

        raw = await asyncio.gather(
            _timed("vector", cls._recall_vector(question, top_n)),
            _timed("keyword", cls._recall_keyword(question, schema_map)),
            _timed("ontology", cls._recall_ontology(question)),
            _timed("entity", cls._recall_entity(question, schema_map)),
        )
        channels: dict[str, list[str]] = {}
        _cost = []
        for name, res, ms in raw:
            channels[name] = [] if isinstance(res, BaseException) else list(res or [])
            _cost.append(f"{name}={int(ms)}ms")
        log.warning("[recall] 通道耗时：{}", " ".join(_cost))

        weights = {
            "vector": cls._cfg_float(cfg, "recall_w_vector", DEFAULT_WEIGHTS["vector"]),
            "keyword": cls._cfg_float(cfg, "recall_w_keyword", DEFAULT_WEIGHTS["keyword"]),
            "ontology": cls._cfg_float(cfg, "recall_w_ontology", DEFAULT_WEIGHTS["ontology"]),
            "entity": cls._cfg_float(cfg, "recall_w_entity", DEFAULT_WEIGHTS["entity"]),
        }
        fused = fuse_rrf(channels, weights)
        min_score = cls._cfg_float(cfg, "recall_min_score", 0.0)
        # **数据源隔离**：只保留本次数据源 schema 里的表。
        # 向量/本体通道是**全局**的（不认数据源），实测 ds:4 的问题被召回到
        # video_*/ai_* 等 system 表 → prompt 里没有真正的业务表 → 模型**编表名** → 空 SQL。
        ranked = [t for t, s in fused if s >= min_score]
        picked = _svc.scope_tables_to_schema(ranked, schema_map, CORE_TABLES, top_k)

        # 关系/KG/AGE 扩表：仅作**补充**、不参与计分。
        # ⚠️ 必须有上限：无限制追加会把 prompt 撑大，实测让生成 P50 从 7.9s 涨到 9.0s。
        try:
            if cls._cfg_bool(cfg, "kg_enabled", True):
                from .agno_kg import _ensure, age_expand_tables, kg_tables

                limit = top_k + max(0, cls._cfg_int(cfg, "recall_expand_cap", 4))
                kg = await _ensure()
                extra: list[str] = []
                if kg:
                    extra.extend(kg_tables(question) or [])
                if picked:
                    extra.extend(await age_expand_tables(sorted(picked)) or [])
                for t in extra:
                    if len(picked) >= limit:
                        break
                    if t in schema_map and t not in picked:
                        picked.append(t)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 扩表失败（忽略）: {e}")
        return picked

    @classmethod
    async def _semantic_tables_legacy(cls, question: str, schema: dict | None = None,
                                      metrics: list[dict] | None = None,
                                      terms: list[dict] | None = None) -> list[str]:
        """【旧实现，仅作 recall_enabled=false 的回退】分层检索 + 关键词 + 实体表基线，合并出联表所需的表集合。

        优先 pgvector，回退内存融合(jieba+embedding)；再并上关键词相关表，
        并按「实体名词→表」映射把联表取名称所需的 name 承载表兜底加入；
        最后按 token 量裁剪到前 16 张，避免 prompt 过大。
        """
        global _VECTOR_SEEDED
        cfg = await cls._cfg()
        if schema is None:
            schema = await cls._system_schema()
        if metrics is None:
            metrics = await cls.list_metrics(_svc.SYSTEM_DS)
        if terms is None:
            terms = await cls.list_terms(_svc.SYSTEM_DS)
        top_k = cls._cfg_int(cfg, "schema_top_k", 16)
        tables: set[str] = set()
        # 1) 语义召回：优先走 Agno 框架(Knowledge+PgVector)
        if cls._cfg_bool(cfg, "agno_semantic_enabled", True):
            try:
                at = await cls._agno_search_tables(question, schema, top_k)
                tables.update(at)
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] Agno 语义检索失败，回退 pgvector: {e}")
        # 2) 回退：pgvector / 内存融合
        if not tables:
            try:
                if not _VECTOR_SEEDED:
                    try:
                        n = await cls._seed_vectors()
                        _VECTOR_SEEDED = True
                        log.info(f"[query] 资产向量已落 pgvector: {n} 条")
                    except Exception as e:  # noqa: BLE001
                        log.warning(f"[query] pgvector 播种失败: {e}")
                rows = await cls._pgv_search(question, top_k=top_k)
                tables.update(rows)
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] pgvector 检索失败: {e}")
        # 3) 内存融合回退
        if not tables:
            try:
                index = await cls._semantic_index()
                if index:
                    from . import retrieval as _ret

                    units = [
                        {"text": u["text"], "vector": u.get("vector"), "meta": u["tables"]}
                        for u in index
                    ]
                    top = await _ret.retrieve(
                        question, units, top_k=top_k,
                        semantic_weight=cls._cfg_float(cfg, "schema_semantic_weight", 0.6),
                        keyword_weight=cls._cfg_float(cfg, "schema_keyword_weight", 0.4),
                        embed_model_id=await cls._embedding_mid(),
                    )
                    for u in top:
                        tables.update(u.get("meta") or set())
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 语义检索失败: {e}")
        # 3) 关键词相关表
        try:
            tables.update(cls._relevant_tables(question, schema, metrics, terms))
        except Exception:  # noqa: BLE001
            pass
        # 3.5) **本体别名 → 表**（本体是唯一语义源，检索也必须用上）
        #
        # 真实踩过：问「各部门的销售额是多少」，本体里有对象「销售订单」
        # （表 demo_sales，属性「销售额」），但检索只认**表名**，demo_sales 没被召回，
        # 模型只好拿 `ai_call_logs.cost` 当"销售额"，返回 0。
        #
        # ⚠️ 只匹配**别名**，不匹配对象名：对象名（如"告警记录表"）含"告警"这种
        # 通用词，会给大量无关问题塞进额外表 —— 实测这让 prompt 变大、
        # 生成 p50 从 3147ms 涨到 6483ms（精度还降了）。别名是人工登记的强信号。
        try:
            from app.plugin.module_ai.ontology import semantic as _sem

            ctx = await _sem.semantic_context(include_properties=False)
            tmap = await _sem.object_table_map()
            code_of: dict[str, str] = {}
            for tbl, code in tmap.items():
                code_of.setdefault(code, tbl)
            q_low = (question or "").lower()
            added = 0
            for o in ctx["objects"]:
                if added >= _svc._ONT_ALIAS_MAX_TABLES:
                    break
                hits = [a for a in (o.get("aliases") or [])
                        if a and len(str(a)) >= 2 and str(a).lower() in q_low]
                if not hits:
                    continue
                tbl = code_of.get(o["code"]) or o["table"]
                if tbl in schema and tbl not in tables:
                    tables.add(tbl)
                    added += 1
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 本体别名检索失败: {e}")
        # 4) 实体名词 → 表 基线（保证联表取名称的表在上下文）
        if cls._cfg_bool(cfg, "entity_enabled", True):
            entity_map = cls._cfg_entity_map(cfg)
            for noun, ts in entity_map.items():
                if noun in question:
                    tables.update(t for t in ts if t in schema)
        # 5) 知识图谱图遍历：补上向量/关键词检索漏掉的关联表与联表路径
        try:
            if cls._cfg_bool(cfg, "kg_enabled", True):
                from .agno_kg import _ensure, kg_tables

                kg = await _ensure()
                if kg:
                    tables.update(t for t in kg_tables(question) if t in schema)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 知识图谱召回失败: {e}")
        # 6) AGE 图库多跳扩表：从已命中表经 Cypher 扩展关联表
        try:
            if cls._cfg_bool(cfg, "kg_enabled", True) and tables:
                from .agno_kg import age_expand_tables

                tables.update(t for t in await age_expand_tables(sorted(tables)) if t in schema)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] AGE 扩表失败: {e}")
        return sorted(tables)[:top_k]

    @classmethod
    async def _recall_grounding(cls, question: str, datasource: str | None = None) -> dict | None:
        """Grounding 可观测：返回本次混合检索锁定的表 + 关键字段，供前端展示「召回表/字段」。

        **必须传数据源**：否则 ds:4 的问题会用 system 源的 schema 去检索，
        召回到 video_*/ai_* 表 → prompt 里没有真正的业务表 → 模型**编表名** → 空 SQL（实测）。
        """
        try:
            if (datasource or _svc.SYSTEM_DS) == _svc.SYSTEM_DS:
                schema = await cls._system_schema()
            else:
                schema = await cls._ds_schema_map(datasource)
            metrics = await cls.list_metrics(datasource)
            terms = await cls.list_terms(datasource)
            rel_tables = await cls._semantic_tables(
                question, schema, metrics, terms, datasource
            )
            fields = {t: [lab.split("(")[0] for lab in schema.get(t, [])][:8]
                      for t in rel_tables}
            return {"tables": rel_tables, "fields": fields}
        except Exception:  # noqa: BLE001
            return None
