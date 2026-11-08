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
from .answer_ops import AnswerOps
from .access_ops import AccessOps
from .assets_ops import AssetsOps
from .workspace_ops import WorkspaceOps
from .rewrite_ops import RewriteOps
from .autopilot_ops import AutopilotOps
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
class AiQueryService(ActionsOps, AssetsOps, MetricsOps, OntologyOps, PropositionsOps, ExecuteOps, ContextOps, Nl2SqlOps, SlowPathOps, AskOps, SettingsOps, DatasourceOps, SessionOps, ReportOps, DqOps, PipelineOps, VersionOps, RecallOps, RoutingOps, SchemaOps, LlmOps, OntBridgeOps, SeedOps, AutopilotOps, AnswerOps, RewriteOps, AccessOps, WorkspaceOps):




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



    # ---------------------------------------------------------------- #
    # Compass 收藏/引用中心
    # ---------------------------------------------------------------- #




    # ---------------------------------------------------------------- #
    # AIP 插件/工具市场
    # ---------------------------------------------------------------- #











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





    # ---------------------------------------------------------------- #
    # Compass 数据目录分类
    # ---------------------------------------------------------------- #

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











    #: 允许表单写入的对象表（演示安全白名单）
    _WORKSHOP_WRITABLE = {"ont_orders"}






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
    async def _auto_index(cls, object_code: str) -> None:
        """后台按建议为某对象建索引（失败不阻断、允许重试）。"""
        from app.plugin.module_ai.ontology import indexing as _idx

        try:
            r = await _idx.apply_suggestions(object_code, only_high=True)
            log.warning("[query] 自动建索引 object={} -> {}", object_code, r.get("msg"))
        except Exception as e:  # noqa: BLE001
            _OQ_INDEXED.discard(object_code)   # 失败回滚占位，下次可再试
            log.warning(f"[query] 自动建索引失败（忽略）object={object_code}: {str(e)[:120]}")









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







    @classmethod
    async def run_metric(cls, metric_key: str, datasource: str | None, params: dict, auth) -> dict:
        metrics = await cls.list_metrics(datasource)
        metric = next((m for m in metrics if m["key"] == metric_key), None)
        if not metric:
            raise CustomException(msg=f"指标「{metric_key}」不存在")
        res = await _execute_metric(metric, params or {}, auth)
        return res

    # ---- 反馈 ----
