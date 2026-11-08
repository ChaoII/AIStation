"""工作台、数据域、分享与字典（2026-11-08 从 service.py 拆出）。

- ``workshop_*``：无代码应用（数据集 + 图表 + 提交审核）；
- ``domain_*`` / ``upsert_domain``：数据域（成员 + 表范围）与对账，是权限收窄的入口；
- ``share_*``：数据集分享（只读副本）；
- ``dl_*``：数据字典条目；
- ``catalog_categories`` / ``concepts_mapping``：目录与概念映射。
"""
from __future__ import annotations

from sqlalchemy import text

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from . import service as _svc
from .model import AiQueryAssetColumnModel


class WorkspaceOps:
    @classmethod
    async def workshop_objects(cls) -> list[dict]:
        """对象应用可选的业务对象 + 字段（供「新建应用」表单选择）。"""
        objs = await cls.list_objects()
        async with async_db_session() as db:
            from sqlalchemy import select as _sel
            from sqlalchemy import text as _t
            col_rows = (await db.execute(_t(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema='public' ORDER BY table_name, ordinal_position"))).fetchall()
            ac_rows = (
                await db.execute(
                    _sel(AiQueryAssetColumnModel).where(AiQueryAssetColumnModel.is_deleted.is_(False))
                )
            ).scalars().all()
        colmeta: dict[str, list[tuple[str, str]]] = {}
        for tbl, col, dtype in col_rows:
            colmeta.setdefault(tbl, []).append((col, dtype))
        acmap = {(c.table_name, c.column_name): c for c in ac_rows}
        out = []
        for o in objs:
            fields = []
            for col, dtype in colmeta.get(o["table"], []):
                ac = acmap.get((o["table"], col))
                fields.append({
                    "name": col,
                    "type": (dtype or "").lower(),
                    "label": (ac.description or "") if ac else "",
                    "sensitive": bool(ac.sensitive) if ac else False,
                })
            out.append({
                "table": o["table"],
                "label": o.get("alias") or o["table"],
                "key_col": o.get("key_col") or "id",
                "name_col": o.get("name_col") or "name",
                "icon": o.get("icon") or "",
                "fields": fields,
            })
        return out

    @classmethod
    async def workshop_preview(cls, app_id: int, auth, limit: int = 50) -> dict:
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            row = (await db.execute(_t(
                "SELECT object_table, columns, view_type FROM ai_workshop_app WHERE id=:i AND is_deleted=false"),
                {"i": app_id})).fetchone()
        if not row:
            return {"ok": False, "msg": "应用不存在"}
        # P0-2：库里的配置同样要过「按用户白名单 + 逐列标识符」，失败抛错、不查数据
        table, cols_list = await cls._require_workshop_source(row[0], row[1], auth)
        select = ", ".join(f'"{c}"' for c in cols_list) if cols_list else "*"
        sql = f'SELECT {select} FROM "{table}"'
        if table in ("video_cameras", "train_tasks", "annotation_dataset", "video_algorithms", "video_edge_devices", "sys_user", "ai_models", "ai_call_logs"):
            sql += " WHERE is_deleted=false"
        sql += " LIMIT :n"
        try:
            async with async_db_session() as db:
                result = await db.execute(text(sql), {"n": limit})
                cols = list(result.keys())
                rows = [tuple("" if v is None else str(v) for v in r) for r in result.fetchall()]
            return {"ok": True, "view_type": row[2], "columns": cols, "rows": rows}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"预览失败：{str(e)[:120]}"}

    @classmethod
    async def workshop_submit(cls, app_id: int, data: dict, auth) -> dict:
        """把表单数据写入对象表（仅限白名单对象，字段须属于应用配置的列）。"""
        async with async_db_session() as db:
            row = (await db.execute(
                text("SELECT object_table, columns FROM ai_workshop_app WHERE id=:i AND is_deleted=false"),
                {"i": app_id})).fetchone()
        if not row:
            raise CustomException(msg="应用不存在")
        # P0-2：历史行可绕过保存期校验，写入前同样过「按用户白名单 + 逐列标识符」
        table, cols = await cls._require_workshop_source(row[0], row[1], auth)
        if table not in cls._WORKSHOP_WRITABLE:
            raise CustomException(msg="该对象暂不支持表单写入")
        if not cols:
            raise CustomException(msg="应用未配置字段")
        allowed = set(cols)
        payload = {k: v for k, v in (data or {}).items() if k in allowed}
        if not payload:
            raise CustomException(msg="请填写至少一个字段")
        keys = list(payload.keys())
        quoted = ", ".join(f'"{k}"' for k in keys)
        ph = ", ".join(":" + k for k in keys)
        sql = f'INSERT INTO "{table}" ({quoted}) VALUES ({ph})'
        try:
            async with async_db_session.begin() as db:
                await db.execute(text(sql), {k: payload[k] for k in keys})
        except Exception as exc:  # noqa: BLE001
            raise CustomException(msg=f"写入失败：{str(exc)[:120]}") from exc
        return {"ok": True}

    @classmethod
    async def upsert_workshop_app(cls, data: dict, auth) -> dict:
        import json as _json
        # P0-2：object_table/columns 决定预览拼出的 SELECT，落库前先过护栏（fail-closed）
        table, cols_list = await cls._require_workshop_source(
            data.get("object_table"), data.get("columns"), auth)
        cols = _json.dumps(cols_list, ensure_ascii=False)
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            if data.get("id"):
                await db.execute(_t(
                    "UPDATE ai_workshop_app SET name=:n, object_table=:o, view_type=:v, columns=:c, "
                    "enabled=:e, updated_time=now() WHERE id=:i"), {
                    "n": data.get("name", ""), "o": table,
                    "v": data.get("view_type", "table"), "c": cols, "e": bool(data.get("enabled", True)),
                    "i": data["id"]})
                return {"id": data["id"]}
            res = await db.execute(_t(
                "INSERT INTO ai_workshop_app(name,object_table,view_type,columns,enabled) "
                "VALUES (:n,:o,:v,:c,:e) RETURNING id"), {
                "n": data.get("name", ""), "o": table,
                "v": data.get("view_type", "table"), "c": cols, "e": bool(data.get("enabled", True))})
            return {"id": res.scalar()}

    @classmethod
    async def list_workshop_apps(cls) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            res = await db.execute(_t(
                "SELECT id,name,object_table,view_type,columns,enabled FROM ai_workshop_app "
                "WHERE is_deleted=false ORDER BY id DESC"))
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "name": r[1] or "", "object_table": r[2] or "", "view_type": r[3] or "table",
            "columns": r[4] if isinstance(r[4], list) else (_json.loads(r[4]) if r[4] else []),
            "enabled": bool(r[5]),
        } for r in rows]

    @classmethod
    async def delete_workshop_app(cls, app_id: int) -> None:
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            await db.execute(_t(
                "UPDATE ai_workshop_app SET is_deleted=true, deleted_time=now() WHERE id=:i"
            ), {"i": app_id})

    @classmethod
    async def _require_workshop_source(cls, table, columns, auth) -> tuple[str, list[str]]:
        """Workshop（无代码应用）「来源表 + 列」统一校验（P0-2 安全修复）。

        保存、预览、表单提交三个入口都会把 ``ai_workshop_app`` 里的 ``object_table``
        / ``columns`` 拼进 SQL（``SELECT {cols} FROM "{table}"`` / ``INSERT INTO
        "{table}"``），不校验等于任意表读写：

        - ``object_table`` 为空或白名单外 → 整表导出（``sys_user`` 一类表在内）；
        - ``columns`` 含注入串 → 闭合引号后可拼出任意 SQL（psycopg2 允许多语句）。

        复用 P0-1 的两道护栏：``_require_queryable_table``（合法标识符 + **按用户收窄**
        的可查白名单）与 ``_require_ident``（逐列标识符）。校验失败抛 CustomException
        （fail-closed），且必须发生在拼 SQL 之前。返回 ``(表名, 列名列表)`` —— 之后的
        SQL 只允许用这两个返回值拼装，任何原始入参都不得再进 SQL。
        """
        name = await cls._require_queryable_table(table, auth)
        raw = columns
        if isinstance(raw, str):
            # columns 列是 JSONB，但历史行/方言可能给回 JSON 字符串
            try:
                import json as _json
                raw = _json.loads(raw) if raw.strip() else []
            except Exception:  # noqa: BLE001
                raw = []
        if not isinstance(raw, list):
            raw = []
        return name, [cls._require_ident(c, "列名") for c in raw]

    @classmethod
    async def domain_objects(cls) -> dict:
        """P3-⑨ 数据域隔离视图：对象按数据域分组 + 域成员 + 当前用户可见域。

        每域附带：对象 / 用到该域表的指标 / 写入该域的管道（数据域血缘网格）。
        """
        objs = await cls.list_objects()
        domains = await cls.list_domains()
        try:
            metrics = await cls.list_metrics()
        except Exception:  # noqa: BLE001
            metrics = []
        try:
            pipes = await cls.list_pipelines()
        except Exception:  # noqa: BLE001
            pipes = []
        by_domain = {}
        # 管道 target_object 存的是本体对象编码（如 coal_assay），数据域成员存的是支撑表
        # （FUEL_CMCS_ASSAY）——先建立编码→表映射，否则域血缘网格里永远看不到管道。
        code2table = {str(o.get("ont_code")): o["table"] for o in objs if o.get("ont_code")}
        for d in domains:
            tables = set(d["tables"] or [])
            dom_m = [{"key": m["key"], "name": m["name"]} for m in metrics
                     if tables and any(t in (m.get("sql_template") or "") for t in tables)]
            dom_p = [{"name": p.get("name"), "source": p.get("source_table"),
                      "target": p.get("target_object")} for p in pipes
                     if p.get("target_object") in tables
                     or code2table.get(str(p.get("target_object"))) in tables]
            by_domain[d["id"]] = {
                "id": d["id"], "name": d["name"], "code": d["code"],
                "description": d["description"], "members": d["members"],
                "objects": [o for o in objs if o["table"] in tables] if tables else [],
                "metrics": dom_m, "pipelines": dom_p,
            }
        unassigned = [o for o in objs if not any(o["table"] in (d["tables"] or []) for d in domains)]
        # 超管可看全部域；普通用户仅可见其成员所在域
        return {"domains": list(by_domain.values()),
                "unassigned": unassigned,
                "total_objects": len(objs)}

    @classmethod
    async def domain_reconcile(cls) -> dict:
        """数据域对账：校验各域 tables 引用的对象是否都已登记（未登记标出），保证域定义完整。

        「已登记」= 系统库 schema ∪ 各业务数据源已同步的 schema（``ai_query_schema``）：
        旧实现只比对系统库，燃料等业务表会被误判为「缺失」，域对账结果不可信。
        """
        domains = await cls.list_domains()
        known: set[str] = set()
        try:
            schema = await cls._system_schema()
            known |= set(schema.keys())
        except Exception:  # noqa: BLE001
            known |= set(_svc.SYSTEM_ALLOWED_TABLES)
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rows = (await db.execute(_t(
                "SELECT DISTINCT table_name FROM ai_query_schema WHERE is_deleted=false"))).fetchall()
        known |= {r[0] for r in rows if r[0]}
        issues = []
        for d in domains:
            for t in (d["tables"] or []):
                if t not in known:
                    issues.append({"domain": d["code"] or d["name"], "domain_id": d["id"],
                                   "table": t, "missing": True})
        return {"ok": True, "total_domains": len(domains),
                "issue_count": len(issues), "issues": issues}

    @classmethod
    async def upsert_domain(cls, data: dict) -> dict:
        import json as _json
        tables = _json.dumps(data.get("tables") or [], ensure_ascii=False)
        members = _json.dumps(data.get("members") or [], ensure_ascii=False)
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            if data.get("id"):
                await db.execute(_t(
                    "UPDATE ai_data_domain SET name=:n, code=:c, description=:d, tables=:t, members=:m, enabled=:e "
                    "WHERE id=:i"), {"n": data.get("name", ""), "c": data.get("code", ""),
                    "d": data.get("description", ""), "t": tables, "m": members,
                    "e": bool(data.get("enabled", True)), "i": data["id"]})
                return {"id": data["id"]}
            res = await db.execute(_t(
                "INSERT INTO ai_data_domain(name,code,description,tables,members,enabled) "
                "VALUES (:n,:c,:d,:t,:m,:e) RETURNING id"), {
                "n": data.get("name", ""), "c": data.get("code", ""),
                "d": data.get("description", ""), "t": tables, "m": members,
                "e": bool(data.get("enabled", True))})
            return {"id": res.scalar()}

    @classmethod
    async def list_domains(cls) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rows = (await db.execute(_t(
                "SELECT id,name,code,description,tables,members,enabled FROM ai_data_domain "
                "WHERE is_deleted=false ORDER BY id DESC"))).fetchall()
        import json as _json
        return [{
            "id": r[0], "name": r[1] or "", "code": r[2] or "", "description": r[3] or "",
            "tables": r[4] if isinstance(r[4], list) else (_json.loads(r[4]) if r[4] else []),
            "members": r[5] if isinstance(r[5], list) else (_json.loads(r[5]) if r[5] else []),
            "enabled": bool(r[6]),
        } for r in rows]

    @classmethod
    async def delete_domain(cls, id: int) -> None:
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            await db.execute(_t("UPDATE ai_data_domain SET is_deleted=true WHERE id=:id"), {"id": id})

    @classmethod
    async def share_create(cls, table_name: str, user_id: int = 0) -> dict:
        import uuid
        from datetime import datetime
        token = uuid.uuid4().hex[:16]
        async with async_db_session.begin() as db:
            await cls._ensure_share_table(db)
            from sqlalchemy import text as _t
            await db.execute(_t(
                "INSERT INTO ai_dataset_share(table_name,token,user_id,created_time) "
                "VALUES (:t,:tok,:u,:now)"),
                {"t": table_name, "tok": token, "u": user_id, "now": datetime.now()})
        return {"ok": True, "table": table_name, "token": token,
                "link": f"/web#/ai/query?share={token}"}

    @classmethod
    async def share_list(cls, user_id: int = 0) -> list[dict]:
        async with async_db_session.begin() as db:
            await cls._ensure_share_table(db)
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rows = (await db.execute(_t(
                "SELECT id,table_name,token,created_time FROM ai_dataset_share "
                "WHERE is_deleted=0 AND user_id=:u ORDER BY id DESC"), {"u": user_id})).fetchall()
        return [{"id": r[0], "table": r[1], "token": r[2], "time": str(r[3]) if r[3] else "",
                 "link": f"/web#/ai/query?share={r[2]}"} for r in rows]

    @classmethod
    async def share_remove(cls, share_id: int, user_id: int = 0) -> dict:
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            await db.execute(_t(
                "UPDATE ai_dataset_share SET is_deleted=1 WHERE id=:i AND user_id=:u"),
                {"i": share_id, "u": user_id})
        return {"ok": True, "msg": "已撤销分享"}

    @classmethod
    async def catalog_categories(cls) -> dict:
        """Compass 数据目录分类：按业务域聚类全部数据资产，形成目录分类树。"""
        assets = await cls.list_assets()
        domains: dict[str, list[dict]] = {}
        for a in assets:
            d = a.get("domain") or "未分类"
            domains.setdefault(d, []).append({
                "table": a["table_name"], "alias": a["alias"], "dq": a.get("dq_score"),
                "sensitive": a.get("sensitive_count") or 0, "object": bool(a.get("object_enabled")),
            })
        cats = [{"domain": d, "count": len(items),
                 "items": items} for d, items in sorted(domains.items(), key=lambda x: -len(x[1]))]
        return {"total": len(assets), "categories": cats, "category_count": len(cats)}

    @classmethod
    async def dl_list(cls) -> list[dict]:
        """数据生命周期/删除策略列表（Palantir Data Lifetime）。"""
        from sqlalchemy import text as _t
        async with async_db_session() as db:
            await cls._ensure_data_lifetime(db)
            rows = (await db.execute(_t(
                "SELECT id, table_name, retention_days, enabled FROM ai_data_lifetime "
                "WHERE is_deleted=false ORDER BY id DESC"))).fetchall()
        return [{"id": r[0], "table": r[1], "retention_days": r[2], "enabled": bool(r[3])} for r in rows]

    @classmethod
    async def dl_save(cls, data: dict) -> dict:
        from sqlalchemy import text as _t
        table = (data.get("table") or "").strip()
        days = int(data.get("retention_days") or 0)
        if not table:
            raise CustomException(msg="请提供数据表")
        async with async_db_session.begin() as db:
            await cls._ensure_data_lifetime(db)
            if data.get("id"):
                await db.execute(_t(
                    "UPDATE ai_data_lifetime SET table_name=:t, retention_days=:d, enabled=:e WHERE id=:i"),
                    {"t": table, "d": days, "e": bool(data.get("enabled", True)), "i": data["id"]})
                return {"id": data["id"]}
            res = await db.execute(_t(
                "INSERT INTO ai_data_lifetime(table_name,retention_days,enabled) VALUES (:t,:d,:e) RETURNING id"),
                {"t": table, "d": days, "e": bool(data.get("enabled", True))})
            return {"id": res.scalar()}

    @classmethod
    async def dl_remove(cls, ids: list[int]) -> None:
        from sqlalchemy import text as _t
        async with async_db_session.begin() as db:
            await cls._ensure_data_lifetime(db)
            for i in ids:
                await db.execute(_t("UPDATE ai_data_lifetime SET is_deleted=true WHERE id=:i"), {"i": i})

    @classmethod
    async def concepts_mapping(cls) -> list[dict]:
        return await cls.list_concepts()
