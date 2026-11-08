"""本体桥：上下文注入、字段级 ACL、导入与治理（2026-11-08 从 service.py 拆出）。

- ``_object_context_block``：把「当前对象」确定性地注入提示词（对齐 Palantir Retrieval Context）；
- ``_context_principal``：把请求身份转成策略引擎的 Principal（裁剪与判定共用）；
- ``_ont_sql_violations``：字段级 ACL 兜底（本体属性 → 可读列）；
- ``_import_ont_table_core`` / ``semantic_extract_objects`` / ``infer_asset_relations``：
  外部表导入本体、从语义层抽取对象、推断表间关系；
- ``ontology_governance``：本体治理看板（孤儿对象、未绑定属性等）。
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.core.database import async_db_session

from . import service as _svc
from .filtering import DEFAULT_FILTER_RULES, is_audit_field, is_system_table
from .model import AiQueryAssetColumnModel, AiQueryAssetModel
from .schema import QueryAssetUpsert


class OntBridgeOps:
    @classmethod
    async def semantic_extract_objects(cls) -> dict:
        """P1-③ 语义抽取/消歧：只把**真实业务实体**表（_svc._ENTITY_TABLE 映射集）标记为业务对象，
        并把非业务表（内部/平台表）取消对象标记（收窄去噪）。"""
        business: set[str] = set().union(*_svc._ENTITY_TABLE.values()) if _svc._ENTITY_TABLE else set()
        schema = await cls._system_schema()
        # 1) 取消非业务表的对象标记（收窄）
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            res = await db.execute(_t(
                "SELECT table_name FROM ai_query_assets WHERE object_enabled=true AND is_deleted=false"))
            marked = res.fetchall()
        narrowed = 0
        for row in marked:
            if row[0] not in business:
                async with async_db_session.begin() as db:
                    from sqlalchemy import text as _t
                    await db.execute(_t(
                        "UPDATE ai_query_assets SET object_enabled=false WHERE table_name=:t AND is_deleted=false"),
                        {"t": row[0]})
                narrowed += 1
        # 2) 为业务实体表标记对象
        created = 0
        aliases: list[dict] = []
        for t in business:
            if t not in schema:
                continue
            labels = schema.get(t) or []
            cols = [lab.split("(")[0] for lab in labels]
            if "id" not in cols:
                continue
            name_col = next((c for c in ("name", "title", "label") if c in cols), None)
            alias = next((n for n, ts in _svc._ENTITY_TABLE.items() if t in ts), t)
            meta = (await cls._asset_tmeta()).get(t) or {}
            await cls.upsert_asset(QueryAssetUpsert(
                table_name=t, alias=meta.get("alias") or alias,
                domain=meta.get("domain") or "", description=meta.get("description") or "",
                business_scenarios=meta.get("business_scenarios") or "",
                included=True, remark="", object_enabled=True,
                object_key_col="id", object_name_col=name_col or "name",
                object_icon="el-icon-Box"), SimpleNamespace(user=SimpleNamespace(id=1)))
            created += 1
            aliases.append({"table": t, "alias": alias, "name_col": name_col or "id",
                            "synonyms": [n for n, ts in _svc._ENTITY_TABLE.items() if t in ts]})
        return {"extracted": created, "narrowed": narrowed, "aliases": aliases}

    @classmethod
    async def _ont_sql_violations(cls, sql: str, user_id: int | None) -> list[str]:
        """问数 SQL 的字段级 ACL：检测是否查询了用户无权限的敏感/受限字段。

        覆盖：本体物化表（ont_*，敏感/受限属性）+ 业务表（字段资产标记 sensitive 的列）。
        用 sqlglot 精确提取查询列，避免正则误报（别名/字符串）。非超管（无 sensitive 权限）时生效。
        """
        if not sql:
            return []
        if await cls._can_see_sensitive(user_id):
            return []
        tables, cols = await cls._sql_query_scope(sql)
        if not tables:
            return []
        restricted: list[tuple[str, str]] = []
        for table in tables:
            base = table.split(".")[-1]
            if base.startswith("ont_"):
                code = base[len("ont_"):]
                props = await cls._ont_props(code)
                for p in props:
                    if p["sensitive"] or (p.get("roles") and not ({"all", "public"} & set(p["roles"]))):
                        restricted.append((base, p["code"]))
            else:
                for c in await cls._sensitive_asset_cols(base):
                    restricted.append((base, c))
        violations = [f"{t}.{c}" for t, c in restricted if c in cols]
        return list(dict.fromkeys(violations))

    @classmethod
    async def ontology_governance(cls) -> dict:
        """本体对象治理：每个本体对象的 来源(管道)/下游(指标/概念/对象)/数据质量分（按本体对象/属性）。"""
        objs = await cls._ont_objs()
        if not objs:
            return {"items": []}
        pipelines = await cls.list_pipelines()
        metrics = await cls.list_metrics()
        concepts = await cls.list_concepts()
        from datetime import datetime, timezone
        items = []
        for code, o in objs.items():
            table = f"ont_{code}"
            props = await cls._ont_props(code)
            name_prop = o.get("name_prop") or "name"
            rows = score = 0
            comp = uniq = fresh = 0.0
            issues = []
            try:
                async with async_db_session() as db:
                    from sqlalchemy import text as _t
                    total = (await db.execute(_t(f'SELECT count(*) FROM "{table}"'))).scalar() or 0
                    rows = total
                    if total and name_prop in [p["code"] for p in props] or True:
                        try:
                            name_null = (await db.execute(_t(
                                f'SELECT count(*) FROM "{table}" WHERE "{name_prop}" IS NULL'))).scalar() or 0
                            name_dist = (await db.execute(_t(
                                f'SELECT count(DISTINCT "{name_prop}") FROM "{table}"'))).scalar() or 0
                            comp = round(100 - (name_null / total * 100), 1) if total else 0
                            uniq = round(name_dist / total * 100, 1) if total else 0
                            if name_null / total > 0.05 if total else False:
                                issues.append(f"{name_prop} 空值率 {round(name_null / total * 100, 1)}%")
                            if name_dist < total:
                                issues.append(f"{name_prop} 有 {total - name_dist} 条重复")
                        except Exception:  # noqa: BLE001
                            comp = uniq = 0
                        ts = None
                        for c in ("updated_time", "created_time"):
                            try:
                                ts = (await db.execute(_t(f'SELECT max({c}) FROM "{table}"'))).scalar()
                                if ts:
                                    break
                            except Exception:  # noqa: BLE001
                                ts = None
                        if not ts:
                            fresh = 0.0
                            issues.append("无时间列/新鲜度未知")
                        else:
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=timezone.utc)
                            days = max(0, (datetime.now(timezone.utc) - ts).days)
                            fresh = round(max(0.0, 100 - days * 5), 1)
                        score = round(comp * 0.4 + uniq * 0.3 + fresh * 0.3, 1)
            except Exception:  # noqa: BLE001
                issues.append("对象表未物化")
            src_pipes = [p["name"] for p in pipelines if p["target_object"] == table or p["target_object"] == code]
            down_metrics = [m["name"] for m in metrics if table in (m.get("sql_template") or "")]
            down_concepts = [c["name"] for c in concepts if table in (c.get("tables") or [])]
            items.append({
                "ontology": code, "name": o["name"], "table": table,
                "rows": rows, "score": score, "completeness": comp, "uniqueness": uniq, "freshness": fresh,
                "issues": issues, "source_pipelines": src_pipes,
                "downstream_metrics": down_metrics, "downstream_concepts": down_concepts,
            })
        avg = round(sum((x["score"] or 0) for x in items) / len(items), 1) if items else 0
        return {"avg_score": avg, "items": items}

    @staticmethod
    async def _import_ont_table_core(datasource_id: int, table: str, cols: list[dict],
                                     table_comment: str = "", domain_code: str = "",
                                     rules: dict | None = None) -> dict:
        """把一张表的列结构写成「本体对象 + 属性 + 物化表」。

        幂等：对象按 code upsert（并复活软删对象），属性**先清后建**，
        因此重复导入同一张表不会像旧实现那样累加重复属性。

        - ``domain_code``：目标域编码，写到 ``ai_ont_object.domain_code``；
        - ``rules``：该数据源自定义 ``filter_rules``，用于 ``is_business`` 判定
          （对象按 ``is_system_table``、属性按 ``is_audit_field``）；
          为空/未配置时回退缺省规则，保持既有行为。
        - ``is_business``：对象按 ``is_system_table(table, rules)`` 判定（系统表→false），
          属性按 ``is_audit_field(cname, rules)`` 判定（审计字段→false）。
        """
        from sqlalchemy import text as _t

        # 用该数据源的自定义规则（与集成页打标口径一致），为空时回退缺省规则
        rules = rules or DEFAULT_FILTER_RULES
        obj_is_business = not is_system_table(table, rules)
        col_names = [c["name"] for c in cols]
        # 主键：有 id 用 id，否则退化为首列（保证 grounding 有键可用）
        key_prop = "id" if "id" in col_names else col_names[0]
        name_prop = key_prop
        for c in cols:
            if str(c["name"]).lower() in ("name", "title", "no"):
                name_prop = c["name"]
                break

        def _pg_type(ctype) -> str:
            """SQL 类型 → 本体属性类型。"""
            t = str(ctype or "").lower()
            if "bool" in t:
                return "boolean"
            if any(k in t for k in ("int", "float", "decimal", "numeric", "double", "real", "serial")):
                return "number"
            if any(k in t for k in ("date", "time")):
                return "date"
            if "json" in t:
                return "json"
            return "string"

        # **中文注释就是语义**：真实业务库表/列名多是英文缩写
        # （FUEL_CB_COALBALANCE / COALMONEY），注释（"燃煤采购结算主表" / "煤款金额"）
        # 是"人话 → 字段"唯一的桥。旧实现拿英文列名同时当 code 和 name，
        # 本体里零中文语义，问数只能瞎猜（实测编出 coal_amount 这种不存在的列）。
        obj_name = (table_comment or "").strip() or table
        prop_names = {}
        for c in cols:
            cname = c["name"]
            label = str(c.get("comment") or "").strip()
            # 注释跟列名一样（如 ID 的注释就是 "ID"）时没有信息量，不如用列名
            prop_names[cname] = label if label and label.lower() != cname.lower() else cname

        async with async_db_session.begin() as db:
            # **必须记下"数据在哪"**：`datasource_id` 指向远端数据源、
            # `backing_table` 是远端真实表名。旧实现两个都不写，于是本体只知道
            # "有这么个对象"，问数不知道去哪儿查数据——本地那张 ont_{table}
            # 只是**空结构镜像**，查出来永远是 0 行。
            await db.execute(_t(
                "INSERT INTO ai_ont_object(code,name,key_prop,name_prop,description,"
                "enabled,is_deleted,datasource_id,backing_table,domain_code,is_business) "
                "VALUES (:c,:n,:k,:np,:d,true,false,:ds,:bt,:dc,:ib) "
                "ON CONFLICT (code) DO UPDATE SET name=:n, key_prop=:k, name_prop=:np, "
                "description=:d, is_deleted=false, datasource_id=:ds, "
                "backing_table=:bt, domain_code=:dc, is_business=:ib, updated_time=now()"),
                {"c": table, "n": obj_name, "k": key_prop, "np": name_prop,
                 "ds": datasource_id, "bt": table,
                 "dc": domain_code, "ib": obj_is_business,
                 "d": f"由数据源 {datasource_id} 的表 {table} 导入"})
            await db.execute(_t("DELETE FROM ai_ont_property WHERE object_code=:c"), {"c": table})
            for c in cols:
                cname = c["name"]
                col_is_business = not is_audit_field(cname, rules)
                await db.execute(_t(
                    "INSERT INTO ai_ont_property(object_code,name,code,prop_type,sensitive,"
                    "description,is_business) "
                    "VALUES (:oc,:n,:c,:pt,:s,:d,:ib)"),
                    {"oc": table, "n": prop_names[cname], "c": cname,
                     "pt": _pg_type(c.get("type")),
                     "s": bool(c.get("is_sensitive")),
                     "d": str(c.get("comment") or f"来自 {table}.{cname}")[:255],
                     "ib": col_is_business})

        # 物化建表 ont_{table}：已存在则补列，绝不删已有数据
        # 跳过 id 列：它已作为自增主键声明，再作为普通列声明会报
        # "column specified more than once"（旧实现因此从未建成任何物化表）。
        extra_cols = list(dict.fromkeys(c for c in col_names if c.lower() != "id"))
        cols_ddl = ", ".join(f'"{c}" TEXT' for c in extra_cols)
        ddl = f'CREATE TABLE IF NOT EXISTS "ont_{table}" (id BIGSERIAL PRIMARY KEY'
        if cols_ddl:
            ddl += f", {cols_ddl}"
        ddl += ")"
        try:
            async with async_db_session.begin() as db:
                await db.execute(_t(ddl))
                for c in extra_cols:
                    await db.execute(_t(f'ALTER TABLE "ont_{table}" ADD COLUMN IF NOT EXISTS "{c}" TEXT'))
            m = {"ok": True, "table": f"ont_{table}", "columns": extra_cols}
        except Exception as e:  # noqa: BLE001
            m = {"ok": False, "msg": str(e)[:60]}
        # 本体对象/支撑表变了 ⇒ 「可查询白名单」缓存立即失效（否则必须重启后端才问得到）
        _svc.invalidate_ont_allow_cache()
        return {"ok": True, "object": table, "props": len(cols), "materialize": m}

    @classmethod
    async def infer_asset_relations(cls, auth) -> dict:
        """根据字段名特征自动推断「关联表/关联字段」，填充资产元数据。

        规则：形如 ``xxx_id / xxx_ids / xxx_code / xxx_uuid`` 的字段，
        取 ``xxx`` 前缀在已纳入表中匹配实体表（表名包含该前缀），
        关联字段取目标表的主键/同名列。
        """
        global _SCHEMA_CACHE, _SEMANTIC_INDEX, _ASSET_TMETA
        async with async_db_session() as db:
            from sqlalchemy import select

            tables = (
                await db.execute(
                    select(AiQueryAssetModel).where(
                        AiQueryAssetModel.is_deleted.is_(False),
                        AiQueryAssetModel.included.is_(True),
                    )
                )
            ).scalars().all()
            cols = (
                await db.execute(
                    select(AiQueryAssetColumnModel).where(
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                        AiQueryAssetColumnModel.included.is_(True),
                    )
                )
            ).scalars().all()
        table_names = {t.table_name for t in tables}
        table_cols: dict[str, set[str]] = {}
        for c in cols:
            table_cols.setdefault(c.table_name, set()).add(c.column_name)

        def _suggest(colname: str):
            low = colname.lower()
            for pat in (r"^(.+?)_(ids?)$", r"^(.+?)_(code)$", r"^(.+?)_(uuid)$"):
                m = re.match(pat, low)
                if not m:
                    continue
                prefix = m.group(1)
                suffix = m.group(2)
                target = None
                for t in table_names:
                    tl = t.lower()
                    if prefix == tl or prefix in tl.split("_") or (len(prefix) >= 3 and prefix in tl):
                        target = t
                        break
                if not target:
                    continue
                relfield = "id"
                tc = table_cols.get(target, set())
                if suffix == "code" and "code" in tc:
                    relfield = "code"
                elif suffix == "uuid" and "uuid" in tc:
                    relfield = "uuid"
                elif "id" in tc:
                    relfield = "id"
                elif tc:
                    relfield = next(iter(tc))
                return target, relfield
            return None

        updated = 0
        async with async_db_session.begin() as db:
            for c in cols:
                if c.related_table and c.related_field:
                    continue
                sug = _suggest(c.column_name)
                if not sug:
                    continue
                rt, rf = sug
                existing = await db.get(AiQueryAssetColumnModel, c.id)
                if existing:
                    existing.related_table = rt
                    existing.related_field = rf
                    existing.updated_id = auth.user.id
                    updated += 1
        _SCHEMA_CACHE = None
        _SEMANTIC_INDEX = None
        _ASSET_TMETA = None
        return {"relations": updated}

    @classmethod
    async def _object_context_block(cls, object_code: str | None, object_key: str | None,
                                    auth) -> str:
        """渲染「当前对象」上下文块（**确定性**注入，不调 LLM）。

        对齐 Palantir Retrieval Context 的 Fixed Object Set：用户在某个对象上提问时，
        系统**自动**把它带给模型，用户不必重复说明「我说的是哪台摄像机」。

        取不到（对象不存在 / 未物化 / 无权限）→ 返回空串：**不报错、不阻断**。
        """
        code = (object_code or "").strip()
        if not code:
            return ""
        from app.plugin.module_ai.ontology import security as _ont_sec
        from app.plugin.module_ai.ontology import service as ont

        uid = getattr(getattr(auth, "user", None), "id", None)
        try:
            principal = await _ont_sec.load_principal(uid)
        except Exception:  # noqa: BLE001
            principal = None
        try:
            meta = await ont._instance_meta(code)
        except Exception:  # noqa: BLE001
            return ""
        if not meta or meta.get("error") or not meta.get("materialized"):
            return ""
        if principal is not None:
            try:
                ok, _why = await _ont_sec.can_view_resource("object", code, principal)
                if not ok:
                    return ""
            except Exception:  # noqa: BLE001
                pass
        name = meta.get("name") or code
        if not object_key:
            return f"【当前对象】{name}（{code}）：用户正在该对象上提问（未指定具体实例）。"
        try:
            inst = await ont.instance_get(code, str(object_key), principal=principal)
        except Exception:  # noqa: BLE001
            return ""
        if not inst.get("ok"):
            return ""
        props = inst.get("props") or {}
        np_ = meta.get("name_prop")
        title = str(props.get(np_) or "") if np_ else ""
        # 只带关键属性并截断：上下文块必须**小**，否则会吃掉 prompt 预算
        keys = [k for k in props
                if k not in ("password", "rtsp_url_main", "rtsp_url_sub")][:8]
        parts = [f"{k}={props.get(k)}" for k in keys if props.get(k) not in (None, "")]
        line = f"【当前对象】{name} #{object_key}" + (f"（{title}）" if title else "")
        if parts:
            line += "：" + "；".join(parts)
        names: list[str] = []
        for x in (inst.get("links") or [])[:6]:
            if isinstance(x, dict):
                nm_ = x.get("name") or x.get("link_name") or x.get("source_name") or ""
                if nm_:
                    names.append(str(nm_))
        if names:
            line += "。可用关系：" + "、".join(names)
        return line

    @classmethod
    async def _context_principal(cls, auth):
        """把 auth 解析成上下文投影用的 Principal；失败返回 None（不裁剪，执行期仍兜底）。"""
        if auth is None:
            return None
        try:
            from app.plugin.module_ai.query.policy.principal import load_principal
            return await load_principal(auth, entry="ask")
        except Exception:  # noqa: BLE001 - 裁剪失败不该阻断问数
            return None
