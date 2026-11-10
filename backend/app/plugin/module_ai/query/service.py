"""智能问数服务：语义层 + 快慢双路径 + 安全查询引擎 + 会话/反馈。

设计要点：
- 语义层(指标/术语/维度)是两条路径共享的知识底座。
- 高频问题命中指标模板 → 快路径(秒级)；未命中 → LLM NL2SQL 慢路径(精准兜底)。
- 所有执行只读 + 白名单表/字段 + 超时 + LIMIT，权限不可绕过。
"""
from __future__ import annotations

import re
from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# 静默降级计数已拆到 ``degraded.py``（2026-11-08）：这里只做**同名再导出**，
# 保证 `service._degrade` / `service.degraded_status` / `S.reset_degraded` 等
# 全部旧调用点（含测试 monkeypatch）继续可用。
from app.core.database import async_db_session  # noqa: F401

from .access_ops import AccessOps
from .actions_ops import ActionsOps
from .allowlist import (
    _DEFAULT_SENSITIVE_COLS,  # noqa: F401
    _ONT_IMPORT_EXCLUDE,  # noqa: F401
    SYSTEM_ALLOWED_TABLES,  # noqa: F401
)
from .answer_ops import AnswerOps
from .ask_ops import AskOps
from .assetio_ops import AssetIoOps
from .assets_ops import AssetsOps
from .assets_ops import ensure_marking_columns as _ensure_marking_columns  # noqa: F401
from .autopilot_ops import AutopilotOps
from .context_ops import ContextOps
from .datasource_core import (
    _assert_ds_access,  # noqa: F401
    _ds_cfg_from_model,  # noqa: F401
    _ds_code,  # noqa: F401
    _load_ds,  # noqa: F401
    _norm_datasource,  # noqa: F401
    list_ds_schema,  # noqa: F401
    sync_datasource_schema,  # noqa: F401
    test_datasource_conn,  # noqa: F401
)
from .datasource_ops import DatasourceOps
from .degraded import degrade as _degrade  # noqa: F401
from .degraded import degraded_status, reset_degraded  # noqa: F401
from .dq_ops import DqOps
from .execute_ops import ExecuteOps
from .execution import (
    _actor_id,  # noqa: F401
    _auth_scope,  # noqa: F401
    _clamp_rows,  # noqa: F401
    _cosine,  # noqa: F401
    _default_sensitive_return_cols,  # noqa: F401
    _execute_bound_metric,  # noqa: F401
    _execute_custom_ds_sql,  # noqa: F401
    _execute_metric,  # noqa: F401
    _execute_sql,  # noqa: F401
    _ir_max_tokens,  # noqa: F401
    _json_cell,  # noqa: F401
    _render_template,  # noqa: F401
    _scan_ont_tables,  # noqa: F401
    _secure_ont_sql,  # noqa: F401
    _system_allowed,  # noqa: F401
    _user_role_codes,  # noqa: F401
    nl2sql_attempts,  # noqa: F401
    nl2sql_max_tokens,  # noqa: F401
    scope_tables_to_schema,  # noqa: F401
)
from .fewshot_ops import FewshotOps
from .governance_ops import GovernanceOps
from .llm_ops import LlmOps
from .metric_rules import AGG_INTENT as _AGG_INTENT  # noqa: F401
from .metric_rules import AGG_NOUN_RE as _AGG_NOUN_RE  # noqa: F401
from .metric_rules import GENERIC_BIGRAMS as _GENERIC_BIGRAMS  # noqa: F401
from .metric_rules import GROUPING_RE as _GROUPING_RE  # noqa: F401
from .metric_rules import LATIN_WORD_RE as _LATIN_WORD_RE  # noqa: F401
from .metric_rules import METRIC_NAME_SUFFIXES as _METRIC_NAME_SUFFIXES  # noqa: F401
from .metric_rules import MIN_METRIC_SCORE as _MIN_METRIC_SCORE  # noqa: F401
from .metric_rules import NEEDS_SQL_RE as _NEEDS_SQL_RE  # noqa: F401
from .metric_rules import ORDER_WORD_RE as _ORDER_WORD_RE  # noqa: F401
from .metric_rules import TIME_QUALIFIER_RE as _TIME_QUALIFIER_RE  # noqa: F401
from .metric_rules import bigrams as _bigrams  # noqa: F401
from .metric_rules import build_params as _build_params  # noqa: F401
from .metric_rules import effective_agg as _effective_agg  # noqa: F401
from .metric_rules import fast_path_blockers as _fast_path_blockers  # noqa: F401
from .metric_rules import latin_words as _latin_words  # noqa: F401
from .metric_rules import match_metric as _match_metric  # noqa: F401
from .metric_rules import metric_accepts_time as _metric_accepts_time  # noqa: F401
from .metric_rules import metric_main_table as _metric_main_table  # noqa: F401
from .metric_rules import metric_name_core as _metric_name_core  # noqa: F401
from .metric_rules import metric_prompt_hint as _metric_prompt_hint  # noqa: F401
from .metric_rules import needs_custom_sql as _needs_custom_sql  # noqa: F401
from .metric_rules import pick_fewshots, score_fewshot  # noqa: F401
from .metric_rules import prefers_rowcount as _prefers_rowcount  # noqa: F401
from .metric_rules import prioritize_metric_object as _prioritize_metric_object  # noqa: F401
from .metric_rules import wants_grouping as _wants_grouping  # noqa: F401
from .metrics_ops import MetricsOps
from .nl2sql_ops import Nl2SqlOps
from .ontbridge_ops import OntBridgeOps
from .ontology_ops import OntologyOps
from .pipeline_ops import PipelineOps
from .propositions_ops import PropositionsOps
from .query_ddl import _QUERY_TABLES_SQL  # noqa: F401
from .question_rules import DAYS_RE as _DAYS_RE  # noqa: F401
from .question_rules import LISTING_RE as _LISTING_RE  # noqa: F401
from .question_rules import detect_time_frame as _detect_time_frame  # noqa: F401
from .question_rules import is_listing_question as _is_listing_question  # noqa: F401
from .question_rules import metric_time_hint as _metric_time_hint  # noqa: F401
from .question_rules import parse_time_range  # noqa: F401
from .question_rules import wants_full_list as _wants_full_list  # noqa: F401
from .recall_ops import RecallOps
from .report_ops import ReportOps
from .rewrite_ops import RewriteOps
from .routing_ops import RoutingOps
from .runtime_flags import (
    _ddl_for_dialect,  # noqa: F401
    _ensure_query_tables,  # noqa: F401
    _ir_circuit_open,  # noqa: F401
    _mark_ir_fail,  # noqa: F401
    bypass_caches,  # noqa: F401
    config_override,  # noqa: F401
    invalidate_ont_allow_cache,  # noqa: F401
    set_eval_context,  # noqa: F401
)
from .schema_ops import SchemaOps
from .seed_data import (
    _ENTITY_TABLE,  # noqa: F401
    _NL2SQL_FEWSHOT,  # noqa: F401
    _SYSTEM_METRICS,  # noqa: F401
    _SYSTEM_TERMS,  # noqa: F401
)
from .seed_ops import SeedOps
from .session_ops import SessionOps
from .settings_ops import SettingsOps
from .slowpath_ops import SlowPathOps
from .sqlcache import cfg_sig as _cfg_sig  # noqa: F401
from .sqlcache import retrieval_cache_key as _retrieval_cache_key  # noqa: F401
from .sqlcache import sql_cache_clear  # noqa: F401
from .sqlcache import sql_cache_get as _sql_cache_get  # noqa: F401
from .sqlcache import sql_cache_key as _sql_cache_key  # noqa: F401
from .sqlcache import sql_cache_set as _sql_cache_set  # noqa: F401
from .sqlguard import COMMENT_RE as _COMMENT_RE  # noqa: F401
from .sqlguard import FORBIDDEN_RE as _FORBIDDEN  # noqa: F401
from .sqlguard import tables_in_sql as _tables_in_sql  # noqa: F401
from .sqlguard import validate_sql  # noqa: F401
from .vector_ops import VectorOps
from .version_ops import VersionOps
from .workspace_ops import WorkspaceOps

# ---------------------------------------------------------------------------
# 本系统数据源保留编码
# ---------------------------------------------------------------------------
SYSTEM_DS = "system"
MAX_ROWS = 1000
QUERY_TIMEOUT = 10  # 秒


# 模块级标记：系统种子仅首次执行，避免每次 ask 都做 upsert 拖慢快路径
_SEED_DONE = False
# 进程级缓存：系统表真实列 schema（供 NL2SQL 注入）
_SCHEMA_CACHE: dict | None = None
# 进程级缓存：embedding schema 向量索引（供语义检索）
_SEMANTIC_INDEX: list | None = None
# pgvector 是否已播种资产向量
_VECTOR_SEEDED = False

# ---------------------------------------------------------------------------
# 建表入口：问数侧历史影子表
#
# 历史遗留：ai_pipeline / ai_pipeline_run / ai_data_domain / ai_workshop_app /
# ai_access_rule / ai_query_writeback / ai_query_writeback_log / ai_delivery_proposition / ai_dq_report
# 此前只在开发库中手工创建，代码里没有建表语句，新环境部署会直接失败。
# 这里补齐统一的运行时建表（幂等、best-effort），并在应用启动时调用一次。
# SQLite（单元测试库）不支持 BIGSERIAL，由测试自身 DDL 提供结构，此处失败不影响功能。
# ---------------------------------------------------------------------------

#: 存量库缺列补齐（SQLite 不支持 ADD COLUMN IF NOT EXISTS，失败忽略）
_QUERY_ALTER_COLS = (
    # 方言无关补列：SQLite **不支持** `ADD COLUMN IF NOT EXISTS`（会语法错误），
    # 旧实现把 ALTER 写在 SQL 串里，SQLite 测试库永远建不出这些列（实测 p.datasource 报错）。
    ("ai_workshop_app", "deleted_time", "TIMESTAMP"),
    ("ai_pipeline", "datasource", "VARCHAR(120)"),
    ("ai_query_sessions", "is_eval", "BOOLEAN"),
)


# Agno 向量库是否已播种语义单元
_AGNO_SEEDED = False
# Agno 语义单元是否正在后台播种
_AGNO_SEEDING = False
# 进程级缓存：工程配置（UI 保存时失效）
_SETTINGS_CACHE: dict | None = None
# 进程级缓存：表级资产元数据（中文名/业务域/描述/业务场景）
_ASSET_TMETA: dict | None = None
_ONT_ALLOW_CACHE: set | None = None
#: 缓存建立时间（monotonic）与有效期。本体定义可能在**别的模块**里被改写
#: （如「数据源→本体对象」导入），跨模块回调失效会引入循环依赖，故用 TTL 兜底：
#: 最多 60 秒后重建；同模块的写入路径则**立即**失效（见 `invalidate_ont_allow_cache`）。
_ONT_ALLOW_CACHE_AT: float = 0.0
_ONT_ALLOW_TTL = 60.0


#: 当前对象上下文（对齐 Palantir Retrieval Context 的 Fixed Object Set）。
#: 由 ``ask()`` / ``ask_stream()`` 在请求开始时**确定性注入**（不由模型决定是否检索），
#: 供 prompt（``_build_schema_context``）与对象查询共用。
#: 用 ContextVar 而非类属性：请求作用域隔离，并发请求与子任务不会互相串。
_OBJECT_CTX: ContextVar[str] = ContextVar("ai_query_object_ctx", default="")

#: 评测上下文：评测（/ai/eval）逐题调用 `ask`，必须与真实用户问数历史隔离。
#: 置 True 时会话打 `is_eval` 标记 → 问数历史默认不显示、使用统计不计入。
_EVAL_CTX: ContextVar[bool] = ContextVar("ai_query_eval_ctx", default=False)

#: 旁路所有问数缓存（SQL / prompt 上下文 / 召回）。
#:
#: 为什么评测必须旁路：``_SQL_CACHE`` TTL 30 分钟，``_slow_path`` 一进来就查它。
#: 「跑一遍 → 改配置/改提示词 → 30 分钟内再跑」时每道题都回放上一轮 SQL，
#: 两次结果必然一致 —— 对比、消融、方差全部失去意义。
#: 反向同样有害：评测生成的 SQL 会写进共享缓存，30 分钟内**喂给真实用户**。
#: 所以评测期间**既不读也不写**。
_BYPASS_CACHE: ContextVar[bool] = ContextVar("ai_query_bypass_cache", default=False)


#: 工程配置的任务内覆盖层。
#:
#: 评测的消融需要「临时改几个开关」。旧实现直接 `UPDATE ai_query_settings` 再恢复，
#: 那是**全局可变状态**：一次消融跑几分钟，期间所有真实用户都跑在消融配置下
#: （比如 recall 被关掉）。改成 ContextVar 覆盖层后：不写库、只影响当前任务，
#: 子任务通过 context 继承自然生效。
_CFG_OVERRIDE: ContextVar[dict[str, str] | None] = ContextVar(
    "ai_query_cfg_override", default=None)


#: 对象查询热度（对象编码 → 命中次数）与「本进程已自动建过索引」的对象。
#: 用途：**热度驱动自动建索引**（G4）。高频对象才值得建索引，避免无谓 DDL；
#: ``_OQ_INDEXED`` 兼作并发去重（先占位再建，失败回滚占位）。
_OQ_HEAT: dict[str, int] = {}
_OQ_INDEXED: set[str] = set()

#: 对象查询 IR 最近一次失败（空正文/超时）的时间戳：失败后**熔断 90 秒**。
#: 实测连问多题时，模型对某类问题持续吐不出 IR，每题都要白等 30s×2 才降级 NL2SQL。
_IR_FAIL_AT: float = 0.0
_IR_FAIL_COOLDOWN = 90.0


# 禁止出现的 SQL 关键片段（防 DDL/DML/多语句/写操作）
# 合法 SQL 标识符（表名/列名）：数据资产入口把参数直接拼进 ``FROM "x"``，
# 表名含 ``"`` 即可闭合引号注入任意 SQL，所以必须先卡标识符再拼 SQL（P0-1）
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 本系统可查询表（白名单，用于系统数据源的安全校验）

#: 实体名词 → 相关表（保证联表取名称时，name 承载表一定进入 schema 上下文）


# ---------------------------------------------------------------------------
# 自定义数据源连接/执行（阶段B）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 语义层：本系统数据源预置指标（可经指标运营后台增改）
# ---------------------------------------------------------------------------


# NL2SQL few-shot 示例：覆盖 JOIN / 时间序列 / 分组聚合 等常用报表模式


# ---------------------------------------------------------------------------
# 时间/参数解析
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# SQL 安全校验
# ---------------------------------------------------------------------------
#: 问题里出现这些词，说明用户要的是**全量列举**（"每个告警规则各触发多少"）

#: 但这些词出现时，用户要的是**前 N 条**，恰恰不能放宽 LIMIT。
#: 真实踩过：`各算法类型的平均延迟，取前5名` 里含"各"，被误判成全量列举，
#: 5 行被放到 1000 行——基准立刻从 ✓ 变 ✗（自己引入的回退，靠复测抓出来的）。


# ---------------------------------------------------------------------------
# 查询执行（只读、超时、行数上限）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# NL2SQL 的 **SQL 缓存**（不是结果缓存）
#
# 为什么只缓存 SQL：问数的"慢"几乎全在**生成 SQL 的那次 LLM 调用**上，
# 而执行只要几十毫秒。缓存生成的 SQL 就能把重复提问从 ~10s 降到 ~百毫秒。
#
# 为什么**不能**缓存结果行：结果必须按调用者身份重新执行——
# 行级/列级策略是在执行时下推的（见 security.secure_sql）。
# 一旦把结果行缓存起来，A 看到的数据就会被 B 拿到。
# 这是"快"与"安全"的边界，不能含糊。
# ---------------------------------------------------------------------------
_SQL_CACHE: dict[str, tuple[float, str]] = {}
_SQL_CACHE_TTL = 1800.0      # 秒；schema/数据口径变化靠 TTL 兜底
_SQL_CACHE_MAX = 500         # 上限，防内存无界增长


#: 别名检索一次最多补几张表。
#: 对象名（如"告警记录表"）含"告警"这种通用词，若拿它当匹配信号，会给大量
#: 无关问题塞进额外表 —— 实测这让 prompt 变大、生成 p50 从 3147ms 涨到 6483ms
#: （精度还降了）。所以只匹配**人工登记的别名**，并且限量。
_ONT_ALIAS_MAX_TABLES = 3

#: 自定义数据源表结构的进程内缓存：{ds:表结构, (时间, {表: [列]})}。
#: 331 张表的同步结果每次问答都读库太浪费。
_DS_SCHEMA_CACHE: dict[str, tuple[float, dict]] = {}
#: 数据源「表 → {列名: 类型}」缓存（与 schema 缓存同 TTL，供 prompt 标注类型用）
_DS_TYPE_CACHE: dict[str, tuple[float, dict]] = {}
#: 问数 prompt 上下文缓存（问题 → 拼好的 schema 文本）：自纠错重试/重复提问复用
_SCHEMA_CTX_CACHE: dict[str, tuple[float, str]] = {}
#: 低基数列取值缓存（数据源|表 → 行），取远端库有成本，缓存 10 分钟
_ENUM_HINT_CACHE: dict[str, tuple[float, list[str]]] = {}
_ENUM_HINT_TTL = 600.0
_SCHEMA_CTX_TTL = 120.0
_SCHEMA_CTX_CACHE_MAX = 50
_DS_SCHEMA_TTL = 600.0

#: 数据源 → sqlglot 读方言（enforce/shadow 才用）。ds 类型很少变，缓存 5 分钟，
#: 避免每次问数都为了取 type 多读一次 `ai_query_datasources`。
_SQL_DIALECT_CACHE: dict[str, tuple[float, str]] = {}
_SQL_DIALECT_TTL = 300.0


#: 检索结果记忆缓存：同一问题在一次问答里会被检索两次（拼 prompt + 溯源），
#: 而检索会走向量搜索。缓存它比缓存 SQL 更安全（不含数据、不含权限），
#: 但同样要带 TTL —— 本体/资产目录变了要能自动失效。
_RETRIEVAL_CACHE: dict[str, tuple[float, list[str]]] = {}
_RETRIEVAL_CACHE_TTL = 600.0
_RETRIEVAL_CACHE_MAX = 500


#: 会影响「召回结果 / prompt 内容」的设置项。这些 key 一变，缓存必须换 key，
#: 否则管理员改完开关，进程内缓存还会按旧配置继续吐结果（TTL 120~600 秒）。
#: 判据：**它出现在 prompt 里，或决定进 prompt 哪些表/列**。新增同类开关记得加进来。
_CTX_CFG_KEYS: tuple[str, ...] = (
    "recall_enabled", "recall_top_k", "recall_min_score", "recall_expand_cap",
    "recall_w_vector", "recall_w_keyword", "recall_w_ontology", "recall_w_entity",
    "schema_top_k", "schema_semantic_weight", "schema_keyword_weight",
    "entity_enabled", "entity_map", "kg_enabled", "agno_semantic_enabled",
    "schema_column_prune_enabled", "enum_hint_enabled",
    "schema_asset_meta_enabled",
    "multi_dialect_enabled",
)


# P1-12 方案 b：内置默认敏感列名单（fail-closed 底板）。
# 作为「配置显式标记（ai_query_asset_columns.sensitive / 本体属性 sensitive）」之外的兜底，
# 凡**返回结果列**命中该名单（大小写不敏感，含常见变体）即默认拦截、永不返回明文。
# 只拦「返回列」，不拦 WHERE / JOIN 里的引用（否则会伤到正常过滤）。


# ---------------------------------------------------------------------------
# 语义匹配（快路径）：术语/指标名 → 指标 + 参数
# ---------------------------------------------------------------------------


#: 无区分度的中文二元组：出现在问句里**不代表**指向某个指标（实测误命中的元凶）

#: 指标命中的最低分（低于此分视为"只是碰巧撞了个通用词"）


#: NL2SQL 生成的 token 下限。实测本机模型**先推理约 2084 token 才输出 SQL**，
#: 低于此下限时预算被推理吃光 → finish_reason=length、正文为空 → "未生成有效的查询语句"。
NL2SQL_MIN_MAX_TOKENS = 4000
NL2SQL_DEFAULT_MAX_TOKENS = 8000


#: 「分组/逐个」诉求：单值指标答不了，快路径必须让位给慢路径（实测会答成语义完全错）


#: 指标名尾部的「度量词」：问句里通常只说实体名（「矿点」），不说「矿点数」。
#: 实测：「矿点一共有多少个？」对指标「矿点数」的二元组得分只有 3（门槛 4），
#: 于是明明有对应指标却走了慢路径。剥掉尾部度量词后直接命中实体名。


#: 「需要 WHERE/DISTINCT」的问法：单值指标模板算不出来 → 必须让位 NL2SQL。
#: 实测：「化验单备注里有多少条包含自动生成？」被「化验单数」答成 2527（总数），
#: 「化验方式有几种？」同样被总数抢答 —— 语义完全错。


#: 时间限定词：出现即说明问句**带了时间范围**。
#: 必须与模板参数对上，否则模板答的是"全量"，却会被标成"最近一个月"——
#: 实测「最近一个月平均收到基低位发热量」返回的 SQL 里**一个时间条件都没有**，
#: 用户完全看不出这是错的。

#: 聚合诉求：对象路径（实体检索）表达不了
_OBJECT_AGG_RE = re.compile(r"(平均|合计|总计|总量|求和|汇总|占比|百分之)")

#: 排序诉求（模板只出聚合值，给不了有序结果集）

#: 「聚合词 + 对象」：用来校验模板算的是不是同一个东西（平均灰分 ≠ 平均发热量）。
#: 对象取 2~6 个中文字，且排除「是多少/为多少」这类提问尾巴。

#: 问句里的「聚合意图」词（只认会导致答案口径完全不同的那几类）


# ---------------------------------------------------------------------------
# 数据源 → 本体：批量导入时默认排除的「纯技术表」
#
# 这些表没有业务对象语义（迁移版本、调度器、日志、向量、配置、纯多对多关联表等），
# 导入后只会在本体里制造噪声对象。需要全量导入时传 include_technical=True。
# 名字做表名精确匹配（不支持通配）。
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 语义层 CRUD + 种子
# ---------------------------------------------------------------------------
class AiQueryService(ActionsOps, AssetsOps, MetricsOps, OntologyOps, PropositionsOps, ExecuteOps, ContextOps, Nl2SqlOps, SlowPathOps, AskOps, SettingsOps, DatasourceOps, SessionOps, ReportOps, DqOps, PipelineOps, VersionOps, RecallOps, RoutingOps, SchemaOps, LlmOps, OntBridgeOps, SeedOps, AutopilotOps, AnswerOps, RewriteOps, AccessOps, WorkspaceOps, GovernanceOps, FewshotOps, AssetIoOps, VectorOps):

    # ---- 指标 ----

    # ---------------------------------------------------------------- #
    # 派生指标规则引擎（Ontology）
    # ---------------------------------------------------------------- #
    _DERIVED_RULES = [
        {"key": "alert_per_online", "name": "今日告警强度", "num": "alert_count_today",
         "den": "camera_online_count", "unit": "条/台",
         "desc": "今日告警数 / 在线摄像头数，衡量告警强度"},
        {"key": "monthly_alert_avg", "name": "本月日均告警", "num": "alert_count_month",
         "den": None, "divisor": 30, "unit": "条/天",
         "desc": "本月告警数 / 30，估算日均告警量"},
    ]

    # ---------------------------------------------------------------- #
    # Compass 收藏/引用中心
    # ---------------------------------------------------------------- #

    # ---------------------------------------------------------------- #
    # AIP 插件/工具市场
    # ---------------------------------------------------------------- #

    # ---------------------------------------------------------------- #
    # 数据质量规则引擎
    # ---------------------------------------------------------------- #
    _DQ_RULE_TEMPLATES = [
        {"key": "not_null", "name": "非空校验", "desc": "校验字段非空率"},
        {"key": "unique", "name": "唯一性校验", "desc": "校验字段是否唯一"},
        {"key": "range", "name": "范围校验", "desc": "校验字段数值在指定范围"},
    ]

    # ---------------------------------------------------------------- #
    # 数据资产入口（导出/浏览/质量规则）统一表名校验（P0-1 安全修复）
    # ---------------------------------------------------------------- #

    # ---------------------------------------------------------------- #
    # Compass 数据目录分类
    # ---------------------------------------------------------------- #

    #: 允许表单写入的对象表（演示安全白名单）
    _WORKSHOP_WRITABLE = {"ont_orders"}

    # ---- 示例工程（few-shot）----

    # ---- 查询限额配置 ----

    # ---- 使用统计 / 反馈闭环 ----

    # ---- 数据源 ----

    # ---- 大模型辅助：筛选规则（suggest / parse / classify-advise） ----

    # ---- 会话与问答 ----

    # ---- 核心：问答入口 ----

    # ------------------------------------------------------------------
    # 对象查询（语义执行层）：LLM 只输出 IR，由本体实例层确定性执行
    # 设计：docs/superpowers/specs/2026-10-14-semantic-query-layer-design.md
    # ------------------------------------------------------------------

    # ---- 语义召回单元（阶段1：自建召回服务的底座）----
    #
    # 旧实现把「裸标识符」喂给向量库（`数据表 {t}` / `表 {t} 的字段 {c}`），
    # 中文业务词检索不到；这里改为从「资产元数据 + 本体语义 + 指标/术语」构建
    # **高语义密度**文本（见 recall.py 的 build_*）。
    _RECALL_UNITS_COLS = (
        "id BIGSERIAL PRIMARY KEY, kind VARCHAR(24) NOT NULL, ref VARCHAR(200) NOT NULL, "
        "text TEXT, meta JSONB, version BIGINT, is_deleted BOOLEAN DEFAULT false, "
        "created_time TIMESTAMP, updated_time TIMESTAMP, UNIQUE(kind, ref)"
    )

    #: 技术列前缀：同步/版本/排序这类，取值对写 SQL 没有帮助
    _ENUM_SKIP_PREFIX = ("SYNC", "VERSION", "SORT", "SERIAL", "ROWVERSION", "DISCRIMINATOR")

    #: 低基数列（枚举）候选：名字像状态/类型/标记的列
    _ENUM_COL_RE = re.compile(
        r"^(IS[A-Z_]+|.*(STATUS|STATE|TYPE|WAY|KIND|MODE|LEVEL|FLAG|CATEGORY|CLASS|SOURCE))$")

    #: 结构性列：主键/外键/时间/名称/状态——即使问句没提到也要保留
    _STRUCT_COL_RE = re.compile(
        r"(^ID$|ID$|CODE$|NAME$|DATE$|TIME$|^IS[A-Z]|STATUS$|TYPE$|WAY$|QTY$|AMOUNT$|PRICE$)")

    #: 字面量里的普通字符串（单引号，排除双引号标识符与转义）
    _SQL_LITERAL_RE = re.compile(r"'((?:[^']|'')*)'")

    #: 模型偷懒时用的占位列名 —— 这些当成"没起名"，摘要里不念出来
    _LAZY_COLS = {"c", "n", "cnt", "count", "total", "num", "value", "v",
                  "数量", "总数", "个数", "结果", "值", "合计", "总计"}

    # ---- 反馈 ----
