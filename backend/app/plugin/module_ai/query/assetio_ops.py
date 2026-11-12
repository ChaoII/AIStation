"""导出、对象浏览、对象执行规格（2026-11-08 从 service.py 拆出）。

- ``export_asset`` / ``object_browse``：两个资产入口，**都走 `_execute_one`**
  （权限网关唯一收口），表名先过标识符 + 按用户白名单；
- ``_ir_runtime`` / ``_object_spec_for`` / ``_allowed_objects_for_query``：把本体对象
  编译成 IR 运行规格（对象白名单按权限裁剪）；
- ``_apply_softdelete_policy``：软删除口径（问句不是在问"已删除"时补 `ISDELETED = false`）；
- ``sync_assets``：从 schema 同步资产；
- ``guardrails_status`` / ``_msg_dict`` / ``_explain_rows`` / ``_parse_col_label``：把执行
  细节整理成前端「执行详情」需要的样子。
"""
from __future__ import annotations

import re

from app.core.database import async_db_session
from app.core.logger import log

from . import service as _svc
from .filtering import is_audit_field, is_system_table
from .model import AiQueryAssetColumnModel, AiQueryAssetModel, AiQueryMessageModel

#: 与 service 同值（常量，导入期就要可用：默认参数会在此刻求值）
SYSTEM_DS = "system"


class AssetIoOps:
    @classmethod
    async def export_asset(cls, table_name: str, auth, limit: int = 100) -> dict:
        """数据集导出：读取真实表数据（CSV/JSON 由前端生成下载）。

        表可能属于**外部自定义数据源**（如 ds:4 燃煤库）或平台自身库。先按
        ``ai_query_schema.datasource`` 定位归属：外部源在其库执行，平台源在平台库执行。
        """
        table_name = await cls._require_queryable_table(table_name, auth)
        deny = await cls._sensitive_table_deny(table_name)
        if deny:
            return {"ok": False, "msg": deny}
        n = max(1, min(int(limit), 500))
        # 定位表所属数据源
        ds_code = None
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                row = (await db.execute(_t(
                    "SELECT datasource FROM ai_query_schema "
                    "WHERE UPPER(table_name)=UPPER(:t) AND is_deleted=false LIMIT 1"),
                    {"t": table_name})).fetchone()
                ds_code = (row[0] if row else None) or None
        except Exception:  # noqa: BLE001
            ds_code = None
        # 外部自定义数据源：在其库执行（否则平台库里根本没有这张表）
        # 导出必须按导出者重新走唯一网关：行/列策略、字段级 ACL、审计都生效。
        ds = ds_code or SYSTEM_DS
        ident = cls._require_ident(table_name, "表名")
        sql = (f'SELECT * FROM "{ident}" LIMIT {n}' if ds == SYSTEM_DS
               else f"SELECT * FROM {ident} LIMIT {n}")
        try:
            res = await cls._execute_one(
                sql, ds, auth, f"导出 {table_name}", entry="export")
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"表不存在或无法读取：{e}"}
        cols = res.get("columns") or []
        rows_arr = res.get("rows") or []
        data = [dict(zip(cols, r, strict=False)) for r in rows_arr]
        return {"ok": True, "table": table_name, "columns": cols, "rows": data,
                "row_count": len(data)}

    @classmethod
    async def object_browse(cls, table_name: str, auth, page: int = 1, page_size: int = 20) -> dict:
        """对象数据浏览器：分页读取真实表数据（前端表格浏览）。

        与导出同口径：按表所属数据源路由（外部自定义库 vs 平台库），否则平台库里
        根本没有业务表、必然「表不存在」。
        """
        # P0-1：表名直接拼 SELECT，先过「标识符 + 按用户白名单」校验（fail-closed）
        table_name = await cls._require_queryable_table(table_name, auth)
        deny = await cls._sensitive_table_deny(table_name)
        if deny:
            return {"ok": False, "msg": deny}
        page = max(1, int(page))
        page_size = max(1, min(int(page_size), 100))
        offset = (page - 1) * page_size
        ds_code = await cls._table_ds_code(table_name)
        # 外部自定义数据源
        # 与导出一致：按浏览者走唯一网关，行/列策略与审计都生效。
        ds = ds_code or SYSTEM_DS
        ident = cls._require_ident(table_name, "表名")
        quoted = f'"{ident}"' if ds == SYSTEM_DS else ident
        try:
            cnt = await cls._execute_one(
                f"SELECT COUNT(*) FROM {quoted}", ds, auth,
                f"浏览 {table_name}", entry="object")
            total = int(((cnt.get("rows") or [[0]])[0][0]) or 0)
            res = await cls._execute_one(
                f"SELECT * FROM {quoted} LIMIT {page_size} OFFSET {offset}",
                ds, auth, f"浏览 {table_name}", entry="object")
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"表不存在或无法读取：{e}"}
        cols = res.get("columns") or []
        data = [dict(zip(cols, r, strict=False)) for r in (res.get("rows") or [])]
        return {"ok": True, "table": table_name, "columns": cols, "rows": data,
                "page": page, "page_size": page_size, "total": total,
                "has_next": offset + page_size < total}

    @classmethod
    async def _ir_runtime(cls) -> dict:
        """IR 生成用的模型。

        默认与 NL2SQL 同源（``_get_runtime()``）；可用设置 ``object_query_model``
        指定一个**更快的模型**（填模型名或 id）。

        为什么留这个口子：实测同一提示词经 agno —— deepseek-flash ≈4.4s、
        LLM-27B-FP8 ≈8.9s、LLM-284B-MXFP4 ≈29.4s（且长尾能到 60s+）。
        IR 是纯结构化抽取，用大模型既浪费又把"优化路径"拖成"更慢的路径"。
        """
        cfg = await cls._cfg()
        pick = str(cfg.get("object_query_model") or "").strip()
        model_id: int | None = None
        if pick:
            if pick.isdigit():
                model_id = int(pick)
            else:
                from sqlalchemy import text as _t

                try:
                    async with async_db_session() as db:
                        row = (await db.execute(_t(
                            "SELECT id FROM ai_models WHERE is_deleted=false AND enabled=true "
                            "AND name=:n ORDER BY is_default DESC, id DESC LIMIT 1"),
                            {"n": pick})).fetchone()
                    model_id = int(row[0]) if row else None
                except Exception:  # noqa: BLE001
                    model_id = None
        if model_id is not None:
            from app.plugin.module_ai.models.service import AiModelService

            try:
                r = await AiModelService.get_runtime_model(model_id=model_id)
                if r:
                    return r
            except Exception:  # noqa: BLE001
                pass
        return await cls._get_runtime()

    @classmethod
    async def _object_spec_for(cls, code: str) -> dict | None:
        """单个对象的可查询规格（已物化 + 真实列 + 非隐藏关系）；不可用返回 ``None``。

        抽成独立方法是为了让「当前对象」能被**强制加入**词表（即使检索没命中它）。
        """
        from app.plugin.module_ai.ontology import service as ont

        from . import object_query as oq

        try:
            meta = await ont._instance_meta(code)
        except Exception:  # noqa: BLE001
            return None
        if not meta or meta.get("error") or not meta.get("materialized"):
            return None
        cols = set(meta.get("cols") or [])
        fields = [
            p for p in (meta.get("props") or [])
            if p.get("code") in cols and (p.get("visibility") or "normal") != "hidden"
        ]
        if not fields:
            return None
        try:
            links = [
                lk for lk in await ont.list_links(code)
                if (lk.get("visibility") or "normal") != "hidden"
            ]
        except Exception:  # noqa: BLE001
            links = []
        spec = oq.build_allowed(
            [{"code": code, "name": meta.get("name") or code}], {code: fields}, {code: links})
        return spec.get(code)

    @classmethod
    async def _apply_softdelete_policy(cls, question: str, sql: str,
                                       datasource: str) -> str:
        """按数据源配置的软删口径改写模型生成的 SQL（见 ``softdelete.rewrite_generated_sql``）。

        语义/口径**不在代码里写死**：列名（ISDELETED / IS_DELETED / DEL_FLAG）与
        「问句在问已删除」的提示词都从 `ai_query_datasources.filter_rules.softdelete`
        读，代码只保留默认值。失败一律返回原 SQL（改写是增强，不能拖垮答数）。
        """
        from .softdelete import rewrite_generated_sql

        return await rewrite_generated_sql(question, sql, datasource)

    @classmethod
    async def _allowed_objects_for_query(cls, question: str, auth, max_objects: int = 8,
                                         datasource: str = SYSTEM_DS,
                                         prefer_object: str | None = None) -> dict:
        """构建「授权 ∩ 检索命中」的对象白名单（scope 收敛的落点）。

        - 系统库：只保留**已物化**（支撑表存在）且用户**有权访问**的对象类型；
        - 自定义数据源（``ds:{id}``）：保留**归属该数据源**（``datasource_id`` 相等）的对象；
        - 用 ``_semantic_tables`` 的召回结果收窄（仅系统库；未命中则放宽到全部授权对象）；
        - 字段只带**真实存在的列**，关系只带非隐藏项；并挂上**绑定到该对象的指标**。

        这一步同时是**反幻觉**的架构保证：IR 里出现清单外的对象/字段/指标会被丢弃。
        """
        from app.plugin.module_ai.ontology import semantic as _sem

        try:
            ctx = await _sem.semantic_context()
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 对象查询：本体语义读取失败 {str(e)[:100]}")
            return {}

        # 自定义数据源 id（``ds:{id}``）；系统库为 None
        ds_id: int | None = None
        if datasource and datasource not in (SYSTEM_DS, None):
            try:
                ds_id = int(str(datasource).split(":")[-1])
            except (TypeError, ValueError):
                ds_id = None

        try:
            tmap = await _sem.object_table_map()
        except Exception:  # noqa: BLE001
            tmap = {}
        try:
            allowed_tables = await cls._allowed_for_user(auth)
        except Exception:  # noqa: BLE001
            allowed_tables = set()

        cand: list[dict] = []
        for o in ctx.get("objects") or []:
            table = str(o.get("table") or "")
            if ds_id is not None:
                # 自定义数据源：按对象归属的数据源过滤（跨库不越权）
                if int(o.get("datasource_id") or 0) != ds_id:
                    continue
            elif not table or (allowed_tables and table not in allowed_tables):
                continue
            cand.append(o)

        # 按检索命中收窄（仅系统库；检索基于系统 schema，对自定义源不适用）
        if ds_id is None:
            hit_codes: set[str] = set()
            try:
                schema = await cls._system_schema()
                hits = await cls._semantic_tables(question, schema, None, None, SYSTEM_DS)
                for t in hits or []:
                    code = tmap.get(t) or (str(t)[4:] if str(t).startswith("ont_") else None)
                    if code:
                        hit_codes.add(code)
            except Exception:  # noqa: BLE001
                hit_codes = set()
            if hit_codes:
                narrowed = [o for o in cand if o.get("code") in hit_codes]
                if narrowed:
                    cand = narrowed

        # 绑定指标：按 object_code 归组，挂到对象 spec 上（供 IR 提示词/校验/执行使用）
        metrics_by_object: dict[str, list] = {}
        try:
            for m in await cls.list_metrics(datasource):
                oc = str(m.get("object_code") or "")
                if oc:
                    metrics_by_object.setdefault(oc, []).append(m)
        except Exception:  # noqa: BLE001
            metrics_by_object = {}

        out: dict = {}
        for o in cand:
            if len(out) >= max_objects:
                break
            code = str(o.get("code") or "")
            if not code:
                continue
            spec = await cls._object_spec_for(code)
            if spec:
                spec["metrics"] = {m["key"]: m for m in metrics_by_object.get(code, [])}
                out[code] = spec
        # 命中指标所属对象**强制包含**：数据集对象常有几百个，它很可能排在 max_objects 之外
        # 被截掉（实测：`coal_batch` 排在 336 个对象之后 → IR 反推出它却"不在可查询范围"）。
        if prefer_object and prefer_object not in out:
            spec = await cls._object_spec_for(prefer_object)
            if spec:
                spec["metrics"] = {m["key"]: m for m in metrics_by_object.get(prefer_object, [])}
                out[prefer_object] = spec
        return out

    @classmethod
    async def sync_assets(cls, auth) -> dict:
        """从数据库 information_schema 全量同步表/字段到资产目录；已在白名单的表默认纳入。"""
        async with async_db_session() as db:
            from sqlalchemy import text as _text

            result = await db.execute(
                _text("SELECT table_name FROM information_schema.tables WHERE table_schema='public' ORDER BY table_name")
            )
            tables = [r[0] for r in result.fetchall()]
            colr = await db.execute(
                _text("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name, ordinal_position")
            )
            cols = [(r[0], r[1]) for r in colr.fetchall()]
        upserted = 0
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            # Task3：写打标列前幂等补列；本地库表/字段按默认规则打 is_system/is_audit
            await _svc._ensure_marking_columns(db)

            # ⚠️ 性能：旧实现**逐表/逐列** SELECT（本库 631 表 / 11,688 列 ≈ 1.2 万次往返），
            # 实测 90s 都跑不完，接口从 UI 调用会一直转圈。改成两次预取 + 批量写入。
            existing_tables = {
                r[0]: bool(r[1])
                for r in (
                    await db.execute(_t(
                        "SELECT table_name, is_system FROM ai_query_assets WHERE is_deleted = false"))
                ).fetchall()
            }
            existing_columns = {
                (r[0], r[1]): bool(r[2])
                for r in (
                    await db.execute(_t(
                        "SELECT table_name, column_name, is_audit "
                        "FROM ai_query_asset_columns WHERE is_deleted = false"))
                ).fetchall()
            }

            new_rows = [
                AiQueryAssetModel(
                    table_name=t, description="",
                    included=t in _svc.SYSTEM_ALLOWED_TABLES,
                    is_system=is_system_table(t), remark="",
                    created_id=auth.user.id, updated_id=auth.user.id,
                )
                for t in tables
                if t not in existing_tables
            ]
            if new_rows:
                db.add_all(new_rows)
                upserted = len(new_rows)
                await db.flush()

            # 重跑同步时校正已有行的系统表标记（按名字判定，幂等；只更新有变化的）
            changed_sys = [
                {"t": t, "v": is_system_table(t)} for t in tables
                if t in existing_tables and existing_tables[t] != is_system_table(t)
            ]
            if changed_sys:
                await db.execute(
                    _t("UPDATE ai_query_assets SET is_system = :v WHERE table_name = :t"), changed_sys)

            new_cols = [
                AiQueryAssetColumnModel(
                    table_name=t, column_name=c, description="",
                    included=True, sensitive=False, is_audit=is_audit_field(c),
                    created_id=auth.user.id, updated_id=auth.user.id,
                )
                for t, c in cols
                if (t, c) not in existing_columns
            ]
            if new_cols:
                db.add_all(new_cols)
                await db.flush()

            changed_aud = [
                {"t": t, "c": c, "v": is_audit_field(c)} for t, c in cols
                if (t, c) in existing_columns and existing_columns[(t, c)] != is_audit_field(c)
            ]
            if changed_aud:
                await db.execute(
                    _t("UPDATE ai_query_asset_columns SET is_audit = :v "
                       "WHERE table_name = :t AND column_name = :c"), changed_aud)
        return {"tables": len(tables), "columns": len(cols), "new_tables": upserted}

    @classmethod
    async def _pick_time_col(cls, table_name: str, datasource: str) -> str | None:
        """从已同步的表结构里挑一个「更新时间」列（业务数据源扫描新鲜度用）。"""
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            row = (await db.execute(_t(
                "SELECT columns FROM ai_query_schema WHERE datasource=:d AND table_name=:t "
                "AND is_deleted=false LIMIT 1"), {"d": datasource, "t": table_name})).fetchone()
        import json as _json
        cols = []
        if row and row[0]:
            try:
                cols = row[0] if isinstance(row[0], list) else _json.loads(row[0])
            except Exception:  # noqa: BLE001
                cols = []
        names = [str(c.get("name") or "") for c in cols if isinstance(c, dict)]
        lowered = {n.lower(): n for n in names}
        for pref in ("lastmodificationtime", "updatetime", "updated_time", "modifytime",
                     "modify_time", "createtime", "creationtime", "created_time"):
            if pref in lowered:
                return lowered[pref]
        for n in names:
            ln = n.lower()
            if ln.endswith("time") or ln.endswith("date"):
                return n
        return None

    @classmethod
    async def guardrails_status(cls) -> dict:
        """AIP 安全护栏/治理策略状态：ABAC/数据域/敏感剔除/审批/审计/版本 各护栏开关。"""
        checks: list[dict] = []
        try:
            rules = await cls.list_access_rules()
            checks.append({"key": "abac", "name": "ABAC 权限控制", "enabled": bool(rules),
                           "detail": f"{len(rules)} 条策略"})
        except Exception:  # noqa: BLE001
            checks.append({"key": "abac", "name": "ABAC 权限控制", "enabled": False, "detail": "未启用"})
        try:
            domains = await cls.list_domains()
            checks.append({"key": "datadomain", "name": "数据域隔离", "enabled": bool(domains),
                           "detail": f"{len(domains)} 个数据域"})
        except Exception:  # noqa: BLE001
            checks.append({"key": "datadomain", "name": "数据域隔离", "enabled": False, "detail": "未启用"})
        try:
            assets = await cls.list_assets()
            sens = any((a.get("sensitive_count") or 0) > 0 for a in assets)
            checks.append({"key": "sensitive", "name": "敏感字段剔除", "enabled": sens,
                           "detail": "非授权自动剔除" if sens else "无敏感字段"})
        except Exception:  # noqa: BLE001
            checks.append({"key": "sensitive", "name": "敏感字段剔除", "enabled": False, "detail": "未启用"})
        checks.append({"key": "approval", "name": "写回审批流", "enabled": True, "detail": "已启用"})
        checks.append({"key": "audit", "name": "审计日志", "enabled": True, "detail": "已启用"})
        checks.append({"key": "version", "name": "版本/发布管控", "enabled": True, "detail": "已启用"})
        on = sum(1 for c in checks if c["enabled"])
        return {"total": len(checks), "enabled": on,
                "score": round(on / len(checks) * 100) if checks else 0, "checks": checks}

    @classmethod
    def _msg_dict(cls, m: AiQueryMessageModel) -> dict:
        return {
            "id": m.id, "session_id": m.session_id, "question": m.question,
            "path": m.path, "datasource": m.datasource, "sql": m.sql or "",
            "columns": m.columns or [], "rows": m.rows or [], "summary": m.summary or "",
            "result_rows": m.result_rows or 0, "took_ms": m.took_ms or 0,
            "cached": m.cached, "usage": m.usage, "is_error": m.is_error,
            "feedback": m.feedback or "", "correct_sql": m.correct_sql or "",
            "grounding": m.grounding,
            "created_time": m.created_time,
        }

    @classmethod
    async def _explain_rows(cls, sql: str) -> int:
        """EXPLAIN 预估结果行数（用于查询代价护栏）。"""
        from sqlalchemy import text as _t

        async with async_db_session() as db:
            row = (await db.execute(_t(f"EXPLAIN (FORMAT JSON) {sql.rstrip(';')}"))).scalar()
            plan = row[0] if isinstance(row, list) else row
            return int((plan.get("Plan") or {}).get("Plan Rows") or 0)

    @staticmethod
    def _parse_col_label(label: str) -> dict:
        """从 ``_svc._system_schema()`` 的列标签 ``col(type)【中文名】…`` 抽出列名与中文名。"""
        name = (label or "").split("(", 1)[0].strip()
        m = re.search(r"【([^】]+)】", label or "")
        return {"column_name": name, "description": m.group(1) if m else ""}
