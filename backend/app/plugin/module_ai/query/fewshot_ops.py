"""少样本与过滤规则（2026-11-08 从 service.py 拆出）。

- ``list_fewshots`` / ``upsert_fewshot`` / ``delete_fewshot`` / ``_dynamic_fewshots``：
  问答样例库（反馈正例沉淀、按问题动态挑选）；
- ``suggest_filter_rules`` / ``parse_filter_rules`` / ``preview_filter_rules``：
  建表时的字段分类与过滤规则（LLM 建议 → 结构化 → 预览）；
- ``classify_advise`` / ``connector_types`` / ``suggest_metrics_terms``：接入辅助。

``_load_ds`` / ``_norm_datasource`` / ``list_ds_schema`` / ``pick_fewshots`` 仍归
``service.py``（或由其再导出），这里用 ``_svc.`` 解析。
"""
from __future__ import annotations

import json

from app.core.database import async_db_session

from . import service as _svc
from .filtering import DEFAULT_FILTER_RULES, classify_fields, classify_tables
from .llm_schemas import ClassifyAdviseOut, FilterRulesOut, MetricsTermsOut
from .model import AiQueryAssetColumnModel, AiQueryAssetModel, AiQueryFewshotModel


class FewshotOps:
    @classmethod
    async def list_fewshots(cls, datasource: str | None = None) -> list[dict]:
        datasource = await _svc._norm_datasource(datasource)
        async with async_db_session() as db:
            from sqlalchemy import select

            q = select(AiQueryFewshotModel).where(AiQueryFewshotModel.is_deleted.is_(False))
            if datasource:
                q = q.where(AiQueryFewshotModel.datasource == datasource)
            q = q.order_by(AiQueryFewshotModel.id.desc())
            rows = (await db.execute(q)).scalars().all()
            return [
                {"id": f.id, "datasource": f.datasource, "question": f.question,
                 "sql": f.sql, "enabled": f.enabled}
                for f in rows
            ]

    @classmethod
    async def upsert_fewshot(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            from sqlalchemy import select

            existing = (
                await db.execute(
                    select(AiQueryFewshotModel).where(
                        AiQueryFewshotModel.question == data.question,
                        AiQueryFewshotModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.sql = data.sql
                existing.enabled = data.enabled
                existing.datasource = data.datasource
                existing.updated_id = auth.user.id
                obj = existing
            else:
                obj = AiQueryFewshotModel(
                    datasource=data.datasource, question=data.question, sql=data.sql,
                    enabled=data.enabled, created_id=auth.user.id, updated_id=auth.user.id,
                )
                db.add(obj)
            await db.flush()
            return {"id": obj.id, "question": obj.question, "sql": obj.sql, "enabled": obj.enabled}

    @classmethod
    async def delete_fewshot(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for fid in ids:
                f = await db.get(AiQueryFewshotModel, fid)
                if f:
                    await db.delete(f)

    @classmethod
    async def _dynamic_fewshots(cls, question: str, datasource: str | None = None) -> list[dict]:
        """按问题关键词与示例相关度挑 top-K，动态引导 NL2SQL。"""
        async with async_db_session() as db:
            from sqlalchemy import select

            rows = (
                await db.execute(
                    select(AiQueryFewshotModel)
                    .where(
                        AiQueryFewshotModel.is_deleted.is_(False),
                        AiQueryFewshotModel.enabled.is_(True),
                    )
                    .order_by(AiQueryFewshotModel.id.desc())
                    .limit(300)
                )
            ).scalars().all()
        examples = [
            {"question": f.question, "sql": f.sql, "datasource": f.datasource} for f in rows
        ]
        # 相关度选取（中文按二元组打分）——旧的整句 token 方案会让所有示例同分
        return [
            {"q": e["question"], "sql": e["sql"]}
            for e in _svc.pick_fewshots(question, examples, datasource, k=4)
        ]

    @classmethod
    async def suggest_filter_rules(cls, datasource_id: int, rules: dict | None = None) -> dict:
        """按命名规律归纳系统表前缀/关键词/精确名/正则与审计字段，输出完整 rules JSON。

        - 表名/字段名各截断最多 400 条（防超长）；
        - ``rules`` 参数可作为当前规则参考，模型仍需输出**完整** ``rules``（含 enabled +
          system_table + audit_fields）。
        """
        tables, fields = await cls._ds_samples(datasource_id)
        cur = await cls._ds_current_rules(datasource_id, rules)
        prompt = (
            "你是数据库表/字段命名规范专家。根据下面给定的数据源表与字段样例，"
            "归纳出「系统表」与「审计字段」的识别规则。\n"
            f"当前规则参考：{json.dumps(cur, ensure_ascii=False)}\n"
            f"表名样例（{len(tables)}）：{json.dumps(tables, ensure_ascii=False)}\n"
            f"字段样例（{len(fields)}）：{json.dumps(fields, ensure_ascii=False)}\n\n"
            "请只输出严格的 JSON，结构为："
            "{\"rules\": {\"enabled\": true, \"system_table\": "
            "{\"prefixes\": [\"...\"], \"keywords\": [\"...\"], "
            "\"exact\": [\"...\"], \"regex\": \"\"}, "
            "\"audit_fields\": [\"...\"]}}\n"
            "必须输出完整 rules（含 enabled、system_table 四要素与 audit_fields），"
            "不要缺省字段，不要输出任何解释。"
        )
        out = await cls._llm_structured(prompt, FilterRulesOut, temperature=0.2)
        return {"rules": out.rules.model_dump()}

    @classmethod
    async def parse_filter_rules(cls, datasource_id: int, text: str) -> dict:
        """把自然语言（如「把 SYS_ 前缀当系统表，created_time 当审计字段」）转成完整 rules JSON。"""
        # 把数据源表名样例作为背景，帮助模型理解命名上下文（非强制）
        tables, _fields = await cls._ds_samples(datasource_id)
        prompt = (
            "你是筛选规则解析助手。把用户的中文描述转换成规则 JSON，"
            "规则用于识别「系统表」（前缀/关键词/精确名/正则）与「审计字段」。\n"
            f"数据源表名样例（{len(tables)}）：{json.dumps(tables, ensure_ascii=False)}\n"
            f"用户描述：{text}\n\n"
            "请只输出严格的 JSON，结构为："
            "{\"rules\": {\"enabled\": true, \"system_table\": "
            "{\"prefixes\": [\"...\"], \"keywords\": [\"...\"], "
            "\"exact\": [\"...\"], \"regex\": \"\"}, "
            "\"audit_fields\": [\"...\"]}}\n"
            "必须输出完整 rules（含 enabled、system_table 四要素与 audit_fields），"
            "不要缺省字段，不要输出任何解释。"
        )
        out = await cls._llm_structured(prompt, FilterRulesOut, temperature=0.2)
        return {"rules": out.rules.model_dump()}

    @classmethod
    async def preview_filter_rules(cls, datasource_id: int, rules: dict | None = None) -> dict:
        """筛选规则分类预览（只读）：对数据源已同步 schema 全量分类并汇总。

        - ``rules`` 为草稿规则（可传 ``None`` 用数据源已保存规则，再缺省用 ``DEFAULT_FILTER_RULES``）；
        - 不写库、不改变已保存规则；数据源不存在时由 ``_svc._load_ds`` 抛 CustomException（直接透传）。
        """
        ds = await _svc._load_ds(datasource_id)
        # 空 dict（历史数据/新建数据源未配置）必须回落到缺省规则：
        # 旧写法把 `{}` 当成「用户显式清空的规则」，于是预览里系统表/审计字段恒为 0，
        # 与「缺省规则」下的真实分类完全矛盾（实测 331 表全被判成业务表）。
        eff = (rules or None) or (ds.filter_rules or None) or DEFAULT_FILTER_RULES
        schema = await _svc.list_ds_schema(datasource_id)
        tables = [s["table"] for s in schema]
        fields = []
        for s in schema:
            for c in s.get("columns") or []:
                fields.append(c.get("name") or c.get("column_name"))
        t = classify_tables(tables, eff)
        f = classify_fields(fields, eff)
        summary = {
            "table_total": len(t),
            "system_tables": sum(1 for x in t if x["is_system"]),
            "business_tables": sum(1 for x in t if not x["is_system"]),
            "field_total": len(f),
            "audit_fields": sum(1 for x in f if x["is_audit"]),
            "business_fields": sum(1 for x in f if not x["is_audit"]),
        }
        return {"tables": t, "fields": f, "summary": summary}

    @classmethod
    async def connector_types(cls) -> list[dict]:
        """连接器目录（Palantir data connection）：支持的数据源类型与接入说明。"""
        return [
            {"type": "postgres", "name": "PostgreSQL", "kind": "关系型",
             "desc": "连接 PostgreSQL 数据库，支持表/字段结构同步与数据读取"},
            {"type": "mysql", "name": "MySQL", "kind": "关系型",
             "desc": "连接 MySQL 数据库，支持表/字段结构同步与数据读取"},
            {"type": "sqlite", "name": "SQLite", "kind": "文件型",
             "desc": "连接本地 SQLite 文件，适合小规模演示与快速接入"},
            {"type": "rest_api", "name": "REST API", "kind": "API",
             "desc": "通过 REST 接口拉取外部数据，经数据管道（ELT）落库到对象"},
            {"type": "csv", "name": "CSV 文件", "kind": "文件型",
             "desc": "读取 CSV 文件，可经数据管道导入业务对象"},
        ]

    @classmethod
    async def classify_advise(cls, datasource_id: int, rules: dict | None = None) -> dict:
        """逐表逐字段分类建议：根据当前规则推理哪些表可能为系统表、哪些字段为审计字段。

        - 样例**收紧到各 120 条**：逐条推演型任务给全量样例会让模型把 token 预算
          全烧在 reasoning 上（实测 400 表 → content 为空、解析失败）；
        - 返回 ``{"system_suggest": [{"name","reason"}], "audit_suggest": [{"name","reason"}]}``。
        """
        tables, fields = await cls._ds_samples(datasource_id, limit=120)
        cur = await cls._ds_current_rules(datasource_id, rules)
        prompt = (
            "你是数据库表/字段分类专家。根据给定的当前规则，判断哪些表疑似系统表、"
            "哪些字段疑似审计字段，并为每项给出简短中文依据（reason 不超过 20 字）。\n"
            f"当前规则：{json.dumps(cur, ensure_ascii=False)}\n"
            f"表名样例（{len(tables)}）：{json.dumps(tables, ensure_ascii=False)}\n"
            f"字段样例（{len(fields)}）：{json.dumps(fields, ensure_ascii=False)}\n\n"
            "**直接给结论，不要逐条推演**；每类最多 30 条（按置信度从高到低）。"
        )
        out = await cls._llm_structured(prompt, ClassifyAdviseOut, temperature=0.2,
                                        max_tokens=12000)
        return {
            "system_suggest": [i.model_dump() for i in out.system_suggest],
            "audit_suggest": [i.model_dump() for i in out.audit_suggest],
        }

    @classmethod
    async def suggest_metrics_terms(cls, auth) -> dict:
        """用 LLM 从数据字典(中文描述)生成候选指标/术语，供用户一键采纳。"""
        # 1) 组装已纳入资产的中文词典
        async with async_db_session() as db:
            from sqlalchemy import select as _sel

            tables = (
                await db.execute(
                    _sel(AiQueryAssetModel).where(
                        AiQueryAssetModel.is_deleted.is_(False),
                        AiQueryAssetModel.included.is_(True),
                    )
                )
            ).scalars().all()
            columns = (
                await db.execute(
                    _sel(AiQueryAssetColumnModel).where(
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                        AiQueryAssetColumnModel.included.is_(True),
                    )
                )
            ).scalars().all()
        colmap: dict[str, list[str]] = {}
        for c in columns:
            colmap.setdefault(c.table_name, []).append(c.column_name)
        dict_lines = []
        for t in tables:
            dict_lines.append(f"表 {t.table_name}：{(t.description or '').strip() or '-'} | 字段: {', '.join(colmap.get(t.table_name, []))}")
        dict_text = "\n".join(dict_lines[:120])
        # 2) LLM 生成建议（agno 结构化输出：结构由模型侧 JSON schema 约束）
        prompt = (
            "你是数据分析师。根据下面的数据库表/字段中文词典，推荐 6~10 个高频业务指标和 6~10 个业务术语。"
            "指标必须是常见统计口径(总数/某类型数量/平均/分布)，且能用给出的表/字段实现；"
            "指标的 sql 必须是可执行的 SELECT COUNT/AVG 等聚合语句，agg 取 count|avg|group；"
            "术语的 type 取 metric|dimension，target 写指标名或「表.字段」。"
            f"\n数据字典：\n{dict_text}"
        )
        out = await cls._llm_structured(prompt, MetricsTermsOut, temperature=0.2,
                                        max_tokens=4000, tag="aistation-suggest")
        return {
            "metrics": [m.model_dump() for m in out.metrics],
            "terms": [t.model_dump() for t in out.terms],
        }
