"""血缘与治理看板（2026-11-08 从 service.py 拆出）。

- ``lineage`` / ``lineage_propagate``：表级/列级血缘与下钻；
- ``impact_analysis``：改动影响面（下游表、报表、指标）；
- ``governance_overview`` / ``asset_hotspots``：覆盖率、孤儿表、敏感暴露、热点；
- ``compass_search``：语义搜索（表/指标/术语/对象统一检索）；
- ``kg_stats`` / ``object_relations`` / ``object_lifecycle``：图谱统计与对象关系/生命周期；
- ``_object_backing_map`` / ``_objects_light`` / ``_metric_value``：本体内部的轻量投影。
"""
from __future__ import annotations

from app.core.database import async_db_session
from app.core.logger import log

from . import service as _svc


class GovernanceOps:
    @classmethod
    async def lineage(cls, table_name: str) -> dict:
        """P3-④ 完整血缘：表 → 字段/指标/对象关联/概念/管道/术语，串成血缘图。"""
        schema = await cls._system_schema()
        metrics = await cls.list_metrics()
        terms = await cls.list_terms()
        concepts = await cls.concepts_mapping()
        pipelines = await cls.list_pipelines()
        # 字段
        fields = [lab.split("(")[0] for lab in schema.get(table_name, [])]
        # 业务表（外部数据源）不在平台 _system_schema 内 → 回退到已同步的 ai_query_schema 列
        if not fields:
            try:
                import json as _json
                async with async_db_session() as db:
                    from sqlalchemy import text as _t
                    row = (await db.execute(_t(
                        "SELECT columns FROM ai_query_schema "
                        "WHERE UPPER(table_name)=UPPER(:t) AND is_deleted=false LIMIT 1"),
                        {"t": table_name})).fetchone()
                if row and row[0]:
                    cols = row[0] if isinstance(row[0], list) else _json.loads(row[0])
                    fields = [c.get("name") for c in cols if isinstance(c, dict) and c.get("name")]
            except Exception:  # noqa: BLE001
                pass
        # 用到此表的指标（真实 SQL 引用 + 绑定型指标经对象 backing_table 匹配）
        obmap = await cls._object_backing_map()
        mets = []
        _mseen: set = set()
        for m in metrics:
            hit = table_name in (m.get("sql_template") or "")
            if not hit:
                oc = m.get("object_code")
                if oc and (obmap.get(oc) or oc).upper() == table_name.upper():
                    hit = True
            if hit and m["key"] not in _mseen:
                _mseen.add(m["key"])
                mets.append({"key": m["key"], "name": m["name"]})
        # 术语/概念映射到表
        rel_terms = [{"term": t["term"], "metric": t.get("metric_key") or t.get("field_path")} for t in terms if table_name in (t.get("field_path") or "")]
        rel_concepts = [{"name": c["name"]} for c in concepts if table_name in (c.get("tables") or [])]
        # 对象关联(入向+出向)
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rows = (await db.execute(_t(
                "SELECT column_name, related_table, related_field FROM ai_query_asset_columns "
                "WHERE (table_name=:t OR related_table=:t) AND is_deleted=false"), {"t": table_name})).fetchall()
        rels = [{"via": r[0], "from": r[0] if r[1] == table_name else r[1], "to": r[1] if r[1] == table_name else r[0]} for r in rows]
        # 管道目标：target_object 存的是本体对象 code（如 coal_assay），也可能直接是表名，
        # 两种口径都要能落到这张表上（否则「表←管道」这条线在血缘里永远是空的）。
        pips = [{"name": p["name"], "source": p["source_table"]} for p in pipelines
                if p["target_object"] == table_name
                or (obmap.get(str(p["target_object"])) or "").upper() == table_name.upper()]
        # 依赖此表的对象(出向是其它对象, 入向是引用它)
        objs = await cls.list_objects()
        out_links = [{"object": o["table"], "alias": o.get("alias") or o["table"]} for o in objs if any(lk["target"] == table_name for lk in o.get("links", []))]
        return {
            "table": table_name, "fields": fields, "metrics": mets,
            "terms": rel_terms, "concepts": rel_concepts, "relations": rels,
            "pipelines": pips, "dependent_objects": out_links,
        }

    @classmethod
    async def lineage_propagate(cls, table_name: str, max_depth: int = 4) -> dict:
        """端到端影响传播：从表沿字段关联反向 BFS，找出所有受影响的下游表与指标。"""
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rows = (await db.execute(_t(
                "SELECT table_name, related_table FROM ai_query_asset_columns "
                "WHERE related_table IS NOT NULL AND related_table<>'' AND is_deleted=false"))).fetchall()
        reverse: dict[str, set[str]] = {}
        for r in rows:
            reverse.setdefault(r[1], set()).add(r[0])  # related -> 依赖它的表
        affected: set[str] = set()
        frontier = [table_name]
        visited = {table_name}
        depth = 0
        while frontier and depth < max_depth:
            nxt = []
            for cur in frontier:
                for up in reverse.get(cur, set()):
                    if up not in visited:
                        visited.add(up)
                        affected.add(up)
                        nxt.append(up)
            frontier = nxt
            depth += 1
        all_tables = {table_name} | affected
        metrics = await cls.list_metrics()
        obmap = await cls._object_backing_map()
        affected_metrics = []
        _seen: set = set()
        for m in metrics:
            hit = any(t in (m.get("sql_template") or "") for t in all_tables)
            if not hit:
                oc = m.get("object_code")
                if oc:
                    _t2 = (obmap.get(oc) or oc)
                    if any(_t2.upper() == t.upper() for t in all_tables):
                        hit = True
            if hit and m["key"] not in _seen:
                _seen.add(m["key"])
                affected_metrics.append(m)
        return {"root": table_name, "affected_tables": sorted(affected),
                "affected_count": len(affected),
                "affected_metrics": [{"key": m["key"], "name": m["name"]} for m in affected_metrics]}

    @classmethod
    async def impact_analysis(cls, table_name: str) -> dict:
        """P1-② 影响分析：哪些指标用到此表 + 哪些字段/对象关联它。"""
        metrics = await cls.list_metrics()
        obmap = await cls._object_backing_map()
        affected_metrics = []
        _seen: set = set()
        for m in metrics:
            hit = table_name in (m.get("sql_template") or "")
            if not hit:
                oc = m.get("object_code")
                if oc and (obmap.get(oc) or oc).upper() == table_name.upper():
                    hit = True
            if hit and m["key"] not in _seen:
                _seen.add(m["key"])
                affected_metrics.append(m)
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            cols = (await db.execute(_t(
                "SELECT column_name, related_table, related_field FROM ai_query_asset_columns "
                "WHERE related_table=:t AND is_deleted=false"), {"t": table_name})).fetchall()
        relations = [{"column": c[0], "from": c[1], "field": c[2]} for c in cols]
        objs = await cls.list_objects()
        obj_links = [o for o in objs if any(ln["target"] == table_name for ln in o.get("links", []))]
        # 血缘：只增字段，开关关闭时返回固定空结构（与改造前**完全一致**）。
        # 默认关的理由：血缘是新数据，先让人核对 3 张表再决定是否默认读它。
        from .lineage import lineage_for_table

        lineage_payload = dict(_svc.EMPTY_LINEAGE)
        try:
            if cls._cfg_bool(await cls._cfg(), "lineage_enabled", False):
                ds_code = await cls._table_ds_code(table_name) or "ds:4"
                lineage_payload = await lineage_for_table(ds_code, table_name.upper())
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 影响分析读血缘失败（返回空）: {str(e)[:100]}")
        return {
            "table": table_name,
            "lineage": lineage_payload,
            "metrics": [{"key": m["key"], "name": m["name"], "desc": m["description"]} for m in affected_metrics],
            "incoming_relations": relations,
            "object_links": [{"object": o["table"], "alias": o.get("alias") or o["table"]} for o in obj_links],
        }

    @classmethod
    async def governance_overview(cls) -> dict:
        """P3-⑩ 治理驾驶舱总览：一次聚合对象/源/管道/动作/权限/域/质量/预警/指标/概念/智能体/应用。"""
        objs = await cls._objects_light()
        ds = await cls.list_datasources()
        pips = await cls.list_pipelines()
        rules = await cls.list_access_rules()
        domains = await cls.list_domains()
        dq = await cls.dq_overview()
        alert = await cls.dq_alert()
        metrics = await cls.list_metrics()
        terms = await cls.list_terms()
        concepts = await cls.list_concepts()
        works = await cls.list_workshop_apps()
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            act = (await db.execute(_t(
                "SELECT count(*) FROM ai_query_writeback WHERE is_deleted=false"))).scalar() or 0
            act_logs = (await db.execute(_t(
                "SELECT count(*) FROM ai_query_writeback_log WHERE is_deleted=false"))).scalar() or 0
            agent = (await db.execute(_t(
                "SELECT count(*) FROM ai_agents WHERE is_deleted=false"))).scalar() or 0
        return {
            "objects": len(objs),
            "datasources": len(ds),
            "pipelines": len(pips),
            "actions": int(act), "action_logs": int(act_logs),
            "access_rules": len(rules),
            "domains": len(domains),
            "agents": int(agent),
            "workshop_apps": len(works),
            "metrics": len(metrics), "terms": len(terms), "concepts": len(concepts),
            "dq": {"avg_score": dq["avg_score"], "healthy": dq["healthy"],
                   "risk": dq["risk"], "total": dq["total_objects"]},
            "dq_alerts": alert["count"],
            "alert_list": alert["alerts"][:6],
            "dq_items": dq["items"],
            "pipeline_runs": [{"name": p["name"], "status": p["last_status"], "at": p["last_at"]}
                              for p in pips if p["last_status"]],
        }

    @classmethod
    async def asset_hotspots(cls) -> dict:
        """数据资产热点：按被指标引用次数(热度)排行数据资产。"""
        metrics = await cls.list_metrics(_svc.SYSTEM_DS)
        assets = await cls.list_assets()
        hot = []
        for a in assets:
            refs = sum(1 for m in metrics if a["table_name"] in (m.get("sql_template") or ""))
            hot.append({"table": a["table_name"], "alias": a["alias"],
                        "refs": refs, "dq": a.get("dq_score"),
                        "sensitive": a.get("sensitive_count") or 0,
                        "object": bool(a.get("object_enabled"))})
        hot.sort(key=lambda x: (-x["refs"], x["table"]))
        return {"total": len(hot), "hot": hot[:12]}

    @classmethod
    async def compass_search(cls, keyword: str) -> dict:
        """Compass 全局数据目录搜索：跨 数据资产表/本体对象/指标/术语 检索。"""
        kw = (keyword or "").strip()
        if not kw:
            return {"assets": [], "objects": [], "metrics": [], "terms": []}
        q = kw.lower()
        assets = []
        try:
            for a in await cls.list_assets():
                if q in (a["table_name"] or "").lower() or q in (a["alias"] or "").lower() or q in (a["description"] or "").lower():
                    assets.append({"table": a["table_name"], "alias": a["alias"], "domain": a["domain"]})
        except Exception:  # noqa: BLE001
            assets = []
        objects = []
        try:
            from app.plugin.module_ai.ontology.service import list_objects as _objs
            for o in await _objs():
                if q in (o["code"] or "").lower() or q in (o["name"] or "").lower():
                    objects.append({"code": o["code"], "name": o["name"]})
        except Exception:  # noqa: BLE001
            objects = []
        metrics = []
        try:
            for m in await cls.list_metrics(_svc.SYSTEM_DS):
                if q in (m["key"] or "").lower() or q in (m["name"] or "").lower():
                    metrics.append({"key": m["key"], "name": m["name"]})
        except Exception:  # noqa: BLE001
            metrics = []
        terms = []
        try:
            for t in await cls.list_terms(_svc.SYSTEM_DS):
                if q in (t["term"] or "").lower():
                    terms.append({"term": t["term"], "metric_key": t.get("metric_key")})
        except Exception:  # noqa: BLE001
            terms = []
        return {"assets": assets, "objects": objects, "metrics": metrics, "terms": terms}

    @classmethod
    async def kg_stats(cls) -> dict:
        """统一图谱统计：数据 schema 图节点/边 + 知识库图实体/关系。

        ``edges`` 取自 schema 图谱（``agno_kg._ensure()``），与「数据关系图」页
        ``unified_graph`` 实际渲染的边同源，保证「关系边」与图一致。
        （旧实现查 ``ai_query_asset_columns.related_table`` 且用 ``is_deleted=0``
        对布尔列比较，异常被吞掉导致恒为 0，与图谱不符。）
        """
        assets = await cls.list_assets()
        objs = [a for a in assets if a.get("object_enabled")]
        edges = 0
        try:
            from .agno_kg import _ensure as _kg_ensure
            edges = len((await _kg_ensure()).edges)
        except Exception:  # noqa: BLE001
            edges = 0
        entities = 0
        relations = 0
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                entities = (await db.execute(_t(
                    "SELECT COUNT(*) FROM ai_knowledge_entities WHERE is_deleted=false"))).scalar() or 0
                relations = (await db.execute(_t(
                    "SELECT COUNT(*) FROM ai_knowledge_relations WHERE is_deleted=false"))).scalar() or 0
        except Exception:  # noqa: BLE001
            entities = relations = 0
        return {"data_nodes": len(assets), "data_edges": int(edges),
                "nodes": len(assets), "edges": int(edges),
                "entities": int(entities), "relations": int(relations),
                "objects": len(objs)}

    @classmethod
    async def object_relations(cls) -> dict:
        """对象关系图：基于字段关联，构建业务对象之间的边（关系图可视化）。"""
        assets = await cls.list_assets()
        objs = {a["table_name"]: a for a in assets if a.get("object_enabled")}
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rows = (await db.execute(_t(
                "SELECT table_name, related_table FROM ai_query_asset_columns "
                "WHERE related_table IS NOT NULL AND related_table<>'' AND is_deleted=false"))).fetchall()
        edges: list[dict] = []
        seen = set()
        for r in rows:
            src, dst = r[0], r[1]
            if src in objs and dst in objs and (src, dst) not in seen:
                seen.add((src, dst))
                edges.append({"source": src, "target": dst, "label": f"{src}→{dst}"})
        nodes = [{"id": t, "label": objs[t].get("alias") or t,
                  "dq": objs[t].get("dq_score"), "sensitive": objs[t].get("sensitive_count") or 0}
                 for t in objs]
        return {"nodes": nodes, "edges": edges, "node_count": len(nodes), "edge_count": len(edges)}

    @classmethod
    async def object_lifecycle(cls) -> dict:
        """对象生命周期看板：对象总数/已发布/草稿/敏感/血缘 概览。"""
        assets = await cls.list_assets()
        objs = [a for a in assets if a.get("object_enabled")]
        published = 0
        try:
            for a in objs:
                rel = await cls.asset_releases(a["table_name"])
                if rel.get("published_version_id"):
                    published += 1
        except Exception:  # noqa: BLE001
            pass
        return {"objects": len(objs), "published": published,
                "draft": max(0, len(objs) - published),
                "sensitive_objects": sum(1 for a in objs if (a.get("sensitive_count") or 0) > 0),
                "total_lineage": sum(a.get("lineage_count") or 0 for a in objs),
                "objects_list": [{"table": a["table_name"], "alias": a["alias"],
                                  "dq": a.get("dq_score"), "sens": a.get("sensitive_count") or 0}
                                 for a in objs]}

    @classmethod
    async def _object_backing_map(cls) -> dict[str, str]:
        """对象编码 → 物理表（ai_ont_object.backing_table）。

        绑定型指标的 ``sql_template`` 是占位（不引用真实表），只能经 ``object_code``
        → 本体对象 → ``backing_table`` 才能连到物理表。这张映射是打通「表↔对象↔绑定指标」的关键。
        """
        # 走 semantic.py 的**唯一接口**：本体表不允许在问数里直连读
        # （`test_query_reads_ontology_only_through_interface` 会扫源码断言）。
        try:
            from app.plugin.module_ai.ontology import semantic as _sem

            return await _sem.object_backing_map()
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 读对象支撑表失败（忽略）: {str(e)[:80]}")
            return {}

    @classmethod
    async def _objects_light(cls) -> list[dict]:
        """轻量对象表：以**本体为唯一源**（与 list_objects 同源），只保留 table/alias/key/name。

        统一对象真相源后，治理/预警统计的对象与「对象列表」「对象查询白名单」完全一致。
        """
        objs = await cls.list_objects()
        return [
            {"table": o["table"], "alias": o["alias"],
             "key_col": o["key_col"], "name_col": o["name_col"]}
            for o in objs
        ]

    @classmethod
    async def _metric_value(cls, key: str):
        metrics = await cls.list_metrics(_svc.SYSTEM_DS)
        m = next((x for x in metrics if x["key"] == key), None)
        if not m or not m.get("sql_template"):
            return None
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                row = (await db.execute(_t(m["sql_template"]))).first()
                v = row[0] if row else None
                return float(v) if v is not None else None
        except Exception:  # noqa: BLE001
            return None
