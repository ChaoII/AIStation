"""问数配置：默认值、生效值、读取封装（2026-11-08 从 service.py 拆出）。

三层语义要分清（踩过：接口返回默认值、代码读另一份，改配置不生效）：
- ``get_settings``：**默认值 + 库里的覆盖值**合并后的界面口径；
- ``effective_settings``：真正生效的那份（含只读/实验开关的硬约束）；
- ``_cfg*``：业务代码统一入口（int/float/bool 归一），不要各处自己 ``str`` 比较。
"""
from __future__ import annotations

import os

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from . import service as _svc
from .model import AiQuerySettingModel


class SettingsOps:
    @classmethod
    async def save_setting(cls, key: str, value: str, remark: str, auth) -> dict:
        """写一条工程配置。

        ``policy_engine`` 是**问数权限判定开关**，只允许超级管理员修改：
        ``/ai/query/settings/save`` 只要求 ``module_ai:query:ask``，任何能问数的人都能
        把它改成 ``legacy`` 来关掉判定（2026-11 复审 I2）。这里不静默忽略 —— 显式报错
        才能让调用方知道"没生效"，也不会让管理员误以为保存成功。
        """
        if str(key or "").strip() == "policy_engine":
            is_super = bool(getattr(getattr(auth, "user", None), "is_superuser", False))
            if not is_super:
                raise CustomException(
                    msg="policy_engine 只允许超级管理员修改（问数权限判定开关，禁止普通用户变更）",
                    status_code=403,
                )
        async with async_db_session.begin() as db:
            from sqlalchemy import select

            existing = (
                await db.execute(
                    select(AiQuerySettingModel).where(
                        AiQuerySettingModel.key == key,
                        AiQuerySettingModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.value = value
                existing.remark = remark
                existing.updated_id = auth.user.id
            else:
                db.add(AiQuerySettingModel(key=key, value=value, remark=remark,
                                           created_id=auth.user.id, updated_id=auth.user.id))
            await db.flush()
        _svc._SETTINGS_CACHE = None
        return {"key": key, "value": value}

    @classmethod
    async def effective_settings(cls) -> dict:
        """当前**生效**配置（默认值 + 库内覆盖），供界面回显。"""
        return await cls._cfg()

    @classmethod
    async def get_settings(cls) -> dict:
        defaults = {
            # 行数上限/超时/重试：**这三个以前只写在默认值里、代码从不读**
            # （`MAX_ROWS`、`QUERY_TIMEOUT`、`range(2)` 都是硬编码），界面改了不生效。
            "query_max_rows": "1000",
            "query_timeout_sec": "10",
            "nl2sql_retry": "2",
            "nl2sql_max_tokens": "1200",
            # agno 阶段的**硬天花板**（秒）：单次 HTTP 超时只是下层，agno 内部还可能重试/多段，
            # 叠起来能把一道题拖到 467 秒（实测）。超时 → 抛错走自纠错/降级，不让用户干等。
            "nl2sql_call_timeout": "90",
            # 思考模式：low（默认，保留少量思考）/ off（完全不思考，最快）/ on（不限制，会重现长尾）
            # 实测同一难题：无限制 22.3s ｜ low 4.6s ｜ off 3.8s
            "nl2sql_thinking_mode": "low",
            # 模型保活：实测冷启动会把首次问数拖到 29.7s（热了 1.8s）→ 周期焐热
            "llm_keepalive_enabled": "true",
            "llm_keepalive_interval": "240",
            # ---- 工程配置（schema 链接 / 提示词策略）----
            "schema_top_k": "16",                    # 注入 schema 上下文的表数量上限
            "schema_semantic_weight": "0.6",         # 语义检索权重
            "schema_keyword_weight": "0.4",          # 关键词检索权重
            "entity_enabled": "true",                # 是否启用「实体名词→表」基线
            # 是否注入枚举字段真实取值。**默认关**：配对实测关掉更好
            # （0.9231 → 0.9487，2 题，仍在噪声内，但没有正收益证据）。
            "enum_hint_enabled": "false",
            "full_entity_no_limit": "true",          # 全量实体查询提示词规则（不 LIMIT 截断）
            "entity_name_rule": "true",              # 实体查询提示词规则（JOIN 取 name）
            "entity_map": "{}",                      # 实体名词→表映射（JSON，覆盖默认）
            "agno_semantic_enabled": "true",         # 语义检索走 Agno(Knowledge+PgVector)，后台播种
            "self_consistency_n": "1",               # 自一致性候选数(>1 多采样投票)
            "query_cost_enabled": "true",            # 查询代价护栏(EXPLAIN 预估)
            "query_cost_max_rows": "50000",          # 代价护栏预估行数上限
            "fewshot_auto_curate": "true",           # 反馈正例自动沉淀为 few-shot
            # ⚠️ 名不副实的历史遗留：它**只在提示词里加一条**「先判断单表/联表/嵌套」，
            #    **不做真分解**（真分解是下面的 two_stage_planning）。别按名字理解它。
            "decomposed_planning": "true",           # 规划提示（仅提示词一条规则，**非真分解**）
            "two_stage_planning": "false",           # 两段式**真分解**；B半A/B 实测 −7.55 分+错误率0→9.4%(计划诱发表名幻觉)→保持关
            "empty_self_correct": "true",            # 结果为空时自纠错重生成
            "agno_tool_agent": "false",              # 工具化 Agent(多轮往返，慢)；false=单次生成+本地执行自纠错
            "kg_enabled": "true",                    # 知识图谱图遍历召回(补关联表/联表路径)
            # ---- 召回服务（阶段1：多路并行 + RRF 融合）----
            "recall_enabled": "true",                # 开关；false 时退回旧的分级检索
            "recall_top_k": "12",                    # 融合后按分数保留的表数上限
            "recall_min_score": "0",                 # RRF 分数下限（0=不过滤）
            "recall_w_vector": "1.0",                # 向量通道权重
            "recall_w_keyword": "0.8",               # 关键词通道权重
            "recall_w_ontology": "1.2",              # 本体强信号权重（别名/同义词/属性）
            "recall_w_entity": "0.6",                # 实体名词通道权重
            # ---- 对象查询（语义执行层）----
            # LLM 只输出结构化「对象查询 IR」，由本体实例层确定性执行；失败自动降级 NL2SQL。
            # 默认关：需用留出法 A/B 验证（对齐 two_stage_planning 的纪律——多一层 LLM 输出
            # 有翻车先例：两段式计划实测 −7.55 分）。
            "object_query_enabled": "false",         # 语义执行层开关（默认关）
            "object_query_max_objects": "5",         # 注入 IR 提示词的对象数上限（scope 收敛）
            "object_query_call_timeout": "20",       # IR 生成单次 LLM 调用超时（秒）
            "object_query_max_traverse_depth": "1",  # traverse 最大跳数（P3：可开 2–3；默认 1=不启用多跳）
            # 为什么是 20（原 60）：IR 只是**结构化抽取**，实测：无法产出时模型会一直想到超时，
            # 60s × 2 次重试 = 120s 的纯等待（实测一次问数因此 158s）。20s 不成就降级 NL2SQL，
            # 用户体验远好于「等两分钟然后还是走 SQL」。
            # IR 生成用哪个模型：**留空 = 与 NL2SQL 同源**（默认模型）。
            # 可填模型名（如 LLM-27B-FP8）或模型 id —— 实测同一提示词：
            # deepseek-flash ≈4.4s ｜ LLM-27B ≈8.9s ｜ LLM-284B ≈29.4s。
            # IR 是纯结构化抽取，用大模型是浪费，且会把"优化路径"变成"更慢的路径"。
            "object_query_model": "",
            # ---- 热度驱动自动建索引（G4）----
            # 对象查询的执行后端是实例层，其快慢取决于过滤/分组字段有无索引。
            # 高频对象自动按建议补索引，比让用户自己去「索引」页点更现实。默认关。
            "object_query_auto_index_enabled": "false",
            "object_query_auto_index_after": "20",   # 命中多少次后触发自动建索引
            # ---- P2 多方言（G6）----
            # 把「你是 PostgreSQL 查询助手」按数据源方言参数化（纯提示词层，风险低，默认开）。
            "multi_dialect_enabled": "true",
            # ---- P2 多轮查询重写（G7）----
            # 把「那上周呢」补全为自包含问题再路由。默认关：多一次 LLM 调用，需 A/B 证明值。
            "query_rewrite_enabled": "false",
            "query_rewrite_call_timeout": "60",      # 重写单次 LLM 调用超时（秒）
            # ---- 提醒词体积/取值纠错（本轮新增，默认开）----
            # 这两个开关是上面几轮 A/B 的产物，**必须同时出现在默认值里**：
            # 只写代码分支、不进默认值 → 新库上的设置弹窗里根本看不到它，
            # 用户想回退只能自己去 UPDATE 数据库（真实踩过：我自己就是这样改的）。
            "schema_column_prune_enabled": "true",   # 按问题裁剪列清单（prompt -52%，耗时 -20%）
            "literal_fix_enabled": "true",           # 字符串字面量等价纠错（空格/全半角/大小写）
            # 下面两个是"做了但实测零收益"，**默认关**并保留代码分支；
            # 一旦进默认值，界面上就能看到、也就有了回退入口。
            "schema_asset_meta_enabled": "false",    # 把资产描述注入 prompt（实测零收益）
            # 血缘：表级血缘已自动产出（ai_query_lineage），但**影响分析先不读它**。
            # 等人工核对 3 张业务表确认无误后再改默认 true（改动只影响接口返回，
            # 关闭时与改造前完全一致）。
            "lineage_enabled": "false",
            # ---- 召回/对象查询的补充旋钮 ----
            # 软删除口径：**确定性改写**，不靠提示词。
            # 实测提示词版规则两轮自翻 5 题（baseline 0 题），收益 1~2 题还不如自身抖动，
            # 已放弃；改为执行前由代码补 `"ISDELETED" = false`（见 softdelete 模块）。
            "sql_softdelete_rewrite_enabled": "true",
            "recall_expand_cap": "4",                # 同义扩展最多追加几张表
            "object_query_max_tokens": "0",          # 0 = 跟随 nl2sql_max_tokens
            # ---- 问数权限网关（P1：legacy/shadow/enforce）----
            # 必须进默认值表：只写代码分支不进默认值 → 设置页看不到、线上切不动
            # （§10 三态开关；值只认 legacy/shadow/enforce，缺失/未知按 legacy）。
            # 也支持环境变量 POLICY_ENGINE 覆盖（见 `_cfg`，dev 用，方便切 shadow）。
            "policy_engine": "legacy",
        # 无 HTTP 身份通道（定时任务/嵌入聊天）使用的服务主体；空 = 不启用（一律拒绝）
        "service_principal_user_id": "",
        }
        async with async_db_session() as db:
            from sqlalchemy import select

            rows = (
                await db.execute(
                    select(AiQuerySettingModel).where(AiQuerySettingModel.is_deleted.is_(False))
                )
            ).scalars().all()
            # 进程级缓存：UI 保存时失效
            global _SETTINGS_CACHE
            _SETTINGS_CACHE = None
            for r in rows:
                defaults[r.key] = r.value or defaults.get(r.key, "")
        # 实体映射：返回「合并后」的有效映射（默认 + 覆盖），供前端行式编辑器展示
        try:
            import json as _json

            defaults["entity_map"] = _json.dumps(cls._cfg_entity_map(defaults), ensure_ascii=False)
        except Exception:  # noqa: BLE001
            pass
        return defaults

    @classmethod
    async def _cfg(cls) -> dict:
        """带进程级缓存的工程配置读取；save_setting 会使其失效。

        覆盖层（``config_override``）只对**当前任务**生效：评测消融用它临时改开关，
        不改库、不改全局缓存（旧实现直接 UPDATE 表，消融几分钟内真实用户全被带跑）。

        环境变量覆盖（``POLICY_ENGINE``）同理只作用于**读取结果**，不写回缓存：
        灰度切 shadow 时不必清缓存/重启进程即可验证，也不会污染库里的默认值。
        优先级：任务内 ``config_override``（评测消融，最具体）> ``POLICY_ENGINE`` 环境变量
        > 库/默认值。未设置环境变量时**零开销**（直接返回缓存对象，不拷贝）。
        """
        # 缓存归 service 的进程级全局（测试用 monkeypatch.setattr(service, "_SETTINGS_CACHE", ...)
        # 打桩）。搬进 mixin 后必须显式回写 service，否则只是本模块的新变量。
        if _svc._SETTINGS_CACHE is None:
            _svc._SETTINGS_CACHE = await cls.get_settings()
        merged = _svc._SETTINGS_CACHE
        env_engine = (os.environ.get("POLICY_ENGINE") or "").strip()
        if env_engine:
            merged = {**merged, "policy_engine": env_engine}
        overlay = _svc._CFG_OVERRIDE.get()
        if overlay:
            merged = {**merged, **overlay}
        return merged

    @classmethod
    def _cfg_bool(cls, cfg: dict, key: str, default: bool = True) -> bool:
        """读布尔开关。

        ⚠️ 曾经写成「值为真时返回 `default`」——于是**所有以 `default=False` 读取的开关
        永远不可能为真**（`two_stage_planning`、`agno_tool_agent`），配置改了也没反应。
        语义必须是：**显式值优先**，只有 key 缺失/为空才回落到 `default`。
        """
        raw = cfg.get(key)
        if raw is None or str(raw).strip() == "":
            return default
        return str(raw).strip().lower() not in ("0", "false", "no", "off")

    @classmethod
    def _cfg_int(cls, cfg: dict, key: str, default: int) -> int:
        try:
            return int(float(cfg.get(key, default)))
        except (TypeError, ValueError):
            return default

    @classmethod
    def _cfg_float(cls, cfg: dict, key: str, default: float) -> float:
        try:
            return float(cfg.get(key, default))
        except (TypeError, ValueError):
            return default

    @classmethod
    def _cfg_entity_map(cls, cfg: dict) -> dict[str, list[str]]:
        """合并默认实体映射与配置覆盖的实体映射，返回 list 值（可 JSON 序列化）。"""
        base: dict[str, list[str]] = {k: list(v) for k, v in _svc._ENTITY_TABLE.items()}
        raw = cfg.get("entity_map") or "{}"
        try:
            import json as _json

            over = _json.loads(raw) if isinstance(raw, str) else raw
        except Exception:  # noqa: BLE001
            over = {}
        for noun, tables in (over or {}).items():
            if isinstance(tables, list):
                base[str(noun)] = [str(x) for x in tables]
            elif isinstance(tables, str):
                base[str(noun)] = [x.strip() for x in tables.split(",") if x.strip()]
        return base

    @classmethod
    async def _ds_time_cfg(cls, datasource: str | None) -> dict:
        """当前数据源**生效**的时间口径（默认 + ``filter_rules.time`` 覆盖）。

        周起始日、月份口径属于业务语义：按数据源维护（数据源编辑页「时间口径」），
        代码只保留默认值（周一起 + 自然月）。
        """
        from .datasource_core import ds_filter_rules
        from .filtering import time_rules_cfg

        try:
            return time_rules_cfg(await ds_filter_rules(datasource or ""))
        except Exception:  # noqa: BLE001 - 读不到就用默认
            return time_rules_cfg(None)
