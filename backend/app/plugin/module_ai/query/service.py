"""智能问数服务：语义层 + 快慢双路径 + 安全查询引擎 + 会话/反馈。

设计要点：
- 语义层(指标/术语/维度)是两条路径共享的知识底座。
- 高频问题命中指标模板 → 快路径(秒级)；未命中 → LLM NL2SQL 慢路径(精准兜底)。
- 所有执行只读 + 白名单表/字段 + 超时 + LIMIT，权限不可绕过。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log

if TYPE_CHECKING:
    from pydantic import BaseModel

# 静默降级计数已拆到 ``degraded.py``（2026-11-08）：这里只做**同名再导出**，
# 保证 `service._degrade` / `service.degraded_status` / `S.reset_degraded` 等
# 全部旧调用点（含测试 monkeypatch）继续可用。
from .actions_ops import ActionsOps
from .ask_ops import AskOps
from .assets_ops import AssetsOps
from .ontbridge_ops import OntBridgeOps
from .seed_ops import SeedOps
from .llm_ops import LlmOps
from .schema_ops import SchemaOps
from .recall_ops import RecallOps
from .routing_ops import RoutingOps
from .pipeline_ops import PipelineOps
from .version_ops import VersionOps
from .dq_ops import DqOps
from .report_ops import ReportOps
from .session_ops import SessionOps
from .datasource_ops import DatasourceOps
from .settings_ops import SettingsOps
from .assets_ops import ensure_marking_columns as _ensure_marking_columns
from .context_ops import ContextOps
from .degraded import degrade as _degrade  # noqa: F401
from .degraded import degraded_status, reset_degraded  # noqa: F401
from .execute_ops import ExecuteOps
from .filtering import (
    DEFAULT_FILTER_RULES,
    classify_fields,
    classify_tables,
    is_audit_field,
    is_system_table,
)
from .llm_schemas import (
    AssetDescriptionOut,
    ClassifyAdviseOut,
    FilterRulesOut,
    MetricsTermsOut,
    PlanOut,
)
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
from .metric_rules import prioritize_metric_object as _prioritize_metric_object  # noqa: F401
from .metric_rules import wants_grouping as _wants_grouping  # noqa: F401
from .metrics_ops import MetricsOps
from .model import (
    AiQueryAssetColumnModel,
    AiQueryAssetModel,
    AiQueryDatasourceModel,
    AiQueryDictionaryModel,
    AiQueryFewshotModel,
    AiQueryMessageModel,
    AiQueryMetricModel,
    AiQuerySchemaModel,
    AiQuerySessionModel,
    AiQuerySettingModel,
)
from .nl2sql_ops import Nl2SqlOps
from .ontology_ops import OntologyOps
from .propositions_ops import PropositionsOps
from .question_rules import DAYS_RE as _DAYS_RE  # noqa: F401
from .question_rules import LISTING_RE as _LISTING_RE  # noqa: F401
from .question_rules import detect_time_frame as _detect_time_frame  # noqa: F401
from .question_rules import is_listing_question as _is_listing_question  # noqa: F401
from .question_rules import metric_time_hint as _metric_time_hint  # noqa: F401
from .question_rules import parse_time_range  # noqa: F401
from .question_rules import wants_full_list as _wants_full_list  # noqa: F401
from .schema import QueryAssetUpsert
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

# ---------------------------------------------------------------------------
# 本系统数据源保留编码
# ---------------------------------------------------------------------------
SYSTEM_DS = "system"
MAX_ROWS = 1000
QUERY_TIMEOUT = 10  # 秒


def _clamp_rows(n) -> int:
    """行数上限的**唯一**收敛点：设置项脏值/<=0 时回落到 ``MAX_ROWS``。

    与 `executor.clamp_max_rows` 同区间，两处必须一致（有守护测试比对）。
    """
    try:
        v = int(float(n))
    except (TypeError, ValueError):
        return MAX_ROWS
    if v <= 0:
        return MAX_ROWS
    return max(1, min(5000, v))


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
_QUERY_TABLES_SQL = (
    "CREATE TABLE IF NOT EXISTS ai_pipeline ("
    "id BIGSERIAL PRIMARY KEY, name VARCHAR(120), source_connection VARCHAR(120), "
    "source_table VARCHAR(120), target_object VARCHAR(120), mappings JSONB DEFAULT '[]', "
    "enabled BOOLEAN DEFAULT true, is_deleted BOOLEAN DEFAULT false, "
    "datasource VARCHAR(120), "
    "created_time TIMESTAMP DEFAULT now(), updated_time TIMESTAMP DEFAULT now())", "CREATE TABLE IF NOT EXISTS ai_pipeline_run ("
    "id BIGSERIAL PRIMARY KEY, pipeline_id BIGINT, status VARCHAR(20), message TEXT, "
    "ran_at TIMESTAMP DEFAULT now(), is_deleted BOOLEAN DEFAULT false, rows INTEGER DEFAULT 0)",
    # ⚠️ 这是**问数/治理侧**的「数据域」（Data Domain：把数据表按业务主题归类，用于问数权限与治理）。
    # 它与本体页的 `ai_ont_domain`（**本体域**：本体对象的命名空间）是**两张完全不同的表**——
    # 互不可见、互不相通、不共享数据：治理面板里的「数据域」数量/内容 ≠ 本体页的「本体域」，
    # 界面上的区分见 GovernancePanel 的说明 tooltip 与本体页「本体域」侧栏标题。
    # 合并两张表会同时动权限模型与本体命名空间，属于数据迁移级改动，**不要顺手做**。
    #
    # ⚠️ 2026-11 核查确认：数据域**目前不参与问数**——既不进 prompt、也不进召回，
    # 更不参与权限（问数可查范围 = 资产白名单 `ai_query_assets.included` + ABAC 规则
    # `ai_access_rule.allowed_tables`）。它只用于治理页的归类与统计。
    # 界面文案已按此修正；若将来要接进召回/权限，改这里的同时记得同步那句文案。
    "CREATE TABLE IF NOT EXISTS ai_data_domain ("
    "id BIGSERIAL PRIMARY KEY, name VARCHAR(120), code VARCHAR(60), description VARCHAR(255), "
    "tables JSONB DEFAULT '[]', members JSONB DEFAULT '[]', enabled BOOLEAN DEFAULT true, "
    "is_deleted BOOLEAN DEFAULT false, created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_workshop_app ("
    "id BIGSERIAL PRIMARY KEY, name VARCHAR(120), object_table VARCHAR(120), "
    "view_type VARCHAR(20) DEFAULT 'table', columns JSONB DEFAULT '[]', "
    "enabled BOOLEAN DEFAULT true, is_deleted BOOLEAN DEFAULT false, "
    "deleted_time TIMESTAMP, created_time TIMESTAMP DEFAULT now(), "
    "updated_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_access_rule ("
    "id BIGSERIAL PRIMARY KEY, name VARCHAR(120), attribute VARCHAR(60) DEFAULT 'role', "
    "value VARCHAR(120), allowed_tables JSONB DEFAULT '[]', sensitive_ok BOOLEAN DEFAULT false, "
    "enabled BOOLEAN DEFAULT true, is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_delivery_proposition ("
    "id BIGSERIAL PRIMARY KEY, title VARCHAR(200), description TEXT, criteria TEXT, "
    "owner VARCHAR(100), step_diagnosis VARCHAR(12) DEFAULT 'todo', "
    "step_modeling VARCHAR(12) DEFAULT 'todo', step_assembly VARCHAR(12) DEFAULT 'todo', "
    "step_shadow VARCHAR(12) DEFAULT 'todo', step_handover VARCHAR(12) DEFAULT 'todo', "
    "gap JSONB DEFAULT '[]', delivery_assets JSONB DEFAULT '[]', "
    "status VARCHAR(20) DEFAULT 'open', is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now(), updated_time TIMESTAMP DEFAULT now(), "
    "fde_translator VARCHAR(100) DEFAULT '', fde_data VARCHAR(100) DEFAULT '', "
    "fde_app VARCHAR(100) DEFAULT '', shadow_metric VARCHAR(120) DEFAULT '', "
    "shadow_golden VARCHAR(64) DEFAULT '', shadow_tolerance VARCHAR(32) DEFAULT '', "
    "shadow_result VARCHAR(32) DEFAULT '', shadow_actual VARCHAR(64) DEFAULT '', "
    "shadow_at TIMESTAMP)",
    # ⚠️ 与本体动作 `ai_ont_action` 是**两套**东西（2026-11 核对）：
    #   - 本表（ai_query_writeback）= 问数侧「表级写回」：直接 UPDATE 业务表某行、
    #     走 writable_cols 白名单 + 审批留痕（ai_query_writeback_log）；属历史实现，
    #     界面已标注「逐步下线」，定义在「数据与集成 → 治理 → 动作/写回」。
    #   - ai_ont_action = 本体对象上的动作：由对象页/决策中心/智能体工具
    #     （ont_action__<code>）调用，带字段白名单、规则校验、副作用与审批。
    #   **问数（NL2SQL）不会自动执行任何一方**；不要在问数链路上接 ai_ont_action。
    "CREATE TABLE IF NOT EXISTS ai_query_writeback ("
    "id BIGSERIAL PRIMARY KEY, name VARCHAR(120), object_table VARCHAR(120), "
    "writable_cols JSONB DEFAULT '[]', validation TEXT, approve BOOLEAN DEFAULT true, "
    "enabled BOOLEAN DEFAULT true, is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now(), updated_time TIMESTAMP DEFAULT now(), "
    "writable_by_role JSONB)",
    "CREATE TABLE IF NOT EXISTS ai_query_writeback_log ("
    "id BIGSERIAL PRIMARY KEY, action_name VARCHAR(120), object_table VARCHAR(120), "
    "object_key VARCHAR(120), params JSONB, operator VARCHAR(100), result VARCHAR(20), "
    "detail TEXT, created_time TIMESTAMP DEFAULT now(), is_deleted BOOLEAN DEFAULT false)",
    "CREATE TABLE IF NOT EXISTS ai_dq_report ("
    "id BIGSERIAL PRIMARY KEY, table_name VARCHAR(120), alias VARCHAR(120), "
    "total INTEGER DEFAULT 0, score NUMERIC DEFAULT 0, completeness NUMERIC DEFAULT 0, "
    "uniqueness NUMERIC DEFAULT 0, freshness NUMERIC DEFAULT 0, issues JSONB DEFAULT '[]', "
    "checked_at TIMESTAMP DEFAULT now(), is_deleted BOOLEAN DEFAULT false)",
)

#: 存量库缺列补齐（SQLite 不支持 ADD COLUMN IF NOT EXISTS，失败忽略）
_QUERY_ALTER_COLS = (
    # 方言无关补列：SQLite **不支持** `ADD COLUMN IF NOT EXISTS`（会语法错误），
    # 旧实现把 ALTER 写在 SQL 串里，SQLite 测试库永远建不出这些列（实测 p.datasource 报错）。
    ("ai_workshop_app", "deleted_time", "TIMESTAMP"),
    ("ai_pipeline", "datasource", "VARCHAR(120)"),
    ("ai_query_sessions", "is_eval", "BOOLEAN"),
)


def _ddl_for_dialect(sql: str) -> str:
    """兼容旧调用名：统一走 ``ddl_dialect.ddl_for_dialect``（方言规则只有一份）。"""
    from .ddl_dialect import ddl_for_dialect

    return ddl_for_dialect(sql)


async def _ensure_query_tables() -> None:
    """确保问数侧影子表与新增列存在（幂等、best-effort）。

    ⚠️ 不加"已执行"进程标记：测试会多次重建 SQLite 库，标记会让第二个库缺列。
    这里只有 3 次 inspect + 少量 CREATE IF NOT EXISTS，重复执行代价可接受。
    """
    for sql in _QUERY_TABLES_SQL:
        try:
            async with async_db_session.begin() as db:
                await db.execute(text(_ddl_for_dialect(sql)))
        except Exception as e:  # noqa: BLE001
            _degrade("shadow_tables", e)
    for table, col, ddl in _QUERY_ALTER_COLS:
        try:
            async with async_db_session.begin() as db:
                from sqlalchemy import inspect

                cols = await db.run_sync(
                    lambda s, _t=table: {c["name"] for c in inspect(s.connection()).get_columns(_t)}
                )
                if col not in cols:
                    await db.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
        except Exception as e:  # noqa: BLE001
            _degrade("shadow_table_columns", e)
    # 策略/审计/shadow 三张表（统一策略引擎的数据层），建表逻辑收敛在 policy/model.py
    from .policy.model import ensure_policy_tables

    await ensure_policy_tables()
    # 血缘表（`ai_query_lineage`）：enforce/shadow 的视图映射依赖它。strict 化后
    # "表不存在"会被当成读取失败 → enforce 全拒、shadow 静默零差异。必须与策略表
    # 在同一处幂等创建；失败只降级（可见），不拖垮启动。
    try:
        from .lineage import ensure_lineage_table

        await ensure_lineage_table()
    except Exception as e:  # noqa: BLE001
        _degrade("query_lineage_table", e)
    # T7 接线自检（addendum 第 4 条）：shadow 差异写入依赖
    # ``ai_policy_shadow_diff.rewrite`` 这一列。补列失败（无 DDL 权限）时差异会整条
    # 写不进去，而写入本身是 fail-open —— 表现为「差异表悄悄没数据」，灰度报告被
    # 静默骗过。启动时明确 warning，别让它沉在日志里。
    _policy_bad = [
        a["area"] for a in degraded_status()["areas"]
        if a["area"] in ("policy_tables", "policy_table_columns")
    ]
    if _policy_bad:
        log.warning(
            "[问数权限] 策略表就绪异常（degraded_status 含 {}）：shadow 差异可能整条"
            "写不进去（fail-open，不会报错），切 shadow/enforce 前先修表结构",
            "/".join(_policy_bad),
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


def invalidate_ont_allow_cache() -> None:
    """本体对象/支撑表变化后调用：让「可查询白名单」缓存立即失效。

    原先该缓存**只在进程启动时建立、永不失效** ⇒ 导入本体后必须重启后端，
    问数才认得新对象的支撑表（表现为「表 xxx 不在可查询白名单内」）。
    """
    global _ONT_ALLOW_CACHE, _ONT_ALLOW_CACHE_AT
    _ONT_ALLOW_CACHE = None
    _ONT_ALLOW_CACHE_AT = 0.0


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


@contextmanager
def bypass_caches():
    """当前任务内旁路全部问数缓存（评测/对比用）。"""
    token = _BYPASS_CACHE.set(True)
    try:
        yield
    finally:
        _BYPASS_CACHE.reset(token)


#: 工程配置的任务内覆盖层。
#:
#: 评测的消融需要「临时改几个开关」。旧实现直接 `UPDATE ai_query_settings` 再恢复，
#: 那是**全局可变状态**：一次消融跑几分钟，期间所有真实用户都跑在消融配置下
#: （比如 recall 被关掉）。改成 ContextVar 覆盖层后：不写库、只影响当前任务，
#: 子任务通过 context 继承自然生效。
_CFG_OVERRIDE: ContextVar[dict[str, str] | None] = ContextVar(
    "ai_query_cfg_override", default=None)


@contextmanager
def config_override(overrides: dict | None):
    """当前任务内临时覆盖工程配置（不落库、不外溢）。"""
    if not overrides:
        yield
        return
    merged = {**(_CFG_OVERRIDE.get() or {}),
              **{str(k): str(v) for k, v in overrides.items()}}
    token = _CFG_OVERRIDE.set(merged)
    try:
        yield
    finally:
        _CFG_OVERRIDE.reset(token)


def set_eval_context(on: bool = True) -> None:
    """评测执行器调用前打标（同任务内生效，子任务会继承）。"""
    _EVAL_CTX.set(bool(on))


#: 对象查询热度（对象编码 → 命中次数）与「本进程已自动建过索引」的对象。
#: 用途：**热度驱动自动建索引**（G4）。高频对象才值得建索引，避免无谓 DDL；
#: ``_OQ_INDEXED`` 兼作并发去重（先占位再建，失败回滚占位）。
_OQ_HEAT: dict[str, int] = {}
_OQ_INDEXED: set[str] = set()

#: 对象查询 IR 最近一次失败（空正文/超时）的时间戳：失败后**熔断 90 秒**。
#: 实测连问多题时，模型对某类问题持续吐不出 IR，每题都要白等 30s×2 才降级 NL2SQL。
_IR_FAIL_AT: float = 0.0
_IR_FAIL_COOLDOWN = 90.0


def _mark_ir_fail() -> None:
    global _IR_FAIL_AT
    _IR_FAIL_AT = time.time()


def _ir_circuit_open() -> bool:
    return _IR_FAIL_AT > 0 and (time.time() - _IR_FAIL_AT) < _IR_FAIL_COOLDOWN


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False)) / (
        (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5) + 1e-9
    )


# 禁止出现的 SQL 关键片段（防 DDL/DML/多语句/写操作）
# 合法 SQL 标识符（表名/列名）：数据资产入口把参数直接拼进 ``FROM "x"``，
# 表名含 ``"`` 即可闭合引号注入任意 SQL，所以必须先卡标识符再拼 SQL（P0-1）
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# 本系统可查询表（白名单，用于系统数据源的安全校验）
SYSTEM_ALLOWED_TABLES = {
    "ai_call_logs", "ai_assistant_messages", "ai_assistant_sessions", "ai_apps", "ai_agents",
    "ai_models", "ai_providers", "ai_skills", "ai_tools", "ai_prompts",
    "ai_reports", "ai_workflows", "annotation_dataset", "annotation_record",
    "annotation_task", "synthesis_job",
    "train_tasks", "train_models", "train_evals", "train_predicts", "train_deploys",
    "train_schedules", "train_model_repos",
    "video_alarm_records", "video_alarm_rules", "video_cameras",
    "video_camera_groups", "video_algorithms", "video_algorithm_tasks",
    "video_edge_devices", "video_edge_events", "video_face_gallery", "video_layouts",
    "video_record_files", "video_record_plans", "video_record_execution_logs",
    "sys_user", "sys_user_notification",
}

#: 实体名词 → 相关表（保证联表取名称时，name 承载表一定进入 schema 上下文）
_ENTITY_TABLE: dict[str, set[str]] = {
    "摄像头": {"video_cameras", "video_camera_groups"},
    "设备": {"video_edge_devices"},
    "算法": {"video_algorithms"},
    "任务": {"video_algorithm_tasks", "annotation_task", "train_tasks"},
    "数据集": {"annotation_dataset"},
    "规则": {"video_alarm_rules"},
    "标注": {"annotation_dataset", "annotation_task", "annotation_record"},
    "告警": {"video_alarm_records"},
    "报警": {"video_alarm_records"},
    "事件": {"video_edge_events"},
    "模型": {"ai_models", "ai_call_logs"},
    "用户": {"sys_user"},
    "合成": {"synthesis_job"},
    "报表": {"ai_reports"},
    "工作流": {"ai_workflows"},
}


# ---------------------------------------------------------------------------
# 自定义数据源连接/执行（阶段B）
# ---------------------------------------------------------------------------
def _ds_cfg_from_model(ds) -> dict:
    return {
        "type": ds.type or "postgres", "host": ds.host or "", "port": ds.port or 0,
        "database": ds.database or "", "username": ds.username or "",
        "password": ds.password or "",
    }


def _ds_code(datasource_id: int) -> str:
    return f"ds:{datasource_id}"


def _actor_id(auth) -> int | None:
    """取当前操作人 id；**内部调度**（无 HTTP 用户上下文）返回 ``None``。

    背景（实测回归）：``generate_asset_descriptions`` 这类批量动作既会被 HTTP
    接口触发（有 auth），也会被自主巡检在**后台**触发（``auth=None``）。旧实现
    直接写 ``auth.user.id`` → AttributeError → 整批「补全描述」必然失败。

    这里统一兜底为 ``None``（= 系统写入，审计字段留空），
    **不放宽任何 ACL**：归属过滤仍按真实 auth 走，``None`` 只影响审计列。
    """
    return getattr(getattr(auth, "user", None), "id", None)


async def _load_ds(datasource_id: int):
    async with async_db_session() as db:
        ds = await db.get(AiQueryDatasourceModel, datasource_id)
        if not ds or ds.is_deleted:
            raise CustomException(msg="数据源不存在")
        return ds


async def _norm_datasource(datasource) -> str | None:
    """把数据源入参**归一化**为后端口径：``system`` / ``ds:{id}``。

    背景（实测踩坑）：前端下拉的 `:value` 用的是**数据源编码**（如 ``ezdcs_pg``），
    而后端语义层（指标 `datasource`、`list_ds_schema`、`_execute_custom_ds_sql`）
    统一用 ``ds:{id}``。不归一化会导致 `int('ezdcs_pg')` 报错、
    ``list_metrics('ezdcs_pg')`` 匹配不到任何指标。

    接受 ``None``/``''``（→None，表示不限）、``system``、``ds:{id}``、编码（→查 id）。
    """
    from sqlalchemy import text as _t

    ds = str(datasource or "").strip()
    if not ds:
        return None
    if ds == SYSTEM_DS or ds.startswith("ds:"):
        return ds
    try:
        async with async_db_session() as db:
            row = (await db.execute(_t(
                "SELECT id FROM ai_query_datasources WHERE code=:c AND is_deleted=false"),
                {"c": ds})).fetchone()
        if row:
            return _ds_code(int(row[0]))
    except Exception:  # noqa: BLE001
        pass
    return ds


async def test_datasource_conn(datasource_id: int) -> dict:
    ds = await _load_ds(datasource_id)
    from . import executor as _ex

    return await _ex.test_connection(_ds_cfg_from_model(ds))


async def sync_datasource_schema(datasource_id: int) -> dict:
    ds = await _load_ds(datasource_id)
    from . import executor as _ex

    tables = await _ex.introspect_schema(_ds_cfg_from_model(ds))
    code = _ds_code(datasource_id)
    # Task3：同步时按该数据源 filter_rules 给每个字段打 is_audit 标
    rules = ds.filter_rules or DEFAULT_FILTER_RULES
    async with async_db_session.begin() as db:
        from sqlalchemy import delete
        from sqlalchemy import text as _t

        # 运行时补列（本项目 ai_* 表不走 Alembic，惯用 ADD COLUMN IF NOT EXISTS）
        try:
            await db.execute(_t(
                "ALTER TABLE ai_query_schema "
                "ADD COLUMN IF NOT EXISTS table_comment VARCHAR(255) DEFAULT ''"))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 补 ai_query_schema.table_comment 失败: {e}")
        await db.execute(
            delete(AiQuerySchemaModel).where(AiQuerySchemaModel.datasource == code)
        )
        for t in tables:
            cols = t["columns"] or []
            for c in cols:
                if isinstance(c, dict) and c.get("name"):
                    c["is_audit"] = is_audit_field(c["name"], rules)
            db.add(
                AiQuerySchemaModel(
                    datasource=code, table_name=t["table"],
                    table_comment=str(t.get("comment") or "")[:255],
                    columns=cols,
                )
            )
    # 同步完顺手重算血缘：schema 变了，旧血缘就不准了。
    # ★ 必须 try/except —— 血缘是增强，不能因为它让 schema 同步失败。
    try:
        from .lineage import rebuild_lineage

        await rebuild_lineage(datasource_id)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[query] 血缘重算失败（忽略）: {str(e)[:120]}")
    return {"tables": len(tables)}


async def list_ds_schema(datasource_id: int, included_only: bool = False) -> list[dict]:
    """某自定义数据源已同步的表结构。

    ``included_only=True`` 时只返回**数据资产目录里已纳入**的表 ——
    用于检索/prompt 的范围收敛（实测 ds:4 同步了 311 张表，其中 92 张是
    SYS_*/_BAK 等技术表，混进检索会污染召回与提示词）。
    """
    code = _ds_code(datasource_id)
    # Task3：按该数据源 filter_rules 现算 is_system/is_audit；数据源不存在时兜底默认规则
    try:
        rules = (await _load_ds(datasource_id)).filter_rules or DEFAULT_FILTER_RULES
    except CustomException:
        rules = DEFAULT_FILTER_RULES
    async with async_db_session() as db:
        from sqlalchemy import select
        from sqlalchemy import text as _t

        rows = (
            await db.execute(
                select(AiQuerySchemaModel).where(
                    AiQuerySchemaModel.datasource == code,
                    AiQuerySchemaModel.is_deleted.is_(False),
                )
            )
        ).scalars().all()
        if included_only:
            # 一张表有三种状态：**显式纳入**（included=true）/ **显式排除**（included=false）/
            # **从未建过资产行**（同步过 schema 但没治理过）。
            #
            # 旧逻辑只认「显式纳入」⇒ 新数据源刚同步完表结构（ai_query_assets 还没有行）
            # 时交集为空，NL2SQL 的 prompt 里一张表都没有 → 模型开始「编表名」。
            # 现在：没治理过的表**默认纳入**（同步即可用，界面上标「未治理」），
            # 用户显式排除的仍然排除——这与前端「纳入」列的口径一致（见 integration/index.vue）。
            seen: dict[str, bool] = {}
            for row in (
                await db.execute(
                    _t(
                        "SELECT table_name, included FROM ai_query_assets WHERE is_deleted=false"
                    )
                )
            ).fetchall():
                seen[str(row[0]).upper()] = bool(row[1])
            rows = [r for r in rows if seen.get(str(r.table_name).upper(), True)]
    return [
        {
            "table": r.table_name,
            "comment": r.table_comment or "",
            # 每列现算 is_audit（存储的 columns 可能来自旧 schema，名字判定更可靠）
            "columns": [
                (
                    {**c, "is_audit": is_audit_field(c.get("name", ""), rules)}
                    if isinstance(c, dict)
                    else c
                )
                for c in (r.columns or [])
            ],
            "is_system": is_system_table(r.table_name, rules),
        }
        for r in rows
    ]


def _user_role_codes(auth) -> set[str]:
    try:
        return {getattr(r, "code", "") for r in getattr(getattr(auth, "user", None), "roles", []) or []}
    except Exception:  # noqa: BLE001
        return set()


async def _assert_ds_access(datasource_id: int, auth) -> None:
    """校验当前用户是否有权访问该自定义数据源；超管/未限角色直接放行。"""
    ds = await _load_ds(datasource_id)
    allowed = ds.allowed_roles or []
    if not allowed:
        return
    if getattr(getattr(auth, "user", None), "is_superuser", False):
        return
    if not (_user_role_codes(auth) & set(allowed)):
        raise CustomException(msg="您无权限访问该数据源")


async def _execute_custom_ds_sql(datasource_id: int, sql: str, auth=None) -> dict:
    """对自定义数据源执行只读 SQL（含 schema 白名单校验 + 角色授权）。"""
    if auth is not None:
        await _assert_ds_access(datasource_id, auth)
    ds = await _load_ds(datasource_id)
    schema_rows = await list_ds_schema(datasource_id)
    allowed = {r["table"] for r in schema_rows}
    from . import executor as _ex
    from .sql_quote import quote_schema_identifiers

    sql = validate_sql(sql, allowed)
    # 大小写敏感库（如 ds:4）必须把表/列名写成「真实大小写 + 双引号」，
    # 否则 PG 折成小写 → 关系/列不存在（实测把整题打崩的根因之一）。
    schema_map = {
        r["table"]: [c.get("name") for c in (r.get("columns") or [])]
        for r in schema_rows
    }
    sql = quote_schema_identifiers(sql, schema_map)
    # **值匹配纠错**：SQL 里的字面量若与库里的取值"归一后相等但写法不同"
    # （尾随空格 / 全角 / 大小写），换成库里的原样写法 —— 否则等值比较查不到行。
    # 这是 Genie「entity matching」的等价物（它做匹配纠错，而不是把值列进提示词）。
    if AiQueryService._cfg_bool(await AiQueryService._cfg(), "literal_fix_enabled", True):
        try:
            used = [t for t in schema_map if t.lower() in sql.lower()][:5]
            if used:
                vmap = await AiQueryService._ds_value_map(f"ds:{datasource_id}", used, schema_map)
                if vmap:
                    fixed, fixes = AiQueryService.fix_sql_literals(sql, vmap)
                    if fixes:
                        log.info("[query] 值匹配纠错：{}（{} 处）", "；".join(fixes[:3]), len(fixes))
                        sql = fixed
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 值匹配纠错失败（忽略）: {str(e)[:80]}")
    # **字段级 ACL 对自定义数据源同样生效**（fail-closed）。
    # 之前这道检查只在系统库分支：本体/资产里把「煤款单价」标成敏感，
    # 走 ds:4 的问数照样能查出来 —— 标记形同摆设。
    # `_ont_sql_violations` 本身是按**表名**匹配 `ai_query_asset_columns.sensitive`，
    # 对外部库的表一样成立，差的只是没人调用它。
    uid = getattr(getattr(auth, "user", None), "id", None) if auth is not None else None
    try:
        violations = await AiQueryService._ont_sql_violations(sql, uid)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[query] 外部源字段级 ACL 校验失败，拒绝执行：{e}")
        raise CustomException(msg=f"字段级权限校验失败，已拒绝执行：{str(e)[:120]}") from e
    if violations:
        raise CustomException(
            msg=f"字段级权限：无权限访问 {', '.join(violations)}（请联系管理员申请可见权限）")
    # 行数上限 / 执行超时同样从设置读取：这两个 key 以前只在默认值表里躺着，
    # 实际生效的是 executor.MAX_ROWS / QUERY_TIMEOUT 常量 —— 界面改了没反应。
    _cfg = await AiQueryService._cfg()
    out = await _ex.execute_select(
        _ds_cfg_from_model(ds), sql,
        max_rows=AiQueryService._cfg_int(_cfg, "query_max_rows", _ex.MAX_ROWS),
        timeout=AiQueryService._cfg_int(_cfg, "query_timeout_sec", int(_ex.QUERY_TIMEOUT)),
    )
    # 回传**实际执行**的 SQL（已加引号）：否则展示/排查看到的是未加引号的模板，会被误导
    out["sql"] = sql
    return out


def _auth_scope(auth) -> str:
    """SQL 缓存的主体指纹：不同用户/角色不能复用同一份生成结果。

    上下文裁剪与权限判定都依赖主体，生成的 SQL 可能不同（行条件、可见表）；
    缓存不加指纹 = 把 A 的 SQL 给 B 用。
    """
    uid = getattr(getattr(auth, "user", None), "id", None)
    if uid is None:
        return "anon"
    try:
        roles = ",".join(sorted(_user_role_codes(auth)))
    except Exception:  # noqa: BLE001 - 角色取不到时退化为按用户隔离
        roles = ""
    return f"{uid}|{roles}"


# ---------------------------------------------------------------------------
# 语义层：本系统数据源预置指标（可经指标运营后台增改）
# ---------------------------------------------------------------------------
_SYSTEM_METRICS = [
    {
        "key": "alert_count_today", "name": "今日告警数", "agg": "count", "unit": "条",
        "description": "今天产生的视频告警总数（按告警时间 alarm_time）",
        "sql_template": (
            "SELECT COUNT(*) AS 数值 FROM video_alarm_records "
            "WHERE alarm_time >= CURRENT_DATE"
        ),
        "params": [], "dimensions": [], "cache_ttl": 30,
    },
    {
        "key": "alert_count_month", "name": "本月告警数", "agg": "count", "unit": "条",
        "description": "本自然月产生的视频告警总数",
        "sql_template": (
            "SELECT COUNT(*) AS 数值 FROM video_alarm_records "
            "WHERE alarm_time >= date_trunc('month', CURRENT_DATE)"
        ),
        "params": [], "dimensions": [], "cache_ttl": 60,
    },
    {
        "key": "alert_by_type", "name": "按告警类型的分布", "agg": "group", "unit": "条",
        "description": "按告警类型分组的告警数量，可过滤最近N天",
        "sql_template": (
            "SELECT COALESCE(alarm_type, '未知') AS 类型, COUNT(*) AS 数量 "
            "FROM video_alarm_records "
            "WHERE alarm_time >= CURRENT_DATE - INTERVAL '{days}' DAY "
            "GROUP BY 类型 ORDER BY 数量 DESC LIMIT 50"
        ),
        "params": [{"key": "days", "label": "最近天数", "type": "value"}],
        "dimensions": [{"key": "类型", "label": "类型", "field": "类型", "type": "string"}],
        "cache_ttl": 60,
    },
    {
        "key": "camera_online_count", "name": "在线摄像头数", "agg": "count", "unit": "台",
        "description": "摄像头总数（未删除）",
        "sql_template": "SELECT COUNT(*) AS 数值 FROM video_cameras WHERE is_deleted = false",
        "params": [], "dimensions": [], "cache_ttl": 30,
    },
    {
        "key": "train_task_count", "name": "训练任务总数", "agg": "count", "unit": "个",
        "description": "训练任务总数（未删除）",
        "sql_template": (
            "SELECT COUNT(*) AS 数值 FROM train_tasks WHERE is_deleted = false"
        ),
        "params": [], "dimensions": [], "cache_ttl": 60,
    },
    {
        "key": "call_count_7d", "name": "近7天模型调用量", "agg": "count", "unit": "次",
        "description": "近7天 AI 调用日志数量",
        "sql_template": (
            "SELECT COUNT(*) AS 数值 FROM ai_call_logs "
            "WHERE created_time >= CURRENT_DATE - 7 AND is_deleted = false"
        ),
        "params": [], "dimensions": [], "cache_ttl": 60,
    },
    {
        "key": "user_count", "name": "系统用户数", "agg": "count", "unit": "人",
        "description": "系统用户总数（未删除）",
        "sql_template": "SELECT COUNT(*) AS 数值 FROM sys_user WHERE is_deleted = false",
        "params": [], "dimensions": [], "cache_ttl": 120,
    },
    # ===== 本体业务语义（Palantir：以本体为单一事实源，把业务黑话确定为可执行指标）=====
    {
        "key": "device_health_rate", "name": "设备健康度", "agg": "ratio", "unit": "%",
        "description": "设备健康度 = 在线摄像头占比（ONLINE / 全部未删除，百分比）",
        "sql_template": (
            "SELECT ROUND(COUNT(*) FILTER (WHERE status='ONLINE')*100.0/COUNT(*),2) AS 数值 "
            "FROM video_cameras WHERE is_deleted = false"
        ),
        "params": [], "dimensions": [], "cache_ttl": 30,
    },
    {
        "key": "active_algorithm_count", "name": "活跃算法数", "agg": "count", "unit": "个",
        "description": "当前正在运行的视频算法任务数量（status=RUNNING）",
        "sql_template": (
            "SELECT COUNT(*) AS 数值 FROM video_algorithm_tasks WHERE status = 'RUNNING'"
        ),
        "params": [], "dimensions": [], "cache_ttl": 30,
    },
    {
        "key": "pending_alert_count", "name": "待处理告警数", "agg": "count", "unit": "条",
        "description": "当前待处理（PENDING）的视频告警数量",
        "sql_template": (
            "SELECT COUNT(*) AS 数值 FROM video_alarm_records WHERE status = 'PENDING'"
        ),
        "params": [], "dimensions": [], "cache_ttl": 30,
    },
    {
        "key": "query_success_rate", "name": "查询成功率", "agg": "ratio", "unit": "%",
        "description": "AI 调用查询成功率 = result='success' 占比（百分比）",
        "sql_template": (
            "SELECT ROUND(COUNT(*) FILTER (WHERE result='success')*100.0/NULLIF(COUNT(*),0),2) AS 数值 "
            "FROM ai_call_logs WHERE is_deleted = false"
        ),
        "params": [], "dimensions": [], "cache_ttl": 60,
    },
    {
        "key": "online_event_ratio", "name": "在线事件占比", "agg": "ratio", "unit": "%",
        "description": "边缘事件在线（matched=true）占比（百分比）",
        "sql_template": (
            "SELECT ROUND(COUNT(*) FILTER (WHERE matched=true)*100.0/NULLIF(COUNT(*),0),2) AS 数值 "
            "FROM video_edge_events"
        ),
        "params": [], "dimensions": [], "cache_ttl": 60,
    },
    {
        "key": "annotation_complete_rate", "name": "标注完成率", "agg": "ratio", "unit": "%",
        "description": "标注完成率 = 已标注图片数占比（百分比）",
        "sql_template": (
            "SELECT ROUND(SUM(annotated_count)*100.0/NULLIF(SUM(image_count),0),2) AS 数值 "
            "FROM annotation_dataset"
        ),
        "params": [], "dimensions": [], "cache_ttl": 60,
    },
    {
        "key": "superadmin_count", "name": "超级管理员数", "agg": "count", "unit": "人",
        "description": "超级管理员数量（is_superuser=true 且未删除）",
        "sql_template": (
            "SELECT COUNT(*) AS 数值 FROM sys_user WHERE is_superuser = true AND is_deleted = false"
        ),
        "params": [], "dimensions": [], "cache_ttl": 120,
    },
]

_SYSTEM_TERMS = [
    # 术语 → 指标/字段 映射（用于快路径意图识别与慢路径语义注入）
    {"term": "告警", "metric_key": "alert_count_today", "type": "metric"},
    {"term": "报警", "metric_key": "alert_count_today", "type": "metric"},
    {"term": "在线摄像头", "metric_key": "camera_online_count", "type": "metric"},
    {"term": "在线设备", "metric_key": "camera_online_count", "type": "metric"},
    {"term": "训练任务", "metric_key": "train_task_count", "type": "metric"},
    {"term": "模型调用", "metric_key": "call_count_7d", "type": "metric"},
    {"term": "调用量", "metric_key": "call_count_7d", "type": "metric"},
    {"term": "用户数", "metric_key": "user_count", "type": "metric"},
    {"term": "人数", "metric_key": "user_count", "type": "metric"},
    {"term": "用户", "metric_key": "user_count", "type": "metric"},
    # 本体业务语义术语（黑话 → 指标）
    {"term": "设备健康度", "metric_key": "device_health_rate", "type": "metric"},
    {"term": "健康度", "metric_key": "device_health_rate", "type": "metric"},
    {"term": "活跃算法", "metric_key": "active_algorithm_count", "type": "metric"},
    {"term": "待处理告警", "metric_key": "pending_alert_count", "type": "metric"},
    {"term": "待办告警", "metric_key": "pending_alert_count", "type": "metric"},
    {"term": "查询成功率", "metric_key": "query_success_rate", "type": "metric"},
    {"term": "成功率", "metric_key": "query_success_rate", "type": "metric"},
    {"term": "在线事件占比", "metric_key": "online_event_ratio", "type": "metric"},
    {"term": "事件占比", "metric_key": "online_event_ratio", "type": "metric"},
    {"term": "标注完成率", "metric_key": "annotation_complete_rate", "type": "metric"},
    {"term": "标注率", "metric_key": "annotation_complete_rate", "type": "metric"},
    {"term": "完成率", "metric_key": "annotation_complete_rate", "type": "metric"},
    {"term": "超级管理员", "metric_key": "superadmin_count", "type": "metric"},
]

# NL2SQL few-shot 示例：覆盖 JOIN / 时间序列 / 分组聚合 等常用报表模式
_NL2SQL_FEWSHOT = [
    {
        "q": "按告警类型统计各类告警的数量",
        "sql": "SELECT alarm_type AS 类型, COUNT(*) AS 数量 FROM video_alarm_records GROUP BY 类型 ORDER BY 数量 DESC LIMIT 50",
    },
    {
        "q": "每个摄像头各产生多少条告警",
        "sql": "SELECT COALESCE(c.name,'未知') AS 摄像头, COUNT(r.id) AS 告警数 FROM video_cameras c LEFT JOIN video_alarm_records r ON r.camera_id=c.id GROUP BY 摄像头 ORDER BY 告警数 DESC",
    },
    {
        "q": "各摄像头组的告警数量",
        "sql": "SELECT COALESCE(g.name,'未分组') AS 摄像头组, COUNT(r.id) AS 告警数 FROM video_cameras c LEFT JOIN video_camera_groups g ON c.group_id=g.id LEFT JOIN video_alarm_records r ON r.camera_id=c.id GROUP BY 摄像头组 ORDER BY 告警数 DESC LIMIT 50",
    },
    {
        "q": "最近7天每天的告警量走势",
        "sql": "SELECT TO_CHAR(alarm_time,'YYYY-MM-DD') AS 日期, COUNT(*) AS 告警数 FROM video_alarm_records WHERE alarm_time >= CURRENT_DATE - 7 GROUP BY 日期 ORDER BY 日期 LIMIT 50",
    },
    {
        "q": "各算法类型的边缘事件数量",
        "sql": "SELECT COALESCE(algorithm_type,'未知') AS 算法类型, COUNT(*) AS 事件数 FROM video_edge_events GROUP BY 算法类型 ORDER BY 事件数 DESC LIMIT 50",
    },
    {
        "q": "平均每次模型调用的耗时",
        "sql": "SELECT ROUND(AVG(latency_ms),1) AS 平均耗时ms, COUNT(*) AS 次数 FROM ai_call_logs WHERE is_deleted = false",
    },
    {
        "q": "模型调用平均耗时（毫秒）是多少",
        "sql": "SELECT ROUND(AVG(latency_ms),1) AS 平均耗时ms FROM ai_call_logs WHERE is_deleted = false",
    },
    # ---- 复杂报表模式：占比 / 窗口函数 / 联表取名称 / 多表对比 / 枚举 / 显式日期 ----
    {
        "q": "告警中 DET_ZONE 类型占比多少",
        "sql": "SELECT ROUND(COUNT(*)*100.0/(SELECT COUNT(*) FROM video_alarm_records),2) AS pct FROM video_alarm_records WHERE alarm_type='DET_ZONE'",
    },
    {
        "q": "在线摄像头占全部摄像头的比例",
        "sql": "SELECT ROUND(COUNT(*) FILTER (WHERE status='ONLINE')*100.0/COUNT(*),2) AS pct FROM video_cameras WHERE is_deleted=false",
    },
    {
        "q": "平均每个摄像头产生多少条告警",
        "sql": "SELECT ROUND(COUNT(*)*1.0/COUNT(DISTINCT camera_id),1) AS avg_cam FROM video_alarm_records WHERE camera_id IS NOT NULL",
    },
    {
        "q": "给每种告警类型按数量排名",
        "sql": "SELECT alarm_type, COUNT(*) AS c, ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC) AS rn FROM video_alarm_records GROUP BY alarm_type ORDER BY rn",
    },
    {
        "q": "各告警类型数量及累计占比",
        "sql": "SELECT alarm_type, COUNT(*) AS c, ROUND(100.0*SUM(COUNT(*)) OVER (ORDER BY COUNT(*) DESC)/SUM(COUNT(*)) OVER (),2) AS cum_pct FROM video_alarm_records GROUP BY alarm_type ORDER BY c DESC",
    },
    {
        "q": "按告警数量给摄像头排名",
        "sql": "SELECT c.name, COUNT(r.id) AS c, RANK() OVER (ORDER BY COUNT(r.id) DESC) AS rk FROM video_cameras c LEFT JOIN video_alarm_records r ON r.camera_id=c.id GROUP BY c.name ORDER BY rk",
    },
    {
        "q": "每个边缘设备各产生多少边缘事件",
        "sql": "SELECT COALESCE(d.name,'未知') AS 设备, COUNT(e.id) AS c FROM video_edge_devices d LEFT JOIN video_edge_events e ON e.edge_code=d.code GROUP BY 设备 ORDER BY c DESC",
    },
    {
        "q": "每个摄像头各有多少边缘事件",
        "sql": "SELECT COALESCE(c.name,'未知') AS 摄像头, COUNT(e.id) AS c FROM video_cameras c LEFT JOIN video_edge_events e ON e.camera_id=c.id GROUP BY 摄像头 ORDER BY c DESC",
    },
    {
        "q": "触发告警最多的前3条告警规则",
        "sql": "SELECT r.name, COUNT(a.id) AS c FROM video_alarm_rules r JOIN video_alarm_records a ON a.rule_id=r.id GROUP BY r.name ORDER BY c DESC LIMIT 3",
    },
    {
        "q": "各摄像头告警数与边缘事件数对比，取告警最多前5",
        "sql": "SELECT c.name, COUNT(DISTINCT r.id) AS alarms, COUNT(DISTINCT e.id) AS events FROM video_cameras c LEFT JOIN video_alarm_records r ON r.camera_id=c.id LEFT JOIN video_edge_events e ON e.camera_id=c.id GROUP BY c.name ORDER BY alarms DESC LIMIT 5",
    },
    {
        "q": "当前正在运行的视频算法任务有多少",
        "sql": "SELECT COUNT(*) AS c FROM video_algorithm_tasks WHERE status='RUNNING'",
    },
    {
        "q": "运行失败的算法任务编号",
        "sql": "SELECT id FROM video_algorithm_tasks WHERE status='ERROR' ORDER BY id",
    },
    {
        "q": "边缘事件的平均处理延迟是多少毫秒",
        "sql": "SELECT ROUND(AVG(latency_ms)::numeric,2) AS avg FROM video_edge_events WHERE latency_ms IS NOT NULL",
    },
    {
        "q": "9月16日当天共有多少条告警",
        "sql": "SELECT COUNT(*) AS c FROM video_alarm_records WHERE alarm_time >= '2026-09-16' AND alarm_time < '2026-09-17'",
    },
    # ---- 设备 / 合成 / 摄像头 / 边缘延迟TOP-N / 联表取名称 / 显式日期 ----
    {
        "q": "列出当前离线的边缘设备",
        "sql": "SELECT name, code FROM video_edge_devices WHERE status='offline' ORDER BY name",
    },
    {
        "q": "在线和离线的边缘设备各有多少",
        "sql": "SELECT status, COUNT(*) AS c FROM video_edge_devices GROUP BY status",
    },
    {
        "q": "距上次心跳最久的10台边缘设备",
        "sql": "SELECT name, last_heartbeat FROM video_edge_devices ORDER BY last_heartbeat ASC NULLS LAST LIMIT 10",
    },
    {
        "q": "各合成算法供应商的完成总量",
        "sql": "SELECT provider, SUM(done) AS done, SUM(total) AS total FROM synthesis_job GROUP BY provider",
    },
    {
        "q": "当前离线的摄像头有多少",
        "sql": "SELECT COUNT(*) AS c FROM video_cameras WHERE status='OFFLINE'",
    },
    {
        "q": "各状态下的摄像头数量",
        "sql": "SELECT status, COUNT(*) AS c FROM video_cameras GROUP BY status",
    },
    {
        "q": "处理延迟最高的10条边缘事件",
        "sql": "SELECT id, latency_ms FROM video_edge_events WHERE latency_ms IS NOT NULL ORDER BY latency_ms DESC LIMIT 10",
    },
    {
        "q": "各算法类型的平均延迟，取前5名",
        "sql": "SELECT algorithm_type, ROUND(AVG(latency_ms)::numeric,2) AS a FROM video_edge_events WHERE latency_ms IS NOT NULL GROUP BY algorithm_type ORDER BY a DESC LIMIT 5",
    },
    {
        "q": "边缘事件每天有多少条",
        "sql": "SELECT date(ts) AS d, COUNT(*) AS c FROM video_edge_events GROUP BY d ORDER BY d",
    },
    {
        "q": "运行中的算法任务对应哪些摄像头",
        "sql": "SELECT c.name, t.id FROM video_algorithm_tasks t LEFT JOIN video_cameras c ON c.id=t.camera_id WHERE t.status='RUNNING'",
    },
    {
        "q": "每个算法被多少个任务使用",
        "sql": "SELECT alg.name, COUNT(t.id) AS c FROM video_algorithms alg LEFT JOIN video_algorithm_tasks t ON t.algorithm_id=alg.id GROUP BY alg.name ORDER BY c DESC",
    },
    {
        "q": "各算法类型分别挂了多少任务",
        "sql": "SELECT alg.algorithm_type, COUNT(t.id) AS c FROM video_algorithms alg LEFT JOIN video_algorithm_tasks t ON t.algorithm_id=alg.id GROUP BY alg.algorithm_type ORDER BY c DESC",
    },
    {
        "q": "9月15号每个摄像头的告警数量",
        "sql": "SELECT c.name, COUNT(*) AS c FROM video_cameras c JOIN video_alarm_records r ON r.camera_id=c.id WHERE r.alarm_time >= '2026-09-15' AND r.alarm_time < '2026-09-16' GROUP BY c.name ORDER BY c DESC",
    },
    {
        "q": "每个标注数据集下各有多少标注任务",
        "sql": "SELECT ds.name, COUNT(t.id) AS c FROM annotation_dataset ds LEFT JOIN annotation_task t ON t.dataset_id=ds.id WHERE ds.is_deleted=false GROUP BY ds.name ORDER BY c DESC",
    },
]


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


def _render_template(template: str, params: dict[str, Any]) -> str:
    """把 {key} 占位替换为安全值（仅支持数字/日期/白名单字符串）。"""
    def repl(m: re.Match) -> str:
        key = m.group(1)
        val = params.get(key)
        if val is None:
            return m.group(0)
        if isinstance(val, (int, float)):
            return str(int(val) if float(val).is_integer() else val)
        s = str(val)
        if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fa5\- ]+", s):
            raise CustomException(msg=f"参数「{key}」包含非法字符")
        return s

    return re.sub(r"\{(\w+)\}", repl, template)


# ---------------------------------------------------------------------------
# 查询执行（只读、超时、行数上限）
# ---------------------------------------------------------------------------
def _json_cell(v):
    """把数据库返回值转成 JSON 安全类型（Decimal→float、日期→iso 等）。"""
    if v is None:
        return None
    if isinstance(v, bool) or isinstance(v, (int, float, str)):
        return v
    from decimal import Decimal

    if isinstance(v, Decimal):
        return float(v)
    from datetime import date, datetime, time

    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_json_cell(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _json_cell(x) for k, x in v.items()}
    return str(v)


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


def scope_tables_to_schema(ranked: list[str], schema_map: dict, core_tables,
                           top_k: int) -> list[str]:
    """**数据源隔离**：把召回结果限制在本次数据源的 schema 内。

    向量/本体通道是全局的（不认数据源），实测 ds:4 的问题会被召回到
    video_*/ai_* 等 system 表 → prompt 里没有真正的业务表 → 模型**编表名** → 空 SQL。

    ⚠️ ``schema_map`` 为空表示**schema 未知**（如测试库取不到 information_schema）
    —— 此时不做隔离（否则会把召回清空），保持原行为。
    """
    if not schema_map:
        picked = list(ranked or [])[:top_k]
        return picked or list(core_tables or [])
    picked = [t for t in (ranked or []) if t in schema_map][:top_k]
    if not picked:
        picked = [t for t in (core_tables or []) if t in schema_map][:top_k]
    if not picked:
        picked = list(schema_map)[:top_k]
    return picked


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


async def _system_allowed() -> set[str]:
    """可查询表白名单 = 系统表 + 本体对象支撑表。

    注意：支撑表**不一定**叫 ``ont_{code}``——由数据源支撑的对象
    （如 ``video_cameras`` / ``demo_sales``）支撑表就是它自己。
    旧实现只拼 ``ont_{code}``，于是这些表**根本查不到**
    （表现为「表 xxx 不在可查询白名单内」）。两种都收进来。
    """
    global _ONT_ALLOW_CACHE, _ONT_ALLOW_CACHE_AT
    now = time.monotonic()
    if _ONT_ALLOW_CACHE is not None and (now - _ONT_ALLOW_CACHE_AT) < _ONT_ALLOW_TTL:
        return _ONT_ALLOW_CACHE
    # 走本体的统一语义接口拿"真实支撑表名 → code"，不再自己拼 SQL
    try:
        from app.plugin.module_ai.ontology import semantic as _sem

        ont_tables = set((await _sem.object_table_map()).keys())
    except Exception:  # noqa: BLE001
        ont_tables = set()
    _ONT_ALLOW_CACHE = set(SYSTEM_ALLOWED_TABLES) | ont_tables
    _ONT_ALLOW_CACHE_AT = now
    return _ONT_ALLOW_CACHE


def _scan_ont_tables(sql: str) -> list[str]:
    """从生成 SQL 中检测用到的本体物化表（ont_xxx），作为「问答使用本体」的可视溯源。"""
    if not sql:
        return []
    return list(dict.fromkeys(
        m.group(1) for m in re.finditer(r"\b(ont_[A-Za-z0-9_]+)\b", sql)
    ))


# P1-12 方案 b：内置默认敏感列名单（fail-closed 底板）。
# 作为「配置显式标记（ai_query_asset_columns.sensitive / 本体属性 sensitive）」之外的兜底，
# 凡**返回结果列**命中该名单（大小写不敏感，含常见变体）即默认拦截、永不返回明文。
# 只拦「返回列」，不拦 WHERE / JOIN 里的引用（否则会伤到正常过滤）。
_DEFAULT_SENSITIVE_COLS: frozenset[str] = frozenset({
    "password", "passwd", "pwd", "secret", "token",
    "access_token", "refresh_token", "api_token",
    "api_key", "apikey", "private_key", "encrypt_key",
    "auth_secret", "credential", "salt",
    "user_passwd", "user_password", "login_password",
    "auth_key", "sign_key", "secret_key", "passkey", "passcode",
})


def _default_sensitive_return_cols(sql: str) -> list[str]:
    """筛出 SQL **返回结果列**中命中内置敏感名单的列名（原始形式）。

    - 用 sqlglot 精确提取 SELECT 投影表达式里的列（含函数内列、别名），
      避免正则误伤字符串；**不扫 WHERE / JOIN**（那里引用敏感列不拦）。
    - 别名场景（``id AS password``）以**别名**作为结果列名判定——结果列就叫 password，必须拦。
    - 解析失败时回退正则（宁可多报、不可漏报，保持 fail-closed）。
    """
    if not sql:
        return []
    try:
        import sqlglot
        from sqlglot import exp as _exp

        parsed = sqlglot.parse_one(sql, read="postgres")
    except Exception:  # noqa: BLE001
        try:
            names = re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", sql)
        except Exception:  # noqa: BLE001
            return []
        return [n for n in names if n.lower() in _DEFAULT_SENSITIVE_COLS]

    candidates: list[str] = []
    for sel in parsed.find_all(_exp.Select):
        for expr in sel.expressions:
            # 别名：以「别名」作为结果列名（如 `id AS password`）
            if isinstance(expr, _exp.Alias):
                candidates.append(expr.alias)
            # 内部列：覆盖直接列（password）、函数内列（MAX(api_token)）
            for col in expr.find_all(_exp.Column):
                candidates.append(col.name)

    seen: set[str] = set()
    hits: list[str] = []
    for name in candidates:
        low = name.lower()
        if low in seen:
            continue
        seen.add(low)
        if low in _DEFAULT_SENSITIVE_COLS:
            hits.append(name)
    return hits


async def _execute_sql(sql: str) -> dict:
    start = time.time()
    try:
        async with async_db_session() as db:
            result = await db.execute(text(sql))
            rows = result.fetchall()
            cols = list(result.keys())
    except Exception as e:  # noqa: BLE001
        log.warning(f"[query] 执行失败: {e}")
        raise CustomException(msg=f"查询执行失败：{e}")
    # 行数上限走设置项（clamp 到安全区间），不再直接吃常量 MAX_ROWS
    limit = MAX_ROWS
    try:
        limit = _clamp_rows(AiQueryService._cfg_int(await AiQueryService._cfg(),
                                                    "query_max_rows", MAX_ROWS))
    except Exception as e:  # noqa: BLE001
        log.warning(f"[query] 读取行数上限失败，回落 {MAX_ROWS}：{str(e)[:80]}")
    data = [[_json_cell(v) for v in r] for r in rows[:limit]]
    return {"columns": cols, "rows": data, "took_ms": int((time.time() - start) * 1000),
            "truncated": len(rows) > limit}


async def _secure_ont_sql(sql: str, auth) -> dict:
    """把问数生成的 SQL 交给本体的行级/列级策略改写。

    返回 ``{"sql": <可能已改写>, "deny": bool, "msg": str, "rewritten": [...]}``。
    取不到身份时**不改写**（保持既有行为），但会在日志里留痕——
    宁可显式记录"这次没做权限改写"，也不要假装做了。
    """
    try:
        uid = getattr(getattr(auth, "user", None), "id", None)
    except Exception:  # noqa: BLE001
        uid = None
    if not uid:
        log.warning("[query] 无调用者身份，跳过本体权限改写")
        return {"sql": sql, "deny": False, "rewritten": [],
                "msg": "无身份，未改写"}
    try:
        from app.plugin.module_ai.ontology import security as _ont_sec

        principal = await _ont_sec.load_principal(uid)
        r = await _ont_sec.secure_sql(sql, principal)
    except Exception as e:  # noqa: BLE001
        # 权限改写失败 → **fail-closed**：宁可拒绝，也不要放行未过滤的查询
        log.warning(f"[query] 本体权限改写失败，拒绝执行：{e}")
        return {"sql": sql, "deny": True, "rewritten": [],
                "msg": f"权限校验失败，已拒绝执行：{str(e)[:120]}"}
    if not r.get("ok"):
        return {"sql": sql, "deny": True, "rewritten": r.get("rewritten") or [],
                "msg": r.get("note") or "存在无法安全改写的表，已拒绝执行"}
    return {"sql": r["sql"], "deny": False, "rewritten": r.get("rewritten") or [],
            "msg": r.get("note") or ""}


async def _execute_bound_metric(metric: dict, auth=None) -> dict:
    """执行**绑定型指标**：口径由「本体对象 + 属性 + 聚合」确定性推导（不写 SQL）。

    对齐设计 §2.2：绑定型指标既可走对象查询路径，也可走指标快路径——这里让快路径
    复用本体实例层（`instance_aggregate`），从而**无需 sql_template**。
    """
    from app.plugin.module_ai.ontology import security as _ont_sec
    from app.plugin.module_ai.ontology import service as ont

    obj = str(metric.get("object_code") or "")
    prop = str(metric.get("property_code") or "")
    fn = str(metric.get("agg_fn") or "count")
    # 快路径是**单值**语义（分组诉求由 `_wants_grouping` 挡在门外，交给对象查询路径）：
    # 故这里不按 bound_dimensions 自动分组，只给总量。
    gb = ""
    a: dict = {"fn": fn}
    if prop:
        a["prop"] = prop
    uid = getattr(getattr(auth, "user", None), "id", None)
    try:
        principal = await _ont_sec.load_principal(uid)
    except Exception:  # noqa: BLE001
        principal = None
    r = await ont.instance_aggregate(obj, group_by=gb, aggs=[a], principal=principal)
    if not r.get("ok"):
        raise CustomException(msg=r.get("msg") or "指标执行失败")
    rows = r.get("rows") or []
    return {
        "sql": f"-- 绑定型指标：本体实例层执行 {obj}.{fn}({prop or '*'})",
        "columns": [gb or "合计", metric.get("name") or fn],
        "rows": rows, "took_ms": 0,
        "note": f"绑定型指标 {metric.get('key')} 由本体实例层确定性执行",
    }


async def _execute_metric(metric: dict, params: dict[str, Any], auth=None) -> dict:
    # 绑定型指标（object_code + agg_fn）：走本体实例层，**不依赖 sql_template**
    if str(metric.get("object_code") or "") and str(metric.get("agg_fn") or ""):
        return await _execute_bound_metric(metric, auth)
    sql = _render_template(metric["sql_template"], params)
    ds_code = metric.get("datasource") or SYSTEM_DS
    if ds_code == SYSTEM_DS:
        table = await AiQueryService._allowed_for_user(auth)
        sql = validate_sql(sql, table)
    # 安全补丁（P0-3）：执行一律走 `_execute_one`（与 ask / ask_stream / 报表共用
    # 的**唯一收口**）—— 字段级 ACL 与本体行/列改写都在那里做，指标不再直连
    # `_execute_sql`，否则「指标模板」就是绕过敏感字段拦截的后门。
    # 第四个参数传**指标名**：软删除口径改写需要“问句”来判断是不是在问已删除。
    # 漏传过一次（只改了 ask 的两条路）—— 指标快路径把「每日耗用量合计」
    # 答成 41,827,138（含 3390 条软删行），金标 3,550,065，评测里就这一道暴露。
    # ``entry="metric"``：审计/shadow 差异按入口标记（P1 唯一收口的口径）。
    res = await AiQueryService._execute_one(
        sql, ds_code, auth, str(metric.get("name") or ""), entry="metric")
    res["sql"] = res.get("sql") or sql
    return res


# ---------------------------------------------------------------------------
# 语义匹配（快路径）：术语/指标名 → 指标 + 参数
# ---------------------------------------------------------------------------


#: 无区分度的中文二元组：出现在问句里**不代表**指向某个指标（实测误命中的元凶）

#: 指标命中的最低分（低于此分视为"只是碰巧撞了个通用词"）


#: NL2SQL 生成的 token 下限。实测本机模型**先推理约 2084 token 才输出 SQL**，
#: 低于此下限时预算被推理吃光 → finish_reason=length、正文为空 → "未生成有效的查询语句"。
NL2SQL_MIN_MAX_TOKENS = 4000
NL2SQL_DEFAULT_MAX_TOKENS = 8000


def nl2sql_max_tokens(cfg: dict | None) -> int:
    """NL2SQL 生成用的 max_tokens：取配置值，但**不得低于下限**。"""
    raw = (cfg or {}).get("nl2sql_max_tokens")
    try:
        val = int(str(raw).strip()) if raw is not None else 0
    except (TypeError, ValueError):
        val = 0
    if val < NL2SQL_MIN_MAX_TOKENS:
        # 低于下限（含未配置/非法）一律用默认值，宁可多给预算也不要出空 SQL
        return NL2SQL_DEFAULT_MAX_TOKENS
    return val


def nl2sql_attempts(cfg: dict | None) -> int:
    """慢路径最多尝试几次（含首次）。

    设置项是 ``nl2sql_retry``，语义按**总尝试次数**解释：``2`` = 首次 + 1 次自纠错
    （与改动前硬编码的 ``range(2)`` 完全等价，默认行为不变）。
    想做"只试一次、不重试省时间"就把值改成 1。
    """
    raw = (cfg or {}).get("nl2sql_retry")
    try:
        val = int(float(str(raw).strip())) if raw not in (None, "") else 2
    except (TypeError, ValueError):
        val = 2
    return max(1, min(5, val))


def _ir_max_tokens(cfg: dict | None) -> int:
    """对象查询（IR 生成）的 max_tokens。

    ``object_query_max_tokens`` 的语义是**覆盖**主预算，``0``（或非法/负数）表示
    「跟随 nl2sql_max_tokens」。之前写的是
    ``_cfg_int(cfg, "object_query_max_tokens", nl2sql_max_tokens(cfg))`` ——
    默认值只在 key **缺失**时生效；而该 key 一进默认值表就恒为 "0"，
    于是 max_tokens=0，模型直接返回空（这个坑正是"键进默认值"时才暴露）。
    """
    raw = (cfg or {}).get("object_query_max_tokens")
    try:
        val = int(float(str(raw).strip())) if raw not in (None, "") else 0
    except (TypeError, ValueError):
        val = 0
    return val if val > 0 else nl2sql_max_tokens(cfg)


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
_ONT_IMPORT_EXCLUDE: set[str] = {
    # 迁移 / 调度
    "alembic_version", "apscheduler_jobs",
    # 框架运行时（Agno 会话）
    "agno_sessions", "agno_schema_versions",
    # 纯日志
    "sys_log", "ai_call_logs", "ai_search_logs", "ai_chunk_annotation_logs",
    "ai_workflow_run_logs", "video_record_execution_logs",
    # 代码生成器脚手架
    "gen_demo", "gen_demo01",
    # 会话/消息运行时
    "ai_assistant_sessions", "ai_assistant_messages",
    # 向量 / schema 注册 / 配置 / 前端布局
    "ai_query_asset_vectors", "ai_query_schema", "ai_query_settings", "ai_query_kg_layout",
    # 纯多对多关联表
    "sys_role_menus", "sys_user_roles", "sys_user_positions", "sys_role_depts",
    "ai_knowledge_entity_chunks",
    # 调度/版本快照
    "ai_workflow_schedules", "ai_workflow_versions",
}


# ---------------------------------------------------------------------------
# 语义层 CRUD + 种子
# ---------------------------------------------------------------------------
class AiQueryService(ActionsOps, AssetsOps, MetricsOps, OntologyOps, PropositionsOps, ExecuteOps, ContextOps, Nl2SqlOps, SlowPathOps, AskOps, SettingsOps, DatasourceOps, SessionOps, ReportOps, DqOps, PipelineOps, VersionOps, RecallOps, RoutingOps, SchemaOps, LlmOps, OntBridgeOps, SeedOps):

    @classmethod
    async def count_writeback_actions(cls) -> int:
        """动作回写（`ai_query_writeback`）条数——控制台统一审计的跨模块取数入口。

        ⚠️ 该表 ``is_deleted`` 是 **boolean**，PG 下写 ``is_deleted=0`` 会直接报
        ``operator does not exist: bool``（历史调用方在 except 里吞掉，导致这个数字
        恒为 0）。
        """
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            return int(
                (
                    await db.execute(
                        _t("SELECT COUNT(*) FROM ai_query_writeback WHERE is_deleted=false")
                    )
                ).scalar()
                or 0
            )



    # ---- 指标 ----

    @classmethod
    async def autopilot(cls) -> dict:
        """AIP Autopilot 自主行动中心：规则扫描治理/质量/安全/审批，生成候选自主行动。"""
        actions: list[dict] = []
        try:
            assets = await cls.list_assets()
        except Exception:  # noqa: BLE001
            assets = []
        # 1) 缺中文描述 → 建议生成
        no_desc = [a for a in assets if not a.get("alias") and not a.get("description")][:5]
        if no_desc:
            actions.append({"id": "desc", "type": "enrich", "severity": "low", "target": "资产描述",
                            "suggestion": f"{len(no_desc)} 张表缺少中文描述，建议补齐后可问数更准确",
                            "tables": [a["table_name"] for a in no_desc], "executable": "generate_desc"})
        # 2) DQ 低分 → 建议重扫
        try:
            dq = await cls.dq_overview()
            risk = [x["table"] for x in dq.get("items", []) if (x.get("score") or 0) < 60][:5]
            if risk:
                actions.append({"id": "dq", "type": "repair", "severity": "medium", "target": "数据质量",
                                "suggestion": f"{len(risk)} 个对象 DQ<60，建议重新扫描校验",
                                "tables": risk, "executable": "dq_scan"})
        except Exception:  # noqa: BLE001
            pass
        # 3) 未识别敏感 → 建议敏感扫描
        no_sens = [a["table_name"] for a in assets if (a.get("sensitive_count") or 0) == 0][:5]
        if no_sens:
            actions.append({"id": "sensitive", "type": "audit", "severity": "medium", "target": "敏感识别",
                            "suggestion": f"{len(no_sens)} 张表未识别出敏感字段，建议自动敏感扫描",
                            "tables": no_sens, "executable": "scan_sensitive"})
        # 4) 审批积压 → 建议处理
        try:
            pend = int((await cls.approval_center()).get("total", 0))
            if pend:
                actions.append({"id": "approval", "type": "review", "severity": "high", "target": "审批",
                                "suggestion": f"{pend} 项待人工审批，请及时处理", "tables": [], "executable": "none"})
        except Exception:  # noqa: BLE001
            pass
        # 5) 数据源停用 → 建议确认
        try:
            dss = await cls.list_datasources()
            off = [d["name"] for d in dss if not d.get("enabled")][:5]
            if off:
                actions.append({"id": "ds", "type": "config", "severity": "low", "target": "数据连接",
                                "suggestion": f"{len(off)} 个数据源停用：{'、'.join(off)}，请确认是否启用",
                                "tables": [], "executable": "none"})
        except Exception:  # noqa: BLE001
            pass
        order = {"audit": 0, "repair": 1, "review": 2, "enrich": 3, "config": 4}
        actions.sort(key=lambda a: order.get(a["type"], 9))
        return {"total": len(actions), "actions": actions}

    @classmethod
    async def autopilot_execute(cls, executable: str, table: str = "", auth=None) -> dict:
        """执行一个安全的自主行动：敏感扫描 / DQ 重扫 / 补全描述 / 启用数据源。"""
        if executable == "scan_sensitive" and table:
            r = await cls.scan_sensitive(table)
            return {"ok": True, "msg": f"已对 {table} 完成敏感扫描，识别 {r.get('count', 0)} 个敏感字段"}
        if executable == "dq_scan" and table:
            try:
                await cls.dq_run(table)
                return {"ok": True, "msg": f"已对 {table} 重跑数据质量扫描"}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "msg": f"DQ 重扫失败：{e}"}
        if executable == "generate_desc":
            try:
                # 原来这里是**占位实现**：只把 alias 写成 "数据表 X"（假描述），
                # 前端看是"已补全"，实际一句中文描述都没生成；
                # 而真正调 LLM 的 generate_asset_descriptions / assets/generate-desc
                # 在前端**零入口**。现在两者接上（生成器按"缺描述的资产"批量处理，
                # 只补缺的，不覆盖人工填过的内容）。
                # 注意：生成器是**批量**动作（自己扫描所有缺描述资产），
                # table 参数对它没有意义，所以这里不再要求 table 非空——
                # 否则自主修复（无 table）会掉到"暂不支持"分支。
                r = await cls.generate_asset_descriptions(auth, force=False) or {}
                return {
                    "ok": True,
                    "msg": (
                        f"AI 生成描述完成：表 {r.get('tables', 0)} 条、"
                        f"字段 {r.get('columns', 0)} 条（人工校对后生效）"
                    ),
                }
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "msg": f"补全描述失败：{e}"}
        if executable == "enable_ds" and table:
            try:
                async with async_db_session.begin() as db:
                    from sqlalchemy import text as _t
                    await db.execute(_t(
                        "UPDATE ai_query_datasources SET enabled=true WHERE name=:n AND is_deleted=false"),
                        {"n": table})
                return {"ok": True, "msg": f"已启用数据源 {table}"}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "msg": f"启用数据源失败：{e}"}
        return {"ok": False, "msg": "该行动为信息项/暂不支持自动执行，请在对应模块处理"}

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

    @classmethod
    async def list_derived_metrics(cls) -> list[dict]:
        """派生指标规则引擎：基于基础指标自动推导（分子/分母/除数）。"""
        metrics = await cls.list_metrics(SYSTEM_DS)
        name_map = {m["key"]: m["name"] for m in metrics}
        out = []
        for r in cls._DERIVED_RULES:
            base = []
            if r.get("num"):
                base.append({"ref": r["num"], "name": name_map.get(r["num"], r["num"])})
            if r.get("den"):
                base.append({"ref": r["den"], "name": name_map.get(r["den"], r["den"])})
            out.append({
                "key": r["key"], "name": r["name"], "unit": r["unit"],
                "desc": r["desc"], "base": base,
                "formula": (f"{r['num']}" + (f" / {r['den']}" if r.get("den") else "") +
                            (f" / {r['divisor']}" if r.get("divisor") else "")),
            })
        return out

    @classmethod
    async def _metric_value(cls, key: str):
        metrics = await cls.list_metrics(SYSTEM_DS)
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

    @classmethod
    async def compute_derived_metric(cls, key: str) -> dict:
        """计算派生指标值（基于基础指标真实执行 SQL）。"""
        r = next((x for x in cls._DERIVED_RULES if x["key"] == key), None)
        if not r:
            return {"ok": False, "msg": "派生指标不存在"}
        num = await cls._metric_value(r["num"])
        if num is None:
            return {"ok": False, "msg": f"基础指标 {r['num']} 不可计算"}
        if r.get("den"):
            den = await cls._metric_value(r["den"])
            if den is None:
                return {"ok": False, "msg": f"基础指标 {r['den']} 不可计算"}
            value = num / den if den else 0
        else:
            divisor = r.get("divisor") or 1
            value = num / divisor if divisor else 0
        value = round(value, 2)
        return {"ok": True, "key": key, "name": r["name"], "value": value, "unit": r["unit"],
                "base": {"num": num, "den": (r.get("den") and await cls._metric_value(r["den"])) or None}}

    @classmethod
    async def security_audit(cls, limit: int = 30) -> dict:
        """数据安全与访问审计中心：敏感资产/字段 + 数据源安全 + ABAC 规则 + 访问审计日志 + 安全评分。"""
        assets = await cls.list_assets()
        sens_assets = [a for a in assets if (a.get("sensitive_count") or 0) > 0]
        sens_fields = sum(a.get("sensitive_count", 0) for a in assets)
        rules = await cls.list_access_rules()
        ds = await cls.list_datasources()
        ds_security = [{"name": d["name"], "type": d["type"],
                        "read_only": bool(d.get("read_only")), "enabled": bool(d.get("enabled"))}
                       for d in ds]
        logs = await cls.list_action_logs(limit)
        # 安全评分（覆盖敏感识别/权限规则/数据源只读）
        dims = []
        if assets:
            cover = len(sens_assets) / len(assets)
            dims.append({"key": "sens", "name": "敏感识别", "score": round(cover * 100),
                         "detail": f"{len(sens_assets)}/{len(assets)} 资产识别到敏感字段"})
        else:
            dims.append({"key": "sens", "name": "敏感识别", "score": 100, "detail": "无数据资产"})
        dims.append({"key": "access", "name": "ABAC 规则", "score": 100 if rules else 0,
                     "detail": f"{len(rules)} 条权限规则"})
        read_only_cnt = sum(1 for d in ds_security if d["read_only"])
        ds_score = 100 if not ds_security or read_only_cnt == len(ds_security) else round(read_only_cnt / len(ds_security) * 100)
        dims.append({"key": "ds", "name": "连接只读", "score": ds_score,
                     "detail": f"{read_only_cnt}/{len(ds_security)} 数据源只读"})
        overall = round(sum(d["score"] for d in dims) / len(dims)) if dims else 0
        issues = [{"level": d["score"] < 60 and "danger" or d["score"] < 80 and "warning" or "success",
                   "msg": f"{d['name']}：{d['detail']}"} for d in dims]
        return {"score": overall, "dims": dims, "issues": issues,
                "assets": len(assets), "sensitive_assets": len(sens_assets),
                "sensitive_fields": sens_fields, "access_rules": len(rules),
                "datasources": ds_security, "action_logs": logs, "log_count": len(logs)}

    # ---------------------------------------------------------------- #
    # Compass 收藏/引用中心
    # ---------------------------------------------------------------- #




    # ---------------------------------------------------------------- #
    # AIP 插件/工具市场
    # ---------------------------------------------------------------- #
    @classmethod
    async def list_plugins(cls) -> list[dict]:
        """AIP 插件目录：为 Agent/应用提供扩展工具能力。"""
        return [
            {"key": "web_fetch", "name": "网页抓取", "kind": "数据接入", "enabled": True,
             "desc": "抓取外部网页内容，供 Agent 阅读理解"},
            {"key": "table_export", "name": "表格导出", "kind": "输出", "enabled": True,
             "desc": "将问数结果导出为 Excel/CSV"},
            {"key": "email_send", "name": "邮件发送", "kind": "消息", "enabled": True,
             "desc": "把分析报告/告警通过邮件推送"},
            {"key": "report_generate", "name": "报告生成", "kind": "产出", "enabled": True,
             "desc": "AI 自动生成结构化报告"},
            {"key": "data_pipeline", "name": "数据管道", "kind": "数据接入", "enabled": True,
             "desc": "通过管道（ELT）拉取外部数据落库"},
        ]

    @classmethod
    async def derived_objects(cls) -> dict:
        """Ontology 派生对象：从启用了对象的资产派生对象（按数据域聚类 + 派生属性）。"""
        assets = await cls.list_assets()
        objs = [a for a in assets if a.get("object_enabled")]
        domains: dict[str, list[str]] = {}
        for a in objs:
            d = a.get("domain") or "未分域"
            domains.setdefault(d, []).append(a["table_name"])
        derived = [{"name": f"{d}域对象", "base_objects": tables, "count": len(tables),
                    "group": d} for d, tables in domains.items()]
        # 派生属性：为每个派生对象汇总列数/敏感/血缘
        for do in derived:
            do["attributes"] = {
                "total_columns": sum(next((a.get("column_count", 0) for a in objs if a["table_name"] == t), 0) for t in do["base_objects"]),
                "sensitive_fields": sum(next((a.get("sensitive_count", 0) for a in objs if a["table_name"] == t), 0) for t in do["base_objects"]),
                "lineage_count": sum(next((a.get("lineage_count", 0) for a in objs if a["table_name"] == t), 0) for t in do["base_objects"]),
            }
        return {"base_objects": len(objs), "derived_objects": derived,
                "total_derived": len(derived), "domains": list(domains.keys())}

    @classmethod
    async def autopilot_auto_fix(cls) -> dict:
        """AIP 自主修复全自动调度：自动批量执行所有可执行的自主行动（敏感扫描/补全描述/DQ重扫）。"""
        plan = await cls.autopilot()
        results: list[dict] = []
        # `generate_desc` 本身是**批量**动作（一次扫描全部缺描述资产），只能触发一次。
        # 旧实现把它和「按表」行动放在同一个循环里 → N 张表就全量重跑 N 轮 LLM
        # （白烧 token，且每轮结果互相覆盖）。这里单独处理、只跑一次。
        desc_done = False
        for a in plan["actions"]:
            if a["executable"] not in ("scan_sensitive", "generate_desc", "dq_scan") or not a.get("tables"):
                continue
            if a["executable"] == "generate_desc":
                if desc_done:
                    continue
                desc_done = True
                try:
                    r = await cls.autopilot_execute("generate_desc", "")
                    results.append({"action": a["type"], "table": "",
                                    "ok": bool(r.get("ok")), "msg": r.get("msg", "")})
                except Exception as e:  # noqa: BLE001
                    results.append({"action": a["type"], "table": "", "ok": False, "msg": str(e)})
                continue
            for t in a["tables"]:
                try:
                    r = await cls.autopilot_execute(a["executable"], t)
                    results.append({"action": a["type"], "table": t,
                                    "ok": bool(r.get("ok")), "msg": r.get("msg", "")})
                except Exception as e:  # noqa: BLE001
                    results.append({"action": a["type"], "table": t, "ok": False, "msg": str(e)})
        fixed = sum(1 for r in results if r["ok"])
        return {"attempted": len(results), "fixed": fixed, "results": results}

    @classmethod
    async def generate_asset_descriptions(cls, auth, force: bool = False) -> dict:
        """用 LLM 为表/字段生成中文描述（带数据画像；人工校对后生效）。

        force=True 时对全部已纳入资产重建，否则仅处理缺描述的。

        ``auth`` 允许为 ``None``（自主巡检/调度器在后台触发时没有 HTTP 用户上下文），
        此时审计列 ``updated_id`` 留空，**不做**任何归属过滤放行。
        """
        actor = _actor_id(auth)
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
        # 仅处理缺描述的；force 时全部重建
        need_tables = [(t.table_name, t) for t in tables if force or not (t.description or "").strip()]
        colmap: dict[str, list[tuple[str, Any]]] = {}
        for c in columns:
            if force or not (c.description or "").strip():
                colmap.setdefault(c.table_name, []).append((c.column_name, c))
        if not need_tables and not colmap:
            return {"tables": 0, "columns": 0}
        updated_tables = updated_cols = 0
        # 按表批量生成（带数据画像）
        for tname, trow in need_tables:
            cols = [c[0] for c in colmap.get(tname, [])] or ["(无字段)"]
            profile = await cls._profile_table(tname, cols)
            prof_lines = [f"表 {tname}：共 {profile['rows']} 行"]
            for cname, info in profile["cols"].items():
                if not info:
                    continue
                seg = f"  {cname}: 可空率{info['null_pct']}%、去重后{info['distinct']}个值"
                if info.get("values"):
                    seg += f"，取值[{','.join(info['values'])}]"
                prof_lines.append(seg)
            prompt = (
                "你是数据库元数据专家。请根据字段名与数据画像，为这张数据库表及字段生成简洁的中文业务描述"
                "（每个不超过30字，只说业务含义）。\n"
                f"表名：{tname}\n字段：{', '.join(cols)}\n数据画像：\n" + "\n".join(prof_lines)
            )
            try:
                out = await cls._llm_structured(prompt, AssetDescriptionOut, temperature=0,
                                                max_tokens=2000, tag="aistation-dict")
                data = out.model_dump()
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 生成表描述失败 {tname}: {e}")
                continue
            tdesc = (data.get("table") or "").strip()
            async with async_db_session.begin() as dbt:
                obj = await dbt.get(AiQueryAssetModel, trow.id)
                if obj and tdesc:
                    obj.description = tdesc
                    obj.updated_id = actor
                    updated_tables += 1
                cdesc = data.get("columns") or {}
                for colname, cobj in colmap.get(tname, []):
                    d = (cdesc.get(colname) or "").strip()
                    if d and isinstance(cobj, AiQueryAssetColumnModel):
                        cobj.description = d
                        cobj.updated_id = actor
                        updated_cols += 1
        return {"tables": updated_tables, "columns": updated_cols}








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
        from .lineage import EMPTY_LINEAGE, lineage_for_table

        lineage_payload = dict(EMPTY_LINEAGE)
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
    @staticmethod
    def _require_ident(name: str, what: str = "表名") -> str:
        """合法 SQL 标识符校验（表名/列名）：仅允许 ``[A-Za-z_][A-Za-z0-9_]*``。

        export_asset / object_browse / dq_rules_run 把路径/查询参数直接拼进
        ``SELECT ... FROM "x"``，表名含 ``"`` 即可闭合引号注入任意 SQL
        （psycopg2 允许多语句），所以必须先过这里。不合法抛 CustomException
        （fail-closed），绝不静默放行。
        """
        s = str(name or "").strip()
        if not _IDENT_RE.match(s):
            raise CustomException(msg=f"非法{what}：{name!r}")
        return s

    @classmethod
    async def _require_queryable_table(cls, table_name: str, auth) -> str:
        """资产入口统一白名单校验：表名必须在**按用户收窄**的可查白名单内。

        与问数主链路同口径：复用 ``_allowed_for_user(auth)``（数据域/ABAC 收窄），
        不是全局 ``_system_allowed()`` —— 否则数据域隔离在这三个入口上失效。
        注意 ``validate_sql`` 的白名单正则 ``\\bfrom\\s+([A-Za-z_]…)`` 对
        ``FROM "x"`` 这种**带引号**的表名不匹配，单靠它会被绕过，所以这里
        先做标识符校验（拼出来的 SQL 只含已校验的标识符，无需再走一遍）。

        校验失败抛 CustomException（fail-closed），且发生在拼 SQL 之前。
        """
        name = cls._require_ident(table_name, "表名")
        allowed = await cls._allowed_for_user(auth)
        if name.lower() not in {str(t).lower() for t in allowed}:
            raise CustomException(msg=f"表「{name}」不在可查询白名单内")
        return name


    @staticmethod
    async def _sensitive_table_deny(table_name: str) -> str:
        """表命中敏感清单时返回拒绝文案，否则空串（导出/浏览共用，2026-11 复审 I1）。

        导出/浏览走的是 ``SELECT *`` 直读，绕过了星号止血与策略网关；含敏感列的表
        必须一律拒绝，否则 ``select * from video_cameras`` 的明文 password 能从
        「数据集导出」出去。

        读清单失败按**拒绝**处理（fail-closed）：判断不了就不能放行。
        """
        from .policy.model import sensitive_tables

        try:
            sensitive = await sensitive_tables()
        except Exception as e:  # noqa: BLE001
            log.warning(f"[问数] 敏感表清单读取失败（导出/浏览按拒绝处理）: err={e}")
            return "敏感列清单读取失败，按拒绝处理（fail-closed）"
        if str(table_name or "").strip().lower() in sensitive:
            return "含敏感列的表不支持导出/浏览"
        return ""

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
        page = max(1, int(page)); page_size = max(1, min(int(page_size), 100))
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

    # ---------------------------------------------------------------- #
    # Compass 数据目录分类
    # ---------------------------------------------------------------- #
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
    async def access_walkthrough(cls, user_id: int = 0) -> dict:
        """数据访问沙箱/演练：为指定用户演示可访问/受限资源（ABAC/数据域）。"""
        assets = await cls.list_assets()
        allowed_tables = set()
        try:
            from types import SimpleNamespace as SN
            roles = await cls._user_role_codes_by_id(user_id)
            auth = SN(user=SN(id=user_id, is_superuser=False, roles=[SN(code=r) for r in roles]))
            allowed_tables = set(await cls._allowed_for_user(auth))
        except Exception:  # noqa: BLE001
            allowed_tables = set()
        can_see_sens = bool(await cls._can_see_sensitive(user_id)) if user_id else False
        allowed = []
        blocked = []
        for a in assets:
            t = a["table_name"]
            if t in allowed_tables:
                allowed.append({"table": t, "alias": a["alias"], "sensitive": a.get("sensitive_count") or 0})
            else:
                blocked.append({"table": t, "alias": a["alias"]})
        return {"user_id": user_id, "allowed_count": len(allowed),
                "blocked_count": len(blocked), "can_see_sensitive": can_see_sens,
                "allowed": allowed[:50], "blocked": blocked[:50]}

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
    async def asset_hotspots(cls) -> dict:
        """数据资产热点：按被指标引用次数(热度)排行数据资产。"""
        metrics = await cls.list_metrics(SYSTEM_DS)
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
    async def delete_workshop_app(cls, app_id: int) -> None:
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            await db.execute(_t(
                "UPDATE ai_workshop_app SET is_deleted=true, deleted_time=now() WHERE id=:i"
            ), {"i": app_id})

    #: 允许表单写入的对象表（演示安全白名单）
    _WORKSHOP_WRITABLE = {"ont_orders"}

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
    async def concepts_mapping(cls) -> list[dict]:
        return await cls.list_concepts()

    @classmethod
    async def access_matrix(cls) -> dict:
        """数据域/表级权限矩阵：每个系统角色 → 合并后可查表 + 是否受限 + 敏感放行。"""
        from sqlalchemy import text as _t
        async with async_db_session() as db:
            rows = (await db.execute(_t(
                "SELECT code, name FROM sys_role WHERE is_deleted=false ORDER BY id"))).fetchall()
        roles = [{"code": r[0] or "", "name": r[1] or r[0] or ""} for r in rows]
        rules = await cls.list_access_rules()
        out = []
        for role in roles:
            code = role["code"]
            matched = [x for x in rules if x["enabled"] and x["attribute"] == "role" and x["value"] == code]
            if matched:
                tables = sorted({t for x in matched for t in (x["allowed_tables"] or [])})
                out.append({**role, "restricted": True, "tables": tables,
                            "sensitive_ok": any(x["sensitive_ok"] for x in matched)})
            else:
                out.append({**role, "restricted": False, "tables": [], "sensitive_ok": False})
        return {"roles": out}

    @classmethod
    async def access_preview(cls, user_id) -> dict:
        """权限沙箱：按 user_id 模拟该用户的问数可查表（超管/角色/数据域判定）+ 敏感放行。"""
        from types import SimpleNamespace as SN
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            uid = 0
        su = await cls._is_superuser(uid)
        roles = await cls._user_role_codes_by_id(uid)
        auth = SN(user=SN(id=uid, is_superuser=su, roles=[SN(code=r) for r in roles]))
        tables = await cls._allowed_for_user(auth)
        domain_tables = await cls._domain_tables_for_user(uid)
        return {
            "user_id": uid, "superuser": su, "roles": sorted(roles),
            "domain_restricted": bool(domain_tables), "count": len(tables),
            "allowed_tables": sorted(tables),
        }

    @classmethod
    async def access_preview_role(cls, role: str) -> dict:
        """权限沙箱：按角色合并其 ABAC 规则的 allowed_tables + 敏感放行；无规则默认全开。"""
        role = (role or "").strip()
        rules = await cls.list_access_rules()
        matched = [x for x in rules if x["enabled"] and x["attribute"] == "role" and x["value"] == role]
        if matched:
            tables = sorted({t for x in matched for t in (x["allowed_tables"] or [])})
            return {"role": role, "restricted": True,
                    "sensitive_ok": any(x["sensitive_ok"] for x in matched),
                    "count": len(tables), "allowed_tables": tables}
        base = await _system_allowed()
        return {"role": role, "restricted": False, "sensitive_ok": False,
                "count": len(base), "allowed_tables": sorted(base)}

    @classmethod
    async def approval_center(cls) -> dict:
        """审批中心统一视图：聚合「动作写回待审批」+「本体发布待审批」。"""
        actions = await cls.list_pending_actions(limit=100)
        from app.plugin.module_ai.ontology.service import list_version_pending as _ont_pending
        versions = await _ont_pending(100)
        return {"actions": actions, "versions": versions,
                "total": len(actions) + len(versions)}

    @classmethod
    async def permission_check(cls, user_id: int, table: str) -> dict:
        """权限检查（Palantir checking permissions）：给定用户+资源，返回能否访问/原因/敏感字段可见性。"""
        from types import SimpleNamespace as SN
        try:
            uid = int(user_id or 0)
        except (TypeError, ValueError):
            uid = 0
        if await cls._is_superuser(uid):
            return {"user_id": uid, "table": table, "allowed": True,
                    "sensitive_visible": True, "reason": "超管（全量可见）"}
        roles = await cls._user_role_codes_by_id(uid)
        auth = SN(user=SN(id=uid, is_superuser=False, roles=[SN(code=r) for r in roles]))
        allowed_tables = await cls._allowed_for_user(auth)
        allowed = table in allowed_tables
        reason = "在可查白名单内" if allowed else "不在该用户可查范围（ABAC/数据域限定）"
        return {"user_id": uid, "table": table, "allowed": allowed,
                "roles": sorted(roles),
                "sensitive_visible": bool(await cls._can_see_sensitive(uid)),
                "reason": reason}

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
            for m in await cls.list_metrics(SYSTEM_DS):
                if q in (m["key"] or "").lower() or q in (m["name"] or "").lower():
                    metrics.append({"key": m["key"], "name": m["name"]})
        except Exception:  # noqa: BLE001
            metrics = []
        terms = []
        try:
            for t in await cls.list_terms(SYSTEM_DS):
                if q in (t["term"] or "").lower():
                    terms.append({"term": t["term"], "metric_key": t.get("metric_key")})
        except Exception:  # noqa: BLE001
            terms = []
        return {"assets": assets, "objects": objects, "metrics": metrics, "terms": terms}

    @classmethod
    async def list_access_rules(cls) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            res = await db.execute(_t(
                "SELECT id,name,attribute,value,allowed_tables,sensitive_ok,enabled "
                "FROM ai_access_rule WHERE is_deleted=false ORDER BY id DESC"))
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "name": r[1] or "", "attribute": r[2] or "role", "value": r[3] or "",
            "allowed_tables": r[4] if isinstance(r[4], list) else (_json.loads(r[4]) if r[4] else []),
            "sensitive_ok": bool(r[5]), "enabled": bool(r[6]),
        } for r in rows]

    @classmethod
    async def upsert_access_rule(cls, data: dict) -> dict:
        import json as _json
        tables = _json.dumps(data.get("allowed_tables") or [], ensure_ascii=False)
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            if data.get("id"):
                await db.execute(_t(
                    "UPDATE ai_access_rule SET name=:n, attribute=:a, value=:v, allowed_tables=:t, "
                    "sensitive_ok=:s, enabled=:e WHERE id=:i"), {
                    "n": data.get("name", ""), "a": data.get("attribute", "role"), "v": data.get("value", ""),
                    "t": tables, "s": bool(data.get("sensitive_ok", False)),
                    "e": bool(data.get("enabled", True)), "i": data["id"]})
                return {"id": data["id"]}
            res = await db.execute(_t(
                "INSERT INTO ai_access_rule(name,attribute,value,allowed_tables,sensitive_ok,enabled) "
                "VALUES (:n,:a,:v,:t,:s,:e) RETURNING id"), {
                "n": data.get("name", ""), "a": data.get("attribute", "role"), "v": data.get("value", ""),
                "t": tables, "s": bool(data.get("sensitive_ok", False)),
                "e": bool(data.get("enabled", True))})
            return {"id": res.scalar()}

    @classmethod
    async def _can_see_sensitive(cls, user_id) -> bool:
        """ABAC：超管可看敏感字段；否则看是否有**针对该用户**的敏感放行规则。

        安全补丁（2026-10-19）：修前只判断"存在**任一**启用且 sensitive_ok 的规则"，
        完全不校验它是否命中当前用户 —— 于是 dev 库里一条 ``role=ADMIN`` 的放行规则
        让**所有用户**都能看敏感字段，`_ont_sql_violations` 被短路、字段级 ACL 形同虚设。
        现在按 ``attribute=value`` 命中当前用户的角色才放行（默认拒绝）。
        """
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                r = (await db.execute(_t(
                    "SELECT is_superuser FROM sys_user WHERE id=:id AND is_deleted=false"), {"id": user_id or 0})).fetchone()
            if r and r[0]:
                return True
            roles = await cls._user_role_codes_by_id(user_id)
            if not roles:
                return False
            rules = await cls.list_access_rules()
            return any(x["sensitive_ok"] and x["enabled"]
                       and x["attribute"] == "role" and x["value"] in roles
                       for x in rules)
        except Exception:  # noqa: BLE001
            return False

    @classmethod
    async def _allowed_for_user(cls, auth) -> set[str]:
        """用户级可查表白名单（Palantir 数据域/表级权限拦截）。

        超管 → 全白名单（SYSTEM + ont_*）。非超管 →
          1) 若属于某启用「数据域」的成员 → 只能查该域 tables 的并集（数据域隔离）；
          2) 否则按 ABAC 规则（attribute=role、value∈用户角色）合并 allowed_tables；
          3) 未配置 → 默认全白名单（向后兼容，避免误锁）。
        均与全局白名单求交收紧。
        """
        base = await _system_allowed()
        try:
            if getattr(getattr(auth, "user", None), "is_superuser", False):
                return base
        except Exception:  # noqa: BLE001
            pass
        uid = getattr(getattr(auth, "user", None), "id", None)
        domain_tables = await cls._domain_tables_for_user(uid)
        if domain_tables:
            return base & domain_tables
        roles = _user_role_codes(auth)
        rules = await cls.list_access_rules()
        allowed: set[str] = set()
        for x in rules:
            if x["enabled"] and x["attribute"] == "role" and x["value"] in roles:
                allowed |= set(x["allowed_tables"] or [])
        if allowed:
            return base & allowed
        return base

    @classmethod
    async def _domain_tables_for_user(cls, user_id) -> set[str]:
        """用户所属启用「数据域」的 tables 并集（成员 id ∈ domain.members）。"""
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            uid = 0
        if not uid:
            return set()
        domains = await cls.list_domains()
        result: set[str] = set()
        for d in domains:
            if d["enabled"] and uid in (d["members"] or []):
                result |= set(d["tables"] or [])
        return result

    @classmethod
    async def _sql_query_scope(
        cls, sql: str, dialect: str = "postgres"
    ) -> tuple[set[str], set[str]]:
        """用 sqlglot 按**数据源方言**解析查询涉及的表集与列名集；失败回退正则（不放过）。

        ``dialect`` 必须与真实库一致：MySQL 的反引号 ``select * from `T``` 用 postgres
        读会解析失败，正则也不认反引号 → 表集合为空（Step 1 复审 C1：会跳过整条编译）。
        """
        try:
            import sqlglot
            from sqlglot import exp as _exp

            parsed = sqlglot.parse_one(sql, read=dialect)
            tables = {t.name for t in parsed.find_all(_exp.Table)}
            cols = {c.name for c in parsed.find_all(_exp.Column)}
            return tables, cols
        except Exception:  # noqa: BLE001
            tables = set(re.findall(
                r"\b(?:from|join)\s+[`\"\[]?([A-Za-z_][A-Za-z0-9_]*)",
                sql or "", re.IGNORECASE,
            ))
            cols = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", sql or ""))
            return tables, cols

    @classmethod
    async def _sensitive_asset_cols(cls, table: str) -> list[str]:
        """从字段资产目录取业务表被标记为敏感（sensitive）的字段清单。"""
        async with async_db_session() as db:
            from sqlalchemy import select as _sel

            rows = (
                await db.execute(
                    _sel(AiQueryAssetColumnModel.column_name).where(
                        AiQueryAssetColumnModel.table_name == table,
                        AiQueryAssetColumnModel.sensitive.is_(True),
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                    )
                )
            ).all()
        return [r[0] for r in rows]



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
            known |= set(SYSTEM_ALLOWED_TABLES)
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
    async def delete_access_rule(cls, id: int) -> None:
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            await db.execute(_t("UPDATE ai_access_rule SET is_deleted=true WHERE id=:id"), {"id": id})

    @classmethod
    async def delete_domain(cls, id: int) -> None:
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            await db.execute(_t("UPDATE ai_data_domain SET is_deleted=true WHERE id=:id"), {"id": id})


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
            from sqlalchemy import select

            # Task3：写打标列前幂等补列；本地库表/字段按默认规则打 is_system/is_audit
            await _ensure_marking_columns(db)
            for t in tables:
                inc = t in SYSTEM_ALLOWED_TABLES
                is_sys = is_system_table(t)
                exists = (
                    await db.execute(select(AiQueryAssetModel).where(AiQueryAssetModel.table_name == t))
                ).scalar_one_or_none()
                if not exists:
                    db.add(AiQueryAssetModel(table_name=t, description="", included=inc,
                                             is_system=is_sys, remark="",
                                             created_id=auth.user.id, updated_id=auth.user.id))
                    upserted += 1
                else:
                    # 重跑同步时校正已有行的系统表标记（按名字判定，幂等）
                    exists.is_system = is_sys
            for t, c in cols:
                is_aud = is_audit_field(c)
                exists = (
                    await db.execute(select(AiQueryAssetColumnModel).where(
                        AiQueryAssetColumnModel.table_name == t,
                        AiQueryAssetColumnModel.column_name == c))
                ).scalar_one_or_none()
                if not exists:
                    db.add(AiQueryAssetColumnModel(table_name=t, column_name=c, description="",
                                                   included=True, sensitive=False,
                                                   is_audit=is_aud,
                                                   created_id=auth.user.id, updated_id=auth.user.id))
                else:
                    exists.is_audit = is_aud
        return {"tables": len(tables), "columns": len(cols), "new_tables": upserted}

    # ---- 示例工程（few-shot）----
    @classmethod
    async def list_fewshots(cls, datasource: str | None = None) -> list[dict]:
        datasource = await _norm_datasource(datasource)
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
            for e in pick_fewshots(question, examples, datasource, k=4)
        ]

    # ---- 查询限额配置 ----
    @staticmethod
    async def _asset_tmeta() -> dict:
        """表级资产元数据（中文名/业务域/描述/业务场景），进程级缓存。"""
        global _ASSET_TMETA
        if _ASSET_TMETA is not None:
            return _ASSET_TMETA
        async with async_db_session() as db:
            from sqlalchemy import select

            rows = (
                await db.execute(
                    select(AiQueryAssetModel).where(AiQueryAssetModel.is_deleted.is_(False))
                )
            ).scalars().all()
        _ASSET_TMETA = {
            a.table_name: {
                "alias": a.alias or "", "domain": a.domain or "",
                "description": a.description or "",
                "business_scenarios": a.business_scenarios or "",
            }
            for a in rows
        }
        return _ASSET_TMETA








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
        global _SETTINGS_CACHE
        _SETTINGS_CACHE = None
        return {"key": key, "value": value}

    # ---- 使用统计 / 反馈闭环 ----
    @classmethod
    async def stats(cls) -> dict:
        async with async_db_session() as db:
            from sqlalchemy import func, or_, select

            # 不计评测会话：评测会走同一条 ask 链路，混进来使用统计就失真了
            base = (
                select(func.count())
                .select_from(AiQueryMessageModel)
                .outerjoin(AiQuerySessionModel,
                           AiQuerySessionModel.id == AiQueryMessageModel.session_id)
                .where(
                    AiQueryMessageModel.is_deleted.is_(False),
                    or_(AiQuerySessionModel.is_eval.is_(False),
                        AiQuerySessionModel.is_eval.is_(None)),
                )
            )
            total = (await db.execute(base)).scalar_one()
            fast = (await db.execute(
                base.where(AiQueryMessageModel.path == "fast"))).scalar_one()
            errors = (await db.execute(
                base.where(AiQueryMessageModel.is_error.is_(True)))).scalar_one()
        return {
            "total": total, "fast": fast, "slow": max(0, total - fast),
            "errors": errors, "ok": max(0, total - errors),
        }

    @classmethod
    async def delete_metric(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for mid in ids:
                m = await db.get(AiQueryMetricModel, mid)
                if m:
                    await db.delete(m)

    @classmethod
    async def delete_term(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for tid in ids:
                t = await db.get(AiQueryDictionaryModel, tid)
                if t:
                    await db.delete(t)

    # ---- 数据源 ----
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
    async def preview_filter_rules(cls, datasource_id: int, rules: dict | None = None) -> dict:
        """筛选规则分类预览（只读）：对数据源已同步 schema 全量分类并汇总。

        - ``rules`` 为草稿规则（可传 ``None`` 用数据源已保存规则，再缺省用 ``DEFAULT_FILTER_RULES``）；
        - 不写库、不改变已保存规则；数据源不存在时由 ``_load_ds`` 抛 CustomException（直接透传）。
        """
        ds = await _load_ds(datasource_id)
        # 空 dict（历史数据/新建数据源未配置）必须回落到缺省规则：
        # 旧写法把 `{}` 当成「用户显式清空的规则」，于是预览里系统表/审计字段恒为 0，
        # 与「缺省规则」下的真实分类完全矛盾（实测 331 表全被判成业务表）。
        eff = (rules or None) or (ds.filter_rules or None) or DEFAULT_FILTER_RULES
        schema = await list_ds_schema(datasource_id)
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

    # ---- 大模型辅助：筛选规则（suggest / parse / classify-advise） ----

    @staticmethod
    def _first_balanced_brace(t: str) -> str | None:
        """取文本中第一个**平衡**的 ``{ ... }`` 子串（跳过字符串内花括号与转义）。

        用于模型在 JSON 前后附带自然语言解释（无围栏、无换行）时，
        精确截取 JSON 对象本身。找不到平衡对象返回 ``None``。
        """
        start = t.find("{")
        if start < 0:
            return None
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(t)):
            c = t[i]
            if in_str:
                if escape:
                    escape = False
                elif c == "\\":
                    escape = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return t[start:i + 1]
        return None

    @classmethod
    def _extract_json(cls, s: str) -> str:
        """从模型输出中提取 JSON 文本。

        1. 先剥离 ```json ... ``` 代码块围栏；
        2. 剥离后若已是合法 JSON，直接返回；
        3. 若模型在 JSON 前后附带了自然语言解释（无围栏/无换行），
           扫描文本找第一个**平衡**的 ``{ ... }`` 并截取该子串返回；
        4. 均失败则原样返回，交由 ``json.loads`` 报错兜底。
        """
        t = (s or "").strip()
        if t.startswith("```"):
            t = t.split("\n", 1)[-1] if "\n" in t else t
            t = t.rsplit("```", 1)[0].strip()
        # 已是合法 JSON：直接返回，避免误截取解释里的花括号
        try:
            json.loads(t)
            return t
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        obj = cls._first_balanced_brace(t)
        return obj if obj is not None else t

    @classmethod
    def _parse_llm_json(cls, raw: str) -> dict:
        """解析模型返回的 JSON 文本：``_extract_json`` + ``json.loads``。

        仅作为 ``_llm_structured`` 的兜底（网关未回原生结构化输出时用），
        非法 JSON 或非对象 → 抛可读 ``CustomException``。
        """
        try:
            parsed = json.loads(cls._extract_json(raw))
        except (json.JSONDecodeError, TypeError, ValueError):
            raise CustomException(msg="大模型返回不是有效 JSON")
        if not isinstance(parsed, dict):
            raise CustomException(msg="大模型返回不是有效 JSON")
        return parsed



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

    # ---- 会话与问答 ----





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

    # ---- 核心：问答入口 ----


    @staticmethod
    def _cache_key(metric: dict, params: dict, user_id: int | None = None) -> str:
        import hashlib
        import json

        raw = json.dumps(
            {"ds": metric.get("datasource"), "key": metric.get("key"),
             "params": sorted(params.items()),
             # 安全补丁（2026-10-19）：缓存 key 必须含 user。指标结果是**按调用者
             # 权限**算出来的（行/列策略已下推），不含 user ⇒ A 按自己权限算出的
             # 结果会在 TTL（30~120s）内被 B 直接拿到 —— 越权读。
             "uid": int(user_id or 0)},
            ensure_ascii=False, sort_keys=True, default=str,
        )
        return f"ai:query:{hashlib.md5(raw.encode()).hexdigest()}"

    @staticmethod
    async def _cache_get(redis, key: str):
        try:
            val = await redis.get(key)
            if not val:
                return None
            import json

            return json.loads(val)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    async def _cache_set(redis, key: str, res: dict, ttl: int) -> None:
        try:
            import json

            await redis.set(key, json.dumps(res, ensure_ascii=False, default=str), ex=max(ttl, 1))
        except Exception:  # noqa: BLE001
            pass

    @classmethod
    async def _apply_softdelete_policy(cls, question: str, sql: str,
                                       datasource: str) -> str:
        """按"业务数据默认排除软删除"口径改写模型生成的 SQL。

        只在**自定义数据源**上用（系统库用 `is_deleted` 小写，且口径已写在提示词里）。
        问句本身在问"已删除"时**不动**；SQL 里已经有 `ISDELETED` 条件时也不动
        （避免覆盖模型自己写的 `= true`）。

        失败一律返回原 SQL：改写是**增强**，绝不能因为改写失败让整题挂掉。
        """
        from .softdelete import asks_about_deletion, inject_softdelete

        try:
            if not sql or asks_about_deletion(question):
                return sql
            if "ISDELETED" in sql.replace(" ", "").upper():
                return sql
            schema_map = await cls._ds_schema_map(datasource)
            del_tables = {
                t.upper() for t, labels in (schema_map or {}).items()
                if any(str(lab).upper().startswith("ISDELETED(") for lab in (labels or []))
            }
            if not del_tables:
                return sql
            new_sql, hit = inject_softdelete(sql, del_tables)
            if hit:
                log.info("[query] 软删除口径改写：表 {}（{} 处）",
                         "/".join(sorted(set(hit))[:3]), len(hit))
            return new_sql
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 软删除口径改写失败（用原 SQL）: {str(e)[:100]}")
            return sql

    @classmethod
    async def _explain_rows(cls, sql: str) -> int:
        """EXPLAIN 预估结果行数（用于查询代价护栏）。"""
        from sqlalchemy import text as _t

        async with async_db_session() as db:
            row = (await db.execute(_t(f"EXPLAIN (FORMAT JSON) {sql.rstrip(';')}"))).scalar()
            plan = row[0] if isinstance(row, list) else row
            return int((plan.get("Plan") or {}).get("Plan Rows") or 0)

    # ------------------------------------------------------------------
    # 对象查询（语义执行层）：LLM 只输出 IR，由本体实例层确定性执行
    # 设计：docs/superpowers/specs/2026-10-14-semantic-query-layer-design.md
    # ------------------------------------------------------------------
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
    async def _rewrite_llm(cls, prompt: str, runtime: dict) -> str:
        """一次 LLM 调用把追问重写为自包含问题（G7，复用 agno）。

        与 ``_ir_llm`` 同款：``_get_runtime()`` 解析模型 → ``OpenAILike`` → ``Agent``。
        LLM 调用本身有 ``wait_for`` 兜底超时；失败由调用方 `_maybe_rewrite` 降级为
        直接用原问题。
        """
        import asyncio as _asyncio

        from agno.agent import Agent
        from agno.models.openai.like import OpenAILike

        from app.plugin.module_ai.models.service import build_headers

        cfg = await cls._cfg()
        model = OpenAILike(
            id=runtime["model"], base_url=runtime["base_url"],
            api_key=runtime.get("api_key") or "sk-none",
            temperature=0.0, max_tokens=nl2sql_max_tokens(cfg), timeout=60,
            # 重写是纯文本改写，不需要深度推理：压掉思考速度更快。
            extra_body={"reasoning_effort": "low"},
            default_headers=build_headers(
                runtime["base_url"], runtime.get("extra_headers"), "aistation-query-rewrite"),
        )
        agent = Agent(model=model, telemetry=False, instructions=prompt)
        resp = await _asyncio.wait_for(
            agent.arun("请重写上面的问题。"),
            timeout=cls._cfg_int(cfg, "query_rewrite_call_timeout", 60),
        )
        return (getattr(resp, "content", "") or "").strip()

    @classmethod
    async def _maybe_rewrite(cls, question: str, session_id: int | None,
                             datasource: str | None = None) -> str:
        """多轮查询重写（G7）：把「那上周呢 / 换成华东呢」补全成自包含问题。

        - 仅在 ``query_rewrite_enabled`` 且 ``needs_rewrite`` 判定为「不自包含」时，
          才发生一次 LLM 调用；否则**零额外开销**（成本纪律）。
        - 重写失败 / 结果与原文相同 / 过长 → 用原问题（**不改变原意**，宁可不用）。
        - 重写后的自包含问题会在 `ask`/`ask_stream` 里**重新走一遍路由**（可命中指标
          快路径或对象查询），不硬进 NL2SQL。
        - 越权防护：重写只改文字，对象/表白名单与权限校验仍在路由与执行层把关。
        """
        from .rewrite import (
            build_rewrite_prompt,
            finalize_rewrite,
            needs_rewrite,
            recent_history,
        )

        q = (question or "").strip()
        if not q:
            return q
        cfg = await cls._cfg()
        if not cls._cfg_bool(cfg, "query_rewrite_enabled", False):
            return q
        try:
            msgs = await cls.list_messages(session_id) if session_id else []
        except Exception as e:  # noqa: BLE001
            log.warning("[query] 读会话历史失败，跳过重写：[{}] {}", type(e).__name__, str(e)[:80])
            msgs = []
        hist = recent_history(msgs)
        if not needs_rewrite(q, hist):
            return q
        try:
            runtime = await cls._get_runtime()
        except Exception as e:  # noqa: BLE001
            log.warning("[query] 获取模型失败，跳过重写：[{}] {}", type(e).__name__, str(e)[:80])
            return q
        try:
            text = await cls._rewrite_llm(build_rewrite_prompt(q, hist), runtime)
        except Exception as e:  # noqa: BLE001
            log.warning("[query] 多轮重写调用失败，用原问题：[{}] {}",
                        type(e).__name__, str(e)[:80])
            return q
        rw = finalize_rewrite(q, text)
        if rw and rw != q:
            log.warning("[query] 多轮重写：{} → {}", q[:40], rw[:40])
            return rw
        return q

    @classmethod
    async def _maybe_auto_index(cls, object_code: str, cfg: dict) -> None:
        """热度驱动自动建索引（G4）：命中次数达阈值且尚未建过 → 后台按建议建索引。

        为什么需要：对象查询的执行后端是实例层，**它的快慢直接取决于过滤/分组字段
        有没有索引**。让高频对象自动补索引，比让用户自己去「索引」页手动点更现实。

        设计取舍：只做**热度触发 + 后台执行**，不新建索引体系（复用 ``indexing.py``）；
        失败不阻断问答，且允许下次重试。
        """
        if not object_code:
            return
        if not cls._cfg_bool(cfg, "object_query_auto_index_enabled", False):
            return
        threshold = cls._cfg_int(cfg, "object_query_auto_index_after", 20)
        _OQ_HEAT[object_code] = _OQ_HEAT.get(object_code, 0) + 1
        if _OQ_HEAT[object_code] < threshold or object_code in _OQ_INDEXED:
            return
        _OQ_INDEXED.add(object_code)      # 先占位：并发命中时只建一次
        asyncio.create_task(cls._auto_index(object_code))   # 后台执行，不阻塞本次问答

    @classmethod
    async def _auto_index(cls, object_code: str) -> None:
        """后台按建议为某对象建索引（失败不阻断、允许重试）。"""
        from app.plugin.module_ai.ontology import indexing as _idx

        try:
            r = await _idx.apply_suggestions(object_code, only_high=True)
            log.warning("[query] 自动建索引 object={} -> {}", object_code, r.get("msg"))
        except Exception as e:  # noqa: BLE001
            _OQ_INDEXED.discard(object_code)   # 失败回滚占位，下次可再试
            log.warning(f"[query] 自动建索引失败（忽略）object={object_code}: {str(e)[:120]}")



    @classmethod
    async def _sql_dialect(cls, datasource: str) -> str:
        """数据源 → **sqlglot 读方言**名（编译器/解析器共用，未知回退 postgres）。

        外部库可能是 MySQL/SQLite：把 PG 语法套过去会直接产生非法 SQL（反引号、
        标识符大小写、函数名）。``api`` / ``file`` 这类没有 SQL 方言的源按 PG 处理
        （它们本来也不走 SQL 执行链路）。
        """
        if not datasource or datasource == SYSTEM_DS:
            return "postgres"
        key = str(datasource)
        hit = _SQL_DIALECT_CACHE.get(key)
        if hit and time.time() - hit[0] <= _SQL_DIALECT_TTL:
            return hit[1]
        ds_type = ""
        try:
            _dialect, ds_type = await cls._resolve_dialect_info(datasource)
        except Exception:  # noqa: BLE001 - 方言解析失败按 PG 兜底（不阻断判定）
            return "postgres"
        value = {"mysql": "mysql", "sqlite": "sqlite"}.get(
            str(ds_type or "").lower(), "postgres")
        if len(_SQL_DIALECT_CACHE) >= 20:
            _SQL_DIALECT_CACHE.clear()
        _SQL_DIALECT_CACHE[key] = (time.time(), value)
        return value


    @classmethod
    async def _finish_sql_stream(cls, question: str, session_id: int, sql: str,
                                 datasource: str, auth) -> list[dict]:
        """流式问数的**唯一出口**：执行 → 落库 → 组装事件。

        抽出来是为了让「缓存命中的 SQL」和「刚生成的 SQL」走**同一段**执行逻辑
        （旧实现只有生成路径，缓存/代价护栏/空结果提示都只存在于非流式分支）。
        """
        try:
            # 代价护栏（对齐非流式 `_slow_path`）：系统库先 EXPLAIN 估行数，超上限直接拒绝
            if datasource in (SYSTEM_DS, None):
                try:
                    er = await cls._explain_rows(sql)
                    max_rows = cls._cfg_int(await cls._cfg(), "query_cost_max_rows", 50000)
                    if er > max_rows:
                        msg = (f"查询代价过高(预计{er}行>上限{max_rows})，"
                               "请改为聚合/加条件/限制范围")
                        await cls._save_message(session_id, question, path="slow",
                                                datasource=datasource, sql=sql, rows=[],
                                                is_error=True, summary=msg)
                        return [{"type": "error", "message": msg}]
                except CustomException as e:  # noqa: BLE001
                    msg = f"SQL 校验失败：{e.msg}"
                    await cls._save_message(session_id, question, path="slow",
                                            datasource=datasource, sql=sql, rows=[],
                                            is_error=True, summary=msg)
                    return [{"type": "error", "message": msg}]
                except Exception:  # noqa: BLE001
                    pass  # EXPLAIN 本身失败不阻断执行（非 PG / 特殊 SQL）
            res = await cls._execute_one(sql, datasource, auth, question)
            cols = res.get("columns") or []
            rows = res.get("rows") or []
            # Grounding **必须落库**（刷新/重开会话后「召回的表 / 本体对象」标签要能复原）
            retrieved = await cls._recall_grounding(question, datasource)
            ont_used = _scan_ont_tables(sql)
            msg = await cls._save_message(
                session_id, question, path="slow", datasource=datasource,
                sql=sql, columns=cols, rows=rows,
                result_rows=len(rows), took_ms=res.get("took_ms", 0), cached=False,
                summary="以下是根据你的问题生成的结果：",
                grounding={"retrieved": retrieved, "ontology_used": ont_used},
            )
            # 只在**真有数据**时写 SQL 缓存（全 NULL 结果会把空表 SQL 缓存住，越查越空）
            flat = [v for r in rows for v in (r if isinstance(r, (list, tuple)) else [r])]
            if flat and any(v is not None for v in flat):
                _sql_cache_set(question, datasource, sql, _auth_scope(auth))
            return [
                {"type": "result", "columns": cols, "rows": rows, "result_rows": len(rows),
                 "sql": sql, "took_ms": res.get("took_ms", 0),
                 "applied": res.get("applied") or [], "policy_ids": res.get("policy_ids") or [],
                 "retrieved": retrieved, "ontology_used": ont_used, "message_id": msg.id,
                 "dq_warning": await cls._dq_warning_for_sql(sql)},
                {"type": "answer", "summary": "以下是根据你的问题生成的结果："},
                {"type": "done", "message_id": msg.id},
            ]
        except Exception as e:  # noqa: BLE001
            await cls._save_message(session_id, question, path="slow", datasource=datasource,
                                    sql=sql, rows=[], is_error=True, summary=f"查询失败：{e}")
            return [{"type": "error", "message": f"查询失败：{e}"}]

    @classmethod
    def _extract_sql(cls, s: str) -> str:
        """从模型输出里抠出 SQL。

        工具化 Agent 按指令要求输出 JSON（``{"sql": "<SELECT ...>"}``），
        而旧实现只做「去围栏 + 取第一个 select + 截到分号」——
        JSON 的**尾部 `"}` 会被留下**，SQL 因此解析不出 Select 节点，
        整条问数报「仅允许 SELECT 查询」而失败（既有缺陷，已用 git stash 复现确认）。
        """
        s = (s or "").strip()
        # 1) JSON 解包（工具化 Agent 的正常输出形态）
        if s.startswith("{"):
            try:
                import json as _json

                obj = _json.loads(s)
                if isinstance(obj, dict) and obj.get("sql"):
                    s = str(obj["sql"])
            except Exception:  # noqa: BLE001
                # JSON 被截断时的兜底：正则捞出 "sql": "..." 的内容
                m = re.search(r'"sql"\s*:\s*"(.*?)"\s*\}?\s*$', s, re.S)
                if m:
                    s = m.group(1).replace('\\"', '"').replace("\\n", "\n")
        # 2) 去 markdown 代码块围栏
        s = re.sub(r"```[a-zA-Z]*", "", s).strip()
        # 3) 取第一个 SELECT 开始
        idx = s.lower().find("select")
        if idx >= 0:
            s = s[idx:]
        # 4) 截到第一个分号，保留多行 SQL（JOIN/GROUP BY/窗口函数通常跨行）
        s = re.split(r";", s, maxsplit=1)[0].strip()
        # 5) 去掉 JSON 残留的尾巴（只去 } ] 与空白，**不动引号**，
        #    否则会把 `... = 'ONLINE'` 的收尾引号一起吃掉
        s = re.sub(r"[}\]]+\s*$", "", s).strip()
        return s



    @staticmethod
    async def _embedding_mid() -> int | None:
        """解析 usage='embedding' 的模型 id（供 embed_texts 使用），无则 None。"""
        try:
            from sqlalchemy import text as _t

            async with async_db_session() as db:
                m = (
                    await db.execute(
                        _t(
                            "SELECT id FROM ai_models "
                            "WHERE usage=:usage AND enabled=true AND is_deleted=false "
                            "ORDER BY is_default DESC, id DESC LIMIT 1"
                        ),
                        {"usage": "embedding"},
                    )
                ).scalar_one_or_none()
                return int(m) if m else None
        except Exception:  # noqa: BLE001
            return None



    @classmethod
    async def _pgv_search(cls, question: str, top_k: int = 12) -> list[str]:
        """pgvector 向量检索：返回最相关表（HNSW 余弦）。"""
        try:
            await cls._ensure_vector_table()
        except Exception:  # noqa: BLE001
            return []
        try:
            from app.plugin.module_ai.knowledge.embedding import embed_texts

            qvec = (await embed_texts([question], model_id=await cls._embedding_mid()))[0]
        except Exception:  # noqa: BLE001
            return []
        async with async_db_session() as db:
            from sqlalchemy import text as _text

            r = await db.execute(
                _text(
                    "SELECT tables FROM ai_query_asset_vectors "
                    "ORDER BY embedding <-> CAST(:q AS vector) LIMIT :k"
                ),
                {"q": str(qvec), "k": top_k},
            )
            rows = r.fetchall()
        tables: set[str] = set()
        for row in rows:
            t = row[0]
            if t:
                tables.update(t)
        return list(tables)


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


    @staticmethod
    def _parse_col_label(label: str) -> dict:
        """从 ``_system_schema()`` 的列标签 ``col(type)【中文名】…`` 抽出列名与中文名。"""
        name = (label or "").split("(", 1)[0].strip()
        m = re.search(r"【([^】]+)】", label or "")
        return {"column_name": name, "description": m.group(1) if m else ""}







    @classmethod
    async def _agno_search_tables(cls, question: str, schema: dict, top_k: int) -> list[str]:
        """用 Agno Knowledge(PgVector) 语义检索，返回命中的表集合。

        首次调用触发**后台播种**（不阻塞当前请求，回退 pgvector），
        播种完成后走 Agno 检索。
        """
        global _AGNO_SEEDED, _AGNO_SEEDING
        from .agno_store import AgnoSemanticStore

        store = await AgnoSemanticStore.get()
        await store.ensure()
        if not _AGNO_SEEDED and (await store.count()) == 0 and not _AGNO_SEEDING:
            _AGNO_SEEDING = True
            import asyncio as _asyncio

            _asyncio.ensure_future(cls._agno_seed_units(schema))
            return []  # 本次回退到 pgvector，播种完成后走 Agno
        texts = await store.search(question, top_k=top_k)
        tables: set[str] = set()
        for txt in texts:
            for t in schema:
                if t in txt:
                    tables.add(t)
        return list(tables)




    @staticmethod
    def _relevant_tables(question: str, schema: dict, metrics: list[dict], terms: list[dict]) -> list[str]:
        """依据问题关键词，只挑相关的表（列名/表名/中文注释命中），控制注入 token 并聚焦。

        **中文注释必须参与打分**：真实业务库的表名列名是英文缩写
        （``FUEL_CB_COALBALANCE`` / ``COALMONEY``），中文问题（"煤款金额"）
        只有靠注释才匹配得上。只认英文标识符的话，检索永远命中不了。
        """
        q = question.lower()
        scores: dict[str, float] = {}
        for t in schema:
            s = 0.0
            tname = t.lower()
            if tname in q:
                s += 6.0
            for col in schema[t]:
                parts = col.split("(", 1)
                colname = parts[0].lower()
                cmt = parts[1].rstrip(")").lower() if len(parts) > 1 else ""
                # 中文注释命中权重最高——它才是业务语义
                if len(cmt) >= 2 and cmt in q:
                    s += 5.0
                if len(colname) >= 3 and colname in q:
                    s += 3.0
                for seg in colname.split("_"):
                    if len(seg) >= 3 and seg in q:
                        s += 1.0
            if s > 0:
                scores[t] = s
        # 命中太少则回退到核心业务表 + 指标涉及的表
        if len(scores) < 3:
            core = [
                "video_alarm_records", "video_cameras", "video_camera_groups",
                "train_tasks", "ai_call_logs", "sys_user", "video_edge_events",
            ]
            for c in core:
                if c in schema:
                    scores[c] = scores.get(c, 0.0) + 1.0
        if not scores:
            return []
        return sorted(scores, key=lambda t: -scores[t])[:12]

    @classmethod
    def _query_conventions(cls) -> str:
        """查询口径规范：统一业务口径，减少 LLM 生成 SQL 时的歧义（时间/用户/联表/占比）。

        ⚠️ 2026-11 试过在这里加"软删除默认排除"和"排序/取单个"两条，配对 A/B 结果：
        软删除版两轮自翻 5 题（baseline 0 题）、收益 1~2 题；排序版两轮零变化。
        两条都已移除 —— **口径这类确定规则交给代码（softdelete 模块）比交给模型稳**。
        别再往这里加"模型应该记得住的规则"，除非 A/B 证明它稳定。
        """
        return (
            "【查询口径规范】\n"
            "1. 时间口径：\n"
            "   - '最近N天/近N天' → WHERE 时间列 >= CURRENT_DATE - N\n"
            "   - '过去N月/近N月' → WHERE 时间列 >= CURRENT_DATE - INTERVAL 'N month'\n"
            "   - '某月a日到b日' → WHERE 时间列 >= 'YYYY-MM-a' AND 时间列 < 'YYYY-MM-(b+1)'（含开头不含结尾）\n"
            "   - '某日当天' → WHERE 时间列 >= '当日' AND 时间列 < '次日'\n"
            "   - '按天/每日/每天' → GROUP BY TO_CHAR(时间列,'YYYY-MM-DD') 或 date(时间列)\n"
            "   - '各小时/按小时' → SELECT EXTRACT(HOUR FROM 时间列)::int AS 小时 ... GROUP BY 小时\n"
            "   - 'YYYY年M月' → WHERE 时间列 >= 'YYYY-MM-01' AND 时间列 < 'YYYY-(M+1)-01'\n"
            "2. 用户/账号统计：一律排除已删除 → WHERE is_deleted=false；超级管理员 = is_superuser=true。\n"
            "3. 联表口径：\n"
            "   - '每个/各主实体...' → 主实体 LEFT JOIN 明细表，用 COALESCE(主实体.name,'未分组/未知') 聚合空维度；"
            "计数用 COUNT(明细表.id)（LEFT JOIN 下 NULL 不计入）。\n"
            "   - 仅'发生过/有关系的' → 用 INNER JOIN。\n"
            "   - video_alarm_records 等表无 is_deleted 字段，统计告警不要加 is_deleted 条件。\n"
            "4. 占比/平均：用 ROUND(分子*100.0/分母,2) 或 ROUND(AVG(x)::numeric,2) 保证精度。"
        )


    #: 技术列前缀：同步/版本/排序这类，取值对写 SQL 没有帮助
    _ENUM_SKIP_PREFIX = ("SYNC", "VERSION", "SORT", "SERIAL", "ROWVERSION", "DISCRIMINATOR")

    #: 低基数列（枚举）候选：名字像状态/类型/标记的列
    _ENUM_COL_RE = re.compile(
        r"^(IS[A-Z_]+|.*(STATUS|STATE|TYPE|WAY|KIND|MODE|LEVEL|FLAG|CATEGORY|CLASS|SOURCE))$")



    #: 结构性列：主键/外键/时间/名称/状态——即使问句没提到也要保留
    _STRUCT_COL_RE = re.compile(
        r"(^ID$|ID$|CODE$|NAME$|DATE$|TIME$|^IS[A-Z]|STATUS$|TYPE$|WAY$|QTY$|AMOUNT$|PRICE$)")

    @classmethod
    def _prune_columns(cls, question: str, labels: list[str]) -> tuple[list[str], int]:
        """按问题裁剪列清单：**保留问句提到的列 + 结构性列**，其余折叠。

        依据：实测 12 张表 × 约 40 列 ≈ 480 个列名，而生成的 SQL 中位数只用
        1 张表、2 个标识符 —— 99% 的 schema 是噪声（prompt 里 84% 的字数来自这里）。

        ⚠️ 本方法曾被一次"整段替换"误删（编译不报错、运行时 AttributeError），
        删掉的后果是所有慢路径问题全挂 —— 改动这段区域时务必跑一次真实提问验证。
        """
        q_grams = _bigrams(question)
        q_low = (question or "").lower()
        kept: list[str] = []
        for lab in labels:
            code = lab.split("(", 1)[0]
            cn = lab[len(code):].strip("() ")
            hit = cls._STRUCT_COL_RE.search(code) is not None
            if not hit and code.lower() in q_low:
                hit = True
            if not hit and _bigrams(cn) & q_grams:
                hit = True
            if hit:
                kept.append(lab)
        return kept, len(labels)

    #: 字面量里的普通字符串（单引号，排除双引号标识符与转义）
    _SQL_LITERAL_RE = re.compile(r"'((?:[^']|'')*)'")

    @staticmethod
    def _norm_value(v: str) -> str:
        """值归一：去首尾空白 + 全角转半角 + 大小写。用于判断"是不是同一个值"。"""
        import unicodedata

        return unicodedata.normalize("NFKC", str(v or "")).strip().lower()

    @classmethod
    def fix_sql_literals(cls, sql: str, value_map: dict[tuple[str, str], list[str]]) -> tuple[str, list[str]]:
        """把 SQL 里**归一后相等**的字面量换成库里的原始写法（值匹配纠错）。

        为什么：用户/模型常写成 ``'烟煤 '``（尾随空格）、``'FL'`` vs ``'fl'``、
        全角 ``'ＡＢ'``，而库里存的是 ``'烟煤'``。语义完全相同，但等值比较查不到行 ——
        这正是 Genie 的 entity matching 想解决的问题。

        **只做"归一后相等"的替换**（strip / 全角→半角 / ASCII 大小写），
        不做模糊匹配（编辑距离），避免把语义改掉。
        """
        if not sql or not value_map:
            return sql, []
        by_norm: dict[str, str] = {}
        for vals in value_map.values():
            for v in vals:
                if isinstance(v, str) and v:
                    by_norm.setdefault(cls._norm_value(v), v)
        if not by_norm:
            return sql, []
        fixes: list[str] = []

        def _sub(m: re.Match) -> str:
            raw = m.group(1)
            canon = by_norm.get(cls._norm_value(raw))
            if canon and canon != raw:
                fixes.append(f"{raw!r} → {canon!r}")
                return "'" + canon.replace("'", "''") + "'"
            return m.group(0)

        return cls._SQL_LITERAL_RE.sub(_sub, sql), fixes



    @classmethod
    def _summarize(cls, metric: dict, res: dict) -> str:
        if not res["rows"]:
            return "暂无数据"
        if len(res["rows"]) == 1 and len(res["columns"]) == 1:
            v = res["rows"][0][0]
            return f"{metric.get('name', '')}为 {v} {metric.get('unit', '')}".strip()
        return f"共 {len(res['rows'])} 行结果"

    #: 模型偷懒时用的占位列名 —— 这些当成"没起名"，摘要里不念出来
    _LAZY_COLS = {"c", "n", "cnt", "count", "total", "num", "value", "v",
                  "数量", "总数", "个数", "结果", "值", "合计", "总计"}

    @classmethod
    def _summarize_rows(cls, columns: list, rows: list) -> str:
        """把结果说成**一句人话**。

        原先慢路径的摘要是硬编码的「以下是根据你的问题生成的结果：」——
        等于没回答。用户问"一共有多少条告警记录"，看到的却是这句话。
        """
        cols = list(columns or [])
        rows = list(rows or [])
        if not rows:
            return "没有查到符合条件的数据"
        if not cols:
            return f"共 {len(rows)} 行结果"
        if len(rows) == 1 and len(cols) == 1:
            v = rows[0][0]
            name = str(cols[0]).strip()
            if name.lower() in cls._LAZY_COLS:
                return f"结果是 {v}"
            return f"{name}：{v}"
        if len(rows) == 1:
            parts = [f"{c} {v}" for c, v in zip(cols, rows[0], strict=False)]
            return "；".join(parts[:5])
        # 多行：说清规模 + 给个头一条，让用户知道看到了什么
        head = "；".join(f"{c} {v}" for c, v in zip(cols, rows[0], strict=False) if
                         str(c).lower() not in cls._LAZY_COLS) or \
               "；".join(f"{c} {v}" for c, v in zip(cols, rows[0], strict=False))
        return f"共 {len(rows)} 行；第一行：{head}"

    @classmethod
    async def _cn_columns(cls, columns: list, sql: str) -> list:
        """把结果列名里的**英文属性名换成中文名**（本体是唯一来源）。

        模型经常写 `SELECT COUNT(*) AS c` 或直接 `SELECT status`，
        表格里就出现 `c` / `status` 这种看不懂的列头。
        """
        cols = list(columns or [])
        if not cols or not sql:
            return cols
        tables = _scan_ont_tables(sql)
        if not tables:
            return cols
        mapping: dict[str, str] = {}
        try:
            from app.plugin.module_ai.ontology import semantic as _sem

            ctx = await _sem.semantic_context()
            code_of = await _sem.object_table_map()
            want_codes = {code_of.get(t) for t in tables} - {None}
            for code in want_codes:
                for p in ctx["properties"].get(code, []):
                    if p["name"] and p["name"] != p["code"]:
                        mapping.setdefault(p["code"], p["name"])
        except Exception:  # noqa: BLE001
            return cols
        if not mapping:
            return cols
        return [mapping.get(str(c).strip().strip('"'), c) for c in cols]


    @classmethod
    def _answer(cls, msg: AiQueryMessageModel, metric: dict | None = None, sql: str | None = None,
                retrieved: dict | None = None) -> dict:
        # 置信度：快路径(指标确定性)=1.0；慢路径(LLM生成)=0.85；错误=0
        confidence = 0.0
        evidence = None
        if not msg.is_error:
            if msg.path == "fast":
                confidence = 1.0
                src = "本体指标"
            elif msg.path == "object":
                # 对象查询：语义由本体定义、执行由实例层确定性完成，正确性高于 LLM 直写 SQL
                confidence = 0.95
                src = "本体对象查询"
            else:
                confidence = 0.85
                src = "LLM 生成"
            evidence = {
                "source": src,
                "ontology_used": _scan_ont_tables(msg.sql or sql or ""),
                "retrieved_tables": (retrieved or {}).get("tables") or [],
            }
        return {
            "id": msg.id, "session_id": msg.session_id, "path": msg.path,
            "datasource": msg.datasource, "sql": msg.sql or sql or "",
            "columns": msg.columns or [], "rows": msg.rows or [],
            "summary": msg.summary or "", "result_rows": msg.result_rows or 0,
            "took_ms": msg.took_ms or 0, "cached": msg.cached, "is_error": msg.is_error,
            "metric": metric,
            "ontology_used": _scan_ont_tables(msg.sql or sql or ""),
            "retrieved": retrieved,
            "confidence": confidence, "evidence": evidence,
        }



    @classmethod
    async def run_metric(cls, metric_key: str, datasource: str | None, params: dict, auth) -> dict:
        metrics = await cls.list_metrics(datasource)
        metric = next((m for m in metrics if m["key"] == metric_key), None)
        if not metric:
            raise CustomException(msg=f"指标「{metric_key}」不存在")
        res = await _execute_metric(metric, params or {}, auth)
        return res

    # ---- 反馈 ----
