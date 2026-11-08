"""本体：概念、图谱、对象解析（2026-11-08 从 service.py 拆出）。

这一组是「问数复用本体语义」的桥：概念（``list_concepts``）给提示词补充业务词汇，
图谱（``_knowledge_graph`` / ``_ont_*``）给上下文注入对象与关系，
``resolve_entity_object`` / ``list_objects`` 把「某台摄像机的告警」落到具体对象实例。

``_norm_datasource`` 仍留在 ``service.py``，这里延迟转发（导入期直接 import 会循环），
延迟导入也保证测试对 ``service._norm_datasource`` 的 monkeypatch 继续生效。
"""
from __future__ import annotations

import re

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log

#: 与 service 同值（搬移期间重复定义，避免循环导入）
SYSTEM_DS = "system"


async def _norm_datasource(datasource):
    """延迟转发到 service 的实现（service 导入期未就绪）。"""
    from .service import _norm_datasource as _impl

    return await _impl(datasource)


class OntologyOps:
    @classmethod
    async def _knowledge_graph(cls, kb_id: int) -> dict:
        """拉取知识库图谱（实体/关系），供统一图谱使用。"""
        try:
            from app.plugin.module_ai.knowledge.service import AiKnowledgeService

            return await AiKnowledgeService.get_graph(kb_id)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 知识库图谱获取失败 kb={kb_id}: {e}")
            return {"nodes": [], "edges": []}

    @classmethod
    async def _ensure_concept_table(cls) -> None:
        """业务概念表（无 Alembic 迁移时运行时建表）。"""
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_query_concept ("
                "id BIGSERIAL PRIMARY KEY, name VARCHAR(120) UNIQUE, description TEXT, "
                "synonyms TEXT, parent_name VARCHAR(120), domain VARCHAR(60), "
                "metric_key VARCHAR(80), tables JSONB, is_deleted BOOLEAN DEFAULT false, "
                "datasource VARCHAR(120), "
                "created_time TIMESTAMP DEFAULT now())"))
            await db.execute(_t(
                "ALTER TABLE ai_query_concept ADD COLUMN IF NOT EXISTS datasource VARCHAR(120)"))

    @classmethod
    async def list_concepts(cls, datasource: str | None = None) -> list[dict]:
        await cls._ensure_concept_table()
        datasource = await _norm_datasource(datasource)
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            sql = ("SELECT id,name,description,synonyms,parent_name,domain,metric_key,tables,datasource "
                   "FROM ai_query_concept WHERE is_deleted=false")
            params: dict = {}
            if datasource:
                sql += " AND datasource=:ds"
                params["ds"] = datasource
            sql += " ORDER BY id"
            res = await db.execute(_t(sql), params)
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "name": r[1], "description": r[2] or "", "synonyms": r[3] or "",
            "parent_name": r[4] or "", "domain": r[5] or "", "metric_key": r[6] or "",
            "tables": r[7] if isinstance(r[7], list) else (_json.loads(r[7]) if r[7] else []),
            "datasource": r[8] or "",
        } for r in rows]

    @classmethod
    async def upsert_concept(cls, data, auth) -> dict:
        await cls._ensure_concept_table()
        import json as _json
        tables = _json.dumps(data.get("tables") or [])
        name = (data.get("name") or "").strip()
        if not name:
            raise CustomException(msg="概念名称不能为空")
        ds = (data.get("datasource") or "").strip()
        ds = await _norm_datasource(ds) or ""
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            if data.get("id"):
                await db.execute(_t(
                    "UPDATE ai_query_concept SET name=:n, description=:d, synonyms=:s, "
                    "parent_name=:p, domain=:do, metric_key=:m, tables=:tb, datasource=:ds "
                    "WHERE id=:id AND is_deleted=false"),
                    {"n": name, "d": data.get("description", ""), "s": data.get("synonyms", ""),
                     "p": data.get("parent_name", ""), "do": data.get("domain", ""),
                     "m": data.get("metric_key", ""), "tb": tables, "ds": ds, "id": data["id"]})
            else:
                await db.execute(_t(
                    "INSERT INTO ai_query_concept(name, description, synonyms, parent_name, "
                    "domain, metric_key, tables, datasource) VALUES (:n,:d,:s,:p,:do,:m,:tb,:ds) "
                    "ON CONFLICT (name) DO UPDATE SET description=EXCLUDED.description, "
                    "synonyms=EXCLUDED.synonyms, parent_name=EXCLUDED.parent_name, "
                    "domain=EXCLUDED.domain, metric_key=EXCLUDED.metric_key, tables=EXCLUDED.tables, "
                    "datasource=EXCLUDED.datasource"),
                    {"n": name, "d": data.get("description", ""), "s": data.get("synonyms", ""),
                     "p": data.get("parent_name", ""), "do": data.get("domain", ""),
                     "m": data.get("metric_key", ""), "tb": tables, "ds": ds})
        return {"name": name}

    @classmethod
    async def delete_concepts(cls, ids: list[int]) -> int:
        await cls._ensure_concept_table()
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            await db.execute(_t(
                "UPDATE ai_query_concept SET is_deleted=true WHERE id IN :ids"),
                {"ids": list(ids)})
        return len(ids)

    @classmethod
    async def _ont_ctx_block(cls, only_tables: set[str] | None = None) -> str:
        """本体语义块（对象 + 属性 + 函数 + **关系**）。

        **改为调用本体的统一语义接口** ``semantic.context_block()``：
        语义只留本体那一份，问数不再自己拼 ``ai_ont_*`` 的 SQL。

        ``only_tables`` 传检索命中的表 → 只带这几张表的语义（实测 37517 → 千余字符）。
        """
        from app.plugin.module_ai.ontology import semantic as _sem

        return await _sem.context_block(only_tables=only_tables)

    @classmethod
    async def _ont_rel_block(cls, objs: dict) -> list[str]:
        """保留旧签名（有测试/调用方依赖），改为从统一接口取关系。"""
        from app.plugin.module_ai.ontology import semantic as _sem

        ctx = await _sem.semantic_context(include_properties=False)
        out = ["【本体关系（写多表查询时按此 join，不要靠字段名猜）】"]
        for r in ctx["relations"]:
            s, t = objs.get(r["source"]), objs.get(r["target"])
            if not s or not t:
                continue
            st = s.get("table") or r["source"]
            tt = t.get("table") or r["target"]
            line = f"- 「{s['name']}」{st}"
            if r["source_field"] and r["target_field"]:
                line += f".{r['source_field']} = 「{t['name']}」{tt}.{r['target_field']}"
            else:
                line += f" ↔ 「{t['name']}」{tt}（{r['join_method']}）"
            if r["name"]:
                line += f"   关系名：{r['name']}"
            if r["card"]:
                line += f"，基数：{r['card']}"
            out.append(line)
        return out if len(out) > 1 else []

    @classmethod
    async def _concept_context(cls) -> str:
        """把业务概念注入 prompt 上下文：概念+描述+同义词+映射。"""
        # 概念也走本体统一语义接口（本体对象的别名/域 + 问数概念表，合并成一份）
        from app.plugin.module_ai.ontology import semantic as _sem

        cs = await _sem.concepts()
        if not cs:
            return ""
        lines = ["【业务概念(本体)】"]
        for c in cs:
            line = f"- {c['name']}"
            if c.get("description"):
                line += f": {c['description']}"
            if c.get("synonyms"):
                line += f"（同义:{c['synonyms']}）"
            if c.get("domain"):
                line += f"[{c['domain']}]"
            if c.get("metric_key"):
                line += f"→指标:{c['metric_key']}"
            if c.get("tables"):
                line += f"→表:{','.join(c['tables'])}"
            lines.append(line)
        return "\n".join(lines)

    @classmethod
    async def _ont_objs(cls) -> dict:
        """本体对象 → dict。**改为走本体的统一语义接口**，不再自己拼 SQL。

        历史上这里直连 ``ai_ont_object``，本体表结构一改就可能悄悄坏掉
        （"看起来接上了，实际靠约定"）。语义只留本体那一份。
        """
        from app.plugin.module_ai.ontology import semantic as _sem

        ctx = await _sem.semantic_context(include_properties=False)
        return {o["code"]: {"code": o["code"], "name": o["name"],
                            "key_prop": o["key_prop"], "name_prop": o["name_prop"],
                            "description": o["description"],
                            # table 是**真实支撑表名**（数据源支撑的对象就叫它自己）
                            "table": o["table"]} for o in ctx["objects"]}

    @classmethod
    async def _ont_props(cls, code: str) -> list[dict]:
        """某个对象的属性（含敏感/角色）。走统一语义接口。"""
        from app.plugin.module_ai.ontology import semantic as _sem

        ctx = await _sem.semantic_context()
        return [{"code": p["code"], "prop_type": p["prop_type"],
                 "sensitive": p["sensitive"], "roles": p["roles"]}
                for p in ctx["properties"].get(code, [])]

    @classmethod
    async def _ont_links(cls, code: str) -> list[tuple]:
        """某个对象的一跳关系。走统一语义接口。"""
        from app.plugin.module_ai.ontology import semantic as _sem

        ctx = await _sem.semantic_context(include_properties=False)
        return [(r["target"], r["source_field"], r["target_field"], r["name"])
                for r in ctx["relations"] if r["source"] == code]

    @classmethod
    async def _resolve_ont_entity(cls, entity: str, key: str, user_id: int | None = None) -> dict | None:
        """本体对象 grounding：先按本体对象类型匹配，再按本体属性/Link 解析实例（Palantir 式）。"""
        from sqlalchemy import text as _t
        objs = await cls._ont_objs()
        match = None
        for o in objs.values():
            if o["name"] and (o["name"] in entity or entity in o["name"]):
                match = o
                break
            if o["code"] and o["code"].replace("_", "") in entity.replace("_", ""):
                match = o
                break
        if not match:
            return None
        code = match["code"]
        # 用**真实支撑表名**：这里原先硬拼 ont_{code}，而数据源支撑的对象
        # 表名就是它自己（video_cameras），拼错会去查一张不存在的表
        table = match.get("table") or code
        props = await cls._ont_props(code)
        name_prop, key_prop = match["name_prop"], match["key_prop"]
        try:
            async with async_db_session() as db:
                row = (await db.execute(_t(
                    f'SELECT * FROM "{table}" WHERE "{name_prop}" ILIKE :k LIMIT 1'), {"k": f"%{key}%"})).mappings().first()
                if row is None:
                    row = (await db.execute(_t(
                        f'SELECT * FROM "{table}" WHERE "{key_prop}" = :k LIMIT 1'), {"k": key})).mappings().first()
        except Exception as e:  # noqa: BLE001
            return {"entity": entity, "ontology": code, "table": table,
                    "error": "本体对象尚未物化为表或查询失败", "hint": "请在【本体】页对该对象执行「物化为表」", "detail": str(e)[:80]}
        if not row:
            return {"entity": entity, "ontology": code, "table": table,
                    "error": f"在本体对象 {table} 未找到「{key}」"}
        can_see = await cls._can_see_sensitive(user_id)
        obj = {}
        restricted = []
        for p in props:
            if p["sensitive"] and not can_see:
                continue
            # 属性级 ACL：roles 非空且不含 'all'/'public' 时，非超管需角色匹配才可见
            if p.get("roles") and not can_see:
                allowed = set(p["roles"])
                if not (allowed & {"all", "public"}):
                    restricted.append(p["code"])
                    continue
            v = row.get(p["code"])
            obj[p["code"]] = str(v) if not isinstance(v, (int, float, bool)) else v
        related: list[dict] = []
        for tgt, sfield, tfield, lname in await cls._ont_links(code):
            tgt_table = f"ont_{tgt}"
            fval = row.get(sfield)
            try:
                async with async_db_session() as db:
                    trow = (await db.execute(_t(
                        f'SELECT * FROM "{tgt_table}" WHERE "{tfield}" = :k LIMIT 1'), {"k": fval})).mappings().first()
            except Exception:  # noqa: BLE001
                trow = None
            tname = (trow.get("name") if trow else None)
            related.append({"relation": lname or f"{code}→{tgt}", "entity": tgt, "key": fval,
                            "name": tname,
                            "target": {k: (str(v) if not isinstance(v, (int, float, bool)) else v) for k, v in trow.items()} if trow else None})
        return {"entity": entity, "ontology": code, "table": table, "object": obj, "related": related}

    @classmethod
    async def resolve_entity_object(cls, entity: str, key: str, datasource: str = SYSTEM_DS,
                                    user_id: int | None = None) -> dict | None:
        """P0·对象 grounding：把业务实体名(如「摄像头/订单」)+ 关键值解析为真实对象及关联邻居。

        返回 ``{entity, table, object:{列:值}, related:[{relation, entity, ...}]}``，供
        Agent/问数作为 grounded context 注入模型（对标 Palantir AIP grounding）。

        ABAC：非超管按敏感字段策略过滤敏感列（object 中剔除标记为 sensitive 的字段）。
        """
        from sqlalchemy import text as _t

        # 优先：本体对象 grounding（Palantir 式）
        try:
            ont_res = await cls._resolve_ont_entity(entity, key, user_id)
            if ont_res:
                return ont_res
        except Exception:  # noqa: BLE001
            pass

        schema = await cls._system_schema()
        tmeta = await cls._asset_tmeta()
        entity = (entity or "").strip()
        key = (key or "").strip()
        if not entity or not key:
            return None
        # 1) 候选表：实体名词映射 + 中文名/别名/表名包含
        cand: list[str] = []
        from .service import _ENTITY_TABLE

        for noun, tables in _ENTITY_TABLE.items():
            if noun in entity or entity in noun:
                cand.extend(tables)
        for t in schema:
            meta = tmeta.get(t) or {}
            if (meta.get("alias") and meta["alias"] in entity) or (
                meta.get("description") and entity in meta["description"]
            ):
                cand.append(t)
            if t and t.replace("_", "") in entity.replace("_", ""):
                cand.append(t)
        cand = list(dict.fromkeys(c for c in cand if c in schema))
        if not cand:
            return None
        # 2) 选主表：优先含 name/title 列且非分组/日志/事件类的实体表

        def labels_of(t: str) -> list[str]:
            return schema.get(t) or []
        has_name = [t for t in cand if any(lab.split("(")[0] in ("name", "title", "label") for lab in labels_of(t))]
        prefer = [t for t in has_name if not any(x in t for x in ("group", "groups", "task", "logs", "records", "events", "call_logs"))]
        table = (prefer or has_name or cand)[0]
        labels = schema.get(table) or []
        id_col = next((lab.split("(")[0] for lab in labels if lab.split("(")[0] == "id"), None) or (labels[0].split("(")[0] if labels else "")
        name_col = next((lab.split("(")[0] for lab in labels if lab.split("(")[0] in ("name", "title", "label")), None)
        # 3) 解析关联：字段名 -> 关联表.关联字段
        rel_re = re.compile(r"【关联:([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)】")
        rel_cols: list[tuple[str, str, str]] = []
        for lab in labels:
            col = lab.split("(")[0]
            m = rel_re.search(lab)
            if m:
                rel_cols.append((col, m.group(1), m.group(2)))
        # 4) 取对象行：优先按 name 匹配，否则按 id
        try:
            async with async_db_session() as db:
                cond = f'"{name_col}" ILIKE :k' if name_col else f'"{id_col}" = :k'
                row = (await db.execute(_t(
                    f'SELECT * FROM "{table}" WHERE {cond} LIMIT 1'), {"k": f"%{key}%"})).mappings().first()
                if row is None and name_col:
                    row = (await db.execute(_t(
                        f'SELECT * FROM "{table}" WHERE "{id_col}" = :k LIMIT 1'), {"k": key})).mappings().first()
                if row is None and id_col:
                    row = (await db.execute(_t(
                        f'SELECT * FROM "{table}" WHERE "{id_col}" = :k LIMIT 1'), {"k": key})).mappings().first()
        except Exception as e:  # noqa: BLE001
            return {"entity": entity, "table": table, "error": str(e)[:120], "related": []}
        if row is None:
            return {"entity": entity, "table": table, "object": None, "related": []}
        obj = {k: (str(v) if not isinstance(v, (int, float, bool)) else v) for k, v in row.items()}
        # ABAC：非超管过滤敏感字段
        try:
            if not await cls._can_see_sensitive(user_id):
                async with async_db_session() as db:
                    sens = (await db.execute(_t(
                        "SELECT column_name FROM ai_query_asset_columns WHERE table_name=:t AND sensitive=true AND is_deleted=false"),
                        {"t": table})).fetchall()
                sens_set = {s[0] for s in sens}
                if sens_set:
                    obj = {k: v for k, v in obj.items() if k not in sens_set}
        except Exception:  # noqa: BLE001
            pass
        # 5) 关联邻居：对每条关联字段取值，取关联表 name 列
        related: list[dict] = []
        try:
            async with async_db_session() as db:
                for col, rt, rf in rel_cols[:6]:
                    val = obj.get(col)
                    if val is None:
                        continue
                    rt_labels = schema.get(rt) or []
                    rname_col = next((lab.split("(")[0] for lab in rt_labels
                                      if lab.split("(")[0] in ("name", "title", "label")), rf)
                    rr = (await db.execute(_t(
                        f'SELECT * FROM "{rt}" WHERE "{rf}" = %(v)s LIMIT 1'), {"v": val})).mappings().first()
                    if rr:
                        related.append({
                            "relation": col,
                            "entity": rt,
                            "name": str(rr.get(rname_col) or rr.get("id")),
                            "summary": f"{rt}#{str(rr.get(rname_col) or rr.get('id'))}",
                        })
        except Exception:  # noqa: BLE001
            pass
        return {"entity": entity, "table": table, "object": obj, "related": related}

    @classmethod
    async def list_objects(cls) -> list[dict]:
        """业务对象(Object Type)：**以本体为唯一真相源**（``ai_ont_object``，enabled 且可解析支撑表）。

        与「对象查询白名单」（``_allowed_objects_for_query`` → ``semantic.semantic_context``）**同源**，
        消除"对象列表里有、对象查询却不认"的断层。

        - 未纳入本体的表**不再出现在对象列表**（仍可用自然语言 NL2SQL 查询）；
          在「表与字段」勾选「纳入本体对象」即可把表纳入本体并出现在此列表。
        - Link 来自本体关系类型（``ai_ont_link``），按 object_code → 支撑表映射。
        """
        from app.plugin.module_ai.ontology import semantic as _sem

        try:
            ctx = await _sem.semantic_context(include_properties=False)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] list_objects 读取本体语义失败：{str(e)[:100]}")
            return []
        objs = [o for o in (ctx.get("objects") or []) if o.get("table")]
        # 关系解析用「去重前」的全量编码 → 支撑表映射：本体里仍可能有指向原始对象编码
        # （如 FUEL_CMCS_ASSAY）的关系，去重后不能把这类关系丢掉。
        code2table = {str(o.get("code")): o.get("table") for o in objs}
        # 同一张支撑表可能同时挂「语义对象」（coal_assay，带数据源归属）与
        # 「按表导入的原始对象」（FUEL_CMCS_ASSAY，datasource_id=0）——去重，
        # 优先保留有数据源归属、且编码为语义编码（小写）的那个，避免对象列表/DQ 出现重复对象。
        by_table: dict[str, dict] = {}
        for o in objs:
            t = str(o.get("table"))
            cur = by_table.get(t)
            if cur is None:
                by_table[t] = o
                continue
            new_score = (int(o.get("datasource_id") or 0) > 0, str(o.get("code") or "").islower())
            cur_score = (int(cur.get("datasource_id") or 0) > 0, str(cur.get("code") or "").islower())
            if new_score > cur_score:
                by_table[t] = o
        objs = list(by_table.values())
        relations = ctx.get("relations") or []
        out = []
        for o in objs:
            links = []
            for r in relations:
                if str(r.get("source")) == str(o.get("code")) and code2table.get(
                    str(r.get("target"))
                ):
                    links.append({
                        "target": code2table[str(r.get("target"))],
                        "via": r.get("source_field") or "",
                        "target_field": r.get("target_field") or "",
                    })
            out.append({
                "table": o.get("table"),
                "alias": o.get("name") or o.get("table"),
                "key_col": o.get("key_prop") or "id",
                "name_col": o.get("name_prop") or "name",
                "icon": "el-icon-Box",
                "ont_code": o.get("code") or "",
                "datasource_id": int(o.get("datasource_id") or 0),
                "links": links,
            })
        return out
