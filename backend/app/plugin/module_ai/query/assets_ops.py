"""数据资产读/写（2026-11-08 从 service.py 拆出）。

包含资产清单与列清单、资产元数据写入（单条/批量/单列）、敏感列扫描、AI 描述起草。
**不含** ``autopilot`` / ``generate_asset_descriptions``：它们被
``tests/test_autopilot_generate_desc.py`` 用 ``monkeypatch.setattr(qservice, "async_db_session")``
打桩，留在 ``service.py`` 才能保证该 patch 命中。
"""
from __future__ import annotations

from sqlalchemy import text

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log

from .degraded import degrade as _degrade
from .filtering import is_audit_field
from .model import AiQueryAssetColumnModel, AiQueryAssetModel, AiQuerySchemaModel


async def ensure_marking_columns(db):
    """幂等补齐 Task3 打标/枚举列（本项目 ai_* 表不走 Alembic，用 ADD COLUMN IF NOT EXISTS）。

    读取/写入 ai_query_assets.is_system、ai_query_asset_columns.is_audit/enum 前执行，
    失败仅告警不影响主流程（参考 Task2 filter_rules 补列样板）。
    """
    for sql in (
        "ALTER TABLE ai_query_assets ADD COLUMN IF NOT EXISTS is_system BOOLEAN DEFAULT false",
        "ALTER TABLE ai_query_asset_columns ADD COLUMN IF NOT EXISTS "
        "is_audit BOOLEAN DEFAULT false",
        "ALTER TABLE ai_query_asset_columns ADD COLUMN IF NOT EXISTS "
        "enum JSONB DEFAULT '[]'",
    ):
        try:
            await db.execute(text(sql))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 补打标/枚举列失败: {e}")


class AssetsOps:
    @classmethod
    async def list_assets(cls) -> list[dict]:
        """资产目录列表。

        ⚠️ **必须批量查，不能逐表查。** 旧实现对每张表各跑 3 次查询
        （字段统计 + DQ 分 + 血缘计数），而 ``_asset_dq_score`` /
        ``_asset_lineage_count`` 还各自**新开一个数据库会话**（又占一条池连接）。
        实测 567 条资产 → 约 1700 次查询、**31.5 秒**，并直接把连接池拖满
        （页面表现为 10 秒超时）。这里改成 3 次聚合查询一次拿全。
        """
        async with async_db_session() as db:
            from sqlalchemy import Integer as _Int
            from sqlalchemy import func as _f
            from sqlalchemy import select
            from sqlalchemy import text as _t

            rows = (
                await db.execute(
                    select(AiQueryAssetModel)
                    .where(AiQueryAssetModel.is_deleted.is_(False))
                    .order_by(AiQueryAssetModel.table_name)
                )
            ).scalars().all()

            # ① 字段统计：一条 GROUP BY 全拿
            col_rows = (await db.execute(
                select(
                    AiQueryAssetColumnModel.table_name,
                    _f.count().label("n"),
                    _f.sum(_f.cast(AiQueryAssetColumnModel.sensitive, _Int)).label("sens"),
                    _f.sum(_f.cast(AiQueryAssetColumnModel.included, _Int)).label("inc"),
                )
                .where(AiQueryAssetColumnModel.is_deleted.is_(False))
                .group_by(AiQueryAssetColumnModel.table_name)
            )).all()
            col_stat = {r[0]: (int(r[1] or 0), int(r[2] or 0), int(r[3] or 0)) for r in col_rows}

            # ② 敏感字段名（只取前 20 个/表，用于列表展示）
            sens_rows = (await db.execute(
                select(AiQueryAssetColumnModel.table_name, AiQueryAssetColumnModel.column_name)
                .where(AiQueryAssetColumnModel.is_deleted.is_(False),
                       AiQueryAssetColumnModel.sensitive.is_(True))
            )).all()
            sens_map: dict[str, list[str]] = {}
            for t, c in sens_rows:
                lst = sens_map.setdefault(t, [])
                if len(lst) < 20:
                    lst.append(c)

            # ③ DQ 分：一条全拿（表可能不存在，容错）
            dq_map: dict[str, float] = {}
            try:
                for t, s in (await db.execute(_t(
                    "SELECT table_name, score FROM ai_dq_report WHERE is_deleted=false"
                ))).all():
                    if s is not None:
                        dq_map[t] = float(s)
            except Exception as e:  # noqa: BLE001
                _degrade("asset_dq", e)

            # ④ 血缘计数：一条 GROUP BY（本表字段数 + 被引用数）
            lin_map: dict[str, int] = {}
            try:
                from .ddl_dialect import cast_int

                for t, n in (await db.execute(_t(
                    "SELECT t, " + cast_int("SUM(n)") + " FROM ("
                    "  SELECT table_name AS t, count(*) AS n FROM ai_query_asset_columns"
                    "   WHERE is_deleted=false GROUP BY table_name"
                    "  UNION ALL"
                    "  SELECT related_table AS t, count(*) AS n FROM ai_query_asset_columns"
                    "   WHERE is_deleted=false AND related_table IS NOT NULL AND related_table <> ''"
                    "   GROUP BY related_table"
                    ") x GROUP BY t"
                ))).all():
                    lin_map[t] = int(n or 0)
            except Exception as e:  # noqa: BLE001
                _degrade("asset_lineage", e)

            out = []
            for a in rows:
                n, sens, inc = col_stat.get(a.table_name, (0, 0, 0))
                out.append({
                    "table_name": a.table_name, "alias": a.alias or "",
                    "domain": a.domain or "", "description": a.description or "",
                    "business_scenarios": a.business_scenarios or "",
                    "included": a.included, "remark": a.remark or "",
                    "object_enabled": getattr(a, "object_enabled", False),
                    "object_key_col": getattr(a, "object_key_col", None) or "id",
                    "object_name_col": getattr(a, "object_name_col", None) or "name",
                    "object_icon": getattr(a, "object_icon", None) or "el-icon-Box",
                    "column_count": n,
                    "sensitive_count": sens,
                    "sensitive_fields": sens_map.get(a.table_name, []),
                    "included_columns": inc,
                    "dq_score": dq_map.get(a.table_name),
                    "lineage_count": lin_map.get(a.table_name, 0),
                })
            return out

    @classmethod
    async def _asset_dq_score(cls, table_name: str) -> float | None:
        """资产 DQ 质量分（来自 ai_dq_report）。"""
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                r = (await db.execute(_t(
                    "SELECT score FROM ai_dq_report WHERE table_name=:t AND is_deleted=false"),
                    {"t": table_name})).scalar()
            return float(r) if r is not None else None
        except Exception:  # noqa: BLE001
            return None

    @classmethod
    async def _asset_lineage_count(cls, table_name: str) -> int:
        """资产血缘引用计数（字段资产里引用该表/被引用的条数）。"""
        from sqlalchemy import func as _f
        from sqlalchemy import select as _sel

        from app.plugin.module_ai.query.model import AiQueryAssetColumnModel
        try:
            async with async_db_session() as db:
                n = (await db.execute(_sel(_f.count()).select_from(AiQueryAssetColumnModel).where(
                    (AiQueryAssetColumnModel.table_name == table_name) |
                    (AiQueryAssetColumnModel.related_table == table_name),
                    AiQueryAssetColumnModel.is_deleted.is_(False)))).scalar() or 0
            return int(n)
        except Exception:  # noqa: BLE001
            return 0

    @classmethod
    async def scan_sensitive(cls, table_name: str) -> dict:
        """敏感数据扫描器（Palantir Sensitive Data Scanner）：
        按字段名规则自动识别敏感列（PII/密码/凭证等），并标记
        ``ai_query_asset_columns.sensitive=true``。

        **并把结果同步回本体**（``ai_ont_property.sensitive``）——本体是敏感标记的
        唯一真相源，两套并行标记已经出现过不一致。
        """
        NAME_RULES = {
            "password": "密码/口令", "pwd": "密码/口令", "passwd": "密码/口令",
            "secret": "密钥", "token": "令牌", "api_key": "API密钥", "access_key": "访问密钥",
            "id_card": "身份证", "idcard": "身份证", "identity": "身份证",
            "phone": "手机号", "mobile": "手机号", "telephone": "电话",
            "email": "邮箱", "mail": "邮箱",
            "bank_card": "银行卡", "card_no": "银行卡号", "account_no": "银行账户",
        }
        # 名字里含关键词但**不是**敏感字段的（真实误报）：
        # `prompt_tokens` / `completion_tokens` 是**计数**，不是令牌；
        # `tokenizer_model` 是模型名。旧规则用子串匹配，把这些也标成了敏感。
        NOT_SECRET = (
            "tokenizer", "prompt_tokens", "completion_tokens", "total_tokens",
            "max_tokens", "token_count", "token_limit", "token_usage", "token_size",
            "mailbox", "email_verified", "phone_verified",
        )
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                try:
                    cols = (await db.execute(_t(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name=:t AND table_schema='public' ORDER BY ordinal_position"),
                        {"t": table_name})).fetchall()
                    col_names = [c[0] for c in cols]
                except Exception:  # noqa: BLE001  # SQLite 兼容
                    cols = (await db.execute(_t(f"PRAGMA table_info(\"{table_name}\")"))).fetchall()
                    col_names = [c[1] for c in cols]
        except Exception:  # noqa: BLE001
            return {"ok": False, "msg": f"表 {table_name} 不存在或不可读"}
        identified: list[dict] = []
        for col in col_names:
            lower = col.lower()
            # 先排除已知误报（计数类 token、tokenizer_model、email_verified …）
            if any(x in lower for x in NOT_SECRET):
                continue
            for key, label in NAME_RULES.items():
                if key in lower:
                    identified.append({"column": col, "reason": f"字段名含「{label}」"})
                    break
        # 标记敏感（幂等，用 ORM 自动处理 uuid 等默认值）
        if identified:
            from sqlalchemy import select as _sel
            async with async_db_session.begin() as db:
                for it in identified:
                    ex = (await db.execute(_sel(AiQueryAssetColumnModel).where(
                        AiQueryAssetColumnModel.table_name == table_name,
                        AiQueryAssetColumnModel.column_name == it["column"],
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                    ))).scalar_one_or_none()
                    if ex:
                        ex.sensitive = True
                    else:
                        db.add(AiQueryAssetColumnModel(
                            table_name=table_name, column_name=it["column"],
                            description="", sensitive=True, included=True))
        # 同步回本体：本体是敏感标记的唯一真相源，两套并行标记会不一致
        synced = 0
        try:
            from app.plugin.module_ai.ontology import semantic as _sem

            tmap = dict(await _sem.object_table_map())
            code = tmap.get(table_name)
            if code:
                from sqlalchemy import text as _t2
                async with async_db_session.begin() as db:
                    for it in identified:
                        await db.execute(_t2(
                            "UPDATE ai_ont_property SET sensitive=true "
                            "WHERE object_code=:o AND code=:c AND is_deleted=false"),
                            {"o": code, "c": it["column"]})
                        synced += 1
        except Exception:  # noqa: BLE001
            synced = 0
        return {"ok": True, "table": table_name, "identified": identified,
                "count": len(identified), "ontology_synced": synced}

    @classmethod
    async def list_asset_columns(cls, table_name: str) -> list[dict]:
        """某张表的字段清单 = **真实字段 ∪ 已维护元数据**。

        为什么必须并上真实字段：旧实现只返回 ``ai_query_asset_columns`` 里
        **已维护过**的字段。于是新表/新字段在维护界面里**根本看不见，也就无从维护**
        ——人工补元数据的第一步就卡住了（上游库注释缺失时尤其致命）。

        真实字段来自该表所属数据源已同步的结构（``ai_query_schema.columns``），
        带上 ``comment``（业务库的中文列注释），维护界面据此预填。
        """
        # Task3：读取打标/枚举列前幂等补列（独立事务提交，失败仅告警）
        async with async_db_session.begin() as db:
            await ensure_marking_columns(db)
        async with async_db_session() as db:
            from sqlalchemy import select

            rows = (
                await db.execute(
                    select(AiQueryAssetColumnModel)
                    .where(
                        AiQueryAssetColumnModel.table_name == table_name,
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                    )
                    .order_by(AiQueryAssetColumnModel.id)
                )
            ).scalars().all()
            by_col = {c.column_name: c for c in rows}

            out: list[dict] = []
            seen: set[str] = set()
            schemas = (
                await db.execute(
                    select(AiQuerySchemaModel).where(
                        AiQuerySchemaModel.table_name == table_name,
                        AiQuerySchemaModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            for s in schemas:
                for c in (s.columns or []):
                    if not isinstance(c, dict) or not c.get("name"):
                        continue
                    name = c["name"]
                    if name in seen:
                        continue
                    seen.add(name)
                    out.append({
                        "table_name": table_name, "column_name": name,
                        "type": c.get("type") or "",
                        "comment": c.get("comment") or "",
                        "datasource": s.datasource,
                        "description": "", "business_scenarios": "",
                        "related_table": "", "related_field": "",
                        "included": True, "sensitive": False, "has_meta": False,
                        # Task3：真实字段的 is_audit 优先用同步时落库标，否则按默认规则现算。
                        # 用「键是否缺失」区分两种情况：数据源自定义规则可能把默认审计字段
                        # （如 created_time）显式标为非审计(False)，此时必须尊重落库标，
                        # 不能因 ``or`` 把 False 当作缺失再按默认规则重算成 True。
                        "is_audit": (
                            bool(c.get("is_audit")) if "is_audit" in c else is_audit_field(name)
                        ),
                        "enum": c.get("enum") or [],
                    })
            # 已维护但真实结构里没有的字段也要保留，不能丢人工成果
            for name in by_col:
                if name not in seen:
                    out.append({
                        "table_name": table_name, "column_name": name,
                        "type": "", "comment": "", "datasource": "",
                        "description": "", "business_scenarios": "",
                        "related_table": "", "related_field": "",
                        "included": True, "sensitive": False, "has_meta": True,
                        "is_audit": False, "enum": [],
                    })
            for item in out:
                c = by_col.get(item["column_name"])
                if c is None:
                    continue
                item.update({
                    "description": c.description or "",
                    "business_scenarios": c.business_scenarios or "",
                    "related_table": c.related_table or "",
                    "related_field": c.related_field or "",
                    "included": c.included,
                    "sensitive": c.sensitive,
                    "is_audit": bool(c.is_audit),
                    "enum": c.enum or [],
                    "has_meta": True,
                })
            return out

    @classmethod
    async def upsert_asset(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            from sqlalchemy import select

            existing = (
                await db.execute(
                    select(AiQueryAssetModel).where(AiQueryAssetModel.table_name == data.table_name,
                                                    AiQueryAssetModel.is_deleted.is_(False))
                )
            ).scalar_one_or_none()
            if existing:
                existing.alias = data.alias
                existing.domain = data.domain
                existing.description = data.description
                existing.business_scenarios = data.business_scenarios
                existing.included = data.included
                existing.remark = data.remark
                existing.object_enabled = data.object_enabled
                existing.object_key_col = data.object_key_col or "id"
                existing.object_name_col = data.object_name_col or "name"
                existing.object_icon = data.object_icon or "el-icon-Box"
                existing.updated_id = auth.user.id
            else:
                db.add(AiQueryAssetModel(table_name=data.table_name, alias=data.alias,
                                         domain=data.domain, description=data.description,
                                         business_scenarios=data.business_scenarios,
                                         included=data.included, remark=data.remark,
                                         object_enabled=data.object_enabled,
                                         object_key_col=data.object_key_col or "id",
                                         object_name_col=data.object_name_col or "name",
                                         object_icon=data.object_icon or "el-icon-Box",
                                         created_id=auth.user.id, updated_id=auth.user.id))
            await db.flush()
        await cls._record_version(data.table_name, {
            "table_name": data.table_name, "alias": data.alias, "domain": data.domain,
            "description": data.description, "business_scenarios": data.business_scenarios,
            "included": data.included, "object_enabled": data.object_enabled,
            "object_key_col": data.object_key_col, "object_name_col": data.object_name_col,
            "object_icon": data.object_icon,
        }, operator=str(getattr(getattr(auth, "user", None), "id", "")))
        from . import service as _svc

        _svc._SCHEMA_CACHE = None
        _svc._SEMANTIC_INDEX = None
        _svc._ASSET_TMETA = None
        return {"table_name": data.table_name, "included": data.included}

    @classmethod
    async def batch_upsert_asset_meta(cls, items: list[dict], auth) -> dict:
        """**批量**维护表级元数据（中文名/业务域/描述）。

        为什么需要：上游业务库常缺注释（实测燃煤库 331 张表里 **137 张没有表注释**），
        一张张填不现实。这里支持一次提交多行，**在同一个事务里**保存，
        任何一行不合法都只跳过那一行，不影响其余。

        每项只要求 ``table_name``，其余字段（alias/domain/description/
        business_scenarios）**给了才覆盖**——这样"只补中文名"不会把已填的描述清空。
        """
        from sqlalchemy import select

        items = items or []
        if not items:
            return {"ok": False, "msg": "没有要保存的内容", "saved": 0}

        allowed = ("alias", "domain", "description", "business_scenarios", "remark")
        saved: list[str] = []
        skipped: list[dict] = []
        operator = getattr(getattr(auth, "user", None), "id", None)

        # **先取出已知表名**：只允许维护"确实存在的表"，防止把打字错
        # （如 FUEL_CMCS_ASSAY 写成 FUEL_CMCS_ASSA）写进资产表污染数据。
        # 已知 = 已同步过结构的表 ∪ 已有资产记录的表。
        known: set[str] = set()
        async with async_db_session() as db0:
            from sqlalchemy import select as _sel

            for (t,) in (await db0.execute(_sel(AiQuerySchemaModel.table_name).distinct())).all():
                if t:
                    known.add(t)
            for (t,) in (await db0.execute(
                _sel(AiQueryAssetModel.table_name).where(
                    AiQueryAssetModel.is_deleted.is_(False))
            )).all():
                if t:
                    known.add(t)

        async with async_db_session.begin() as db:
            for it in items:
                table = str((it or {}).get("table_name") or "").strip()
                if not table:
                    skipped.append({"table_name": "", "msg": "表名为空"})
                    continue
                if known and table not in known:
                    skipped.append({"table_name": table, "msg": "不在已同步的表里（检查拼写）"})
                    continue
                payload = {k: it[k] for k in allowed if k in it and it[k] is not None}
                if not payload:
                    skipped.append({"table_name": table, "msg": "没有可写入的字段"})
                    continue
                row = (await db.execute(
                    select(AiQueryAssetModel).where(
                        AiQueryAssetModel.table_name == table,
                        AiQueryAssetModel.is_deleted.is_(False))
                )).scalars().first()
                if row is None:
                    row = AiQueryAssetModel(table_name=table, included=True,
                                            created_id=operator, updated_id=operator,
                                            **payload)
                    db.add(row)
                else:
                    for k, v in payload.items():
                        setattr(row, k, v)
                    row.updated_id = operator
                saved.append(table)
            await db.flush()

        # 三个缓存都是 **service 模块** 的进程级全局：搬进 mixin 后必须显式回写，
        # 否则只是在本模块建了新变量，问数侧继续用旧缓存（改完资产不生效）。
        from . import service as _svc

        _svc._SCHEMA_CACHE = None
        _svc._SEMANTIC_INDEX = None
        _svc._ASSET_TMETA = None
        return {"ok": True, "saved": len(saved), "tables": saved,
                "skipped": skipped, "total": len(items)}

    @classmethod
    @classmethod
    async def draft_asset_descriptions(cls, auth, tables: list[str],
                                       missing_only: bool = False) -> dict:
        """为指定表生成描述草稿（**不落库**，人工确认后再走 /assets/save）。

        与 ``generate_asset_descriptions`` 的区别：那个是"批量直接写库"，
        适合全量重建；这个是日常路径，避免 AI 猜错污染资产目录。
        """
        from app.plugin.module_ai.query.asset_draft import (
            MAX_TABLES,
            DraftResult,
            build_draft_prompt,
            filter_drafts,
        )

        names = list(dict.fromkeys(
            str(t).strip() for t in (tables or []) if str(t).strip()))[:MAX_TABLES]
        if not names and missing_only:
            # 批量模式：自动挑选「还没有描述」的资产（最多 MAX_TABLES 张）
            from sqlalchemy import or_ as _or
            from sqlalchemy import select as _sel

            async with async_db_session() as db:
                rows = (await db.execute(_sel(AiQueryAssetModel.table_name).where(
                    AiQueryAssetModel.is_deleted.is_(False),
                    AiQueryAssetModel.included.is_(True),
                    _or(AiQueryAssetModel.description.is_(None),
                        AiQueryAssetModel.description == ""),
                ).limit(MAX_TABLES))).scalars().all()
            names = [str(x) for x in rows]
        if not names:
            raise CustomException(msg="请选择要起草的表（或没有缺描述的资产）")
        async with async_db_session() as db:
            from sqlalchemy import select as _sel

            trows = (await db.execute(_sel(AiQueryAssetModel).where(
                AiQueryAssetModel.table_name.in_(names),
                AiQueryAssetModel.is_deleted.is_(False),
            ))).scalars().all()
            crows = (await db.execute(_sel(AiQueryAssetColumnModel).where(
                AiQueryAssetColumnModel.table_name.in_(names),
                AiQueryAssetColumnModel.is_deleted.is_(False),
            ))).scalars().all()
        if not trows:
            raise CustomException(msg="没有找到可起草的表（请先同步资产目录）")
        cols_by: dict[str, list[str]] = {}
        for c in crows:
            cols_by.setdefault(c.table_name, []).append(c.column_name)
        known = {t.table_name: cols_by.get(t.table_name, []) for t in trows}
        result = await cls._llm_structured(
            build_draft_prompt(known), DraftResult, max_tokens=6000, tag="aistation-asset-draft")
        return {"drafts": filter_drafts(result, known), "table_count": len(known)}

    @classmethod
    async def upsert_asset_column(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            from sqlalchemy import select

            # Task3：写枚举列前幂等补列
            await ensure_marking_columns(db)
            existing = (
                await db.execute(
                    select(AiQueryAssetColumnModel).where(
                        AiQueryAssetColumnModel.table_name == data.table_name,
                        AiQueryAssetColumnModel.column_name == data.column_name,
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            enum = getattr(data, "enum", None) or []
            if existing:
                existing.description = data.description
                existing.business_scenarios = data.business_scenarios
                existing.related_table = data.related_table
                existing.related_field = data.related_field
                existing.included = data.included
                existing.sensitive = data.sensitive
                existing.enum = enum
                existing.updated_id = auth.user.id
            else:
                db.add(AiQueryAssetColumnModel(table_name=data.table_name, column_name=data.column_name,
                                               description=data.description,
                                               business_scenarios=data.business_scenarios,
                                               related_table=data.related_table,
                                               related_field=data.related_field,
                                               included=data.included, sensitive=data.sensitive,
                                               enum=enum,
                                               created_id=auth.user.id, updated_id=auth.user.id))
            await db.flush()
        from . import service as _svc

        _svc._SEMANTIC_INDEX = None
        _svc._SCHEMA_CACHE = None
        return {"table_name": data.table_name, "column_name": data.column_name}
