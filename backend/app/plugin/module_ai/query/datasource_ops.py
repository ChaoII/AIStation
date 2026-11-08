"""数据源：连接配置 + 资产导入（2026-11-08 从 service.py 拆出）。

覆盖数据源的增删改查、连接测试入口、规则/样例预览，以及「把外部库的表导入本体」。
**不含** schema 缓存三件套（``_system_schema`` / ``_ds_schema_map`` / ``_ds_value_map``）：
它们直接读写四个进程级缓存，且被「按主体裁剪」的上下文构建依赖，单独一轮再搬。

``_load_ds`` / ``_ds_code`` / ``list_ds_schema`` / ``_ONT_IMPORT_EXCLUDE`` 仍归
``service.py``，这里用 ``_svc.`` 在调用时解析。
"""
from __future__ import annotations

from sqlalchemy import text

from app.core.database import async_db_session
from app.core.logger import log

from . import service as _svc
from .filtering import DEFAULT_FILTER_RULES
from .model import AiQueryDatasourceModel


class DatasourceOps:
    @staticmethod
    async def _table_ds_code(table_name: str) -> str | None:
        """返回表所属数据源编码（如 ``ds:4`` / ``system``），查不到返回 None。"""
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                row = (await db.execute(_t(
                    "SELECT datasource FROM ai_query_schema "
                    "WHERE UPPER(table_name)=UPPER(:t) AND is_deleted=false LIMIT 1"),
                    {"t": table_name})).fetchone()
                return (row[0] if row else None) or None
        except Exception:  # noqa: BLE001
            return None

    @classmethod
    async def import_ds_table_as_ontology(cls, datasource_id: int, table: str,
                                          domain_code: str = "") -> dict:
        """数据源连接器 → 本体对象：把外部数据源某张表结构自动生成本体对象（对象+属性+物化），连接器真正生根本体。

        ``domain_code`` 指定导入的目标域，写到对象 ``domain_code`` 列。
        """
        ds = await _svc._load_ds(datasource_id)
        rules = ds.filter_rules or DEFAULT_FILTER_RULES
        records = await _svc.list_ds_schema(datasource_id)
        rec = next((r for r in records if r["table"] == table), None)
        if not rec:
            return {"ok": False, "msg": f"数据源 {datasource_id} 未同步表 {table}"}
        cols = [c for c in (rec.get("columns") or []) if isinstance(c, dict) and c.get("name")]
        if not cols:
            return {"ok": False, "msg": f"表 {table} 无列信息"}
        return await cls._import_ont_table_core(
            datasource_id, table, cols, domain_code=domain_code, rules=rules)

    @classmethod
    async def import_ds_tables_as_ontology(cls, datasource_id: int, tables: list[str] | None = None,
                                           include_technical: bool = False,
                                           domain_code: str = "") -> dict:
        """批量把数据源的表结构导入为本体对象。

        - ``tables`` 为空 → 导入该数据源已同步的全部表（默认排除 ``_svc._ONT_IMPORT_EXCLUDE`` 纯技术表）
        - ``tables`` 指定 → 只导入给定表（取与已同步表的交集）
        - ``include_technical=True`` → 不排除纯技术表
        - ``domain_code`` → 批量导入的每张表统一写入的目标域
        """
        ds = await _svc._load_ds(datasource_id)
        rules = ds.filter_rules or DEFAULT_FILTER_RULES
        records = await _svc.list_ds_schema(datasource_id)
        all_tables = [r["table"] for r in records]
        if not all_tables:
            return {"ok": False, "msg": f"数据源 {datasource_id} 尚未同步任何表"}
        by_table = {r["table"]: (r.get("columns") or []) for r in records}
        cmt_of = {r["table"]: (r.get("comment") or "") for r in records}

        if tables:
            wanted = {t for t in tables if t}
            targets = [t for t in all_tables if t in wanted]
        elif include_technical:
            targets = list(all_tables)
        else:
            targets = [t for t in all_tables if t not in _svc._ONT_IMPORT_EXCLUDE]

        ok: list[dict] = []
        failed: list[dict] = []
        for t in targets:
            cols = [c for c in by_table.get(t, []) if isinstance(c, dict) and c.get("name")]
            if not cols:
                failed.append({"table": t, "msg": "无列信息"})
                continue
            try:
                r = await cls._import_ont_table_core(datasource_id, t, cols,
                                                     table_comment=cmt_of.get(t, ""),
                                                     domain_code=domain_code,
                                                     rules=rules)
                ok.append({"table": t, "props": r.get("props", 0),
                           "materialize": bool((r.get("materialize") or {}).get("ok"))})
            except Exception as e:  # noqa: BLE001
                failed.append({"table": t, "msg": str(e)[:120]})

        return {"ok": True, "datasource_id": datasource_id, "synced_total": len(all_tables),
                "imported": len(ok), "failed": len(failed),
                "skipped_technical": sorted(set(all_tables) - set(targets)) if not tables else [],
                "objects": ok, "errors": failed}

    @classmethod
    async def datasource_detail(cls, datasource_id: int) -> dict:
        """数据源连接详情：源信息 + 已同步表结构 + 连接器说明 + 关联数据资产数。"""
        async with async_db_session() as db:
            from sqlalchemy import select
            d = (await db.execute(
                select(AiQueryDatasourceModel).where(AiQueryDatasourceModel.id == datasource_id,
                                                     AiQueryDatasourceModel.is_deleted.is_(False))
            )).scalar_one_or_none()
        if d is None:
            return {}
        source = {"id": d.id, "name": d.name, "type": d.type, "host": d.host, "port": d.port,
                  "database": d.database, "username": d.username, "read_only": d.read_only,
                  "enabled": d.enabled, "filter_rules": d.filter_rules or DEFAULT_FILTER_RULES,
                  "remark": d.remark or ""}
        tables = await _svc.list_ds_schema(datasource_id)
        connector = next((c for c in await cls.connector_types() if c["type"] == d.type), None)
        asset_count = 0
        try:
            for a in await cls.list_assets():
                if (a.get("datasource_code") == _svc._ds_code(datasource_id)
                        or a.get("datasource") == _svc._ds_code(datasource_id)):
                    asset_count += 1
        except Exception:  # noqa: BLE001
            asset_count = 0
        return {"source": source, "tables": tables, "connector": connector, "asset_count": asset_count}

    @classmethod
    async def list_datasources(cls) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import select
            from sqlalchemy import text as _t

            rows = (
                await db.execute(
                    select(AiQueryDatasourceModel)
                    .where(AiQueryDatasourceModel.is_deleted.is_(False))
                    .order_by(AiQueryDatasourceModel.id.desc())
                )
            ).scalars().all()
            # 已同步表数：供「本体导入」等界面判断该数据源是否可用
            cnt_rows = (await db.execute(_t(
                "SELECT datasource, count(*) FROM ai_query_schema "
                "WHERE is_deleted=false GROUP BY datasource"))).fetchall()
            counts = {r[0]: int(r[1] or 0) for r in cnt_rows}
            return [
                {"id": d.id, "name": d.name, "code": d.code, "type": d.type,
                 "host": d.host, "port": d.port, "database": d.database,
                 "username": d.username, "read_only": d.read_only, "default": d.default,
                 "enabled": d.enabled, "allowed_roles": d.allowed_roles or [],
                 "filter_rules": d.filter_rules,
                 "table_count": counts.get(f"ds:{d.id}", 0),
                 "remark": d.remark or ""}
                for d in rows
            ]

    @classmethod
    async def upsert_datasource(cls, data, auth) -> dict:
        # 密码加密由上层/前端处理，这里仅透传（演示环境明文存，生产应加密）
        async with async_db_session.begin() as db:
            # 运行时补列（本项目 ai_* 表不走 Alembic，惯用 ADD COLUMN IF NOT EXISTS）；
            # 确保既有库读到 filter_rules 列，失败仅告警不影响主流程。
            try:
                await db.execute(text(
                    "ALTER TABLE ai_query_datasources "
                    "ADD COLUMN IF NOT EXISTS filter_rules JSONB"))
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 补 ai_query_datasources.filter_rules 失败: {e}")
            from sqlalchemy import select

            existing = (
                await db.execute(
                    select(AiQueryDatasourceModel).where(
                        AiQueryDatasourceModel.code == data.code,
                        AiQueryDatasourceModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                for k in ("name", "type", "host", "port", "database", "username",
                          "read_only", "default", "enabled", "remark"):
                    setattr(existing, k, getattr(data, k))
                existing.allowed_roles = data.allowed_roles or []
                # filter_rules 未传(None)时保留既有配置，避免覆盖用户已保存的自定义规则
                if data.filter_rules is not None:
                    existing.filter_rules = data.filter_rules
                if data.password:
                    existing.password = data.password
                existing.updated_id = auth.user.id
                obj = existing
            else:
                obj = AiQueryDatasourceModel(
                    name=data.name, code=data.code, type=data.type, host=data.host,
                    port=data.port, database=data.database, username=data.username,
                    password=data.password, read_only=data.read_only, default=data.default,
                    enabled=data.enabled, allowed_roles=data.allowed_roles or [],
                    filter_rules=data.filter_rules or DEFAULT_FILTER_RULES,
                    remark=data.remark, created_id=auth.user.id, updated_id=auth.user.id,
                )
                db.add(obj)
            await db.flush()
            return {"id": obj.id, "name": obj.name, "code": obj.code, "type": obj.type}

    @classmethod
    async def delete_datasource(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for did in ids:
                d = await db.get(AiQueryDatasourceModel, did)
                if d:
                    await db.delete(d)

    @classmethod
    async def _ds_current_rules(cls, datasource_id: int, rules: dict | None) -> dict:
        """取当前规则上下文：``rules`` 显式非空时直接返回（免去多余 DB 查询）；
        否则用数据源已保存规则，缺省回落到 ``DEFAULT_FILTER_RULES``。

        注意：空 dict 视为「未配置」，不能当成显式规则——否则分类结果全为「业务」，
        与缺省规则下的真实分类矛盾。
        """
        if rules:
            return rules
        try:
            ds = await _svc._load_ds(datasource_id)
            saved = getattr(ds, "filter_rules", None) or None
        except Exception:  # noqa: BLE001 - 取不到已保存规则时优雅降级到默认规则
            saved = None
        return saved or DEFAULT_FILTER_RULES

    @classmethod
    async def _ds_samples(cls, datasource_id: int,
                          limit: int = 400) -> tuple[list[str], list[str]]:
        """取表名/字段名样例（各截断 ``limit`` 条，默认 400）。

        ``limit`` 可按调用方收紧：**逐条推演型任务**（classify-advise）样例越多，
        模型思考越久（实测 400 表会把 token 预算全烧在 reasoning 上），故需传小值。

        统一 try/except：``_svc.list_ds_schema`` 失败（如数据源不存在/DB 异常）时优雅降级为
        空样例 ``([], [])``，不阻断大模型调用（suggest/parse/classify-advise 三处行为一致）。
        """
        try:
            schema = await _svc.list_ds_schema(datasource_id)
        except Exception:  # noqa: BLE001
            return [], []
        tables = [s["table"] for s in schema][:limit]
        fields = [
            c.get("name") or c.get("column_name")
            for s in schema for c in (s.get("columns") or []) if isinstance(c, dict)
        ][:limit]
        return tables, fields
