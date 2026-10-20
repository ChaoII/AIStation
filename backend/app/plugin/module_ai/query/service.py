"""智能问数服务：语义层 + 快慢双路径 + 安全查询引擎 + 会话/反馈。

设计要点：
- 语义层(指标/术语/维度)是两条路径共享的知识底座。
- 高频问题命中指标模板 → 快路径(秒级)；未命中 → LLM NL2SQL 慢路径(精准兜底)。
- 所有执行只读 + 白名单表/字段 + 超时 + LIMIT，权限不可绕过。
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from contextvars import ContextVar
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log

if TYPE_CHECKING:
    from pydantic import BaseModel

from .dialect import build_system_prompt, dialect_name, templated_note
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
from .schema import QueryAssetUpsert

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
_query_tables_ready = False

_QUERY_TABLES_SQL = (
    "CREATE TABLE IF NOT EXISTS ai_pipeline ("
    "id BIGSERIAL PRIMARY KEY, name VARCHAR(120), source_connection VARCHAR(120), "
    "source_table VARCHAR(120), target_object VARCHAR(120), mappings JSONB DEFAULT '[]', "
    "enabled BOOLEAN DEFAULT true, is_deleted BOOLEAN DEFAULT false, "
    "created_time TIMESTAMP DEFAULT now(), updated_time TIMESTAMP DEFAULT now())",
    "CREATE TABLE IF NOT EXISTS ai_pipeline_run ("
    "id BIGSERIAL PRIMARY KEY, pipeline_id BIGINT, status VARCHAR(20), message TEXT, "
    "ran_at TIMESTAMP DEFAULT now(), is_deleted BOOLEAN DEFAULT false, rows INTEGER DEFAULT 0)",
    # ⚠️ 这是**问数/治理侧**的「数据域」（Data Domain：把数据表按业务主题归类，用于问数权限与治理）。
    # 它与本体页的 `ai_ont_domain`（**本体域**：本体对象的命名空间）是**两张完全不同的表**——
    # 互不可见、互不相通、不共享数据：治理面板里的「数据域」数量/内容 ≠ 本体页的「本体域」，
    # 界面上的区分见 GovernancePanel 的说明 tooltip 与本体页「本体域」侧栏标题。
    # 合并两张表会同时动权限模型与本体命名空间，属于数据迁移级改动，**不要顺手做**。
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
_QUERY_ALTER_SQL = (
    "ALTER TABLE ai_workshop_app ADD COLUMN IF NOT EXISTS deleted_time TIMESTAMP",
)


async def _ensure_query_tables() -> None:
    """确保问数侧影子表与新增列存在（幂等、best-effort）。"""
    global _query_tables_ready
    if _query_tables_ready:
        return
    for sql in _QUERY_TABLES_SQL + _QUERY_ALTER_SQL:
        try:
            async with async_db_session.begin() as db:
                await db.execute(text(sql))
        except Exception:  # noqa: BLE001
            pass
    _query_tables_ready = True


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

#: 对象查询热度（对象编码 → 命中次数）与「本进程已自动建过索引」的对象。
#: 用途：**热度驱动自动建索引**（G4）。高频对象才值得建索引，避免无谓 DDL；
#: ``_OQ_INDEXED`` 兼作并发去重（先占位再建，失败回滚占位）。
_OQ_HEAT: dict[str, int] = {}
_OQ_INDEXED: set[str] = set()


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False)) / (
        (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5) + 1e-9
    )


# 禁止出现的 SQL 关键片段（防 DDL/DML/多语句/写操作）
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|merge|grant|revoke|"
    r"copy|vacuum|analyze|call|do|commit|rollback|savepoint|into|execute)\b",
    re.IGNORECASE,
)
_COMMENT_RE = re.compile(r"(--.*$)|(/\*.*?\*/)", re.MULTILINE | re.DOTALL)

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


async def _ensure_marking_columns(db):
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
    out = await _ex.execute_select(_ds_cfg_from_model(ds), sql)
    # 回传**实际执行**的 SQL（已加引号）：否则展示/排查看到的是未加引号的模板，会被误导
    out["sql"] = sql
    return out


def _to_metric_dict(m: AiQueryMetricModel) -> dict:
    return {
        "id": m.id, "datasource": m.datasource, "key": m.key, "name": m.name,
        "description": m.description or "", "sql_template": m.sql_template,
        "params": m.params or [], "dimensions": m.dimensions or [], "agg": m.agg,
        "unit": m.unit or "", "permission_tag": m.permission_tag or "",
        "enabled": m.enabled, "sort": m.sort or 0, "cache_ttl": m.cache_ttl or 0,
        # 指标 ↔ 本体绑定（S1）
        "object_code": getattr(m, "object_code", "") or "",
        "property_code": getattr(m, "property_code", "") or "",
        "agg_fn": getattr(m, "agg_fn", "") or "",
        "bound_dimensions": getattr(m, "bound_dimensions", None) or [],
    }


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
            "SELECT ROUND(COUNT(*) FILTER (WHERE result='success')*100.0/COUNT(*),2) AS 数值 "
            "FROM ai_call_logs WHERE is_deleted = false"
        ),
        "params": [], "dimensions": [], "cache_ttl": 60,
    },
    {
        "key": "online_event_ratio", "name": "在线事件占比", "agg": "ratio", "unit": "%",
        "description": "边缘事件在线（matched=true）占比（百分比）",
        "sql_template": (
            "SELECT ROUND(COUNT(*) FILTER (WHERE matched=true)*100.0/COUNT(*),2) AS 数值 "
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
_DAYS_RE = re.compile(r"(?:最近|近|过去)\s*(\d+)\s*(?:天|日)", re.IGNORECASE)


def parse_time_range(question: str) -> dict[str, Any]:
    """从问句中解析时间区间，返回可注入 SQL 的参数。"""
    m = _DAYS_RE.search(question)
    if m:
        return {"days": int(m.group(1))}
    if re.search(r"今天|今日", question):
        return {"days": 1}
    if re.search(r"本月|这个月", question):
        return {"days": 30}
    if re.search(r"本周|这周", question):
        return {"days": 7}
    return {}


# ---------------------------------------------------------------------------
# SQL 安全校验
# ---------------------------------------------------------------------------
#: 问题里出现这些词，说明用户要的是**全量列举**（"每个告警规则各触发多少"）
_ALL_LIST_HINTS = ("每个", "各", "所有", "全部", "分别", "每类", "每种", "列出",
                   "逐个", "清单", "都有哪些", "有哪些")

#: 但这些词出现时，用户要的是**前 N 条**，恰恰不能放宽 LIMIT。
#: 真实踩过：`各算法类型的平均延迟，取前5名` 里含"各"，被误判成全量列举，
#: 5 行被放到 1000 行——基准立刻从 ✓ 变 ✗（自己引入的回退，靠复测抓出来的）。
_TOP_N_RE = re.compile(r"前\s*\d+|排名|排前|top\s*\d+|前几|最多前", re.IGNORECASE)


def _wants_full_list(question: str) -> bool:
    q = question or ""
    if _TOP_N_RE.search(q):
        return False
    return any(h in q for h in _ALL_LIST_HINTS)


def validate_sql(sql: str, allowed_tables: set[str], question: str = "") -> str:
    """校验并规范化 SQL：只读、单语句、白名单表、加 LIMIT。

    返回净化后的 SQL；不合法抛 CustomException。
    """
    if not sql or not sql.strip():
        raise CustomException(msg="未生成有效的查询语句")
    # 去除注释
    cleaned = _COMMENT_RE.sub("", sql).strip()
    # 单语句
    removed_semis = cleaned.rstrip(";")
    if ";" in removed_semis:
        raise CustomException(msg="查询语句必须为单条 SELECT")
    # 只读
    head = removed_semis.strip().lower()
    if not head.startswith("select") or head.startswith("select "):
        if not head.startswith("select"):
            raise CustomException(msg="仅允许 SELECT 查询")
    if _FORBIDDEN.search(removed_semis):
        raise CustomException(msg="查询包含被禁止的写/DDL 语句")
    # 白名单表（**大小写不敏感**：大小写敏感库里模型可能把小写名写出来，
    # 后面 quote_schema_identifiers 会还原成真名并加引号，所以这里放宽是安全的）
    from_src = re.findall(
        r"\bfrom\s+([A-Za-z_][A-Za-z0-9_\.]*)", removed_semis, re.IGNORECASE
    )
    allowed_lower = {str(t).lower() for t in allowed_tables} if allowed_tables else set()
    for tbl in from_src:
        base = tbl.split(".")[-1].strip().strip('"')
        if allowed_lower and base.lower() not in allowed_lower:
            raise CustomException(msg=f"表「{base}」不在可查询白名单内")
    # AST 级校验（sqlglot）：确保是合法且仅 SELECT 的单条语句
    try:
        import sqlglot
        from sqlglot import exp as sql_exp

        parsed = sqlglot.parse_one(removed_semis, read="postgres")
        if parsed is None:
            raise CustomException(msg="生成的 SQL 无法解析")
        # 任意位置出现写/DML 节点一律拒绝（容错过滤不存在的节点类）
        dml_nodes = [
            getattr(sql_exp, n, None)
            for n in ("Insert", "Update", "Delete", "Drop", "Create", "Alter", "Merge", "Grant")
        ]
        dml_nodes = [n for n in dml_nodes if n is not None]
        if any(parsed.find(n) for n in dml_nodes):
            raise CustomException(msg="查询包含被禁止的写/DDL 语句")
        if not parsed.find(sql_exp.Select):
            raise CustomException(msg="仅允许 SELECT 查询")
    except CustomException:
        raise
    except ImportError:
        pass  # 未安装 sqlglot 时跳过 AST 校验，交给正则层
    # 限制行数。
    # 这里还顺手修一类**确定性**的错：问题要"每个/各/所有"这类全量列举时，
    # 模型常自作主张加一个小 LIMIT（实测把 216 行截成 50 行，答案直接判错）。
    # 提示词里已经写了"不要 LIMIT"，但模型不总听——所以在这里兜住：
    # 放宽到系统上限（外层本来就有 MAX_ROWS 保护，放宽不会失控）。
    m_lim = re.search(r"\blimit\s+(\d+)", removed_semis, re.IGNORECASE)
    if not m_lim:
        removed_semis = removed_semis + f" LIMIT {MAX_ROWS}"
    elif _wants_full_list(question) and int(m_lim.group(1)) < MAX_ROWS:
        removed_semis = re.sub(r"\blimit\s+\d+", f"LIMIT {MAX_ROWS}",
                               removed_semis, flags=re.IGNORECASE)
    return removed_semis


def _tables_in_sql(sql: str) -> set[str]:
    """从指标 SQL 提取涉及的系统表（含 FROM/JOIN）。"""
    names = {
        m.group(1)
        for m in re.finditer(
            r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", sql or "", re.IGNORECASE
        )
    }
    return {n for n in names if n in SYSTEM_ALLOWED_TABLES}


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


def _sql_cache_key(question: str, datasource: str | None) -> str:
    """归一化问题文本作为键（去空白、统一小写），避免大小写/空格差异漏命中。"""
    q = re.sub(r"\s+", "", (question or "").strip().lower())
    return f"{datasource or 'system'}::{q}"


def _sql_cache_get(question: str, datasource: str | None) -> str | None:
    key = _sql_cache_key(question, datasource)
    hit = _SQL_CACHE.get(key)
    if not hit:
        return None
    ts, sql = hit
    if time.time() - ts > _SQL_CACHE_TTL:
        _SQL_CACHE.pop(key, None)
        return None
    return sql


def _sql_cache_set(question: str, datasource: str | None, sql: str) -> None:
    if not sql or not sql.strip():
        return
    if len(_SQL_CACHE) >= _SQL_CACHE_MAX:
        # 简单淘汰：删最早插入的一批，避免引入额外依赖
        for k in list(_SQL_CACHE)[: max(1, _SQL_CACHE_MAX // 10)]:
            _SQL_CACHE.pop(k, None)
    _SQL_CACHE[_sql_cache_key(question, datasource)] = (time.time(), sql)


def sql_cache_stats() -> dict:
    """给运维/自检用：缓存规模与命中情况。"""
    now = time.time()
    alive = sum(1 for ts, _ in _SQL_CACHE.values() if now - ts <= _SQL_CACHE_TTL)
    return {"size": len(_SQL_CACHE), "alive": alive, "ttl_s": int(_SQL_CACHE_TTL)}


def sql_cache_clear() -> int:
    n = len(_SQL_CACHE)
    _SQL_CACHE.clear()
    return n


#: 别名检索一次最多补几张表。
#: 对象名（如"告警记录表"）含"告警"这种通用词，若拿它当匹配信号，会给大量
#: 无关问题塞进额外表 —— 实测这让 prompt 变大、生成 p50 从 3147ms 涨到 6483ms
#: （精度还降了）。所以只匹配**人工登记的别名**，并且限量。
_ONT_ALIAS_MAX_TABLES = 3

#: 自定义数据源表结构的进程内缓存：{ds:表结构, (时间, {表: [列]})}。
#: 331 张表的同步结果每次问答都读库太浪费。
_DS_SCHEMA_CACHE: dict[str, tuple[float, dict]] = {}
_DS_SCHEMA_TTL = 600.0


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


def _retrieval_cache_key(question: str, datasource: str | None = None) -> str:
    """检索缓存 key：**必须含数据源** —— 否则同一句话在两个数据源之间互相串结果
    （实测 ds:4 的问题会命中 system 源的缓存，召回到 video_*/ai_* 表）。"""
    q = re.sub(r"\s+", "", (question or "").strip().lower())
    return f"{datasource or ''}|{q}"


def retrieval_cache_stats() -> dict:
    now = time.time()
    alive = sum(1 for ts, _ in _RETRIEVAL_CACHE.values()
                if now - ts <= _RETRIEVAL_CACHE_TTL)
    return {"size": len(_RETRIEVAL_CACHE), "alive": alive,
            "ttl_s": int(_RETRIEVAL_CACHE_TTL)}


def retrieval_cache_clear() -> int:
    n = len(_RETRIEVAL_CACHE)
    _RETRIEVAL_CACHE.clear()
    return n


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
    data = [[_json_cell(v) for v in r] for r in rows[:MAX_ROWS]]
    return {"columns": cols, "rows": data, "took_ms": int((time.time() - start) * 1000)}


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


def _metric_prompt_hint(metric: dict | None) -> str:
    """命中指标时，给 IR 提示词加一条**确定性**建议（让模型直接填 metric）。"""
    if not metric:
        return ""
    return (
        f"【强烈建议】本问题已匹配到指标 `{metric.get('key')}`（{metric.get('name')}，"
        f"对象 {metric.get('object_code')}）。请**直接填 `metric`**，"
        "不要自己拼 group_by+aggregations——由系统用该指标的权威口径执行。\n\n"
    )


def _prioritize_metric_object(allowed: dict, metric: dict | None) -> dict:
    """把命中指标所属对象排到白名单**最前**（提示词按顺序展示，越前越易被选中）。"""
    if not metric or not allowed:
        return allowed
    code = str(metric.get("object_code") or "")
    if code and code in allowed:
        return {code: allowed[code], **{k: v for k, v in allowed.items() if k != code}}
    return allowed


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
        # 指标模板同样要过本体行级/列级权限（否则走指标就能绕过）
        secured = await _secure_ont_sql(sql, auth)
        if secured.get("deny"):
            raise CustomException(msg=secured["msg"])
        res = await _execute_sql(secured["sql"])
        if secured.get("rewritten"):
            res["ont_secured"] = secured["rewritten"]
    else:
        # 自定义数据源：ds:{id}，走独立连接 + schema 白名单 + 角色授权
        try:
            ds_id = int(ds_code.split(":")[-1])
        except ValueError:
            raise CustomException(msg=f"数据源编码异常：{ds_code}")
        res = await _execute_custom_ds_sql(ds_id, sql, auth)
        res["sql"] = res.get("sql", sql)
    res["sql"] = res.get("sql") or sql
    return res


# ---------------------------------------------------------------------------
# 语义匹配（快路径）：术语/指标名 → 指标 + 参数
# ---------------------------------------------------------------------------
def _detect_time_frame(question: str) -> str:
    """识别问句的时间语境，用于指标维度对齐。"""
    q = question.lower()
    if re.search(r"本月|这个月|当月", q):
        return "month"
    if re.search(r"今天|今日", q):
        return "today"
    if re.search(r"近7|最近7|近七|最近七|过去7", q):
        return "days"
    return ""


def _metric_time_hint(m: dict) -> str:
    """从指标 key/name/描述推断其时间维度，用于对齐问句时间语境。"""
    s = f"{m.get('key', '')} {m.get('name', '')} {m.get('description', '')}".lower()
    if "month" in s or "本月" in s or "当月" in s:
        return "month"
    if "7d" in s or "最近" in s or "近7" in s or "近七" in s:
        return "days"
    if "today" in s or "今日" in s or "今天" in s:
        return "today"
    return ""


_LISTING_RE = re.compile(
    r"(哪些|列出|列表|清单|明细|罗列|有哪些|分别是什么|各叫什么|的名称|的名字|叫啥|叫什么名字)"
)


def _is_listing_question(question: str) -> bool:
    """列举类问题（哪些/列出/名称等）不走指标模板，强制慢路径 NL2SQL。"""
    return bool(_LISTING_RE.search(question or ""))


#: 无区分度的中文二元组：出现在问句里**不代表**指向某个指标（实测误命中的元凶）
_GENERIC_BIGRAMS = {
    "多少", "数量", "合计", "统计", "所有", "每个", "分别", "共有", "总数", "总共",
    "一共", "几条", "几个", "哪些", "什么", "怎么", "是否", "有无", "多种", "多个",
}

#: 指标命中的最低分（低于此分视为"只是碰巧撞了个通用词"）
_MIN_METRIC_SCORE = 4


_LATIN_WORD_RE = re.compile(r"[a-z0-9_]{2,}")


def _latin_words(text: str) -> set[str]:
    return set(_LATIN_WORD_RE.findall((text or "").lower()))


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


def score_fewshot(question: str, ex_question: str) -> int:
    """few-shot 示例与问句的相关度：**中文二元组** + 英文/数字词 的重叠数。

    旧实现 `re.findall(r"[\\w\\u4e00-\\u9fa5]{2,}", question)` 把整句中文当成**一个 token**
    （中文都是 `\\w`），于是 `tok in 示例问句` 几乎永不成立 → 所有示例同分 →
    实际返回"最老的 4 条"，与问句无关（实测：补 few-shot 反而让准确率下降）。
    """
    return len(_bigrams(question) & _bigrams(ex_question)) + len(
        _latin_words(question) & _latin_words(ex_question)
    )


def pick_fewshots(question: str, examples: list[dict], datasource: str | None = None,
                  k: int = 4) -> list[dict]:
    """按相关度挑 top-K 示例；同数据源加权，同分时**新示例优先**。

    ⚠️ **防泄漏**：排除与当前问句**完全相同**的示例 —— 否则"把错题沉淀成示例"
    会让评测时模型直接看到本题答案，分数虚高（实测 80.7% → 95.0% 里有很大水分）。
    """
    qkey = re.sub(r"\s+", "", (question or "").strip())
    scored: list[tuple[int, int, dict]] = []
    for i, f in enumerate(examples or []):
        fq = str(f.get("question") or "")
        if re.sub(r"\s+", "", fq.strip()) == qkey:
            continue
        s = score_fewshot(question, fq)
        if not datasource or f.get("datasource") == datasource or datasource == SYSTEM_DS:
            s += 1
        scored.append((s, i, f))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return [f for _, _, f in scored[:k]]


def _bigrams(text: str) -> set[str]:
    """取中文二元组（剔除非中文与通用词），用于"指标自己的用词"是否出现在问句里。"""
    zh = re.sub(r"[^\u4e00-\u9fff]+", " ", text or "")
    out: set[str] = set()
    for part in zh.split():
        for i in range(len(part) - 1):
            bg = part[i:i + 2]
            if bg not in _GENERIC_BIGRAMS:
                out.add(bg)
    return out


#: 「分组/逐个」诉求：单值指标答不了，快路径必须让位给慢路径（实测会答成语义完全错）
_GROUPING_RE = re.compile(r"(每个|各|逐[个条]|分别|分布|按.{0,8}(分组|统计|汇总|分类))")


def _wants_grouping(question: str) -> bool:
    """问句是否要求**按实体分组/逐个**（单值指标答不了）。"""
    return bool(_GROUPING_RE.search(question or ""))


def _match_metric(question: str, metrics: list[dict], terms: list[dict],
                  concepts: list[dict] | None = None) -> dict | None:
    """按得分选指标：**指标自己的用词**命中 + 术语绑定 + 概念(含同义词)绑定 + 时间语境对齐。

    打分（实测调过）：
      - 指标名整体出现在问句：+6；key 出现：+4；绑定术语命中：+3；
      - 与**指标名**的中文二元组重合：每个 +3；与**描述**重合：每个 +1
        （名称比描述更具体，权重更高）；
      - 时间语境一致 +4，冲突 -2；
      - 总分需 ≥ ``_MIN_METRIC_SCORE`` 才算命中。

    旧实现用「类型/分布/数量/多少」这类通用词给所有指标一起加分，
    导致「合同**数量**」被描述里含「数量」的「结算**量**」抢走（真实误命中）。
    """
    q = question.lower()
    q_grams = _bigrams(question)
    frame = _detect_time_frame(question)
    # 业务概念（含同义词）→ 指标：与术语同等参与快路径匹配，闭合「概念→指标」
    concept_bind: list[tuple[str, str]] = []
    for c in concepts or []:
        mk = (c.get("metric_key") or "").strip()
        if not mk:
            continue
        syns = c.get("synonyms") or ""
        syn_list = [x.strip() for x in str(syns).split(",") if x.strip()] if syns else []
        for nm in [c.get("name"), *syn_list]:
            if nm:
                concept_bind.append((str(nm).lower(), mk))
    best = None
    best_score = 0
    for m in metrics:
        if not m["enabled"]:
            continue
        name = (m.get("name") or "").lower()
        key = (m.get("key") or "").lower()
        # 「词证据」：指标自己的用词出现在问句里才算数；名称权重 > 描述，且不重复计同一个词
        n_grams = _bigrams(m.get("name"))
        d_grams = _bigrams(m.get("description")) - n_grams
        word = 3 * len(q_grams & n_grams) + 1 * len(q_grams & d_grams)
        if name and name in q:
            word += 6
        if key and key in q:
            word += 4
        for t in terms:
            if t.get("metric_key") == m["key"] and t.get("term") and t["term"].lower() in q:
                word += 3
        for nm, mk in concept_bind:
            if mk == m["key"] and nm in q:
                word += 3
        # 时间语境：指标自身的时间维度与问句一致（允许"只靠时间维度"选中，
        # 如「这个月…报警」→ 本月告警数，其名称与问句没有共同词）
        mtime = _metric_time_hint(m)
        time_bonus = 0
        if frame and mtime == frame:
            time_bonus = 4
        elif frame and mtime and mtime != frame:
            time_bonus = -2
        # 合格门槛：词证据够强，或时间维度正好对上
        if word < _MIN_METRIC_SCORE and not (frame and mtime == frame):
            continue
        score = word + time_bonus
        if score > best_score:
            best_score = score
            best = m
    return best if best and best_score > 0 else None


def _build_params(metric: dict, question: str) -> dict[str, Any]:
    """从问句抽取指标所需参数（时间、实体等）。"""
    params = parse_time_range(question)
    # 指标声明的 value 型参数若未从问句得到则给默认
    for p in metric.get("params") or []:
        if p.get("key") not in params:
            if p.get("type") == "value" and p.get("default") is not None:
                params[p["key"]] = p["default"]
            else:
                params[p["key"]] = 30
    return params


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
class AiQueryService:

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

    @classmethod
    async def pipeline_run_status(cls) -> dict[str, int]:
        """数据管道运行状态分布（`ai_pipeline_run` 按 status 计数）。"""
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rows = (
                await db.execute(
                    _t(
                        "SELECT status, count(*) FROM ai_pipeline_run "
                        "WHERE is_deleted=false GROUP BY status"
                    )
                )
            ).fetchall()
        return {str(r[0]): int(r[1]) for r in rows}

    @classmethod
    async def ensure_system_seed(cls) -> None:
        """首次执行时写入系统数据源预置指标与术语；之后跳过（避免拖慢快路径）。"""
        global _SEED_DONE
        if _SEED_DONE:
            return
        async with async_db_session.begin() as db:
            from sqlalchemy import select

            for m in _SYSTEM_METRICS:
                existing = (
                    await db.execute(
                        select(AiQueryMetricModel).where(
                            AiQueryMetricModel.datasource == SYSTEM_DS,
                            AiQueryMetricModel.key == m["key"],
                            AiQueryMetricModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.name = m["name"]
                    existing.description = m.get("description", "")
                    existing.sql_template = m["sql_template"]
                    existing.params = m.get("params") or []
                    existing.dimensions = m.get("dimensions") or []
                    existing.agg = m.get("agg", "count")
                    existing.unit = m.get("unit", "")
                    existing.cache_ttl = m.get("cache_ttl", 0)
                else:
                    db.add(
                        AiQueryMetricModel(
                            datasource=SYSTEM_DS, key=m["key"], name=m["name"],
                            description=m.get("description", ""),
                            sql_template=m["sql_template"], params=m.get("params") or [],
                            dimensions=m.get("dimensions") or [], agg=m.get("agg", "count"),
                            unit=m.get("unit", ""), permission_tag=m.get("permission_tag", ""),
                            enabled=True, sort=0, cache_ttl=m.get("cache_ttl", 0),
                        )
                    )
            for t in _SYSTEM_TERMS:
                existing = (
                    await db.execute(
                        select(AiQueryDictionaryModel).where(
                            AiQueryDictionaryModel.datasource == SYSTEM_DS,
                            AiQueryDictionaryModel.term == t["term"],
                            AiQueryDictionaryModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    existing.metric_key = t.get("metric_key", "")
                    existing.type = t.get("type", "term")
                else:
                    db.add(
                        AiQueryDictionaryModel(
                            datasource=SYSTEM_DS, term=t["term"],
                            metric_key=t.get("metric_key", ""), field_path="",
                            type=t.get("type", "term"),
                        )
                    )
            for eg in _NL2SQL_FEWSHOT:
                exists_fs = (
                    await db.execute(
                        select(AiQueryFewshotModel).where(
                            AiQueryFewshotModel.question == eg["q"],
                            AiQueryFewshotModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if not exists_fs:
                    db.add(
                        AiQueryFewshotModel(
                            datasource=SYSTEM_DS, question=eg["q"], sql=eg["sql"], enabled=True
                        )
                    )
        _SEED_DONE = True

    # ---- 指标 ----
    @classmethod
    async def list_metrics(cls, datasource: str | None = None) -> list[dict]:
        await cls.ensure_system_seed()
        datasource = await _norm_datasource(datasource)
        async with async_db_session() as db:
            from sqlalchemy import select

            q = select(AiQueryMetricModel).where(AiQueryMetricModel.is_deleted.is_(False))
            if datasource:
                q = q.where(AiQueryMetricModel.datasource == datasource)
            q = q.order_by(AiQueryMetricModel.datasource, AiQueryMetricModel.sort, AiQueryMetricModel.id)
            rows = (await db.execute(q)).scalars().all()
            return [_to_metric_dict(m) for m in rows]

    @classmethod
    async def upsert_metric(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            from sqlalchemy import select

            existing = (
                await db.execute(
                    select(AiQueryMetricModel).where(
                        AiQueryMetricModel.datasource == data.datasource,
                        AiQueryMetricModel.key == data.key,
                        AiQueryMetricModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                for k in ("name", "description", "sql_template", "params", "dimensions",
                          "agg", "unit", "permission_tag", "enabled", "sort", "cache_ttl",
                          "object_code", "property_code", "agg_fn", "bound_dimensions"):
                    setattr(existing, k, getattr(data, k))
                existing.updated_id = auth.user.id
                obj = existing
            else:
                obj = AiQueryMetricModel(
                    datasource=data.datasource, key=data.key, name=data.name,
                    description=data.description, sql_template=data.sql_template,
                    params=data.params, dimensions=data.dimensions, agg=data.agg,
                    unit=data.unit, permission_tag=data.permission_tag,
                    enabled=data.enabled, sort=data.sort, cache_ttl=data.cache_ttl,
                    object_code=data.object_code, property_code=data.property_code,
                    agg_fn=data.agg_fn, bound_dimensions=data.bound_dimensions,
                    created_id=auth.user.id, updated_id=auth.user.id,
                )
                db.add(obj)
            await db.flush()
            return _to_metric_dict(obj)

    @classmethod
    async def generate_modeling(cls, kind: str, datasource: str, auth,
                                max_objects: int = 12, dry: bool = False,
                                offset: int = 0) -> dict:
        """触发大模型自动建模（``kind``：``metrics`` / ``annotate``），并失效语义缓存。

        建模会**写指标/对象/属性** → 必须失效缓存，否则前端与问数看不到刚生成的内容
        （`_SETTINGS_CACHE`/`_SEMANTIC_INDEX`/`_ASSET_TMETA` 均为进程内缓存）。
        """
        global _SETTINGS_CACHE, _SEMANTIC_INDEX, _ASSET_TMETA

        from . import modeling as _m

        datasource = await _norm_datasource(datasource)

        if kind == "metrics":
            out = await _m.generate_metrics(datasource, auth, max_objects=max_objects,
                                            dry=dry, offset=offset)
        elif kind == "annotate":
            out = await _m.generate_annotations(datasource, auth, max_objects=max_objects,
                                                offset=offset)
        else:
            raise CustomException(msg=f"未知建模类型：{kind}")
        if not dry:
            _SETTINGS_CACHE = None
            _SEMANTIC_INDEX = None
            _ASSET_TMETA = None
        return out

    @classmethod
    async def promote_message_to_metric(cls, message_id: int, name: str, key: str, auth) -> dict:
        """FDE 复用闭环：把一条已验证问答沉淀为「可复用指标」（确定性快路径）。

        校验 SQL 合法后落为系统指标，并把该问题登记为术语（黑话→指标），
        下次同类问题直接走快路径（100%、秒级），不再依赖 LLM 生成。
        """
        name = (name or "").strip()
        key = (key or "").strip()
        if not name or not key:
            raise CustomException(msg="请提供指标名称(key)与显示名(name)")
        if not re.fullmatch(r"[A-Za-z0-9_]+", key):
            raise CustomException(msg="指标 key 仅允许字母/数字/下划线")
        async with async_db_session.begin() as db:
            from sqlalchemy import select as _sel

            m = await db.get(AiQueryMessageModel, message_id)
            if not m or not (m.sql or ""):
                raise CustomException(msg="问答记录无效或缺少 SQL")
            try:
                validate_sql(m.sql, await _system_allowed())
            except CustomException as e:  # noqa: BLE001
                raise CustomException(msg=f"该 SQL 无法作为指标：{e}") from e
            existing = (
                await db.execute(
                    _sel(AiQueryMetricModel).where(
                        AiQueryMetricModel.datasource == SYSTEM_DS,
                        AiQueryMetricModel.key == key,
                        AiQueryMetricModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.name = name
                existing.sql_template = m.sql
                existing.enabled = True
                existing.updated_id = auth.user.id
            else:
                db.add(AiQueryMetricModel(
                    datasource=SYSTEM_DS, key=key, name=name,
                    description=f"由问答「{m.question[:40]}」沉淀", sql_template=m.sql,
                    params=[], dimensions=[], agg="count", unit="",
                    enabled=True, cache_ttl=60,
                    created_id=auth.user.id, updated_id=auth.user.id,
                ))
            # 把问题登记为术语（黑话 → 指标）
            term = (m.question or "").strip()[:128]
            if term:
                tex = (
                    await db.execute(
                        _sel(AiQueryDictionaryModel).where(
                            AiQueryDictionaryModel.datasource == SYSTEM_DS,
                            AiQueryDictionaryModel.term == term,
                            AiQueryDictionaryModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if tex:
                    tex.metric_key = key
                else:
                    db.add(AiQueryDictionaryModel(
                        datasource=SYSTEM_DS, term=term, metric_key=key,
                        field_path="", type="metric",
                    ))
            await db.flush()
            return {"key": key, "name": name, "term": term}

    # ---- 术语 ----
    @classmethod
    async def list_terms(cls, datasource: str | None = None) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import select

            q = select(AiQueryDictionaryModel).where(AiQueryDictionaryModel.is_deleted.is_(False))
            if datasource:
                q = q.where(AiQueryDictionaryModel.datasource == datasource)
            rows = (await db.execute(q)).scalars().all()
            return [
                {"id": t.id, "datasource": t.datasource, "term": t.term,
                 "metric_key": t.metric_key or "", "field_path": t.field_path or "",
                 "type": t.type}
                for t in rows
            ]

    @classmethod
    async def upsert_term(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            from sqlalchemy import select

            existing = (
                await db.execute(
                    select(AiQueryDictionaryModel).where(
                        AiQueryDictionaryModel.datasource == data.datasource,
                        AiQueryDictionaryModel.term == data.term,
                        AiQueryDictionaryModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.metric_key = data.metric_key
                existing.field_path = data.field_path
                existing.type = data.type
                existing.updated_id = auth.user.id
                obj = existing
            else:
                obj = AiQueryDictionaryModel(
                    datasource=data.datasource, term=data.term, metric_key=data.metric_key,
                    field_path=data.field_path, type=data.type,
                    created_id=auth.user.id, updated_id=auth.user.id,
                )
                db.add(obj)
            await db.flush()
            return {"id": obj.id, "datasource": obj.datasource, "term": obj.term,
                    "metric_key": obj.metric_key or "", "field_path": obj.field_path or "",
                    "type": obj.type}

    # ---- 数据资产目录（表/字段筛选 + 中文描述维护）----

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
            except Exception:  # noqa: BLE001
                pass

            # ④ 血缘计数：一条 GROUP BY（本表字段数 + 被引用数）
            lin_map: dict[str, int] = {}
            try:
                for t, n in (await db.execute(_t(
                    "SELECT t, SUM(n)::int FROM ("
                    "  SELECT table_name AS t, count(*) AS n FROM ai_query_asset_columns"
                    "   WHERE is_deleted=false GROUP BY table_name"
                    "  UNION ALL"
                    "  SELECT related_table AS t, count(*) AS n FROM ai_query_asset_columns"
                    "   WHERE is_deleted=false AND related_table IS NOT NULL AND related_table <> ''"
                    "   GROUP BY related_table"
                    ") x GROUP BY t"
                ))).all():
                    lin_map[t] = int(n or 0)
            except Exception:  # noqa: BLE001
                pass

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
        if executable == "generate_desc" and table:
            try:
                # 原来这里是**占位实现**：只把 alias 写成 "数据表 X"（假描述），
                # 前端看是"已补全"，实际一句中文描述都没生成；
                # 而真正调 LLM 的 generate_asset_descriptions / assets/generate-desc
                # 在前端**零入口**。现在两者接上（生成器按"缺描述的资产"批量处理，
                # 只补缺的，不覆盖人工填过的内容）。
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
                        "UPDATE ai_query_datasource SET enabled=true WHERE name=:n AND is_deleted=false"),
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
    @classmethod
    async def _ensure_favorite_table(cls, db) -> None:
        from sqlalchemy import text as _t
        dialect = (db.bind.dialect.name if db.bind else "")
        if dialect == "postgresql":
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_favorite ("
                "id BIGSERIAL PRIMARY KEY, kind VARCHAR(64), ref VARCHAR(255), "
                "user_id INTEGER, is_deleted INTEGER DEFAULT 0, created_time TIMESTAMP)"))
        else:
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_favorite ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, ref TEXT, "
                "user_id INTEGER, is_deleted INTEGER DEFAULT 0, created_time TEXT)"))

    @classmethod
    async def favorites_list(cls, user_id: int = 0) -> list[dict]:
        async with async_db_session.begin() as db:
            await cls._ensure_favorite_table(db)
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rows = (await db.execute(_t(
                "SELECT id,kind,ref,created_time FROM ai_favorite WHERE is_deleted=0 AND user_id=:u ORDER BY id DESC"),
                {"u": user_id})).fetchall()
        return [{"id": r[0], "kind": r[1], "ref": r[2], "time": str(r[3]) if r[3] else ""} for r in rows]

    @classmethod
    async def favorites_add(cls, kind: str, ref: str, user_id: int = 0) -> dict:
        from datetime import datetime
        async with async_db_session.begin() as db:
            await cls._ensure_favorite_table(db)
            from sqlalchemy import text as _t
            ex = (await db.execute(_t(
                "SELECT id FROM ai_favorite WHERE kind=:k AND ref=:r AND user_id=:u AND is_deleted=0"),
                {"k": kind, "r": ref, "u": user_id})).fetchone()
            if ex:
                return {"ok": True, "msg": "已收藏"}
            await db.execute(_t(
                "INSERT INTO ai_favorite(kind,ref,user_id,created_time) VALUES (:k,:r,:u,:now)"),
                {"k": kind, "r": ref, "u": user_id,
                 "now": datetime.now()})
        return {"ok": True, "msg": "收藏成功"}

    @classmethod
    async def favorites_remove(cls, fav_id: int, user_id: int = 0) -> dict:
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            await db.execute(_t(
                "UPDATE ai_favorite SET is_deleted=true WHERE id=:i AND user_id=:u"),
                {"i": fav_id, "u": user_id})
        return {"ok": True, "msg": "已取消收藏"}

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
        for a in plan["actions"]:
            if a["executable"] in ("scan_sensitive", "generate_desc", "dq_scan") and a.get("tables"):
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
            await _ensure_marking_columns(db)
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
        global _SCHEMA_CACHE, _SEMANTIC_INDEX, _ASSET_TMETA
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
        _SCHEMA_CACHE = None
        _SEMANTIC_INDEX = None
        _ASSET_TMETA = None
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

        global _SCHEMA_CACHE, _SEMANTIC_INDEX, _ASSET_TMETA
        _SCHEMA_CACHE = None
        _SEMANTIC_INDEX = None
        _ASSET_TMETA = None
        return {"ok": True, "saved": len(saved), "tables": saved,
                "skipped": skipped, "total": len(items)}

    @classmethod
    async def generate_asset_descriptions(cls, auth, force: bool = False) -> dict:
        """用 LLM 为表/字段生成中文描述（带数据画像；人工校对后生效）。

        force=True 时对全部已纳入资产重建，否则仅处理缺描述的。
        """
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
                    obj.updated_id = auth.user.id
                    updated_tables += 1
                cdesc = data.get("columns") or {}
                for colname, cobj in colmap.get(tname, []):
                    d = (cdesc.get(colname) or "").strip()
                    if d and isinstance(cobj, AiQueryAssetColumnModel):
                        cobj.description = d
                        cobj.updated_id = auth.user.id
                        updated_cols += 1
        return {"tables": updated_tables, "columns": updated_cols}

    @classmethod
    async def _knowledge_graph(cls, kb_id: int) -> dict:
        """拉取知识库图谱（实体/关系），供统一图谱使用。"""
        try:
            from app.plugin.module_ai.knowledge.service import AiKnowledgeService

            return await AiKnowledgeService.get_graph(kb_id)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 知识库图谱获取失败 kb={kb_id}: {e}")
            return {"nodes": [], "edges": []}

    @classmethod
    async def _ensure_concept_table(cls) -> None:
        """业务概念表（无 Alembic 迁移时运行时建表）。"""
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_query_concept ("
                "id BIGSERIAL PRIMARY KEY, name VARCHAR(120) UNIQUE, description TEXT, "
                "synonyms TEXT, parent_name VARCHAR(120), domain VARCHAR(60), "
                "metric_key VARCHAR(80), tables JSONB, is_deleted BOOLEAN DEFAULT false, "
                "created_time TIMESTAMP DEFAULT now())"))

    @classmethod
    async def list_concepts(cls) -> list[dict]:
        await cls._ensure_concept_table()
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            res = await db.execute(_t(
                "SELECT id,name,description,synonyms,parent_name,domain,metric_key,tables "
                "FROM ai_query_concept WHERE is_deleted=false ORDER BY id"))
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "name": r[1], "description": r[2] or "", "synonyms": r[3] or "",
            "parent_name": r[4] or "", "domain": r[5] or "", "metric_key": r[6] or "",
            "tables": r[7] if isinstance(r[7], list) else (_json.loads(r[7]) if r[7] else []),
        } for r in rows]

    @classmethod
    async def upsert_concept(cls, data, auth) -> dict:
        await cls._ensure_concept_table()
        import json as _json
        tables = _json.dumps(data.get("tables") or [])
        name = (data.get("name") or "").strip()
        if not name:
            raise CustomException(msg="概念名称不能为空")
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            if data.get("id"):
                await db.execute(_t(
                    "UPDATE ai_query_concept SET name=:n, description=:d, synonyms=:s, "
                    "parent_name=:p, domain=:do, metric_key=:m, tables=:tb "
                    "WHERE id=:id AND is_deleted=false"),
                    {"n": name, "d": data.get("description", ""), "s": data.get("synonyms", ""),
                     "p": data.get("parent_name", ""), "do": data.get("domain", ""),
                     "m": data.get("metric_key", ""), "tb": tables, "id": data["id"]})
            else:
                await db.execute(_t(
                    "INSERT INTO ai_query_concept(name, description, synonyms, parent_name, "
                    "domain, metric_key, tables) VALUES (:n,:d,:s,:p,:do,:m,:tb) "
                    "ON CONFLICT (name) DO UPDATE SET description=EXCLUDED.description, "
                    "synonyms=EXCLUDED.synonyms, parent_name=EXCLUDED.parent_name, "
                    "domain=EXCLUDED.domain, metric_key=EXCLUDED.metric_key, tables=EXCLUDED.tables"),
                    {"n": name, "d": data.get("description", ""), "s": data.get("synonyms", ""),
                     "p": data.get("parent_name", ""), "do": data.get("domain", ""),
                     "m": data.get("metric_key", ""), "tb": tables})
        return {"name": name}

    @classmethod
    async def delete_concepts(cls, ids: list[int]) -> int:
        await cls._ensure_concept_table()
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            await db.execute(_t(
                "UPDATE ai_query_concept SET is_deleted=true WHERE id IN :ids"),
                {"ids": list(ids)})
        return len(ids)

    @classmethod
    async def _ont_ctx_block(cls, only_tables: set[str] | None = None) -> str:
        """本体语义块（对象 + 属性 + 函数 + **关系**）。

        **改为调用本体的统一语义接口** ``semantic.context_block()``：
        语义只留本体那一份，问数不再自己拼 ``ai_ont_*`` 的 SQL。

        ``only_tables`` 传检索命中的表 → 只带这几张表的语义（实测 37517 → 千余字符）。
        """
        from app.plugin.module_ai.ontology import semantic as _sem

        return await _sem.context_block(only_tables=only_tables)

    @classmethod
    async def _ont_rel_block(cls, objs: dict) -> list[str]:
        """保留旧签名（有测试/调用方依赖），改为从统一接口取关系。"""
        from app.plugin.module_ai.ontology import semantic as _sem

        ctx = await _sem.semantic_context(include_properties=False)
        out = ["【本体关系（写多表查询时按此 join，不要靠字段名猜）】"]
        for r in ctx["relations"]:
            s, t = objs.get(r["source"]), objs.get(r["target"])
            if not s or not t:
                continue
            st = s.get("table") or r["source"]
            tt = t.get("table") or r["target"]
            line = f"- 「{s['name']}」{st}"
            if r["source_field"] and r["target_field"]:
                line += f".{r['source_field']} = 「{t['name']}」{tt}.{r['target_field']}"
            else:
                line += f" ↔ 「{t['name']}」{tt}（{r['join_method']}）"
            if r["name"]:
                line += f"   关系名：{r['name']}"
            if r["card"]:
                line += f"，基数：{r['card']}"
            out.append(line)
        return out if len(out) > 1 else []

    @classmethod
    async def _concept_context(cls) -> str:
        """把业务概念注入 prompt 上下文：概念+描述+同义词+映射。"""
        # 概念也走本体统一语义接口（本体对象的别名/域 + 问数概念表，合并成一份）
        from app.plugin.module_ai.ontology import semantic as _sem

        cs = await _sem.concepts()
        if not cs:
            return ""
        lines = ["【业务概念(本体)】"]
        for c in cs:
            line = f"- {c['name']}"
            if c.get("description"):
                line += f": {c['description']}"
            if c.get("synonyms"):
                line += f"（同义:{c['synonyms']}）"
            if c.get("domain"):
                line += f"[{c['domain']}]"
            if c.get("metric_key"):
                line += f"→指标:{c['metric_key']}"
            if c.get("tables"):
                line += f"→表:{','.join(c['tables'])}"
            lines.append(line)
        return "\n".join(lines)

    @classmethod
    async def _ont_objs(cls) -> dict:
        """本体对象 → dict。**改为走本体的统一语义接口**，不再自己拼 SQL。

        历史上这里直连 ``ai_ont_object``，本体表结构一改就可能悄悄坏掉
        （"看起来接上了，实际靠约定"）。语义只留本体那一份。
        """
        from app.plugin.module_ai.ontology import semantic as _sem

        ctx = await _sem.semantic_context(include_properties=False)
        return {o["code"]: {"code": o["code"], "name": o["name"],
                            "key_prop": o["key_prop"], "name_prop": o["name_prop"],
                            "description": o["description"],
                            # table 是**真实支撑表名**（数据源支撑的对象就叫它自己）
                            "table": o["table"]} for o in ctx["objects"]}

    @classmethod
    async def _ont_props(cls, code: str) -> list[dict]:
        """某个对象的属性（含敏感/角色）。走统一语义接口。"""
        from app.plugin.module_ai.ontology import semantic as _sem

        ctx = await _sem.semantic_context()
        return [{"code": p["code"], "prop_type": p["prop_type"],
                 "sensitive": p["sensitive"], "roles": p["roles"]}
                for p in ctx["properties"].get(code, [])]

    @classmethod
    async def _ont_links(cls, code: str) -> list[tuple]:
        """某个对象的一跳关系。走统一语义接口。"""
        from app.plugin.module_ai.ontology import semantic as _sem

        ctx = await _sem.semantic_context(include_properties=False)
        return [(r["target"], r["source_field"], r["target_field"], r["name"])
                for r in ctx["relations"] if r["source"] == code]

    @classmethod
    async def _resolve_ont_entity(cls, entity: str, key: str, user_id: int | None = None) -> dict | None:
        """本体对象 grounding：先按本体对象类型匹配，再按本体属性/Link 解析实例（Palantir 式）。"""
        from sqlalchemy import text as _t
        objs = await cls._ont_objs()
        match = None
        for o in objs.values():
            if o["name"] and (o["name"] in entity or entity in o["name"]):
                match = o
                break
            if o["code"] and o["code"].replace("_", "") in entity.replace("_", ""):
                match = o
                break
        if not match:
            return None
        code = match["code"]
        # 用**真实支撑表名**：这里原先硬拼 ont_{code}，而数据源支撑的对象
        # 表名就是它自己（video_cameras），拼错会去查一张不存在的表
        table = match.get("table") or code
        props = await cls._ont_props(code)
        name_prop, key_prop = match["name_prop"], match["key_prop"]
        try:
            async with async_db_session() as db:
                row = (await db.execute(_t(
                    f'SELECT * FROM "{table}" WHERE "{name_prop}" ILIKE :k LIMIT 1'), {"k": f"%{key}%"})).mappings().first()
                if row is None:
                    row = (await db.execute(_t(
                        f'SELECT * FROM "{table}" WHERE "{key_prop}" = :k LIMIT 1'), {"k": key})).mappings().first()
        except Exception as e:  # noqa: BLE001
            return {"entity": entity, "ontology": code, "table": table,
                    "error": "本体对象尚未物化为表或查询失败", "hint": "请在【本体】页对该对象执行「物化为表」", "detail": str(e)[:80]}
        if not row:
            return {"entity": entity, "ontology": code, "table": table,
                    "error": f"在本体对象 {table} 未找到「{key}」"}
        can_see = await cls._can_see_sensitive(user_id)
        obj = {}
        restricted = []
        for p in props:
            if p["sensitive"] and not can_see:
                continue
            # 属性级 ACL：roles 非空且不含 'all'/'public' 时，非超管需角色匹配才可见
            if p.get("roles") and not can_see:
                allowed = set(p["roles"])
                if not (allowed & {"all", "public"}):
                    restricted.append(p["code"])
                    continue
            v = row.get(p["code"])
            obj[p["code"]] = str(v) if not isinstance(v, (int, float, bool)) else v
        related: list[dict] = []
        for tgt, sfield, tfield, lname in await cls._ont_links(code):
            tgt_table = f"ont_{tgt}"
            fval = row.get(sfield)
            try:
                async with async_db_session() as db:
                    trow = (await db.execute(_t(
                        f'SELECT * FROM "{tgt_table}" WHERE "{tfield}" = :k LIMIT 1'), {"k": fval})).mappings().first()
            except Exception:  # noqa: BLE001
                trow = None
            tname = (trow.get("name") if trow else None)
            related.append({"relation": lname or f"{code}→{tgt}", "entity": tgt, "key": fval,
                            "name": tname,
                            "target": {k: (str(v) if not isinstance(v, (int, float, bool)) else v) for k, v in trow.items()} if trow else None})
        return {"entity": entity, "ontology": code, "table": table, "object": obj, "related": related}

    @classmethod
    async def resolve_entity_object(cls, entity: str, key: str, datasource: str = SYSTEM_DS,
                                    user_id: int | None = None) -> dict | None:
        """P0·对象 grounding：把业务实体名(如「摄像头/订单」)+ 关键值解析为真实对象及关联邻居。

        返回 ``{entity, table, object:{列:值}, related:[{relation, entity, ...}]}``，供
        Agent/问数作为 grounded context 注入模型（对标 Palantir AIP grounding）。

        ABAC：非超管按敏感字段策略过滤敏感列（object 中剔除标记为 sensitive 的字段）。
        """
        from sqlalchemy import text as _t

        # 优先：本体对象 grounding（Palantir 式）
        try:
            ont_res = await cls._resolve_ont_entity(entity, key, user_id)
            if ont_res:
                return ont_res
        except Exception:  # noqa: BLE001
            pass

        schema = await cls._system_schema()
        tmeta = await cls._asset_tmeta()
        entity = (entity or "").strip()
        key = (key or "").strip()
        if not entity or not key:
            return None
        # 1) 候选表：实体名词映射 + 中文名/别名/表名包含
        cand: list[str] = []
        for noun, tables in _ENTITY_TABLE.items():
            if noun in entity or entity in noun:
                cand.extend(tables)
        for t in schema:
            meta = tmeta.get(t) or {}
            if (meta.get("alias") and meta["alias"] in entity) or (
                meta.get("description") and entity in meta["description"]
            ):
                cand.append(t)
            if t and t.replace("_", "") in entity.replace("_", ""):
                cand.append(t)
        cand = list(dict.fromkeys(c for c in cand if c in schema))
        if not cand:
            return None
        # 2) 选主表：优先含 name/title 列且非分组/日志/事件类的实体表

        def labels_of(t: str) -> list[str]:
            return schema.get(t) or []
        has_name = [t for t in cand if any(lab.split("(")[0] in ("name", "title", "label") for lab in labels_of(t))]
        prefer = [t for t in has_name if not any(x in t for x in ("group", "groups", "task", "logs", "records", "events", "call_logs"))]
        table = (prefer or has_name or cand)[0]
        labels = schema.get(table) or []
        id_col = next((lab.split("(")[0] for lab in labels if lab.split("(")[0] == "id"), None) or (labels[0].split("(")[0] if labels else "")
        name_col = next((lab.split("(")[0] for lab in labels if lab.split("(")[0] in ("name", "title", "label")), None)
        # 3) 解析关联：字段名 -> 关联表.关联字段
        rel_re = re.compile(r"【关联:([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)】")
        rel_cols: list[tuple[str, str, str]] = []
        for lab in labels:
            col = lab.split("(")[0]
            m = rel_re.search(lab)
            if m:
                rel_cols.append((col, m.group(1), m.group(2)))
        # 4) 取对象行：优先按 name 匹配，否则按 id
        try:
            async with async_db_session() as db:
                cond = f'"{name_col}" ILIKE :k' if name_col else f'"{id_col}" = :k'
                row = (await db.execute(_t(
                    f'SELECT * FROM "{table}" WHERE {cond} LIMIT 1'), {"k": f"%{key}%"})).mappings().first()
                if row is None and name_col:
                    row = (await db.execute(_t(
                        f'SELECT * FROM "{table}" WHERE "{id_col}" = :k LIMIT 1'), {"k": key})).mappings().first()
                if row is None and id_col:
                    row = (await db.execute(_t(
                        f'SELECT * FROM "{table}" WHERE "{id_col}" = :k LIMIT 1'), {"k": key})).mappings().first()
        except Exception as e:  # noqa: BLE001
            return {"entity": entity, "table": table, "error": str(e)[:120], "related": []}
        if row is None:
            return {"entity": entity, "table": table, "object": None, "related": []}
        obj = {k: (str(v) if not isinstance(v, (int, float, bool)) else v) for k, v in row.items()}
        # ABAC：非超管过滤敏感字段
        try:
            if not await cls._can_see_sensitive(user_id):
                async with async_db_session() as db:
                    sens = (await db.execute(_t(
                        "SELECT column_name FROM ai_query_asset_columns WHERE table_name=:t AND sensitive=true AND is_deleted=false"),
                        {"t": table})).fetchall()
                sens_set = {s[0] for s in sens}
                if sens_set:
                    obj = {k: v for k, v in obj.items() if k not in sens_set}
        except Exception:  # noqa: BLE001
            pass
        # 5) 关联邻居：对每条关联字段取值，取关联表 name 列
        related: list[dict] = []
        try:
            async with async_db_session() as db:
                for col, rt, rf in rel_cols[:6]:
                    val = obj.get(col)
                    if val is None:
                        continue
                    rt_labels = schema.get(rt) or []
                    rname_col = next((lab.split("(")[0] for lab in rt_labels
                                      if lab.split("(")[0] in ("name", "title", "label")), rf)
                    rr = (await db.execute(_t(
                        f'SELECT * FROM "{rt}" WHERE "{rf}" = %(v)s LIMIT 1'), {"v": val})).mappings().first()
                    if rr:
                        related.append({
                            "relation": col,
                            "entity": rt,
                            "name": str(rr.get(rname_col) or rr.get("id")),
                            "summary": f"{rt}#{str(rr.get(rname_col) or rr.get('id'))}",
                        })
        except Exception:  # noqa: BLE001
            pass
        return {"entity": entity, "table": table, "object": obj, "related": related}

    @classmethod
    async def list_objects(cls) -> list[dict]:
        """业务对象(Object Type)：**以本体为唯一真相源**（``ai_ont_object``，enabled 且可解析支撑表）。

        与「对象查询白名单」（``_allowed_objects_for_query`` → ``semantic.semantic_context``）**同源**，
        消除"对象列表里有、对象查询却不认"的断层。

        - 未纳入本体的表**不再出现在对象列表**（仍可用自然语言 NL2SQL 查询）；
          在「表与字段」勾选「纳入本体对象」即可把表纳入本体并出现在此列表。
        - Link 来自本体关系类型（``ai_ont_link``），按 object_code → 支撑表映射。
        """
        from app.plugin.module_ai.ontology import semantic as _sem

        try:
            ctx = await _sem.semantic_context(include_properties=False)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] list_objects 读取本体语义失败：{str(e)[:100]}")
            return []
        objs = [o for o in (ctx.get("objects") or []) if o.get("table")]
        code2table = {str(o.get("code")): o.get("table") for o in objs}
        relations = ctx.get("relations") or []
        out = []
        for o in objs:
            links = []
            for r in relations:
                if str(r.get("source")) == str(o.get("code")) and code2table.get(
                    str(r.get("target"))
                ):
                    links.append({
                        "target": code2table[str(r.get("target"))],
                        "via": r.get("source_field") or "",
                        "target_field": r.get("target_field") or "",
                    })
            out.append({
                "table": o.get("table"),
                "alias": o.get("name") or o.get("table"),
                "key_col": o.get("key_prop") or "id",
                "name_col": o.get("name_prop") or "name",
                "icon": "el-icon-Box",
                "ont_code": o.get("code") or "",
                "links": links,
            })
        return out

    @classmethod
    async def list_propositions(cls) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            res = await db.execute(_t(
                "SELECT id,title,description,criteria,owner,step_diagnosis,step_modeling,"
                "step_assembly,step_shadow,step_handover,gap,delivery_assets,status,created_time,"
                "fde_translator,fde_data,fde_app,shadow_metric,shadow_golden,shadow_tolerance,"
                "shadow_result,shadow_actual,shadow_at "
                "FROM ai_delivery_proposition WHERE is_deleted=false ORDER BY id DESC"))
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "title": r[1] or "", "description": r[2] or "", "criteria": r[3] or "",
            "owner": r[4] or "", "steps": {
                "diagnosis": r[5], "modeling": r[6], "assembly": r[7], "shadow": r[8], "handover": r[9],
            },
            "gap": r[10] if isinstance(r[10], list) else (_json.loads(r[10]) if r[10] else []),
            "delivery_assets": r[11] if isinstance(r[11], list) else (_json.loads(r[11]) if r[11] else []),
            "status": r[12] or "open", "created_time": str(r[13]) if r[13] else "",
            "fde_translator": r[14] or "", "fde_data": r[15] or "", "fde_app": r[16] or "",
            "shadow_metric": r[17] or "", "shadow_golden": r[18] or "", "shadow_tolerance": r[19] or "",
            "shadow_result": r[20] or "", "shadow_actual": r[21] or "", "shadow_at": str(r[22]) if r[22] else "",
        } for r in rows]

    @classmethod
    async def upsert_proposition(cls, data: dict, auth) -> dict:
        import json as _json
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            pid = data.get("id")
            gap = _json.dumps(data.get("gap") or [], ensure_ascii=False)
            assets = _json.dumps(data.get("delivery_assets") or [], ensure_ascii=False)
            if pid:
                await db.execute(_t(
                    "UPDATE ai_delivery_proposition SET title=:t, description=:d, criteria=:c, owner=:o, "
                    "step_diagnosis=:s1, step_modeling=:s2, step_assembly=:s3, step_shadow=:s4, "
                    "step_handover=:s5, gap=:g, delivery_assets=:a, status=:st, "
                    "fde_translator=:ft, fde_data=:fd, fde_app=:fa, "
                    "shadow_metric=:sm, shadow_golden=:sg, shadow_tolerance=:stl, updated_time=now() "
                    "WHERE id=:pid"), {
                    "t": data.get("title", ""), "d": data.get("description", ""),
                    "c": data.get("criteria", ""), "o": data.get("owner", ""),
                    "s1": data.get("steps", {}).get("diagnosis", "todo"),
                    "s2": data.get("steps", {}).get("modeling", "todo"),
                    "s3": data.get("steps", {}).get("assembly", "todo"),
                    "s4": data.get("steps", {}).get("shadow", "todo"),
                    "s5": data.get("steps", {}).get("handover", "todo"),
                    "g": gap, "a": assets, "st": data.get("status", "open"), "pid": pid,
                    "ft": data.get("fde_translator", ""), "fd": data.get("fde_data", ""),
                    "fa": data.get("fde_app", ""), "sm": data.get("shadow_metric", ""),
                    "sg": data.get("shadow_golden", ""), "stl": data.get("shadow_tolerance", "")})
            else:
                res = await db.execute(_t(
                    "INSERT INTO ai_delivery_proposition(title,description,criteria,owner,step_diagnosis,"
                    "step_modeling,step_assembly,step_shadow,step_handover,gap,delivery_assets,status,"
                    "fde_translator,fde_data,fde_app,shadow_metric,shadow_golden,shadow_tolerance) "
                    "VALUES (:t,:d,:c,:o,:s1,:s2,:s3,:s4,:s5,:g,:a,:st,:ft,:fd,:fa,:sm,:sg,:stl) RETURNING id"), {
                    "t": data.get("title", ""), "d": data.get("description", ""),
                    "c": data.get("criteria", ""), "o": data.get("owner", ""),
                    "s1": data.get("steps", {}).get("diagnosis", "todo"),
                    "s2": data.get("steps", {}).get("modeling", "todo"),
                    "s3": data.get("steps", {}).get("assembly", "todo"),
                    "s4": data.get("steps", {}).get("shadow", "todo"),
                    "s5": data.get("steps", {}).get("handover", "todo"),
                    "g": gap, "a": assets, "st": data.get("status", "open"),
                    "ft": data.get("fde_translator", ""), "fd": data.get("fde_data", ""),
                    "fa": data.get("fde_app", ""), "sm": data.get("shadow_metric", ""),
                    "sg": data.get("shadow_golden", ""), "stl": data.get("shadow_tolerance", "")})
                pid = res.scalar()
        return {"id": pid}

    @classmethod
    async def shadow_check(cls, proposition_id: int) -> dict:
        """P2-① 影子运行：执行命题绑定的指标，与黄金标准比对（±容差）。"""
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            row = (await db.execute(_t(
                "SELECT shadow_metric,shadow_golden,shadow_tolerance FROM ai_delivery_proposition WHERE id=:i"),
                {"i": proposition_id})).fetchone()
        if not row or not row[0]:
            return {"ok": False, "msg": "未配置校验指标/黄金标准"}
        metric_key, golden, tol = row[0], row[1] or "", row[2] or ""
        try:
            metrics = await cls.list_metrics(SYSTEM_DS)
            m = next((x for x in metrics if x["key"] == metric_key), None)
            if not m:
                return {"ok": False, "msg": f"指标 {metric_key} 不存在"}
            from types import SimpleNamespace as SN
            auth = SN(user=SN(id=1))
            res = await _execute_metric(m, {}, auth)
            actual = res.get("rows", [[None]])[0][0] if res.get("rows") else None
            sv = float(actual) if actual is not None else None
            gv = float(golden) if golden else None
            ok = False
            if sv is not None and gv is not None:
                if tol.endswith("%") and gv != 0:
                    ok = abs(sv - gv) / abs(gv) * 100 <= float(tol[:-1])
                elif tol.endswith("%") and gv == 0:
                    ok = sv == 0
                elif tol:
                    ok = abs(sv - gv) <= float(tol)
                else:
                    ok = sv == gv
            result = "pass" if ok else "fail"
            async with async_db_session.begin() as db:
                from sqlalchemy import text as _t
                await db.execute(_t(
                    "UPDATE ai_delivery_proposition SET shadow_result=:r, shadow_actual=:a, "
                    "step_shadow=:ss, shadow_at=now() WHERE id=:i"), {
                    "r": result, "a": str(actual), "ss": "done" if ok else "doing", "i": proposition_id})
            return {"ok": True, "result": result, "actual": actual, "golden": golden, "tolerance": tol}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"校验失败：{str(e)[:120]}"}

    @classmethod
    async def delete_proposition(cls, pid: int) -> None:
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            await db.execute(_t("UPDATE ai_delivery_proposition SET is_deleted=true WHERE id=:pid"), {"pid": pid})

    @classmethod
    async def list_actions(cls) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            res = await db.execute(_t(
                "SELECT id,name,object_table,writable_cols,writable_by_role,validation,approve,enabled "
                "FROM ai_query_writeback WHERE is_deleted=false ORDER BY id DESC"))
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "name": r[1], "object_table": r[2],
            "writable_cols": r[3] if isinstance(r[3], list) else (_json.loads(r[3]) if r[3] else []),
            "writable_by_role": r[4] if isinstance(r[4], dict) else (_json.loads(r[4]) if r[4] else {}),
            "validation": r[5] or "", "approve": bool(r[6]), "enabled": bool(r[7]),
        } for r in rows]

    @classmethod
    async def upsert_action(cls, data: dict) -> dict:
        import json as _json
        cols = _json.dumps(data.get("writable_cols") or [], ensure_ascii=False)
        wr = _json.dumps(data.get("writable_by_role") or {}, ensure_ascii=False)
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            if data.get("id"):
                await db.execute(_t(
                    "UPDATE ai_query_writeback SET name=:n, object_table=:o, writable_cols=:w, writable_by_role=:wr, "
                    "validation=:v, approve=:a, enabled=:e, updated_time=now() WHERE id=:i"), {
                    "n": data.get("name", ""), "o": data.get("object_table", ""), "w": cols, "wr": wr,
                    "v": data.get("validation", ""), "a": bool(data.get("approve", True)),
                    "e": bool(data.get("enabled", True)), "i": data["id"]})
                return {"id": data["id"]}
            res = await db.execute(_t(
                "INSERT INTO ai_query_writeback(name,object_table,writable_cols,writable_by_role,validation,approve,enabled) "
                "VALUES (:n,:o,:w,:wr,:v,:a,:e) ON CONFLICT (name) DO UPDATE SET object_table=:o, "
                "writable_cols=:w, writable_by_role=:wr, validation=:v, approve=:a, enabled=:e RETURNING id"), {
                "n": data.get("name", ""), "o": data.get("object_table", ""), "w": cols, "wr": wr,
                "v": data.get("validation", ""), "a": bool(data.get("approve", True)),
                "e": bool(data.get("enabled", True))})
            return {"id": res.scalar()}

    @classmethod
    async def _user_role_codes_by_id(cls, user_id) -> set[str]:
        """按 user_id 查询其角色 code 集合（sys_user_roles → sys_role）。"""
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            uid = 0
        if not uid:
            return set()
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                rows = (await db.execute(_t(
                    "SELECT r.code FROM sys_role r JOIN sys_user_roles ur ON ur.role_id=r.id "
                    "WHERE ur.user_id=:u AND r.is_deleted=false"), {"u": uid})).fetchall()
            return {r[0] for r in rows}
        except Exception:  # noqa: BLE001
            return set()

    @classmethod
    async def _action_writable_for(cls, act: dict, operator: str) -> set[str]:
        """动作可写字段：超管/未配角色字段 → 全局 writable_cols；否则收窄为该角色允许字段的交集。"""
        writable = set(act.get("writable_cols") or [])
        wr = act.get("writable_by_role") or {}
        if not wr:
            return writable
        try:
            if await cls._is_superuser(operator):
                return writable
        except Exception:  # noqa: BLE001
            pass
        roles = await cls._user_role_codes_by_id(operator)
        role_allowed: set[str] = set()
        for r in roles:
            role_allowed |= set(wr.get(r) or [])
        if role_allowed:
            return writable & role_allowed
        return writable

    @classmethod
    async def execute_action(cls, name: str, object_key: str, params: dict, operator: str, approve: bool = False) -> dict:
        """P1·Action 写回：校验动作+可写字段，更新对象行，写审计日志。approve 未通过则只返回待审批。"""
        from sqlalchemy import text as _t
        actions = await cls.list_actions()
        act = next((a for a in actions if a["name"] == name), None)
        if not act or not act.get("enabled"):
            return {"ok": False, "msg": "动作不存在或未启用"}
        table = act["object_table"]
        writable = await cls._action_writable_for(act, operator)
        if not writable:
            return {"ok": False, "msg": "该动作未配置可写字段"}
        # 审批门禁：需审批且未批准 → 落审批单（pending），返回待审批 id
        if act.get("approve") and not approve:
            import json as _json
            async with async_db_session.begin() as db:
                pres = await db.execute(_t(
                    "INSERT INTO ai_query_writeback_log(action_name,object_table,object_key,params,operator,result,detail) "
                    "VALUES (:n,:t,:k,:p,:o,'pending','待审批') RETURNING id"), {
                    "n": name, "t": table, "k": object_key,
                    "p": _json.dumps(params, ensure_ascii=False), "o": operator or ""})
                pid = pres.scalar()
            return {"ok": False, "msg": "该操作需人工审批后执行", "needs_approval": True,
                    "approval_id": pid, "pending": {"params": params, "key": object_key}}
        # 校验 params 列均在可写集合
        cols = list(params.keys())
        bad = [c for c in cols if c not in writable]
        if bad:
            return {"ok": False, "msg": f"以下字段不可写：{','.join(bad)}"}
        if not object_key:
            return {"ok": False, "msg": "缺少对象关键值"}
        sets = ", ".join(f'"{c}" = :{c}' for c in cols)
        try:
            async with async_db_session.begin() as db:
                res = await db.execute(_t(
                    f'UPDATE "{table}" SET {sets} WHERE "id"::text = :__k'), {**params, "__k": str(object_key)})
                detail = f"action={name} {table}#{object_key} cols={cols}"
            # 审计
            import json as _json
            async with async_db_session.begin() as db2:
                await db2.execute(_t(
                    "INSERT INTO ai_query_writeback_log(action_name,object_table,object_key,params,operator,result,detail) "
                    "VALUES (:n,:t,:k,:p,:o,:r,:d)"), {
                    "n": name, "t": table, "k": object_key,
                    "p": _json.dumps(params, ensure_ascii=False), "o": operator or "",
                    "r": "success" if res.rowcount else "noop", "d": detail})
            return {"ok": True, "rows": int(res.rowcount or 0), "msg": "已执行并留痕"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"执行失败：{str(e)[:120]}"}

    @classmethod
    async def _is_superuser(cls, user_id) -> bool:
        """按 user_id 判断是否超管（用于审批人约束）。"""
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            uid = 0
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                r = (await db.execute(_t(
                    "SELECT is_superuser FROM sys_user WHERE id=:id AND is_deleted=false"),
                    {"id": uid})).fetchone()
            return bool(r and r[0])
        except Exception:  # noqa: BLE001
            return False

    @classmethod
    async def list_pending_actions(cls, limit: int = 50) -> list[dict]:
        """待审批的 Action 写回请求（result='pending'）。"""
        import json as _json
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            res = await db.execute(_t(
                "SELECT id,action_name,object_table,object_key,params,operator,created_time "
                "FROM ai_query_writeback_log WHERE result='pending' AND is_deleted=false "
                "ORDER BY id DESC LIMIT :n"), {"n": max(1, min(limit, 200))})
            rows = res.fetchall()
        return [{
            "id": r[0], "action": r[1], "table": r[2], "key": r[3],
            "params": r[4] if isinstance(r[4], dict) else (_json.loads(r[4]) if r[4] else {}),
            "operator": r[5], "time": str(r[6]) if r[6] else "",
        } for r in rows]

    @classmethod
    async def approve_action(cls, approval_id: int, operator: str) -> dict:
        """批准待审批的 Action：执行真实写回（可写字段校验）+ 落审计，审批单置为 approved。

        审批人约束：仅超管可批准写回。
        """
        if not await cls._is_superuser(operator):
            return {"ok": False, "msg": "仅超管可审批写回操作"}
        import json as _json

        from sqlalchemy import text as _t
        async with async_db_session() as db:
            row = (await db.execute(_t(
                "SELECT action_name,object_table,object_key,params FROM ai_query_writeback_log "
                "WHERE id=:i AND result='pending' AND is_deleted=false"), {"i": approval_id})).fetchone()
        if not row:
            return {"ok": False, "msg": "审批单不存在或已处理"}
        name, table, key, params = row[0], row[1], row[2], row[3]
        params = params if isinstance(params, dict) else (_json.loads(params) if params else {})
        actions = await cls.list_actions()
        act = next((a for a in actions if a["name"] == name), None)
        if not act or not act.get("enabled"):
            return {"ok": False, "msg": "动作不存在或未启用"}
        writable = await cls._action_writable_for(act, operator)
        cols = list(params.keys())
        bad = [c for c in cols if c not in writable]
        if bad:
            return {"ok": False, "msg": f"以下字段不可写：{','.join(bad)}"}
        if not key:
            return {"ok": False, "msg": "缺少对象关键值"}
        sets = ", ".join(f'"{c}" = :{c}' for c in cols)
        try:
            async with async_db_session.begin() as db:
                res = await db.execute(_t(
                    f'UPDATE "{table}" SET {sets} WHERE "id"::text = :__k'),
                    {**params, "__k": str(key)})
                await db.execute(_t(
                    "UPDATE ai_query_writeback_log SET result='approved', detail=:d, operator=:o WHERE id=:i"),
                    {"d": f"已批准，影响 {res.rowcount} 行", "o": operator or "", "i": approval_id})
            return {"ok": True, "rows": int(res.rowcount or 0), "msg": "已批准并执行留痕"}
        except Exception as e:  # noqa: BLE001
            async with async_db_session.begin() as db:
                await db.execute(_t(
                    "UPDATE ai_query_writeback_log SET result='rejected', detail=:d WHERE id=:i"),
                    {"d": f"批准执行失败：{str(e)[:100]}", "i": approval_id})
            return {"ok": False, "msg": f"执行失败：{str(e)[:120]}"}

    @classmethod
    async def reject_action(cls, approval_id: int, operator: str) -> dict:
        """驳回待审批的 Action。审批人约束：仅超管可驳回。"""
        if not await cls._is_superuser(operator):
            return {"ok": False, "msg": "仅超管可驳回写回操作"}
        from sqlalchemy import text as _t
        async with async_db_session.begin() as db:
            await db.execute(_t(
                "UPDATE ai_query_writeback_log SET result='rejected', detail=:d WHERE id=:i AND result='pending'"),
                {"d": f"已驳回 by {operator or ''}", "i": approval_id})
        return {"ok": True, "msg": "已驳回"}

    @classmethod
    async def list_action_logs(cls, limit: int = 100) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            res = await db.execute(_t(
                "SELECT id,action_name,object_table,object_key,params,operator,result,detail,created_time "
                "FROM ai_query_writeback_log WHERE is_deleted=false ORDER BY id DESC LIMIT :n"), {"n": max(1, min(limit, 200))})
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "action": r[1], "table": r[2], "key": r[3],
            "params": r[4] if isinstance(r[4], dict) else (_json.loads(r[4]) if r[4] else {}),
            "operator": r[5], "result": r[6], "detail": r[7] or "", "time": str(r[8]) if r[8] else "",
        } for r in rows]

    @classmethod
    async def _record_version(cls, table_name: str, snapshot: dict, field_name: str = "", operator: str = "") -> None:
        import json as _json
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            n = (await db.execute(_t(
                "SELECT COALESCE(MAX(version_no),0) FROM ai_asset_version WHERE table_name=:t AND field_name=:f AND is_deleted=false"),
                {"t": table_name, "f": field_name})).scalar() or 0
            await db.execute(_t(
                "INSERT INTO ai_asset_version(table_name,field_name,snapshot,version_no,operator) "
                "VALUES (:t,:f,:s,:n,:o)"), {
                "t": table_name, "f": field_name, "s": _json.dumps(snapshot, ensure_ascii=False),
                "n": int(n) + 1, "o": operator or ""})

    @classmethod
    async def list_versions(cls, table_name: str) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            res = await db.execute(_t(
                "SELECT id,table_name,field_name,snapshot,version_no,operator,created_time "
                "FROM ai_asset_version WHERE table_name=:t AND is_deleted=false ORDER BY id DESC LIMIT 50"),
                {"t": table_name})
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "table": r[1], "field": r[2],
            "snapshot": r[3] if isinstance(r[3], dict) else (_json.loads(r[3]) if r[3] else {}),
            "version": r[4], "operator": r[5] or "", "time": str(r[6]) if r[6] else "",
        } for r in rows]

    @classmethod
    async def version_diff(cls, id_a: int, id_b: int) -> dict:
        """版本 diff：对比两个版本快照，输出新增/删除/变更的字段（表级或字段级）。"""
        import json as _json
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            ra = (await db.execute(_t("SELECT table_name,field_name,snapshot,version_no FROM ai_asset_version WHERE id=:i AND is_deleted=false"), {"i": id_a})).fetchone()
            rb = (await db.execute(_t("SELECT table_name,field_name,snapshot,version_no FROM ai_asset_version WHERE id=:i AND is_deleted=false"), {"i": id_b})).fetchone()
        if not ra or not rb:
            return {"ok": False, "msg": "版本不存在"}

        def _load(raw):
            return raw if isinstance(raw, dict) else (_json.loads(raw) if raw else {})
        sa, sb = _load(ra[2]), _load(rb[2])
        keys = set(sa.keys()) | set(sb.keys())
        changed = []
        for k in sorted(keys):
            va, vb = sa.get(k), sb.get(k)
            if va != vb:
                changed.append({"key": k, "from": va, "to": vb})
        return {"ok": True, "table": ra[0], "field": ra[1] or "", "field_b": rb[1] or "",
                "version_a": ra[3], "version_b": rb[3],
                "changed": changed, "changed_count": len(changed)}

    @classmethod
    async def asset_publish(cls, table_name: str, version_id: int, auth) -> dict:
        """数据集/对象版本发布：把指定版本标记为当前发布版本（可回滚发布）。"""
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            v = (await db.execute(_t(
                "SELECT table_name,field_name,snapshot,version_no FROM ai_asset_version WHERE id=:i AND is_deleted=false"),
                {"i": version_id})).fetchone()
        if not v:
            return {"ok": False, "msg": "版本不存在"}
        if v[0] != table_name:
            return {"ok": False, "msg": "版本不属于该对象"}
        from datetime import datetime
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_asset_publish "
                "(table_name TEXT PRIMARY KEY, version_id INTEGER, published_time TEXT, operator TEXT)"))
            await db.execute(_t(
                "INSERT OR REPLACE INTO ai_asset_publish(table_name,version_id,published_time,operator) "
                "VALUES (:t,:v,:now,:op)"),
                {"t": table_name, "v": int(version_id),
                 "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "op": str(getattr(getattr(auth, "user", None), "id", ""))})
        return {"ok": True, "table": table_name, "version": v[3], "msg": f"已发布版本 {v[3]}"}

    @classmethod
    async def asset_releases(cls, table_name: str) -> dict:
        """当前发布版本 + 该对象的版本列表（含是否已发布）。"""
        import json as _json
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            version_rows = (await db.execute(_t(
                "SELECT id,field_name,snapshot,version_no,created_time FROM ai_asset_version "
                "WHERE table_name=:t AND is_deleted=false ORDER BY version_no DESC LIMIT 50"),
                {"t": table_name})).fetchall()
            pub = (await db.execute(_t(
                "SELECT version_id,published_time FROM ai_asset_publish WHERE table_name=:t"),
                {"t": table_name})).fetchone()
        published_version_id = int(pub[0]) if pub else None
        versions = []
        for r in version_rows:
            snap = r[2] if isinstance(r[2], dict) else (_json.loads(r[2]) if r[2] else {})
            versions.append({"id": r[0], "field": r[1] or "", "snapshot": snap,
                             "version": r[3], "time": str(r[4]) if r[4] else "",
                             "published": (r[0] == published_version_id)})
        return {"table": table_name, "published_version_id": published_version_id,
                "published_time": str(pub[1]) if pub and pub[1] else "",
                "versions": versions}

    @classmethod
    async def rollback_version(cls, version_id: int, auth) -> dict:
        import json as _json
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            v = (await db.execute(_t(
                "SELECT table_name,field_name,snapshot,version_no FROM ai_asset_version WHERE id=:i AND is_deleted=false"),
                {"i": version_id})).fetchone()
        if not v:
            return {"ok": False, "msg": "版本不存在"}
        table, field, snap_raw, vno = v[0], v[1], v[2], v[3]
        snap = snap_raw if isinstance(snap_raw, dict) else (_json.loads(snap_raw) if snap_raw else {})
        if field:
            # 字段级回滚
            async with async_db_session.begin() as db:
                from sqlalchemy import text as _t
                await db.execute(_t(
                    "UPDATE ai_query_asset_columns SET description=:d, business_scenarios=:s, "
                    "related_table=:rt, related_field=:rf, sensitive=:se "
                    "WHERE table_name=:t AND column_name=:c AND is_deleted=false"), {
                    "d": snap.get("description", ""), "s": snap.get("business_scenarios", ""),
                    "rt": snap.get("related_table") or "", "rf": snap.get("related_field") or "",
                    "se": bool(snap.get("sensitive", False)), "t": table, "c": field})
        else:
            async with async_db_session.begin() as db:
                from sqlalchemy import text as _t
                await db.execute(_t(
                    "UPDATE ai_query_assets SET alias=:a, domain=:d, description=:de, business_scenarios=:b, "
                    "included=:i, object_enabled=:oe, object_key_col=:ok, object_name_col=:on, object_icon=:oi "
                    "WHERE table_name=:t AND is_deleted=false"), {
                    "a": snap.get("alias", ""), "d": snap.get("domain", ""), "de": snap.get("description", ""),
                    "b": snap.get("business_scenarios", ""), "i": bool(snap.get("included", True)),
                    "oe": bool(snap.get("object_enabled", False)), "ok": snap.get("object_key_col") or "id",
                    "on": snap.get("object_name_col") or "name", "oi": snap.get("object_icon") or "el-icon-Box",
                    "t": table})
        await cls._record_version(table, snap, field, operator=str(getattr(getattr(auth, "user", None), "id", "")))
        _SCHEMA_CACHE = None
        _ASSET_TMETA = None
        return {"ok": True, "msg": f"已回滚到版本 {vno}"}

    @classmethod
    async def impact_analysis(cls, table_name: str) -> dict:
        """P1-② 影响分析：哪些指标用到此表 + 哪些字段/对象关联它。"""
        metrics = await cls.list_metrics(SYSTEM_DS)
        affected_metrics = [m for m in metrics if table_name in (m.get("sql_template") or "")]
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            cols = (await db.execute(_t(
                "SELECT column_name, related_table, related_field FROM ai_query_asset_columns "
                "WHERE related_table=:t AND is_deleted=false"), {"t": table_name})).fetchall()
        relations = [{"column": c[0], "from": c[1], "field": c[2]} for c in cols]
        objs = await cls.list_objects()
        obj_links = [o for o in objs if any(ln["target"] == table_name for ln in o.get("links", []))]
        return {
            "table": table_name,
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
        metrics = await cls.list_metrics(SYSTEM_DS)
        affected_metrics = [m for m in metrics
                            if any(t in (m.get("sql_template") or "") for t in all_tables)]
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

    @classmethod
    async def dq_rules_list(cls) -> list[dict]:
        metrics = await cls.list_metrics(SYSTEM_DS)
        return [dict(t) | {"on": bool(metrics)} for t in cls._DQ_RULE_TEMPLATES]

    @classmethod
    async def dq_rules_run(cls, table: str, column: str, rule_type: str) -> dict:
        """执行数据质量规则：非空率/唯一性。"""
        if rule_type == "not_null":
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                try:
                    total = (await db.execute(_t(f'SELECT COUNT(*) FROM "{table}"'))).scalar() or 0
                    nonnull = (await db.execute(_t(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NOT NULL'))).scalar() or 0
                except Exception:  # noqa: BLE001
                    return {"ok": False, "msg": f"无法校验表 {table} 字段 {column}"}
            rate = round(nonnull / total * 100, 1) if total else 100.0
            return {"ok": True, "rule": "not_null", "table": table, "column": column,
                    "total": total, "valid": nonnull, "pass_rate": rate, "passed": rate >= 99}
        if rule_type == "unique":
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                try:
                    total = (await db.execute(_t(f'SELECT COUNT(*) FROM "{table}"'))).scalar() or 0
                    uniq = (await db.execute(_t(f'SELECT COUNT(DISTINCT "{column}") FROM "{table}"'))).scalar() or 0
                except Exception:  # noqa: BLE001
                    return {"ok": False, "msg": f"无法校验表 {table} 字段 {column}"}
            rate = round(uniq / total * 100, 1) if total else 100.0
            return {"ok": True, "rule": "unique", "table": table, "column": column,
                    "total": total, "valid": uniq, "pass_rate": rate, "passed": rate >= 99}
        return {"ok": False, "msg": "不支持的规则类型"}

    @classmethod
    async def export_asset(cls, table_name: str, limit: int = 100) -> dict:
        """数据集导出：读取真实表数据用于导出（CSV/JSON 由前端生成下载）。"""
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            try:
                rows = (await db.execute(_t(
                    f'SELECT * FROM "{table_name}" LIMIT {max(1, min(int(limit), 500))}'))).fetchall()
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "msg": f"表不存在或无法读取：{e}"}
        cols = list(rows[0]._mapping.keys()) if rows else []
        data = [dict(r._mapping) for r in rows]
        return {"ok": True, "table": table_name, "columns": cols, "rows": data,
                "row_count": len(data)}

    @classmethod
    async def object_browse(cls, table_name: str, page: int = 1, page_size: int = 20) -> dict:
        """对象数据浏览器：分页读取真实表数据（前端表格浏览）。"""
        page = max(1, int(page)); page_size = max(1, min(int(page_size), 100))
        offset = (page - 1) * page_size
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            try:
                total = (await db.execute(_t(f'SELECT COUNT(*) FROM "{table_name}"'))).scalar() or 0
                rows = (await db.execute(_t(
                    f'SELECT * FROM "{table_name}" LIMIT {page_size} OFFSET {offset}'))).fetchall()
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "msg": f"表不存在或无法读取：{e}"}
        cols = list(rows[0]._mapping.keys()) if rows else []
        data = [dict(r._mapping) for r in rows]
        return {"ok": True, "table": table_name, "columns": cols, "rows": data,
                "page": page, "page_size": page_size, "total": int(total),
                "has_next": offset + page_size < int(total)}

    @classmethod
    async def _ensure_share_table(cls, db) -> None:
        from sqlalchemy import text as _t
        dialect = (db.bind.dialect.name if db.bind else "")
        if dialect == "postgresql":
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_dataset_share ("
                "id BIGSERIAL PRIMARY KEY, table_name VARCHAR(255), token VARCHAR(64), "
                "user_id INTEGER, is_deleted INTEGER DEFAULT 0, created_time TIMESTAMP)"))
        else:
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_dataset_share ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, token TEXT, "
                "user_id INTEGER, is_deleted INTEGER DEFAULT 0, created_time TEXT)"))

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
        """统一图谱统计：数据 schema 图节点/边 + 知识库图实体/关系。"""
        assets = await cls.list_assets()
        objs = [a for a in assets if a.get("object_enabled")]
        edges = 0
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                edges = (await db.execute(_t(
                    "SELECT COUNT(*) FROM ai_query_asset_columns "
                    "WHERE related_table IS NOT NULL AND related_table<>'' AND is_deleted=0"))).scalar() or 0
        except Exception:  # noqa: BLE001
            edges = 0
        entities = 0
        relations = 0
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                entities = (await db.execute(_t(
                    "SELECT COUNT(*) FROM ai_kg_entity WHERE is_deleted=0")).scalar() or 0)
                relations = (await db.execute(_t(
                    "SELECT COUNT(*) FROM ai_kg_relation WHERE is_deleted=0")).scalar() or 0)
        except Exception:  # noqa: BLE001
            entities = relations = 0
        return {"data_nodes": len(assets), "data_edges": int(edges),
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
    async def governance_report(cls) -> dict:
        """AIP 数据治理报告：聚合 治理总览 + 合规姿态 + 安全评分 + 护栏，生成可导出报告。"""
        from datetime import datetime

        from app.plugin.module_ai.overview.service import AiOverviewService
        try:
            gov = await cls.governance_overview()
        except Exception:  # noqa: BLE001
            gov = {}
        posture = await AiOverviewService.compliance_posture()
        guard = await cls.guardrails_status()
        dq = gov.get("dq", {})
        summary = [
            f"数据对象 {gov.get('objects', 0)} 个，数据源 {gov.get('datasources', 0)} 个，管道 {gov.get('pipelines', 0)} 条",
            f"ABAC 权限规则 {gov.get('access_rules', 0)} 条，数据域 {gov.get('domains', 0)} 个",
            f"数据质量平均 {dq.get('avg_score', 0)} 分，DQ 预警 {gov.get('dq_alerts', 0)} 条",
            f"合规姿态 {posture.get('score', 0)} 分（{posture.get('level', '')}）",
            f"安全护栏 {guard.get('enabled', 0)}/{guard.get('total', 0)} 项已启用（{guard.get('score', 0)}%）",
            f"待审批 {posture.get('pending_approvals', 0)} 项",
        ]
        overview = {
            "objects": gov.get("objects", 0), "datasources": gov.get("datasources", 0),
            "pipelines": gov.get("pipelines", 0), "actions": gov.get("actions", 0),
            "access_rules": gov.get("access_rules", 0), "domains": gov.get("domains", 0),
            "agents": gov.get("agents", 0), "metrics": gov.get("metrics", 0),
            "terms": gov.get("terms", 0), "concepts": gov.get("concepts", 0),
        }
        scores = {"compliance": posture.get("score", 0), "security": 0,
                  "guardrails": guard.get("score", 0)}
        try:
            scores["security"] = (await cls.security_audit()).get("score", 0)
        except Exception:  # noqa: BLE001
            pass
        markdown = "\n".join([
            "# AIStation 数据治理报告",
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 总览",
            *[f"- {s}" for s in summary],
            "",
            f"## 评分：合规 {scores['compliance']} / 安全 {scores['security']} / 护栏 {scores['guardrails']}",
        ])
        return {"generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "summary": summary, "overview": overview, "scores": scores,
                "markdown": markdown}

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
    async def semantic_extract_objects(cls) -> dict:
        """P1-③ 语义抽取/消歧：只把**真实业务实体**表（_ENTITY_TABLE 映射集）标记为业务对象，
        并把非业务表（内部/平台表）取消对象标记（收窄去噪）。"""
        business: set[str] = set().union(*_ENTITY_TABLE.values()) if _ENTITY_TABLE else set()
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
            alias = next((n for n, ts in _ENTITY_TABLE.items() if t in ts), t)
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
                            "synonyms": [n for n, ts in _ENTITY_TABLE.items() if t in ts]})
        return {"extracted": created, "narrowed": narrowed, "aliases": aliases}

    @classmethod
    async def industry_templates(cls) -> list[dict]:
        return [
            {"id": "isa95", "name": "制造业（ISA-95/IEC 62264）", "objects": [
                {"name": "设备", "desc": "生产设备/工位", "domain": "生产"},
                {"name": "工单", "desc": "制造工单/生产订单", "domain": "生产"},
                {"name": "批次", "desc": "生产批次/批号", "domain": "生产"},
                {"name": "物料", "desc": "原材料/半成品/成品", "domain": "物料"},
                {"name": "质量特性", "desc": "质量指标/判定标准", "domain": "质量"},
                {"name": "工艺路线", "desc": "工序/工艺路线", "domain": "工艺"},
                {"name": "班组/班次", "desc": "班组/班次/日历", "domain": "组织"},
            ]},
            {"id": "gmp", "name": "制药（GMP/ICH）", "objects": [
                {"name": "批记录", "desc": "生产批记录", "domain": "质量"},
                {"name": "工艺规程", "desc": "工艺规程/处方", "domain": "工艺"},
                {"name": "偏差", "desc": "偏差/变更/OOS", "domain": "质量"},
                {"name": "物料批次", "desc": "物料批次/追溯", "domain": "物料"},
                {"name": "清洁验证", "desc": "清洁/验证记录", "domain": "质量"},
            ]},
            {"id": "generic", "name": "通用业务", "objects": [
                {"name": "客户", "desc": "客户/客户主数据", "domain": "客户"},
                {"name": "订单", "desc": "销售/采购订单", "domain": "交易"},
                {"name": "产品", "desc": "产品/商品", "domain": "产品"},
                {"name": "供应商", "desc": "供应商主数据", "domain": "采购"},
            ]},
        ]

    @classmethod
    async def apply_industry_template(cls, template_id: str, auth) -> dict:
        tpl = next((t for t in await cls.industry_templates() if t["id"] == template_id), None)
        if not tpl:
            return {"ok": False, "msg": "模板不存在"}
        created = 0
        for obj in tpl["objects"]:
            d = {"name": obj["name"], "description": obj["desc"], "synonyms": "", "parent_name": "",
                 "domain": obj["domain"], "metric_key": "", "tables": []}
            await cls.upsert_concept(d, auth)
            created += 1
        return {"ok": True, "created": created, "template": tpl["name"]}

    @classmethod
    async def pipeline_graph(cls) -> dict:
        """数据管道(ELT)编排图：源表 → 管道 → 本体对象，返回 nodes/edges（number id 供 GraphCanvas）。"""
        pipes = await cls.list_pipelines()
        nodes: list[dict] = []
        edges: list[dict] = []
        idmap: dict[str, int] = {}

        def nid(key: str) -> int:
            if key not in idmap:
                idmap[key] = len(idmap) + 1
            return idmap[key]

        def add_node(key: str, name: str, etype: str) -> None:
            if key in idmap:
                return
            i = nid(key)
            nodes.append({"id": i, "name": name or "-", "etype": etype, "weight": 1})

        for p in pipes:
            src = f"src:{p.get('source_table')}"
            pipe = f"pipe:{p.get('name')}"
            tgt = f"obj:{p.get('target_object')}"
            add_node(pipe, p.get("name") or "管道", "pipeline")
            if p.get("source_table"):
                add_node(src, p["source_table"], "source")
                edges.append({"source": nid(src), "target": nid(pipe), "rtype": "to", "weight": 1})
            if p.get("target_object"):
                add_node(tgt, p["target_object"], "object")
                edges.append({"source": nid(pipe), "target": nid(tgt), "rtype": "writes", "weight": 1})
        return {"nodes": nodes, "edges": edges}

    @classmethod
    async def list_pipelines(cls) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            res = await db.execute(_t(
                "SELECT p.id,p.name,p.source_connection,p.source_table,p.target_object,p.mappings,p.enabled,"
                "(SELECT status FROM ai_pipeline_run r WHERE r.pipeline_id=p.id AND r.is_deleted=false ORDER BY r.id DESC LIMIT 1) AS last_status,"
                "(SELECT ran_at FROM ai_pipeline_run r WHERE r.pipeline_id=p.id AND r.is_deleted=false ORDER BY r.id DESC LIMIT 1) AS last_at "
                "FROM ai_pipeline p WHERE p.is_deleted=false ORDER BY p.id DESC"))
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "name": r[1] or "", "source_connection": r[2] or "", "source_table": r[3] or "",
            "target_object": r[4] or "",
            "mappings": r[5] if isinstance(r[5], list) else (_json.loads(r[5]) if r[5] else []),
            "enabled": bool(r[6]), "last_status": r[7] or "", "last_at": str(r[8]) if r[8] else "",
        } for r in rows]

    @classmethod
    async def upsert_pipeline(cls, data: dict) -> dict:
        import json as _json
        mp = _json.dumps(data.get("mappings") or [], ensure_ascii=False)
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            if data.get("id"):
                await db.execute(_t(
                    "UPDATE ai_pipeline SET name=:n, source_connection=:sc, source_table=:st, "
                    "target_object=:to, mappings=:m, enabled=:e, updated_time=now() WHERE id=:i"), {
                    "n": data.get("name", ""), "sc": data.get("source_connection", ""),
                    "st": data.get("source_table", ""), "to": data.get("target_object", ""),
                    "m": mp, "e": bool(data.get("enabled", True)), "i": data["id"]})
                return {"id": data["id"]}
            res = await db.execute(_t(
                "INSERT INTO ai_pipeline(name,source_connection,source_table,target_object,mappings,enabled) "
                "VALUES (:n,:sc,:st,:to,:m,:e) RETURNING id"), {
                "n": data.get("name", ""), "sc": data.get("source_connection", ""),
                "st": data.get("source_table", ""), "to": data.get("target_object", ""),
                "m": mp, "e": bool(data.get("enabled", True))})
            return {"id": res.scalar()}

    @classmethod
    async def run_pipeline(cls, pipeline_id: int) -> dict:
        """P3-⑤ 真实数据接入：从外部数据源/本系统拉取源表数据，按映射落库到目标对象表，并同步资产与运行血缘。

        source_connection 为数字 → 视为外部数据源 id（走 executor 真实连接拉数）；
        否则 / 空 → 视为本系统表。目标数据落到 ``ai_pipeline_data_{id}`` 运行物化表。
        """
        import json as _json
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            row = (await db.execute(_t(
                "SELECT name,source_connection,source_table,target_object,mappings FROM ai_pipeline "
                "WHERE id=:i AND is_deleted=false"), {"i": pipeline_id})).fetchone()
        if not row:
            return {"ok": False, "msg": "管道不存在"}
        name, sc, st, to, mp_raw = row[0], row[1], row[2], row[3], row[4]
        mappings = mp_raw if isinstance(mp_raw, list) else (_json.loads(mp_raw) if mp_raw else [])
        # 1) 拉取源数据
        try:
            if str(sc).strip().isdigit() and int(sc) > 0:
                ds = await _load_ds(int(sc))
                cfg = _ds_cfg_from_model(ds)
                from . import executor as _ex
                res = await _ex.execute_select(cfg, f'SELECT * FROM "{st}" LIMIT 200')
                src_cols, src_rows = res.get("columns") or [], res.get("rows") or []
                source_desc = f"{ds.name}({ds.type})"
            else:
                async with async_db_session() as db:
                    from sqlalchemy import text as _t
                    src = (await db.execute(_t(
                        f'SELECT * FROM "{st}" LIMIT 200'))).mappings().fetchall()
                src_cols = list(src[0].keys()) if src else []
                src_rows = [[str(v) if v is not None else None for v in r.values()] for r in src]
                source_desc = f"本系统 {st}"
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"拉取源数据失败：{str(e)[:120]}"}
        # 2) 按映射构建目标行
        col_idx = {c: i for i, c in enumerate(src_cols)}
        target_cols = [mp.get("target_col") or mp.get("source_col") for mp in mappings]
        target_rows: list[list] = []
        for r in src_rows:
            out = []
            for mp in mappings:
                s = mp.get("source_col", "")
                val = r[col_idx[s]] if s in col_idx else None
                out.append(val)
            target_rows.append(out)
        # 3) 物化到 ai_pipeline_data_{id}（全量刷新）
        materialized = 0
        try:
            async with async_db_session.begin() as db:
                from sqlalchemy import text as _t
                tname = f"ai_pipeline_data_{pipeline_id}"
                cols_ddl = ", ".join(f'"{c}" TEXT' for c in target_cols) if target_cols else ""
                await db.execute(_t(
                    f'CREATE TABLE IF NOT EXISTS "{tname}" (id BIGSERIAL PRIMARY KEY, {cols_ddl})'))
                await db.execute(_t(f'DELETE FROM "{tname}"'))
                for r in target_rows:
                    ph = ", ".join(f":c{i}" for i in range(len(r)))
                    cols_sql = ", ".join(f'"{c}"' for c in target_cols) if target_cols else ""
                    params = {f"c{i}": v for i, v in enumerate(r)}
                    await db.execute(_t(
                        f'INSERT INTO "{tname}" ({cols_sql}) VALUES ({ph})'), params)
                    materialized += 1
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"落库失败：{str(e)[:120]}"}
        # 3.5) 目标为本体对象 → 把数据同步进本体对象表 ont_{to}（数据与集成支撑本体）
        ont_synced = 0
        try:
            objs = await cls._ont_objs()
            if to in objs:
                ont_table = f"ont_{to}"
                props = await cls._ont_props(to)
                prop_codes = [p["code"] for p in props] or target_cols
                cols_ddl = ", ".join(f'"{c}" TEXT' for c in prop_codes)
                async with async_db_session.begin() as db:
                    from sqlalchemy import text as _t
                    await db.execute(_t(
                        f'CREATE TABLE IF NOT EXISTS "{ont_table}" (id BIGSERIAL PRIMARY KEY, {cols_ddl})'))
                    await db.execute(_t(f'DELETE FROM "{ont_table}"'))
                    for r in target_rows:
                        # 仅写入本体属性列
                        mapped = {tc: v for tc, v in zip(target_cols, r)}
                        ins_cols = [c for c in prop_codes if c in mapped]
                        if not ins_cols:
                            continue
                        ph = ", ".join(f":c{i}" for i in range(len(ins_cols)))
                        cols_sql = ", ".join(f'"{c}"' for c in ins_cols)
                        params = {f"c{i}": mapped[c] for i, c in enumerate(ins_cols)}
                        await db.execute(_t(
                            f'INSERT INTO "{ont_table}" ({cols_sql}) VALUES ({ph})'), params)
                        ont_synced += 1
        except Exception:  # noqa: BLE001
            ont_synced = 0
        # 4) 同步资产元数据（对象可见 + 映射目标列描述）
        meta = (await cls._asset_tmeta()).get(to) or {}
        try:
            await cls.upsert_asset(QueryAssetUpsert(
                table_name=to, alias=meta.get("alias") or to, domain=meta.get("domain") or "接入",
                description=meta.get("description") or f"由管道 {name} 接入", business_scenarios="",
                included=True, remark="", object_enabled=True, object_key_col="id",
                object_name_col="name", object_icon="el-icon-Connection"),
                SimpleNamespace(user=SimpleNamespace(id=1)))
            async with async_db_session.begin() as db:
                from sqlalchemy import text as _t
                for mp in mappings:
                    tgt = mp.get("target_col") or mp.get("source_col")
                    upd = await db.execute(_t(
                        "UPDATE ai_query_asset_columns SET description=:d WHERE table_name=:t AND column_name=:c AND is_deleted=false"),
                        {"t": to, "c": tgt, "d": f"自 {source_desc}.{st}#{mp.get('source_col')} 接入"})
                    if not (upd.rowcount or 0):
                        await db.execute(_t(
                            "INSERT INTO ai_query_asset_columns(table_name,column_name,description,included,is_deleted) "
                            "VALUES (:t,:c,:d,true,false)"), {"t": to, "c": tgt, "d": f"自 {source_desc}.{st}#{mp.get('source_col')} 接入"})
        except Exception:  # noqa: BLE001
            pass
        # 5) 记录运行
        msg = f"自 {source_desc}.{st} 拉取 {len(src_rows)} 行，落库 {materialized} 行到对象 {to}"
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            await db.execute(_t(
                "INSERT INTO ai_pipeline_run(pipeline_id,status,message,rows) VALUES (:p,'success',:m,:r)"),
                {"p": pipeline_id, "m": msg, "r": materialized})
        _SCHEMA_CACHE = None
        _ASSET_TMETA = None
        return {"ok": True, "msg": msg, "synced": len(mappings), "rows": materialized, "ont_synced": ont_synced}

    @classmethod
    async def pipeline_data(cls, pipeline_id: int, limit: int = 50) -> dict:
        """P3-⑤ 查看管道落库结果（物化表 ai_pipeline_data_{id}）。"""
        tname = f"ai_pipeline_data_{pipeline_id}"
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                res = await db.execute(_t(f'SELECT * FROM "{tname}" ORDER BY id DESC LIMIT :n'), {"n": limit})
                cols = list(res.keys())
                rows = [list(r) for r in res.fetchall()]
            return {"ok": True, "columns": cols, "rows": rows}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"暂无落库结果：{str(e)[:80]}"}

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
    async def workshop_submit(cls, app_id: int, data: dict) -> dict:
        """把表单数据写入对象表（仅限白名单对象，字段须属于应用配置的列）。"""
        async with async_db_session() as db:
            row = (await db.execute(
                text("SELECT object_table, columns FROM ai_workshop_app WHERE id=:i AND is_deleted=false"),
                {"i": app_id})).fetchone()
        if not row:
            raise CustomException(msg="应用不存在")
        table = row[0]
        if table not in cls._WORKSHOP_WRITABLE:
            raise CustomException(msg="该对象暂不支持表单写入")
        cols = row[1] if isinstance(row[1], list) else []
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
    async def upsert_workshop_app(cls, data: dict) -> dict:
        import json as _json
        cols = _json.dumps(data.get("columns") or [], ensure_ascii=False)
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            if data.get("id"):
                await db.execute(_t(
                    "UPDATE ai_workshop_app SET name=:n, object_table=:o, view_type=:v, columns=:c, "
                    "enabled=:e, updated_time=now() WHERE id=:i"), {
                    "n": data.get("name", ""), "o": data.get("object_table", ""),
                    "v": data.get("view_type", "table"), "c": cols, "e": bool(data.get("enabled", True)),
                    "i": data["id"]})
                return {"id": data["id"]}
            res = await db.execute(_t(
                "INSERT INTO ai_workshop_app(name,object_table,view_type,columns,enabled) "
                "VALUES (:n,:o,:v,:c,:e) RETURNING id"), {
                "n": data.get("name", ""), "o": data.get("object_table", ""),
                "v": data.get("view_type", "table"), "c": cols, "e": bool(data.get("enabled", True))})
            return {"id": res.scalar()}

    @classmethod
    async def workshop_preview(cls, app_id: int, limit: int = 50) -> dict:
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            row = (await db.execute(_t(
                "SELECT object_table, columns, view_type FROM ai_workshop_app WHERE id=:i AND is_deleted=false"),
                {"i": app_id})).fetchone()
        if not row:
            return {"ok": False, "msg": "应用不存在"}
        table = row[0]
        cols = row[1] if isinstance(row[1], list) else []
        select = ", ".join(f'"{c}"' for c in cols) if cols else "*"
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
        metrics = await cls.list_metrics(SYSTEM_DS)
        terms = await cls.list_terms(SYSTEM_DS)
        concepts = await cls.concepts_mapping()
        pipelines = await cls.list_pipelines()
        # 字段
        fields = [lab.split("(")[0] for lab in schema.get(table_name, [])]
        # 用到此表的指标
        mets = [{"key": m["key"], "name": m["name"]} for m in metrics if table_name in (m.get("sql_template") or "")]
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
        # 管道目标
        pips = [{"name": p["name"], "source": p["source_table"]} for p in pipelines if p["target_object"] == table_name]
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
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_data_lifetime "
                "(id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, retention_days INTEGER, enabled INTEGER DEFAULT 1, is_deleted INTEGER DEFAULT 0)"))
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
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_data_lifetime "
                "(id INTEGER PRIMARY KEY AUTOINCREMENT, table_name TEXT, retention_days INTEGER, enabled INTEGER DEFAULT 1, is_deleted INTEGER DEFAULT 0)"))
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
    async def _sql_query_scope(cls, sql: str) -> tuple[set[str], set[str]]:
        """用 sqlglot 精确解析查询涉及的表集与列名集；失败回退正则（不放过）。"""
        try:
            import sqlglot
            from sqlglot import exp as _exp

            parsed = sqlglot.parse_one(sql, read="postgres")
            tables = {t.name for t in parsed.find_all(_exp.Table)}
            cols = {c.name for c in parsed.find_all(_exp.Column)}
            return tables, cols
        except Exception:  # noqa: BLE001
            tables = set(re.findall(r"\b(?:from|join)\s+([A-Za-z_][A-Za-z0-9_]*)", sql or "", re.IGNORECASE))
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
    async def dq_run(cls, table_name: str) -> dict:
        """P3-⑦ 数据质量(DQ)：对业务对象扫描 完整性/唯一性/新鲜度 并打分落库。"""
        import json as _json
        objs = await cls.list_objects()
        obj = next((o for o in objs if o["table"] == table_name), None)
        if not obj:
            return {"ok": False, "msg": f"{table_name} 不是业务对象，暂不支持 DQ"}
        schema = await cls._system_schema()
        if table_name not in schema:
            return {"ok": False, "msg": f"{table_name} 不在可用 schema"}
        name_col, key_col = obj["name_col"], obj["key_col"]
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            total = (await db.execute(_t(f'SELECT count(*) FROM "{table_name}"'))).scalar() or 0
            name_null = name_distinct = key_distinct = None
            try:
                name_null = (await db.execute(_t(
                    f'SELECT count(*) FROM "{table_name}" WHERE "{name_col}" IS NULL'))).scalar() or 0
                name_distinct = (await db.execute(_t(
                    f'SELECT count(DISTINCT "{name_col}") FROM "{table_name}"'))).scalar() or 0
            except Exception:  # noqa: BLE001
                pass
            try:
                key_distinct = (await db.execute(_t(
                    f'SELECT count(DISTINCT "{key_col}") FROM "{table_name}"'))).scalar() or 0
            except Exception:  # noqa: BLE001
                pass
            fresh_ts = None
            for c in ("updated_time", "created_time"):
                try:
                    mv = (await db.execute(_t(f'SELECT max({c}) FROM "{table_name}"'))).scalar()
                    if mv:
                        fresh_ts = mv
                        break
                except Exception:  # noqa: BLE001
                    pass
        # 打分
        comp = round(100 - (name_null / total * 100) if total else 100, 1) if name_null is not None else 100
        if total and name_distinct is not None:
            uniq = round(name_distinct / total * 100, 1)
        elif total and key_distinct is not None:
            uniq = round(key_distinct / total * 100, 1)
        else:
            uniq = 100.0
        from datetime import datetime, timezone
        if fresh_ts:
            if fresh_ts.tzinfo is None:
                fresh_ts = fresh_ts.replace(tzinfo=timezone.utc)
            days = max(0, (datetime.now(timezone.utc) - fresh_ts).days)
            fresh = round(max(0.0, 100 - days * 5), 1)
        else:
            fresh = 0.0
        score = round(comp * 0.4 + uniq * 0.3 + fresh * 0.3, 1)
        issues = []
        if name_null is not None and total and name_null / total > 0.05:
            issues.append(f"名称列 {name_col} 空值率 {round(name_null / total * 100, 1)}%")
        if total and name_distinct is not None and name_distinct < total:
            issues.append(f"名称列 {name_col} 有 {total - name_distinct} 条重名")
        if total and key_distinct is not None and key_distinct < total:
            issues.append(f"主键列 {key_col} 不唯一（{total - key_distinct} 重复）")
        if fresh_ts is None:
            issues.append("无更新时间列，新鲜度未知")
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            await db.execute(_t(
                "UPDATE ai_dq_report SET is_deleted=true WHERE table_name=:t"), {"t": table_name})
            await db.execute(_t(
                "INSERT INTO ai_dq_report(table_name,alias,total,score,completeness,uniqueness,freshness,issues,checked_at) "
                "VALUES (:t,:a,:n,:s,:c,:u,:f,:i,now())"), {
                "t": table_name, "a": obj["alias"], "n": total, "s": score,
                "c": comp, "u": uniq, "f": fresh,
                "i": _json.dumps(issues, ensure_ascii=False)})
        return {"ok": True, "table": table_name, "alias": obj["alias"], "total": total,
                "score": score, "completeness": comp, "uniqueness": uniq, "freshness": fresh,
                "issues": issues}

    @classmethod
    async def dq_overview(cls) -> dict:
        """P3-⑦ DQ 总览：从 ai_dq_report 缓存读取（直接查对象表，避免慢路径与超时）。"""
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            obj_rows = (await db.execute(_t(
                "SELECT table_name, CAST(object_key_col AS VARCHAR), CAST(object_name_col AS VARCHAR) "
                "FROM ai_query_assets WHERE object_enabled=true AND is_deleted=false"))).fetchall()
            rep_rows = (await db.execute(_t(
                "SELECT table_name,alias,total,score,completeness,uniqueness,freshness,issues,checked_at "
                "FROM ai_dq_report WHERE is_deleted=false"))).fetchall()
        cache = {r[0]: {"alias": r[1], "total": r[2], "score": float(r[3]),
                        "completeness": float(r[4]), "uniqueness": float(r[5]),
                        "freshness": float(r[6]), "issues": r[7],
                        "checked_at": str(r[8]) if r[8] else ""} for r in rep_rows}
        results = []
        for r in obj_rows:
            t = r[0]
            results.append(cache.get(t, {"table": t, "alias": t, "total": 0, "score": 0,
                                         "completeness": 0, "uniqueness": 0, "freshness": 0,
                                         "issues": [], "checked_at": "", "scanned": False})
                           | {"table": t, "scanned": t in cache})
        scored = [x for x in results if x.get("scanned")]
        avg = round(sum((x["score"] or 0) for x in scored) / len(scored), 1) if scored else 0
        return {"avg_score": avg, "total_objects": len(results),
                "healthy": sum(1 for x in scored if (x["score"] or 0) >= 80),
                "risk": sum(1 for x in scored if (x["score"] or 0) < 60),
                "items": results}

    @classmethod
    async def dq_scan_all(cls) -> dict:
        """P3-⑦ 显式全量扫描全部业务对象。"""
        objs = await cls.list_objects()
        scanned = 0
        for o in objs:
            r = await cls.dq_run(o["table"])
            if r.get("ok"):
                scanned += 1
        return {"ok": True, "scanned": scanned, "msg": f"已扫描 {scanned} 个对象"}

    @classmethod
    async def dq_alert(cls) -> dict:
        """P3-⑧ DQ 预警 + 影响联动：风险对象(健康分<60) → 血缘下游影响(对象/指标/管道/概念)。"""
        ov = await cls.dq_overview()
        objs = {o["table"]: o for o in await cls._objects_light()}
        pipelines = await cls.list_pipelines()
        metrics = await cls.list_metrics()
        concepts = await cls.list_concepts()
        alerts = []
        for it in ov["items"]:
            if (it["score"] or 0) < 60:
                t = it["table"]
                async with async_db_session() as db:
                    from sqlalchemy import text as _t
                    deps = (await db.execute(_t(
                        "SELECT DISTINCT related_table FROM ai_query_asset_columns "
                        "WHERE related_table=:t AND is_deleted=false"), {"t": t})).fetchall()
                dep_objs = [objs.get(r[0], {}).get("alias") or r[0] for r in deps if r[0] and r[0] != t]
                rel_mets = [m["name"] for m in metrics if t in (m.get("sql_template") or "")]
                rel_pips = [p["name"] for p in pipelines if p["target_object"] == t]
                rel_concepts = [c["name"] for c in concepts if t in (c.get("tables") or [])]
                alerts.append({
                    "table": it["table"], "alias": it["alias"],
                    "score": it["score"], "issues": it["issues"] or [],
                    "downstream": {"objects": dep_objs, "metrics": rel_mets,
                                   "pipelines": rel_pips, "concepts": rel_concepts},
                })
        return {"count": len(alerts), "alerts": alerts}

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
        """数据域对账：校验各域 tables 引用的对象是否都已登记（未登记标出），保证域定义完整。"""
        domains = await cls.list_domains()
        try:
            schema = await cls._system_schema()
            known = set(schema.keys())
        except Exception:  # noqa: BLE001
            known = set(SYSTEM_ALLOWED_TABLES)
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
            metrics = await cls.list_metrics(SYSTEM_DS)
        except Exception:  # noqa: BLE001
            metrics = []
        try:
            pipes = await cls.list_pipelines()
        except Exception:  # noqa: BLE001
            pipes = []
        by_domain = {}
        for d in domains:
            tables = set(d["tables"] or [])
            dom_m = [{"key": m["key"], "name": m["name"]} for m in metrics
                     if tables and any(t in (m.get("sql_template") or "") for t in tables)]
            dom_p = [{"name": p.get("name"), "source": p.get("source_table"),
                      "target": p.get("target_object")} for p in pipes
                     if p.get("target_object") in tables]
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
        invalidate_ont_allow_cache()
        return {"ok": True, "object": table, "props": len(cols), "materialize": m}

    @classmethod
    async def import_ds_table_as_ontology(cls, datasource_id: int, table: str,
                                          domain_code: str = "") -> dict:
        """数据源连接器 → 本体对象：把外部数据源某张表结构自动生成本体对象（对象+属性+物化），连接器真正生根本体。

        ``domain_code`` 指定导入的目标域，写到对象 ``domain_code`` 列。
        """
        ds = await _load_ds(datasource_id)
        rules = ds.filter_rules or DEFAULT_FILTER_RULES
        records = await list_ds_schema(datasource_id)
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

        - ``tables`` 为空 → 导入该数据源已同步的全部表（默认排除 ``_ONT_IMPORT_EXCLUDE`` 纯技术表）
        - ``tables`` 指定 → 只导入给定表（取与已同步表的交集）
        - ``include_technical=True`` → 不排除纯技术表
        - ``domain_code`` → 批量导入的每张表统一写入的目标域
        """
        ds = await _load_ds(datasource_id)
        rules = ds.filter_rules or DEFAULT_FILTER_RULES
        records = await list_ds_schema(datasource_id)
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
            targets = [t for t in all_tables if t not in _ONT_IMPORT_EXCLUDE]

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
    async def _profile_table(cls, tname: str, colnames: list[str]) -> dict:
        """对表做轻量数据画像：行数 + 每列可空率/基数/低基数枚举分布。"""
        from sqlalchemy import text as _t

        profile: dict = {"table": tname, "rows": 0, "cols": {}}
        if not tname or not colnames:
            return profile
        try:
            async with async_db_session() as db:
                rc = (await db.execute(_t(f'SELECT COUNT(*) FROM "{tname}"'))).scalar() or 0
                profile["rows"] = int(rc)
                for c in colnames:
                    info: dict = {}
                    try:
                        row = (await db.execute(
                            _t(f'SELECT COUNT(*) FILTER (WHERE "{c}" IS NULL) AS nn, '
                                f'COUNT(DISTINCT "{c}") AS nd FROM "{tname}"')
                        )).fetchone()
                        nn = int(row[0] or 0)
                        nd = int(row[1] or 0)
                        info["null_pct"] = round(nn * 100.0 / rc, 1) if rc else 0
                        info["distinct"] = nd
                        if nd <= 12 and nd > 0:
                            vals = [
                                str(r[0]) for r in (await db.execute(
                                    _t(f'SELECT DISTINCT "{c}" FROM "{tname}" WHERE "{c}" IS NOT NULL LIMIT 12')
                                )).fetchall()
                            ]
                            info["values"] = vals[:12]
                    except Exception:  # noqa: BLE001
                        info = {}
                    profile["cols"][c] = info
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 画像失败 {tname}: {e}")
        return profile

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
    async def upsert_asset_column(cls, data, auth) -> dict:
        global _SEMANTIC_INDEX, _SCHEMA_CACHE
        async with async_db_session.begin() as db:
            from sqlalchemy import select

            # Task3：写枚举列前幂等补列
            await _ensure_marking_columns(db)
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
        _SEMANTIC_INDEX = None
        _SCHEMA_CACHE = None
        return {"table_name": data.table_name, "column_name": data.column_name}

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
    async def get_settings(cls) -> dict:
        defaults = {
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
            "enum_hint_enabled": "true",             # 是否注入枚举字段真实取值
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
            "object_query_call_timeout": "60",       # IR 生成单次 LLM 调用超时（秒）
            "object_query_max_traverse_depth": "1",  # traverse 最大跳数（P3：可开 2–3；默认 1=不启用多跳）
            # 为什么是 60：实测**裸调用** 11~19s，但经 agno Agent 包装后 17~32s（含波动）。
            # 给 30 会频繁超时降级（实测踩到，日志只有空字符串的 TimeoutError）；
            # 给 60 让绝大多数请求成功，真正的长尾再降级。
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
        """带进程级缓存的工程配置读取；save_setting 会使其失效。"""
        global _SETTINGS_CACHE
        if _SETTINGS_CACHE is None:
            _SETTINGS_CACHE = await cls.get_settings()
        return _SETTINGS_CACHE

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
        base: dict[str, list[str]] = {k: list(v) for k, v in _ENTITY_TABLE.items()}
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
    async def save_setting(cls, key: str, value: str, remark: str, auth) -> dict:
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
            from sqlalchemy import func, select

            total = (await db.execute(
                select(func.count()).select_from(AiQueryMessageModel)
                .where(AiQueryMessageModel.is_deleted.is_(False)))).scalar_one()
            fast = (await db.execute(
                select(func.count()).select_from(AiQueryMessageModel)
                .where(AiQueryMessageModel.is_deleted.is_(False),
                       AiQueryMessageModel.path == "fast"))).scalar_one()
            errors = (await db.execute(
                select(func.count()).select_from(AiQueryMessageModel)
                .where(AiQueryMessageModel.is_deleted.is_(False),
                       AiQueryMessageModel.is_error.is_(True)))).scalar_one()
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
        tables = await list_ds_schema(datasource_id)
        connector = next((c for c in await cls.connector_types() if c["type"] == d.type), None)
        asset_count = 0
        try:
            for a in await cls.list_assets():
                if (a.get("datasource_code") == _ds_code(datasource_id)
                        or a.get("datasource") == _ds_code(datasource_id)):
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
    async def preview_filter_rules(cls, datasource_id: int, rules: dict | None = None) -> dict:
        """筛选规则分类预览（只读）：对数据源已同步 schema 全量分类并汇总。

        - ``rules`` 为草稿规则（可传 ``None`` 用数据源已保存规则，再缺省用 ``DEFAULT_FILTER_RULES``）；
        - 不写库、不改变已保存规则；数据源不存在时由 ``_load_ds`` 抛 CustomException（直接透传）。
        """
        ds = await _load_ds(datasource_id)
        eff = rules if rules is not None else (ds.filter_rules or DEFAULT_FILTER_RULES)
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
    async def _llm_structured(cls, prompt: str, schema: type[BaseModel], *,
                              temperature: float = 0.2, max_tokens: int = 4000,
                              runtime: dict | None = None,
                              tag: str = "aistation-suggest") -> Any:
        """结构化输出：走 agno ``output_schema``，由模型侧 JSON schema 约束结果。

        相比「提示词里要求 JSON + 事后手工解析」（旧 ``_llm_json`` 路径），
        这里把结构约束交给模型服务端，返回**已校验**的 ``schema`` 实例。

        - ``runtime`` 为空时自行 ``_get_runtime()``（调用方已有 runtime 时可传入复用）；
        - 超时只在 agno **之外**用 ``asyncio.wait_for`` 兜底（agno 的 timeout 仅单次 HTTP）；
        - 网关不回原生结构时，兼容 dict / JSON 文本两种形态兜底解析。
        """
        from agno.agent import Agent
        from agno.models.openai.like import OpenAILike

        from app.plugin.module_ai.models.service import build_headers

        if runtime is None:
            try:
                runtime = await cls._get_runtime()
            except Exception as e:  # noqa: BLE001
                raise CustomException(msg=f"未配置可用的辅助模型：{e}")
        cfg = await cls._cfg()
        model = OpenAILike(
            id=runtime["model"], base_url=runtime["base_url"],
            api_key=runtime.get("api_key") or "sk-none",
            temperature=temperature, max_tokens=max_tokens, timeout=90,
            # 辅助任务只要结果，压住思考避免长尾（与 NL2SQL 的思考控制结论一致）
            extra_body={"reasoning_effort": "low"},
            default_headers=build_headers(
                runtime["base_url"], runtime.get("extra_headers"), tag),
        )
        agent = Agent(model=model, output_schema=schema, telemetry=False, markdown=False)
        try:
            resp = await asyncio.wait_for(
                agent.arun(prompt),
                timeout=cls._cfg_int(cfg, "nl2sql_call_timeout", 90),
            )
        except asyncio.TimeoutError:
            raise CustomException(msg="大模型辅助调用超时，请稍后重试")
        except Exception as e:  # noqa: BLE001
            raise CustomException(msg=f"大模型辅助调用失败：{str(e)[:200]}")
        content = getattr(resp, "content", None)
        if isinstance(content, schema):
            return content
        if content is None or (isinstance(content, str) and not content.strip()):
            # 实测：推理型模型可能把 max_tokens 全花在思考上，最终 content 为空
            raise CustomException(msg="大模型未返回结构化结果（思考可能耗尽输出预算，请重试或减小输入规模）")
        try:
            if isinstance(content, dict):
                return schema.model_validate(content)
            return schema.model_validate(cls._parse_llm_json(str(content)))
        except Exception as e:  # noqa: BLE001
            log.warning("[query] 结构化输出解析失败：{}｜模型原文：{}",
                        str(e)[:100], str(content)[:200])
            raise CustomException(msg=f"大模型返回结构不完整：{str(e)[:100]}")

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
    async def _ds_current_rules(cls, datasource_id: int, rules: dict | None) -> dict:
        """取当前规则上下文：``rules`` 显式非 None 时直接返回（免去多余 DB 查询）；
        否则用数据源已保存规则，缺省回落到 ``DEFAULT_FILTER_RULES``。"""
        if rules is not None:
            return rules
        try:
            ds = await _load_ds(datasource_id)
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

        统一 try/except：``list_ds_schema`` 失败（如数据源不存在/DB 异常）时优雅降级为
        空样例 ``([], [])``，不阻断大模型调用（suggest/parse/classify-advise 三处行为一致）。
        """
        try:
            schema = await list_ds_schema(datasource_id)
        except Exception:  # noqa: BLE001
            return [], []
        tables = [s["table"] for s in schema][:limit]
        fields = [
            c.get("name") or c.get("column_name")
            for s in schema for c in (s.get("columns") or []) if isinstance(c, dict)
        ][:limit]
        return tables, fields

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
    async def get_or_create_session(cls, session_id: int | None, title: str, auth) -> dict:
        async with async_db_session.begin() as db:
            if session_id:
                s = await db.get(AiQuerySessionModel, session_id)
                if s:
                    return {"id": s.id, "title": s.title, "datasource": s.datasource}
            user = getattr(getattr(auth, "user", None), "id", None)
            s = AiQuerySessionModel(
                user_id=user, tenant_id=None, title=title[:60] or "新会话",
                datasource=SYSTEM_DS, created_id=user, updated_id=user,
            )
            db.add(s)
            await db.flush()
            return {"id": s.id, "title": s.title, "datasource": s.datasource}

    @classmethod
    async def list_sessions(cls, auth) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import select

            rows = (
                await db.execute(
                    select(AiQuerySessionModel)
                    .where(AiQuerySessionModel.is_deleted.is_(False))
                    .order_by(AiQuerySessionModel.id.desc())
                    .limit(100)
                )
            ).scalars().all()
            return [
                {"id": s.id, "title": s.title, "datasource": s.datasource,
                 "created_time": s.created_time}
                for s in rows
            ]

    @classmethod
    def _ensure_session_owner(cls, sess: AiQuerySessionModel | None, auth) -> None:
        """会话归属校验。

        修复前 `list_messages` / `delete_session` **只按 id 查**，任何拿到
        ``module_ai:query:ask`` 权限的用户都能按 id 读到、删掉**别人的**问数历史
        （枚举 id 即可越权）。这里统一校验：归属人必须是当前用户；
        报「不存在」而不是「无权限」，避免暴露 id 的存在性。
        """
        if sess is None:
            raise CustomException(msg="会话不存在")
        if auth is None:
            return  # 内部调用（如问句重写读历史）无 HTTP 用户上下文；HTTP 边界一律传 auth
        owner = getattr(sess, "user_id", None)
        if owner is None:
            return  # 历史遗留数据（无归属），保持可访问
        uid = getattr(getattr(auth, "user", None), "id", None)
        if uid is None or int(owner) != int(uid):
            raise CustomException(msg="会话不存在")

    @classmethod
    async def list_messages(cls, session_id: int, auth=None) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import select

            cls._ensure_session_owner(await db.get(AiQuerySessionModel, session_id), auth)
            rows = (
                await db.execute(
                    select(AiQueryMessageModel)
                    .where(
                        AiQueryMessageModel.session_id == session_id,
                        AiQueryMessageModel.is_deleted.is_(False),
                    )
                    .order_by(AiQueryMessageModel.id)
                )
            ).scalars().all()
            return [cls._msg_dict(m) for m in rows]

    @classmethod
    async def delete_session(cls, session_id: int, auth=None) -> None:
        async with async_db_session.begin() as db:
            s = await db.get(AiQuerySessionModel, session_id)
            if s is None:
                return  # 已不存在：保持幂等，不因重复删除而报错
            cls._ensure_session_owner(s, auth)
            await db.delete(s)

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
    @classmethod
    async def report_suggest(cls, question: str, datasource: str | None = None) -> list[dict]:
        """按问题检索已确认启用的报表（澄清后选择，不自动执行，避免误命中/参数对不上）。"""
        try:
            async with async_db_session() as db:
                rows = (
                    await db.execute(
                        text(
                            "SELECT id,name,description,question,params FROM ai_report_template "
                            "WHERE is_deleted=false AND verified=true AND enabled=true AND datasource=:d "
                            "ORDER BY sort, id"
                        ),
                        {"d": datasource or "system"},
                    )
                ).fetchall()
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] report_suggest 拉取报表失败：{e!r}")
            return []
        if not rows:
            return []
        reports = []
        for r in rows:
            import json as _j

            params = r[4] if isinstance(r[4], list) else (_j.loads(r[4]) if r[4] else [])
            reports.append({"id": r[0], "name": r[1] or "", "description": r[2] or "",
                            "question": r[3] or "", "params": params})
        q = (question or "").lower().strip()
        if not q:
            return []
        scored = []
        for r in reports:
            name = (r.get("name") or "").lower()
            desc = (r.get("description") or "").lower()
            rq = (r.get("question") or "").lower()
            score = 0
            if name and (name in q or q in name):
                score += 4
            if rq and (rq in q or q in rq):
                score += 4
            if desc:
                for i in range(max(1, len(q) - 1)):
                    sub = q[i : i + 2]
                    if sub and sub in desc:
                        score += 1
            if score >= 3:
                scored.append({
                    "id": r["id"], "name": r["name"],
                    "description": r.get("description") or "",
                    "question": r.get("question") or "",
                    "params": len(r.get("params") or []),
                    "_score": score,
                })
        scored.sort(key=lambda x: -x["_score"])
        return scored[:3]

    @classmethod
    async def ask(cls, question: str, auth, session_id: int | None = None,
                  datasource: str | None = None, redis=None, force_slow: bool = False,
                  object_code: str | None = None, object_key: str | None = None) -> dict:
        """主入口：意图路由 → 快/慢路径 → 执行 → 落库。"""
        await cls.ensure_system_seed()
        question = (question or "").strip()
        datasource = await _norm_datasource(datasource)
        # 当前对象上下文：**确定性注入**（对齐 Palantir Retrieval Context）。
        # ⚠️ 每次调用都**显式设置**（没有对象时置空）——否则同一个任务里连续调用 ask
        #    （如评测逐题跑）会把上一题的上下文带进下一题。
        _OBJECT_CTX.set(await cls._object_context_block(object_code, object_key, auth))
        if not question:
            raise CustomException(msg="请输入要查询的问题")

        sess = await cls.get_or_create_session(session_id, question[:30], auth)

        # 评测强制慢路径：跳过模板匹配，直接用 LLM 生成 SQL。
        # 注意：这一步必须在加载指标/术语**之前** —— 旧实现先查了 metrics+terms，
        # 慢路径里 `_nl2sql` 又查一遍，等于白跑两次库。
        if force_slow:
            return await cls._slow_path(question, sess["id"], datasource or SYSTEM_DS, auth)

        # P2 多轮查询重写（G7）：把「那上周呢」补全为自包含问题，随后**重新走一遍路由**
        # （可能命中指标快路径 / 对象查询）。放在 force_slow 之后：评测逐题生成不应受
        # 历史重写影响，保持 A/B 公平。开关默认关，仅在判定不自包含时才多一次 LLM 调用。
        question = await cls._maybe_rewrite(question, sess["id"], datasource)

        metrics = await cls.list_metrics(datasource or None)
        terms = await cls.list_terms(datasource or None)

        # 澄清反问：命中**确定性歧义**（如「按原煤仓分组」而表里同时有名称/编号两列）
        # → 先问用户，不生成 SQL。猜错的成本远高于问一句。
        # 用户已回答（问句里带【澄清】）则跳过；每轮最多问一次。
        if "【澄清】" not in question:
            try:
                from .clarify import detect_clarify

                schema_map = (
                    await cls._system_schema()
                    if (datasource or SYSTEM_DS) == SYSTEM_DS
                    else await cls._ds_schema_map(datasource)
                )
                _c = detect_clarify(question, schema_map)
                if _c:
                    # 澄清这一轮也要**落库**：否则刷新后丢历史、会话标题不更新
                    try:
                        await cls._save_message(
                            sess["id"], question, path="clarify",
                            datasource=datasource or SYSTEM_DS, sql="", rows=[],
                            summary=_c.get("question") or "需要确认口径", is_error=False,
                        )
                    except Exception as e:  # noqa: BLE001
                        log.warning(f"[query] 澄清轮落库失败（忽略）: {str(e)[:100]}")
                    return {"path": "clarify", "clarify": _c, "question": question,
                            "is_error": False, "sql": "", "columns": [], "rows": [],
                            "took_ms": 0, "metric": None, "ontology_used": []}
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 澄清检测失败（忽略，继续正常问答）: {str(e)[:100]}")

        # 列举类问题不走指标模板（快路径只认指标聚合），强制走 NL2SQL
        if not _is_listing_question(question):
            try:
                _concepts = await cls.list_concepts()
            except Exception:  # noqa: BLE001
                _concepts = []
            metric = _match_metric(question, metrics, terms, _concepts)
            # 「每个/各/按X分组」是**分组诉求**：单值指标答不了 →
            # 除非命中本身就是「分组型」指标（agg=group），否则让位给慢路径。
            # 实测 bug：问「统计每个摄像头的告警数量」被 alert_count_today 抢答成
            # 「今日告警数=0」，语义完全错。
            if metric and metric.get("agg") != "group" and _wants_grouping(question):
                log.warning(
                    "[query] 分组诉求，跳过单值指标快路径：metric={} question={}",
                    metric.get("key"), question[:40],
                )
                metric = None
        else:
            metric = None
        if metric:
            params = _build_params(metric, question)
            try:
                cache_key, cached, res = None, False, None
                ttl = metric.get("cache_ttl") or 0
                if redis and ttl:
                    # 安全补丁：缓存 key 必须含调用者 —— 指标结果是按权限算的
                    cache_key = cls._cache_key(
                        metric, params,
                        user_id=getattr(getattr(auth, "user", None), "id", None))
                    hit = await cls._cache_get(redis, cache_key)
                    if hit is not None:
                        res, cached = hit, True
                if res is None:
                    res = await _execute_metric(metric, params, auth)
                    if redis and ttl and cache_key:
                        await cls._cache_set(redis, cache_key, res, ttl)
                msg = await cls._save_message(
                    sess["id"], question, path="fast", datasource=metric["datasource"],
                    sql=res["sql"], columns=res["columns"], rows=res["rows"],
                    result_rows=len(res["rows"]), took_ms=res.get("took_ms", 0), cached=cached,
                    summary=cls._summarize(metric, res),
                )
                return cls._answer(msg, metric=metric)
            except Exception as e:  # noqa: BLE001
                # 快路径**任何**失败（含驱动异常）都不得整题崩溃 → 记录错误并回退慢路径。
                # 早期只 catch CustomException，裸 ProgrammingError 会直接冒泡（实测 ds:4）。
                reason = getattr(e, "msg", None) or str(e)
                await cls._save_message(
                    sess["id"], question, path="fast", datasource=metric["datasource"],
                    sql=metric["sql_template"], rows=[], is_error=True,
                    summary=f"快路径执行失败：{reason}",
                )
                return await cls._slow_path(question, sess["id"], metric["datasource"], auth)

        # 报表建议（澄清后选择）：未命中指标时，把相关已确认报表作为候选推荐，不自动执行。
        # 放在对象查询前：沉淀的"困难题"比现推更贴近用户意图；关键词命中率高才推荐（防误命中）。
        try:
            sugg = await cls.report_suggest(question, datasource or None)
            if sugg:
                return {"path": "report_suggest", "question": question, "reports": sugg,
                        "is_error": False, "sql": "", "columns": [], "rows": [],
                        "took_ms": 0, "metric": None, "ontology_used": []}
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 报表建议失败（忽略，继续对象/NL2SQL）: {str(e)[:100]}")

        # 对象查询（语义执行层）：LLM 出 IR → 本体实例层执行；任何失败自动降级
        cfg = await cls._cfg()
        if cls._cfg_bool(cfg, "object_query_enabled", False):
            try:
                ans = await cls._object_query_path(
                    question, sess["id"], datasource or SYSTEM_DS, auth,
                    object_code=object_code, object_key=object_key)
                if ans:
                    return ans
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 对象查询异常，降级 NL2SQL：{str(e)[:120]}")

        # 慢路径
        return await cls._slow_path(question, sess["id"], datasource or SYSTEM_DS, auth)

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
    async def _execute_one(cls, sql: str, datasource: str, auth) -> dict:
        if datasource and datasource != SYSTEM_DS:
            ds_id = int(datasource.split(":")[-1])
            return await _execute_custom_ds_sql(ds_id, sql, auth)
        # 复用本体的行级/列级权限：把本体对象支撑表改写成"已过滤的子查询"。
        # 问数是**任意形状的读**（聚合/分组/join），外面套 WHERE 是错的——
        # 过滤必须在聚合之前，所以这里做子查询改写。
        secured = await _secure_ont_sql(sql, auth)
        if secured.get("deny"):
            raise CustomException(msg=secured["msg"])
        # 安全补丁（2026-10-19）：字段级 ACL 必须在**共同执行出口**生效，且 fail-closed。
        # 修前只在 ask_stream 里调过一次且包着 ``except: pass`` —— 非流式 ask 走的
        # 慢路径根本没调它；而且检查一炸就等于没做，受限字段会被原样查出来。
        uid = getattr(getattr(auth, "user", None), "id", None)
        try:
            violations = await cls._ont_sql_violations(sql, uid)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 字段级 ACL 检查失败，拒绝执行：{e}")
            raise CustomException(
                msg=f"字段级权限校验失败，已拒绝执行：{str(e)[:120]}") from e
        if violations:
            raise CustomException(
                msg=f"字段级权限：无权限访问 {', '.join(violations)}（本体属性级 ACL）")
        return await _execute_sql(secured["sql"])

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
    async def _ir_llm(cls, prompt: str, runtime: dict) -> str:
        """一次 LLM 调用生成对象查询 IR（复用 agno，与 NL2SQL 同源）。

        模型解析走 ``_get_runtime()``：``usage`` 精确匹配优先（query → chat → 默认），
        因此这里用的就是「模型配置」里那个默认 chat 模型（本项目为 LLM-284B-MXFP4）。
        """
        import asyncio as _asyncio

        from agno.agent import Agent
        from agno.models.openai.like import OpenAILike

        from app.plugin.module_ai.models.service import build_headers

        cfg = await cls._cfg()
        model = OpenAILike(
            id=runtime["model"], base_url=runtime["base_url"],
            api_key=runtime.get("api_key") or "sk-none",
            # ⚠️ 必须用带下限的预算：本机模型是**推理型**，thinking 计入 max_tokens，
            # 预算太小会被思考吃光 → finish_reason=length、正文为空（实测 1200 就会空）。
            # 可用 `object_query_max_tokens` 单独调大（默认沿用 NL2SQL 的预算）。
            temperature=0.0,
            max_tokens=cls._cfg_int(cfg, "object_query_max_tokens", nl2sql_max_tokens(cfg)),
            timeout=60,
            # 思考压到 low：实测**原始调用** A(enable_thinking=false)=19.0s ｜
            # B(reasoning_effort=low)=10.9s ｜ C(默认)=17.8s —— low 最快，故用 low。
            # ⚠️ 注意 agno 包装会额外耗时（裸调用 11~19s，经 Agent 后 17~32s），
            #    所以下面的 wait_for 超时必须留足余量（见 object_query_call_timeout 的说明）。
            extra_body={"reasoning_effort": "low"},
            default_headers=build_headers(
                runtime["base_url"], runtime.get("extra_headers"), "aistation-query-ir"),
        )
        agent = Agent(model=model, telemetry=False, instructions=prompt)

        async def _call() -> str:
            resp = await _asyncio.wait_for(
                agent.arun("请严格按上面的格式只输出对象查询 JSON。"),
                timeout=cls._cfg_int(cfg, "object_query_call_timeout", 60),
            )
            return (getattr(resp, "content", "") or "").strip()

        out = await _call()
        if not out:
            # 偶发空正文（推理型模型把预算用在 thinking / 网关抖动）：**重试一次**。
            # 空正文必然降级 NL2SQL，重试成本远低于降级成本。
            log.warning("[query] IR 首次空正文，重试一次")
            try:
                out = await _call()
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] IR 重试失败 [{type(e).__name__}]: {str(e)[:100]}")
                out = ""
        return out

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
    async def _object_query_path(cls, question: str, session_id: int, datasource: str,
                                 auth, object_code: str | None = None,
                                 object_key: str | None = None) -> dict | None:
        """对象查询路径：LLM 出 IR → 本体实例层执行。

        **任何环节失败都返回 ``None``**（由调用方降级 NL2SQL）——
        绝不因新路径失败而答不出来。返回 ``None`` 的时机：
        非系统库 / 无可用对象 / 无可用模型 / IR 生成失败 / 校验不通过 / 执行失败。
        """
        from app.plugin.module_ai.ontology import security as _ont_sec

        from . import object_query as oq
        from .object_exec import execute_ir

        cfg = await cls._cfg()
        max_objs = cls._cfg_int(cfg, "object_query_max_objects", 8)

        # 指标字典（供 IR 提示词注入 / 校验收敛 / 绑定型指标执行）
        try:
            metrics_list = await cls.list_metrics(datasource)
        except Exception:  # noqa: BLE001
            metrics_list = []
        metrics_map = {m["key"]: m for m in metrics_list}
        # 检索优化（S4）：问题命中某个指标时，把其对象排到最前并显式建议用 metric
        try:
            matched = _match_metric(
                question, metrics_list, await cls.list_terms(datasource),
                await cls.list_concepts())
        except Exception:  # noqa: BLE001
            matched = None

        # 对象白名单：系统库按授权过滤，自定义数据源按对象归属过滤（S2 放开）
        allowed = await cls._allowed_objects_for_query(
            question, auth, max_objects=max_objs, datasource=datasource,
            prefer_object=(matched or {}).get("object_code"))
        allowed = _prioritize_metric_object(allowed, matched)
        # 「当前对象」即使没被检索命中，也**强制进词表并排在最前**：
        # 用户已经明确站在这个对象上提问，不该因为召回没命中就查不了它。
        if object_code:
            if object_code not in allowed:
                spec = await cls._object_spec_for(object_code)
                if spec:
                    allowed[object_code] = spec
            if object_code in allowed:
                allowed = {object_code: allowed[object_code],
                           **{k: v for k, v in allowed.items() if k != object_code}}
        if not allowed:
            log.warning("[query] 对象查询：没有可用（已物化且授权）的对象，降级 NL2SQL")
            return None

        try:
            runtime = await cls._ir_runtime()
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 对象查询：无可用模型 {str(e)[:100]}")
            return None

        try:
            text = await cls._ir_llm(
                _metric_prompt_hint(matched)
                + oq.render_ir_prompt(question, allowed, max_objects=max_objs,
                                      max_traverse_depth=cls._cfg_int(
                                          cfg, "object_query_max_traverse_depth", 1),
                                      metrics=metrics_map),
                runtime)
        except Exception as e:  # noqa: BLE001
            # ⚠️ 必须打**异常类型**：TimeoutError 的 str(e) 是空串，只打 message 时
            #    日志里会是"IR 生成失败 "，完全看不出是超时（实测踩到，排查了半天）。
            log.warning("[query] 对象查询：IR 生成失败 [{}] {}", type(e).__name__, str(e)[:120])
            return None

        # 留痕：模型原始输出（问数排查时这是唯一能定位"模型到底给了什么"的地方）
        log.warning("[OQ] IR 原始输出={}", (text or "")[:800])

        parsed = oq.parse_ir(text)
        if (parsed is not None and object_key and not parsed.object_key
                and oq._resolve_object(parsed.object, allowed) == object_code):
            # 当前对象就是用户问的那个 → 把实例主键补进 IR（单对象读取 / 关系跳转需要它）
            parsed.object_key = str(object_key)
        ir, reasons = oq.validate_ir(
            parsed, allowed,
            max_traverse_depth=cls._cfg_int(cfg, "object_query_max_traverse_depth", 1),
            metrics=metrics_map)
        if not ir:
            log.warning("[query] 对象查询未通过校验，降级 NL2SQL：{}", "；".join(reasons[:3]))
            return None

        uid = getattr(getattr(auth, "user", None), "id", None)
        try:
            principal = await _ont_sec.load_principal(uid)
        except Exception:  # noqa: BLE001
            principal = None
        res = await execute_ir(ir, principal, metrics=metrics_map)
        if not res.get("ok"):
            log.warning("[query] 对象查询执行失败，降级 NL2SQL：{}", res.get("error"))
            return None

        cols = res.get("columns") or []
        rows = res.get("rows") or []
        retrieved = await cls._recall_grounding(question, SYSTEM_DS)
        msg = await cls._save_message(
            session_id, question, path="object", datasource=SYSTEM_DS,
            sql="", columns=cols, rows=rows, result_rows=len(rows),
            summary=cls._summarize_rows(cols, rows),
            grounding={"ir": ir.to_dict(), "ir_reasons": reasons, "retrieved": retrieved},
        )
        ans = cls._answer(msg, sql="", retrieved=retrieved)
        ans["ir"] = ir.to_dict()
        ans["object_query"] = {
            "shape": res.get("shape"), "note": res.get("note") or "", "reasons": reasons,
        }
        # 前端「本体对象」标签用（对象查询没有 SQL，故手动补）
        ans["ontology_used"] = [ir.object]
        # message_id：前端反馈按钮按 v-if="m.id" 门控（与快/慢路径对齐）
        ans["message_id"] = msg.id
        # 热度驱动自动建索引：**放在答案构造之后**，且自带 try —— 绝不能影响这次问答
        try:
            await cls._maybe_auto_index(ir.object, cfg)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 自动索引判定失败（忽略）: {str(e)[:100]}")
        log.warning("[query] 对象查询命中：object={} shape={} rows={}",
                    ir.object, res.get("shape"), len(rows))
        return ans

    @classmethod
    async def _slow_path(cls, question: str, session_id: int, datasource: str, auth) -> dict:
        """生成 SQL（带 SQL 缓存）→ EXPLAIN 代价护栏 → 按身份执行 → 失败自纠错。

        **慢的地方只有"生成"这一步**（一次 LLM 调用），执行只要几十毫秒。
        所以这里缓存**生成的 SQL**，重复提问直接跳过 LLM。
        结果行**绝不缓存**——行级/列级策略在执行时下推，缓存结果会串权限。
        """
        cfg = await cls._cfg()
        n = cls._cfg_int(cfg, "self_consistency_n", 1)
        cost_enabled = cls._cfg_bool(cfg, "query_cost_enabled", True)
        max_rows = cls._cfg_int(cfg, "query_cost_max_rows", 50000)
        last_err: str | None = None
        sql = ""
        cached_sql = _sql_cache_get(question, datasource)
        cache_used = bool(cached_sql)
        # 阶段计时：问数是"慢"被投诉的功能，必须能一眼看出时间花在哪
        t_start = time.perf_counter()
        t_gen = t_start
        t_exec = t_start
        for attempt in range(2):
            candidate_sqls: list[str] = []
            if cached_sql and attempt == 0:
                # 缓存命中：跳过生成（这是"快"的主要来源）
                candidate_sqls = [cached_sql]
            else:
                try:
                    for i in range(max(n, 1)):
                        # 自一致性：不同候选用不同温度增加多样性
                        temp = round(0.2 * i, 2) if n > 1 else 0.0
                        candidate_sqls.append(
                            await cls._nl2sql(question, datasource, prev_error=last_err, temperature=temp, auth=auth)
                        )
                except CustomException as e:
                    last_err = e.msg
                    # 模型偶发**返回空**（实测本地 284B 会这样）：原样重试基本没用，
                    # 给一条可操作的提示才有意义——否则白等两轮（实测 28 秒）。
                    if "未生成有效的查询语句" in (e.msg or ""):
                        last_err = ("你上次**没有返回任何 SQL**。请只输出一条 SELECT 语句，"
                                    "不要输出解释、不要输出空内容。")
                    log.warning(f"[query] NL2SQL 生成/校验失败第 {attempt + 1} 轮: {e.msg}")
                    continue
            t_gen = time.perf_counter()
            # 逐一执行；代价护栏过滤超重查询；结果一致性分组取多数
            groups: dict = {}
            results: list[tuple[str, dict]] = []
            for csql in candidate_sqls:
                try:
                    if cost_enabled and datasource in (SYSTEM_DS, None):
                        try:
                            er = await cls._explain_rows(csql)
                        except CustomException as e:
                            last_err = e.msg
                            continue
                        except Exception as e:  # noqa: BLE001
                            # EXPLAIN 失败说明候选 SQL 不合法（如引用了不存在的列/表），跳过该候选
                            last_err = f"SQL 校验失败：{e}"
                            continue
                        if er > max_rows:
                            last_err = f"查询代价过高(预计{er}行>上限{max_rows})，请改为聚合/加条件/限制范围"
                            continue
                    res = await cls._execute_one(csql, datasource, auth)
                    results.append((csql, res))
                    sig = tuple(sorted(tuple(str(v) for v in r) for r in res["rows"]))
                    groups.setdefault(sig, []).append(csql)
                except CustomException as e:
                    last_err = e.msg
                except Exception as e:  # noqa: BLE001
                    last_err = f"执行失败：{e}"
            if results:
                t_exec = time.perf_counter()
                # 优先非空结果；多数一致组内取第一候选；全空则按多数
                if any(c[1]["rows"] for c in results):
                    nonempty_ids = {c for c, res in results if res["rows"]}
                    base = max((g for g in groups.values() if set(g) & nonempty_ids), key=len)
                    sql = base[0]
                else:
                    sql = max(groups.values(), key=len)[0]
                res = next(r for (c, r) in results if c == sql)
                # 缓存里的 SQL 执行失败（schema/口径变了）→ 清掉缓存，下一轮重新生成。
                # 不这么做的话，一条坏 SQL 会被反复命中，变成"越缓存越慢还查不出东西"。
                if cache_used and attempt == 0 and not res["rows"]:
                    _SQL_CACHE.pop(_sql_cache_key(question, datasource), None)
                    cached_sql, cache_used = None, False
                    last_err = "上一轮查询返回结果为空，可能是条件/表/字段选择不准确，请检查后再重新生成一条 SQL。"
                    continue
                # 执行反馈自纠错：结果为空且还有重试机会 → 携带空结果提示二次生成
                if not res["rows"] and attempt == 0 and cls._cfg_bool(cfg, "empty_self_correct", True):
                    last_err = "上一轮查询返回结果为空，可能是条件/表/字段选择不准确，请检查后再重新生成一条 SQL。"
                    continue
                # 结果自校验：占比合计/累计单调/排名范围/分组行数 —— 可疑就**带具体错因**重试一次
                if attempt == 0 and cls._cfg_bool(cfg, "empty_self_correct", True):
                    try:
                        from .selfcheck import format_issue, run_selfcheck

                        _iss = run_selfcheck(
                            question, res.get("columns") or [], res.get("rows") or []
                        )
                        if _iss:
                            last_err = ("上一次结果看起来有问题：" + format_issue(_iss)
                                        + "。请修正后重新只返回一条 SQL。")
                            log.warning(f"[query] 自校验命中，重试一次：{format_issue(_iss)}")
                            continue
                    except Exception as e:  # noqa: BLE001
                        log.warning(f"[query] 自校验失败（忽略）: {str(e)[:100]}")
                # 生成成功才入缓存（失败/空的 SQL 不入，避免污染）
                _sql_cache_set(question, datasource, sql)
                # 结果列头中文化 + 一句人话的答案（原先摘要是硬编码废话）
                cn_cols = await cls._cn_columns(res["columns"], sql)
                res["columns"] = cn_cols
                summary = cls._summarize_rows(cn_cols, res["rows"])
                # 收尾阶段单独计时：这一步里有两个"重"调用（再次检索 + DQ 概览），
                # 缓存命中时生成阶段为 0，若收尾仍慢就会吃掉缓存的收益
                t_tail = time.perf_counter()
                retrieved = await cls._recall_grounding(question, datasource)
                grounding = {"retrieved": retrieved, "ontology_used": _scan_ont_tables(sql)}
                msg = await cls._save_message(
                    session_id, question, path="slow", datasource=datasource,
                    sql=sql, columns=res["columns"], rows=res["rows"],
                    result_rows=len(res["rows"]), took_ms=res.get("took_ms", 0),
                    cached=cache_used,
                    summary=summary, grounding=grounding,
                )
                ans = cls._answer(msg, sql=sql, retrieved=retrieved)
                ans["dq_warning"] = await cls._dq_warning_for_sql(sql)
                log.warning(
                    "[query] 计时 缓存命中={} 生成={:.0f}ms 执行={:.0f}ms 收尾={:.0f}ms 总计={:.0f}ms",
                    cache_used, (t_gen - t_start) * 1000, (t_exec - t_gen) * 1000,
                    (time.perf_counter() - t_tail) * 1000,
                    (time.perf_counter() - t_start) * 1000)
                return ans
        await cls._save_message(
            session_id, question, path="slow", datasource=datasource,
            sql=sql, rows=[], is_error=True, summary=f"查询失败：{last_err}",
        )
        return {"path": "slow", "is_error": True, "answer": f"查询失败：{last_err}", "sql": sql}

    @classmethod
    async def _plan_llm(cls, prompt: str, runtime: dict, temperature: float = 0.0) -> str:
        """计划阶段的一次 LLM 调用（只出 JSON 计划，不写 SQL）。统一走 agno。

        用 agno ``output_schema``（模型原生 JSON schema）约束计划结构，
        返回规范化后的计划 JSON 文本，交由 ``plan.parse_plan`` 解析与表名过滤。
        """
        out = await cls._llm_structured(
            prompt, PlanOut, temperature=temperature,
            max_tokens=nl2sql_max_tokens(None), runtime=runtime,
            tag="aistation-query-plan")
        return json.dumps(out.model_dump(), ensure_ascii=False)

    @classmethod
    async def _resolve_dialect_info(cls, datasource: str) -> tuple[dict, str]:
        """按数据源字符串解析方言配置。

        返回 ``(dialect配置, 数据源类型)``。``datasource`` 取值：
        - ``system`` / ``None`` → PostgreSQL；
        - ``ds:{id}`` → 读该数据源模型的 ``type``（postgres/mysql/sqlite/file/api）；
        - 其它 / 读取失败 → 回退 PostgreSQL（不报错，避免因方言问题整题失败）。

        纯逻辑解析在 ``dialect.resolve_dialect`` 里做；此处只负责「数据源字符串 →
        数据源类型」这一段，本文件已用 ``_ds_cfg_from_model`` 统一暴露类型。
        """
        from .dialect import resolve_dialect

        cfg = await cls._cfg()
        if not cls._cfg_bool(cfg, "multi_dialect_enabled", True):
            # 开关关闭：回到旧的「统一 PostgreSQL 提示词」行为。
            return resolve_dialect("postgres"), "postgres"
        if not datasource or datasource == SYSTEM_DS:
            return resolve_dialect("postgres"), "postgres"
        if str(datasource).startswith("ds:"):
            try:
                _id = int(str(datasource).split(":")[-1])
                _ds = await _load_ds(_id)
                _t = (_ds_cfg_from_model(_ds).get("type") or "postgres")
                return resolve_dialect(_t), _t
            except Exception as e:  # noqa: BLE001
                log.warning("[query] 读取数据源方言失败，回退 PostgreSQL：[{}] {}",
                            type(e).__name__, str(e)[:80])
                return resolve_dialect("postgres"), "postgres"
        return resolve_dialect("postgres"), "postgres"

    @classmethod
    async def _nl2sql(cls, question: str, datasource: str, prev_error: str | None = None,
                      temperature: float = 0.0, auth=None) -> str:
        """Agno Agent 生成 SQL（慢路径）。prev_error 为上一次执行报错，用于自纠错。"""
        try:
            runtime = await cls._get_runtime()
        except Exception as e:  # noqa: BLE001
            raise CustomException(msg=f"未配置可用的问答模型：{e}")
        metrics = await cls.list_metrics(datasource or None)
        terms = await cls.list_terms(datasource or None)
        t_p0 = time.perf_counter()
        schema_ctx = await cls._build_schema_context(question, datasource, metrics, terms)
        t_p1 = time.perf_counter()
        # 留痕：prompt 体积。生成耗时几乎全在 prefill 上，prompt 一大就慢，
        # 所以这个数字必须可见（实测全量倾倒时 37K 字符 → 生成 7s）
        log.warning("[query] prompt 长度={} 字符（schema 构建={}ms）",
                    len(schema_ctx), int((t_p1 - t_p0) * 1000))
        cfg = await cls._cfg()
        # 两段式分解：**多步题先出执行计划**（可检查的中间产物），再据计划写 SQL。
        # 失败即**降级**为单段生成（绝不因计划失败而答不出来）。
        # ⚠️ 独立开关、**默认关**：实测对个别题会把 SQL 变空（prompt 变长 + 模型只输出计划），
        #    必须先用留出法 A/B 验证再决定是否默认开启。
        if cls._cfg_bool(cfg, "two_stage_planning", False):
            try:
                from .plan import format_plan, is_multistep, parse_plan, plan_prompt

                if is_multistep(question):
                    # 必须把**真实表清单**给第一段：它看不到 schema，不给词表就只能编表名，
                    # 而编出来的名字会被第二段当成计划执行 → 毒先验（实测 −7.55 分 + 错误率 +9.4%）。
                    _sch = await cls._ds_schema_map(datasource or "")
                    _plan_text = await cls._plan_llm(
                        plan_prompt(question, tables=list(_sch.keys())), runtime, temperature
                    )
                    _plan = parse_plan(_plan_text)
                    # 约束：只保留**在真实 schema 里**的表；编出来的直接丢掉（宁可降级，不可毒化）
                    if _plan:
                        _ok_tables = [t for t in (_plan.get("tables") or []) if t in _sch]
                        if not _ok_tables:
                            _plan = None
                            log.warning("[query] 两段式：计划里的表名全都不在 schema 中，丢弃计划")
                        else:
                            _plan["tables"] = _ok_tables
                    if _plan:
                        schema_ctx = schema_ctx + "\n\n" + format_plan(_plan)
                        log.warning("[query] 两段式：计划已生成（表 {} 张）",
                                    len(_plan.get("tables") or []))
                    else:
                        log.warning("[query] 两段式：计划解析失败，降级为单段生成")
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 计划阶段失败，降级为单段生成: {str(e)[:100]}")
        rules = []
        if cls._cfg_bool(cfg, "entity_name_rule", True):
            rules.append("（1）问题要求按实体（摄像头/设备/算法/数据集/规则等）展示时，"
                         "应 JOIN 对应表用其「name」列，而不是直接返回外键 id；")
        if cls._cfg_bool(cfg, "enum_hint_enabled", True):
            rules.append("（2）status/framework/severity/task_type 等枚举字段必须使用【取值】里给出的原始值；")
        rules.append("（3）占比用“COUNT(*) * 100.0 / 总数”或“FILTER (WHERE ...)”计算；")
        rules.append("（4）多行 SQL 直接换行输出即可，不要加注释。")
        rules.append("（5）**所有聚合列和计算列必须起中文别名**（如 COUNT(*) AS 告警数、"
                     "SUM(amount) AS 销售额），不要用 c / count / total 这类占位名——"
                     "用户会直接看到列头。")
        if cls._cfg_bool(cfg, "decomposed_planning", True):
            rules.append("（6）先判断问题属于「单表聚合 / 多表联查 / 嵌套子查询」，再按此规划生成 SQL；")
        extra = ""
        if cls._cfg_bool(cfg, "full_entity_no_limit", True):
            extra = ("注意：问题若要求列出/统计全量实体（每个摄像头/每台设备/每个数据集/每类…），"
                     "不要为了省事写 LIMIT 截断，应返回全部（系统最多保留 1000 行）。\n")
        _dialect, _ds_type = await cls._resolve_dialect_info(datasource)
        system_prompt = build_system_prompt(
            _dialect, rules, schema_ctx, extra + templated_note(_ds_type))
        user_msg = question
        if prev_error:
            user_msg = (
                f"{question}\n\n注意：你上次的 SQL 存在问题：\n{prev_error}\n"
                "请修正 SQL（补全 FROM、改用正确表/列名、修正条件）后重新只返回一条 SQL。"
            )
        try:
            from agno.agent import Agent
            from agno.models.openai.like import OpenAILike

            from app.plugin.module_ai.models.service import build_headers

            # 必须注入网关请求头：opencode 网关要求 `x-opencode-session`，
            # 缺了它会直接返回一段错误文本，而那段文本会被当成 SQL 去校验，
            # 最终表现为「仅允许 SELECT 查询」——完全看不出真实原因。
            # 本文件其它两处（embedding / 检索）都用了 build_headers，这里漏了。
            # 思考长度控制（关键）：模型是**推理型**，thinking **计入 max_tokens**。
            # 之前把 max_tokens 从 2000 提到 8000（为了不被推理吃光而返回空 SQL），
            # 等于给了思考 8000 token 的预算 → 难题会想到**几分钟**（实测最长 467 秒）。
            # 实测同一难题：无限制 22.3s ｜ reasoning_effort=low 4.6s ｜ enable_thinking=false 3.8s
            # 现在把"思考"与"SQL 输出"**分开控制**：SQL 输出仍给足空间，思考被压住。
            _thinking = str(cfg.get("nl2sql_thinking_mode") or "low").strip().lower()
            _extra: dict = {}
            if _thinking == "off":
                _extra = {"enable_thinking": False}
            elif _thinking == "on":
                _extra = {}          # 完全不限制（会重现长尾，仅用于排查）
            else:
                _extra = {"reasoning_effort": "low"}   # 默认：保留少量思考
            model = OpenAILike(
                id=runtime["model"], base_url=runtime["base_url"],
                api_key=runtime["api_key"] or "sk-none",
                temperature=temperature, max_tokens=nl2sql_max_tokens(cfg),
                # 超时兜底：本地模型偶发长时间不返回 / 返回空。没有超时会把一次
                # 问答拖到几十秒（实测 32 秒换一个错误，是最差的体验）。
                timeout=60,
                extra_body=_extra or None,
                default_headers=build_headers(
                    runtime["base_url"], runtime.get("extra_headers"), "aistation-query"),
            )
            # 默认**关掉工具往返**：实测每题触发 ~7.25 次工具调用，每次都是一轮
            # LLM 往返；而工具能提供的信息（表结构 / 枚举值 / few-shot / join 路径 /
            # 代价护栏 / 执行校验）本地检索与本地执行已全覆盖——花 7 次往返去
            # "自主检索"是纯亏。执行反馈自纠错仍在（_slow_path 的 attempt 循环
            # 会带真实报错重新生成）。
            tool_agent = cls._cfg_bool(cfg, "agno_tool_agent", False)
            if tool_agent:
                # 工具化 Agent：让模型自主决定何时调用 schema/fewshots/cost 工具
                # （执行层不再叠加额外执行工具，避免重复；schema/fewshot 由模型自主检索）
                from .agno_query_tools import QUERY_TOOLS

                agent = Agent(
                    model=model,
                    telemetry=False,
                    tools=list(QUERY_TOOLS),
                    tool_call_limit=6, instructions=(
                        f"你是 {dialect_name(_dialect)} 数据库查询助手，生成只读 SELECT。"
                        "先调用 search_schema(question) 获取相关表/字段，必要时再调用 "
                        "get_fewshots(question) 参考样例、check_cost(候选SQL) 评估代价；"
                        "获取足够上下文后，生成一条 SELECT SQL；若对字段/关联/枚举不确定，可用 "
                        "resolve_value / find_join_path 确认；"
                        "最终消息必须输出 JSON：{\"sql\": \"<生成的 SELECT SQL>\"}。"
                        "禁止 DELETE/UPDATE/INSERT/DDL。\n注意："
                        + "".join(rules)
                    ),
                )
            else:
                agent = Agent(model=model, telemetry=False, instructions=system_prompt)
            t_llm0 = time.perf_counter()
            # 硬上限：agno 的 model 虽有 timeout=60，但那只是**单次 HTTP** 的超时；
            # agno 内部还可能重试/多段请求，叠起来能把一道题拖到 467 秒（实测）。
            # 在 agno **之外**用 wait_for 兜底，保证单次问答的 agno 阶段有天花板。
            resp = await asyncio.wait_for(
                agent.arun(user_msg),
                timeout=cls._cfg_int(cfg, "nl2sql_call_timeout", 90),
            )
            log.warning("[NL2SQL] agno 阶段耗时={}ms（占 生成 计时的比例见上一条计时行）",
                        int((time.perf_counter() - t_llm0) * 1000))
            # 留痕：模型原始输出。问数失败时这是唯一能定位"模型到底给了什么"的地方
            log.warning("[NL2SQL] 原始输出={}", (resp.content or "")[:500])
            sql = cls._extract_sql((resp.content or "").strip())
            table = await cls._allowed_for_user(auth) if datasource in (SYSTEM_DS, None) else None
            try:
                return validate_sql(sql, table or set(), question)
            except Exception:
                # 工具化模式若模型未取到 schema 导致校验失败，回退到提示版完整上下文重新生成
                if not tool_agent:
                    raise
                fallback = Agent(model=model, telemetry=False, instructions=system_prompt)
                resp2 = await fallback.arun(user_msg)
                sql2 = cls._extract_sql((resp2.content or "").strip())
                return validate_sql(sql2, table or set(), question)
        except Exception as e:  # noqa: BLE001
            raise CustomException(msg=f"问答模型(Agno)调用失败：{e}")

    @classmethod
    async def ask_stream(cls, question: str, auth, session_id: int | None = None,
                         datasource: str | None = None, object_code: str | None = None,
                         object_key: str | None = None) -> None:
        """流式问数：产出思考过程/工具调用/输出/最终结果的事件（作为 SSE 下发）。

        事件类型：meta / ir / reasoning_start / reasoning / reasoning_done /
        tool_start / tool_result / tool_error / sql_delta / sql_final /
        result / done / error / answer。
        """
        from .agno_query_tools import QUERY_TOOLS

        await cls.ensure_system_seed()
        question = (question or "").strip()
        if not question:
            yield {"type": "error", "message": "请输入要查询的问题"}
            return
        datasource = await _norm_datasource(datasource)
        # 当前对象上下文：与 ask() 同款，**显式设置**（每次调用都覆盖，避免串题）
        _OBJECT_CTX.set(await cls._object_context_block(object_code, object_key, auth))
        sess = await cls.get_or_create_session(session_id, question[:30], auth)
        datasource = datasource or SYSTEM_DS
        yield {"type": "meta", "session_id": sess["id"], "datasource": datasource,
               "question": question}

        # P2 多轮重写（G7）：把追问补全为自包含问题，随后**重新走路由**（对象查询 / 流式
        # NL2SQL）。meta 已带原始问题，这里只影响后续生成。开关默认关。
        question = await cls._maybe_rewrite(question, sess["id"], datasource)

        # ---- 澄清反问：命中确定性歧义 → 先问用户，不生成 SQL（对齐非流式 ask）----
        if "【澄清】" not in question:
            try:
                from .clarify import detect_clarify

                schema_map = (
                    await cls._system_schema()
                    if (datasource or SYSTEM_DS) == SYSTEM_DS
                    else await cls._ds_schema_map(datasource)
                )
                _c = detect_clarify(question, schema_map)
                if _c:
                    yield {"type": "clarify", "clarify": _c}
                    yield {"type": "done", "path": "clarify", "session_id": sess["id"]}
                    return
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 流式澄清检测失败（忽略）: {str(e)[:80]}")

        # ---- 指标快路径（对齐 ask）：确定性、零 LLM；命中即流式返回 ----
        if not _is_listing_question(question):
            try:
                metrics = await cls.list_metrics(datasource)
                terms = await cls.list_terms(datasource)
                try:
                    _concepts = await cls.list_concepts()
                except Exception:  # noqa: BLE001
                    _concepts = []
                metric = _match_metric(question, metrics, terms, _concepts)
                if metric and metric.get("agg") != "group" and _wants_grouping(question):
                    metric = None
                if metric:
                    params = _build_params(metric, question)
                    res = await _execute_metric(metric, params, auth)
                    # 摘要本地算一次即可：_save_message 返回的是 ORM 模型（没有 .get()），
                    # 之前写成 msg.get("summary") → AttributeError → 被 except 吞掉后
                    # **降级走 NL2SQL**，但消息已经提交入库 → 一次提问落 2 条历史消息、
                    # 快路径占比统计被污染（单测当时把 _save_message mock 成 dict 了，所以没发现）。
                    summary = cls._summarize(metric, res)
                    msg = await cls._save_message(
                        sess["id"], question, path="fast", datasource=metric["datasource"],
                        sql=res["sql"], columns=res["columns"], rows=res["rows"],
                        result_rows=len(res["rows"]), took_ms=res.get("took_ms", 0),
                        summary=summary)
                    yield {"type": "result", "path": "fast",
                           "columns": res["columns"], "rows": res["rows"],
                           "summary": summary, "message_id": msg.id}
                    yield {"type": "done", "path": "fast", "session_id": sess["id"]}
                    return
            except Exception as e:  # noqa: BLE001
                # 快路径失败**不得中断 SSE** → 记录并继续走对象/NL2SQL 流式
                log.warning("[query] 流式指标快路径失败，降级：[{}] {}",
                            type(e).__name__, str(e)[:120])

        # ---- 报表建议（澄清后选择）：未命中指标时推荐相关报表，不自动执行、不打断 SSE ----
        try:
            sugg = await cls.report_suggest(question, datasource or None)
            if sugg:
                yield {"type": "report_suggest", "reports": sugg}
                yield {"type": "done", "path": "report_suggest", "session_id": sess["id"]}
                return
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 流式报表建议失败（忽略）：{e!r}")

        # ---- 对象查询（语义执行层）：能出合法 IR 就流式返回，否则继续 NL2SQL 流式 ----
        cfg0 = await cls._cfg()
        if cls._cfg_bool(cfg0, "object_query_enabled", False):
            try:
                ans = await cls._object_query_path(
                    question, sess["id"], datasource, auth,
                    object_code=object_code, object_key=object_key)
            except Exception as e:  # noqa: BLE001
                log.warning("[query] 流式对象查询异常，降级 NL2SQL：[{}] {}",
                            type(e).__name__, str(e)[:120])
                ans = None
            if ans:
                yield {"type": "ir", "ir": ans.get("ir") or {},
                       "object_query": ans.get("object_query") or {},
                       "confidence": ans.get("confidence")}
                yield {"type": "result", "path": "object",
                       "columns": ans.get("columns") or [], "rows": ans.get("rows") or [],
                       "summary": ans.get("summary") or "",
                       "ontology_used": ans.get("ontology_used") or [],
                       "message_id": ans.get("message_id")}
                yield {"type": "done", "path": "object", "session_id": sess["id"],
                       "message_id": ans.get("message_id")}
                return

        # ---- 构建生成 Agent（与 _nl2sql 工具化模式一致） ----
        try:
            runtime = await cls._get_runtime()
        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "message": f"未配置可用的问答模型：{e}"}
            return
        cfg = await cls._cfg()
        rules = []
        if cls._cfg_bool(cfg, "entity_name_rule", True):
            rules.append("（1）问题要求按实体（摄像头/设备/算法/数据集/规则等）展示时，"
                         "应 JOIN 对应表用其「name」列，而不是直接返回外键 id；")
        if cls._cfg_bool(cfg, "enum_hint_enabled", True):
            rules.append("（2）status/framework/severity/task_type 等枚举字段必须使用【取值】里给出的原始值；")
        rules.append("（3）占比用“COUNT(*) * 100.0 / 总数”或“FILTER (WHERE ...)”计算；")
        rules.append("（4）多行 SQL 直接换行输出即可，不要加注释。")
        rules.append("（5）**所有聚合列和计算列必须起中文别名**（如 COUNT(*) AS 告警数、"
                     "SUM(amount) AS 销售额），不要用 c / count / total 这类占位名——"
                     "用户会直接看到列头。")
        if cls._cfg_bool(cfg, "decomposed_planning", True):
            rules.append("（6）先判断问题属于「单表聚合 / 多表联查 / 嵌套子查询」，再按此规划生成 SQL；")
        extra = ""
        if cls._cfg_bool(cfg, "full_entity_no_limit", True):
            extra = ("注意：问题若要求列出/统计全量实体（每个摄像头/每台设备/每个数据集/每类…），"
                     "不要为了省事写 LIMIT 截断，应返回全部（系统最多保留 1000 行）。\n")
        schema_ctx = await cls._build_schema_context(question, datasource,
                                                     await cls.list_metrics(datasource),
                                                     await cls.list_terms(datasource))
        _dialect, _ds_type = await cls._resolve_dialect_info(datasource)
        system_prompt = build_system_prompt(
            _dialect, rules, schema_ctx, extra + templated_note(_ds_type))

        from agno.agent import Agent
        from agno.models.openai.like import OpenAILike

        from app.plugin.module_ai.models.service import build_headers

        model = OpenAILike(
            id=runtime["model"], base_url=runtime["base_url"],
            api_key=runtime["api_key"] or "sk-none",
            temperature=0.0, max_tokens=nl2sql_max_tokens(cfg),
            timeout=60,
            default_headers=build_headers(
                runtime["base_url"], runtime.get("extra_headers"), "aistation-query"),
        )
        if cls._cfg_bool(cfg, "agno_tool_agent", False):
            agent = Agent(
                model=model, telemetry=False,
                tools=list(QUERY_TOOLS), tool_call_limit=6,
                instructions=(
                    f"你是 {dialect_name(_dialect)} 数据库查询助手，生成只读 SELECT。"
                    "先调用 search_schema(question) 获取相关表/字段，可再用 "
                    "semantic_search(question) 做向量语义检索、table_metadata(表) 查看元数据标注、"
                    "get_fewshots(question) 参考样例、check_cost(候选SQL) 评估代价；"
                    "获取足够上下文后，最终消息必须直接输出一条 SELECT SQL（不要调用工具、不要多余解释）。"
                    "禁止 DELETE/UPDATE/INSERT/DDL。\n注意：" + "".join(rules)
                ),
            )
        else:
            agent = Agent(model=model, telemetry=False, instructions=system_prompt)

        # ---- 流式运行 Agent，转发思考/工具/输出事件 ----
        content_buf: list[str] = []
        final_content = ""
        sql = ""
        try:
            async for ev in agent.arun(question, stream=True, stream_events=True):
                etype = getattr(ev, "event", "")
                if etype == "RunStarted":
                    yield {"type": "run_start"}
                elif etype == "ReasoningStarted":
                    yield {"type": "reasoning_start"}
                elif etype == "ReasoningContentDelta":
                    yield {"type": "reasoning", "delta": getattr(ev, "reasoning_content", "") or ""}
                elif etype == "ReasoningStep":
                    yield {"type": "reasoning", "delta": getattr(ev, "reasoning_content", "") or getattr(ev, "content", "") or ""}
                elif etype == "ReasoningCompleted":
                    yield {"type": "reasoning_done"}
                elif etype == "ToolCallStarted":
                    tool = getattr(ev, "tool", None)
                    yield {"type": "tool_start",
                           "name": getattr(tool, "tool_name", ""), "call_id": getattr(tool, "tool_call_id", ""),
                           "args": getattr(tool, "tool_args", None)}
                elif etype == "ToolCallCompleted":
                    tool = getattr(ev, "tool", None)
                    yield {"type": "tool_result",
                           "name": getattr(tool, "tool_name", ""),
                           "call_id": getattr(tool, "tool_call_id", ""),
                           "result": getattr(tool, "result", None) or getattr(ev, "content", None)}
                elif etype == "ToolCallError":
                    tool = getattr(ev, "tool", None)
                    yield {"type": "tool_error",
                           "name": getattr(tool, "tool_name", ""), "error": getattr(ev, "error", "") or str(getattr(ev, "content", ""))}
                elif etype == "RunContent":
                    rc = getattr(ev, "reasoning_content", None)
                    if rc:
                        yield {"type": "reasoning", "delta": str(rc)}
                    c = getattr(ev, "content", None)
                    if c:
                        content_buf.append(str(c))
                        yield {"type": "sql_delta", "delta": str(c)}
                elif etype == "RunContentCompleted":
                    yield {"type": "sql_done"}
                elif etype == "RunCompleted":
                    c = getattr(ev, "content", None)
                    if c:
                        final_content = str(c)
                    rc = getattr(ev, "reasoning_content", None)
                    if rc:
                        yield {"type": "reasoning_done"}
                elif etype == "RunError":
                    yield {"type": "error", "message": str(getattr(ev, "content", ""))}
                    return
        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "message": f"问答模型(Agno)调用失败：{e}"}
            return

        # ---- 提取并校验 SQL ----
        sql_source = "".join(content_buf) if content_buf else (final_content or "")
        sql = cls._extract_sql(sql_source)
        table = await cls._allowed_for_user(auth) if datasource in (SYSTEM_DS, None) else None
        try:
            sql = validate_sql(sql, table or set())
        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "message": f"SQL 校验失败：{e}"}
            return
        yield {"type": "sql_final", "sql": sql}

        # ---- 执行并返回结果 ----
        # 本体字段级 ACL：已下沉到 `_execute_one`（ask 与 ask_stream 的共同出口）
        # 统一执行且 fail-closed。修前这里是**唯一**调用点，却包着 `except: pass`
        # ⇒ 检查一炸就等于没做，受限字段被原样查出来；非流式 ask 更是完全不走这里。
        try:
            res = await cls._execute_one(sql, datasource, auth)
            cols = res.get("columns") or []
            rows = res.get("rows") or []
            # Grounding **必须落库**（非流式 ask 一直有写，流式漏了）：
            # 否则刷新/重开会话后「召回的表 / 本体对象」标签就消失了。
            retrieved = await cls._recall_grounding(question, datasource)
            ont_used = _scan_ont_tables(sql)
            msg = await cls._save_message(
                sess["id"], question, path="slow", datasource=datasource,
                sql=sql, columns=cols, rows=rows,
                result_rows=len(rows), took_ms=res.get("took_ms", 0), cached=False,
                summary="以下是根据你的问题生成的结果：",
                grounding={"retrieved": retrieved, "ontology_used": ont_used},
            )
            # message_id 必须回传：前端「有用/没用/存为报表/沉淀为指标」按钮按
            # v-if="m.id" 门控，不带 id 用户就必须刷新/点开旧会话才看得到。
            yield {"type": "result", "columns": cols, "rows": rows, "result_rows": len(rows),
                   "retrieved": retrieved, "ontology_used": ont_used, "message_id": msg.id,
                   "dq_warning": await cls._dq_warning_for_sql(sql)}
            yield {"type": "answer", "summary": "以下是根据你的问题生成的结果："}
            yield {"type": "done", "message_id": msg.id}
        except Exception as e:  # noqa: BLE001
            await cls._save_message(sess["id"], question, path="slow", datasource=datasource,
                                    sql=sql, rows=[], is_error=True, summary=f"查询失败：{e}")
            yield {"type": "error", "message": f"查询失败：{e}"}
            return

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

    @classmethod
    async def _system_schema(cls) -> dict:
        """拉取系统可查表的真实列（带类型）+ 资产目录筛选/中文描述。

        仅纳入数据资产目录中 included 的表/字段；字段有中文描述时附加，敏感字段标注。
        未同步资产目录时回退到内置白名单。结果缓存到进程级。
        """
        global _SCHEMA_CACHE
        if _SCHEMA_CACHE is not None:
            return _SCHEMA_CACHE
        # 1) 资产目录（已纳入的表 + 字段描述/敏感）
        async with async_db_session() as db:
            from sqlalchemy import select as _sel

            asset_rows = (
                await db.execute(
                    _sel(AiQueryAssetModel).where(
                        AiQueryAssetModel.included.is_(True),
                        AiQueryAssetModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
            col_rows = (
                await db.execute(
                    _sel(AiQueryAssetColumnModel).where(
                        AiQueryAssetColumnModel.included.is_(True),
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                    )
                )
            ).scalars().all()
        if asset_rows:
            tables = {a.table_name for a in asset_rows}
        else:
            tables = set(SYSTEM_ALLOWED_TABLES)
        colmap = {(c.table_name, c.column_name): c for c in col_rows}
        # 2) 拉真实列类型
        async with async_db_session() as db:
            from sqlalchemy import text as _text

            result = await db.execute(
                _text(
                    "SELECT table_name, column_name, data_type "
                    "FROM information_schema.columns "
                    "WHERE table_schema='public' ORDER BY table_name, ordinal_position"
                )
            )
            rows = result.fetchall()
        schema: dict[str, list[str]] = {}
        coltype: dict[tuple[str, str], str] = {}
        for t, c, ty in rows:
            if t not in tables:
                continue
            coltype[(t, c)] = (ty or "").lower()
            label = f"{c}({ty})"
            ac = colmap.get((t, c))
            if ac and ac.description:
                label += f"【{ac.description}】"
            if ac and ac.related_table and ac.related_field:
                label += f"【关联:{ac.related_table}.{ac.related_field}】"
            if ac and ac.sensitive:
                label += "[敏感]"
            schema.setdefault(t, []).append(label)
        # 3) 低基数枚举列：注入真实取值，帮助 LLM 使用正确枚举值（如 status=ERROR/RUNNING/STOPPED）
        try:
            cfg = await cls._cfg()
            if not cls._cfg_bool(cfg, "enum_hint_enabled", True):
                _SCHEMA_CACHE = schema
                return schema
            _enum_re = re.compile(
                r"(^|_)(status|framework|severity|task_type|kind|usage|scene_type|state|result|level|format|stream_type)$",
                re.IGNORECASE,
            )
            from sqlalchemy import text as _text2

            async with async_db_session() as db:
                # 人工维护的字段枚举优先（ai_query_asset_columns.enum）：人工枚举 > 真实库 DISTINCT
                manual_enum: dict = {}
                try:
                    from sqlalchemy import select as _sel2

                    _rows = (
                        await db.execute(
                            _sel2(
                                AiQueryAssetColumnModel.table_name,
                                AiQueryAssetColumnModel.column_name,
                                AiQueryAssetColumnModel.enum,
                            ).where(AiQueryAssetColumnModel.is_deleted.is_(False))
                        )
                    ).all()
                    for _tn, _cn, _ev in _rows:
                        _vs = _ev if isinstance(_ev, list) else (json.loads(_ev) if _ev else [])
                        if _vs:
                            manual_enum[(_tn, _cn)] = [str(x) for x in _vs]
                except Exception:  # noqa: BLE001
                    manual_enum = {}
                for t, labels in list(schema.items()):
                    for i, lab in enumerate(labels):
                        c = lab.split("(")[0]
                        if not _enum_re.search(c):
                            continue
                        # 跳过 json/jsonb/text/数组等高基数/大字段，避免把大段数据写入 prompt
                        if coltype.get((t, c)) in {
                            "json", "jsonb", "text", "bytea", "character varying[]",
                            "jsonb[]", "uuid",
                        }:
                            continue
                        # 人工维护的枚举优先，其次回退真实库 DISTINCT
                        _me = manual_enum.get((t, c))
                        if _me:
                            labels[i] = lab + f"【取值:{','.join(_me[:16])}】"
                            continue
                        try:
                            vals = await db.execute(
                                _text2(
                                    f'SELECT DISTINCT "{c}" AS v FROM "{t}" '
                                    f'WHERE "{c}" IS NOT NULL LIMIT 16'
                                )
                            )
                            vs = [str(r[0]) for r in vals.fetchall() if r[0] is not None]
                            if vs:
                                labels[i] = lab + f"【取值:{','.join(vs)}】"
                        except Exception:  # noqa: BLE001
                            continue
        except Exception:  # noqa: BLE001
            pass

        # 4) 字段关联增强：外键列标注「关联目标表的名称列」，帮助模型 JOIN 后直接 SELECT 名称
        def _name_col_of(rt: str) -> str | None:
            cols = [c for (t, c) in coltype if t == rt]
            for cand in ("name", "title", "label", "camera_name", "algorithm_name", "dataset_name", "device_name"):
                if cand in cols:
                    return cand
            for cand in cols:
                if coltype.get((rt, cand)) in {"character varying", "varchar", "text"}:
                    return cand
            return None

        for _t, _labels in schema.items():
            for _i, _lab in enumerate(_labels):
                _c = _lab.split("(")[0]
                _ac = colmap.get((_t, _c))
                if not (_ac and _ac.related_table and _ac.related_field):
                    continue
                _name_col = _name_col_of(_ac.related_table)
                if _name_col and _name_col != _c:
                    _labels[_i] = _lab + f"➜{_ac.related_table}.{_name_col}"

        _SCHEMA_CACHE = schema
        return schema

    @classmethod
    async def _semantic_index(cls) -> list | None:
        """把表/列/指标/术语编码成向量索引（进程级缓存，仅首次构建）。"""
        global _SEMANTIC_INDEX
        if _SEMANTIC_INDEX is not None:
            return _SEMANTIC_INDEX
        schema = await cls._system_schema()
        metrics = await cls.list_metrics(SYSTEM_DS)
        terms = await cls.list_terms(SYSTEM_DS)
        units: list[dict] = []
        for t in schema:
            units.append({"text": f"数据表 {t}", "tables": {t}})
            for col in schema[t]:
                cname = col.split("(")[0]
                units.append({"text": f"表 {t} 的字段 {cname}", "tables": {t}})
        for m in metrics:
            units.append(
                {"text": f"统计指标 {m['name']}：{m['description']}", "tables": _tables_in_sql(m.get("sql_template", ""))}
            )
        for tm in terms:
            units.append(
                {"text": f"业务术语 {tm['term']} 对应 {tm.get('metric_key') or tm.get('field_path')}", "tables": set()}
            )
        try:
            from app.plugin.module_ai.knowledge.embedding import embed_texts

            vecs = await embed_texts([u["text"] for u in units], model_id=await cls._embedding_mid())
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] schema 向量化失败，退化为关键字: {e}")
            return []
        if not vecs:
            return []
        _SEMANTIC_INDEX = [
            {"text": u["text"], "tables": u["tables"], "vector": v}
            for u, v in zip(units, vecs, strict=False)
        ]
        return _SEMANTIC_INDEX

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
    async def _ensure_vector_table(cls) -> None:
        """确保 pgvector 资产向量表存在（vector 扩展需已启用）。

        HNSW 索引上限 2000 维，本库 2560 维 → 用顺序余弦扫描（数百行足够快），
        仅当维度≤2000 才尝试建 HNSW 索引。
        """
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _text

            await db.execute(
                _text(
                    "CREATE TABLE IF NOT EXISTS ai_query_asset_vectors ("
                    "id BIGSERIAL PRIMARY KEY, asset_type VARCHAR(32), ref VARCHAR(256) UNIQUE, "
                    "txt TEXT, tables JSONB, embedding vector(2560))"
                )
            )

    @classmethod
    async def _seed_vectors(cls) -> int:
        """把资产单元向量写入 pgvector（幂等：按 ref upsert）。"""
        try:
            await cls._ensure_vector_table()
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 创建 pgvector 表失败: {e}")
            return 0
        index = await cls._semantic_index()
        if not index:
            return 0
        # 只保留带 tables 的单元
        rows = [u for u in index if u.get("tables")]
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _text

            for u in rows:
                ref = u["text"][:220]
                vec = str(u["vector"])
                tables = list(u["tables"])
                await db.execute(
                    _text(
                        "INSERT INTO ai_query_asset_vectors(asset_type, ref, txt, tables, embedding) "
                        "VALUES ('unit', :ref, :txt, CAST(:tables AS jsonb), CAST(:vec AS vector)) "
                        "ON CONFLICT (ref) DO UPDATE SET txt=EXCLUDED.txt, tables=EXCLUDED.tables, embedding=EXCLUDED.embedding"
                    ),
                    {"ref": ref, "txt": u["text"], "tables": json.dumps(tables, ensure_ascii=False), "vec": vec},
                )
        return len(rows)

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

    @classmethod
    async def _agno_seed_units(cls, schema: dict) -> None:
        """后台把 schema 单元播种进 Agno 向量库（不阻塞请求）。"""
        global _AGNO_SEEDED, _AGNO_SEEDING
        try:
            from .agno_store import AgnoSemanticStore

            store = await AgnoSemanticStore.get()
            await store.ensure()
            if (await store.count()) == 0:
                units: list[dict] = []
                for t in schema:
                    units.append({"text": f"数据表 {t}", "tables": {t}})
                    for col in schema[t]:
                        cname = col.split("(")[0]
                        units.append({"text": f"表 {t} 的字段 {cname}", "tables": {t}})
                n = await store.seed(units, reset=True)
                log.info(f"[query] Agno 语义单元后台入库: {n} 条")
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] Agno 后台播种失败: {e}")
        finally:
            _AGNO_SEEDED = True
            _AGNO_SEEDING = False

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

    @classmethod
    async def _ensure_recall_units_table(cls) -> None:
        """建语义单元表（幂等）。

        ``embedding`` 列**只在 PostgreSQL 上创建**——测试用 SQLite，没有 pgvector。
        """
        cols = cls._RECALL_UNITS_COLS
        from app.config.setting import settings

        if settings.DATABASE_TYPE == "postgres":
            cols = cols.replace("meta JSONB,", "meta JSONB, embedding vector(2560),")
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            await db.execute(
                _t(f"CREATE TABLE IF NOT EXISTS ai_query_recall_units ({cols})")
            )

    @staticmethod
    def _parse_col_label(label: str) -> dict:
        """从 ``_system_schema()`` 的列标签 ``col(type)【中文名】…`` 抽出列名与中文名。"""
        name = (label or "").split("(", 1)[0].strip()
        m = re.search(r"【([^】]+)】", label or "")
        return {"column_name": name, "description": m.group(1) if m else ""}

    @classmethod
    async def _collect_recall_units(cls) -> list[dict]:
        """收集召回单元：表 / 本体对象 / 概念 / 指标 / 术语。"""
        from app.plugin.module_ai.ontology import semantic as _sem

        from .recall import (
            build_concept_unit,
            build_metric_unit,
            build_object_unit,
            build_table_unit,
            build_term_unit,
        )

        units: list[dict] = []
        try:
            schema = await cls._system_schema()
            assets = {a.get("table_name"): a for a in await cls.list_assets()}
            for table, labels in (schema or {}).items():
                cols = [cls._parse_col_label(x) for x in (labels or [])]
                units.append(build_table_unit(table, assets.get(table) or {}, cols))
        except Exception as e:  # noqa: BLE001 - 单个来源失败不阻断整体重建
            log.warning(f"[query][recall] 表单元构建失败: {e}")
        try:
            ctx = await _sem.semantic_context(include_properties=True)
            rels = ctx.get("relations") or []
            props = ctx.get("properties") or {}
            for o in ctx.get("objects") or []:
                code, table = o.get("code"), o.get("table")
                mine = [
                    r for r in rels
                    if r.get("source") in (code, table) or r.get("target") in (code, table)
                ]
                units.append(build_object_unit(o, props.get(code) or [], mine))
            # semantic_context 的 concepts 已合并「本体别名 + ai_query_concept」
            for c in ctx.get("concepts") or []:
                units.append(build_concept_unit(c))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 本体单元构建失败: {e}")
        try:
            for m in await cls.list_metrics(SYSTEM_DS):
                units.append(build_metric_unit(m))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 指标单元构建失败: {e}")
        try:
            for t in await cls.list_terms(SYSTEM_DS):
                units.append(build_term_unit(t))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 术语单元构建失败: {e}")

        # 同一 (kind, ref) 只保留一条，保证幂等
        seen: set[tuple[str, str]] = set()
        out: list[dict] = []
        for u in units:
            key = (u.get("kind") or "", u.get("ref") or "")
            if not key[1] or key in seen:
                continue
            seen.add(key)
            out.append(u)
        return out

    @classmethod
    async def rebuild_recall_units(cls) -> dict:
        """重建语义召回单元（幂等，可重复执行）。

        返回 ``{"units": 条数, "embedded": 已向量化条数, "version": 批次}``。
        非 PostgreSQL 环境不写 ``embedding``（无 pgvector），只存文本。
        """
        import json as _json

        from sqlalchemy import text as _t

        from app.config.setting import settings
        from app.plugin.module_ai.knowledge.embedding import embed_texts

        await cls._ensure_recall_units_table()
        units = await cls._collect_recall_units()
        is_pg = settings.DATABASE_TYPE == "postgres"

        vecs: list[list[float] | None] = [None] * len(units)
        embedded = 0
        if is_pg and units:
            try:
                got = await embed_texts([u["text"] for u in units])
                for i, v in enumerate(got):
                    if i < len(vecs):
                        vecs[i] = v
                embedded = len(got)
            except Exception as e:  # noqa: BLE001 - 向量化失败仍保留文本单元
                log.warning(f"[query][recall] 单元向量化失败（仅存文本）: {e}")

        version = int(time.time())
        async with async_db_session.begin() as db:
            for u, v in zip(units, vecs, strict=False):
                params = {
                    "kind": u["kind"],
                    "ref": u["ref"],
                    "text": u["text"],
                    "meta": _json.dumps(u.get("meta") or {}, ensure_ascii=False),
                    "ver": version,
                }
                if is_pg:
                    params["emb"] = _json.dumps(v) if v is not None else None
                    await db.execute(
                        _t(
                            "INSERT INTO ai_query_recall_units"
                            "(kind,ref,text,meta,embedding,version,is_deleted,"
                            "created_time,updated_time) VALUES "
                            "(:kind,:ref,:text,CAST(:meta AS jsonb),CAST(:emb AS vector),"
                            ":ver,false,now(),now()) "
                            "ON CONFLICT (kind,ref) DO UPDATE SET text=EXCLUDED.text, "
                            "meta=EXCLUDED.meta, "
                            "embedding=COALESCE(EXCLUDED.embedding, "
                            "ai_query_recall_units.embedding), "
                            "version=EXCLUDED.version, is_deleted=false, updated_time=now()"
                        ),
                        params,
                    )
                else:
                    await db.execute(
                        _t(
                            "INSERT INTO ai_query_recall_units"
                            "(kind,ref,text,meta,version,is_deleted,created_time,updated_time) "
                            "VALUES (:kind,:ref,:text,:meta,:ver,false,now(),now()) "
                            "ON CONFLICT (kind,ref) DO UPDATE SET text=EXCLUDED.text, "
                            "meta=EXCLUDED.meta, version=EXCLUDED.version, "
                            "is_deleted=false, updated_time=now()"
                        ),
                        params,
                    )
        log.info(f"[query][recall] 语义单元重建完成: {len(units)} 条（向量化 {embedded}）")
        return {"units": len(units), "embedded": embedded, "version": version}

    @classmethod
    async def _recall_vector(cls, question: str, top_n: int) -> list[str]:
        """向量召回通道：**直查 pgvector**（绕过 Agno 的同步引擎与默认 10 条限制）。

        非 PostgreSQL / 未装 pgvector / 单元未重建时**优雅降级为空列表**，由其余通道兜底
        （测试库是 SQLite，走的正是这条路径）。
        """
        import json as _json

        from app.config.setting import settings

        if settings.DATABASE_TYPE != "postgres":
            return []
        try:
            from sqlalchemy import text as _t

            from app.plugin.module_ai.knowledge.embedding import embed_texts

            vecs = await embed_texts([question])
            if not vecs or not vecs[0]:
                return []
            async with async_db_session() as db:
                rows = (
                    await db.execute(
                        _t(
                            "SELECT meta FROM ai_query_recall_units "
                            "WHERE is_deleted = false AND embedding IS NOT NULL "
                            "ORDER BY embedding <=> CAST(:q AS vector) LIMIT :n"
                        ),
                        {"q": _json.dumps(vecs[0]), "n": int(top_n)},
                    )
                ).fetchall()
            out: list[str] = []
            for (meta,) in rows:
                m = meta if isinstance(meta, dict) else _json.loads(meta or "{}")
                for t in m.get("tables") or []:
                    if t and t not in out:
                        out.append(t)
            return out
        except Exception as e:  # noqa: BLE001 - 向量通道失败不得阻断召回
            log.warning(f"[query][recall] 向量通道失败，已降级: {e}")
            return []

    @classmethod
    async def _recall_keyword(cls, question: str, schema: dict | None = None) -> list[str]:
        """关键词通道（薄包装：取数据后调纯函数 ``recall_keyword``）。

        ⚠️ 必须用**调用方传入的 schema**：外部数据源（如 ds:4 燃煤库）的表不在
        ``_system_schema()`` 里，固定用系统 schema 会让该通道对外部源完全失效。
        """
        from .recall import recall_keyword

        try:
            schemas = schema if schema is not None else await cls._system_schema()
            return recall_keyword(
                question, schemas,
                await cls.list_metrics(SYSTEM_DS), await cls.list_terms(SYSTEM_DS),
            )
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 关键词通道失败: {e}")
            return []

    @classmethod
    async def _recall_ontology(cls, question: str) -> list[str]:
        """本体强信号通道：别名 > 同义词 > 属性名 > 对象名。"""
        from app.plugin.module_ai.ontology import semantic as _sem

        from .recall import recall_ontology

        try:
            ctx = await _sem.semantic_context(include_properties=True)
            tmap = await _sem.object_table_map()
            props = ctx.get("properties") or {}
            objs: list[dict] = []
            for o in ctx.get("objects") or []:
                oo = dict(o)
                oo["properties"] = [
                    (p.get("name") or p.get("code"))
                    for p in (props.get(o.get("code")) or [])
                ]
                objs.append(oo)
            return recall_ontology(question, objs, tmap)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 本体通道失败: {e}")
            return []

    @classmethod
    async def _recall_entity(cls, question: str, schema: dict | None = None) -> list[str]:
        """实体名词通道（薄包装）；同样必须用传入的 schema（外部数据源场景）。"""
        from .recall import recall_entity

        try:
            cfg = await cls._cfg()
            schemas = schema if schema is not None else await cls._system_schema()
            return recall_entity(question, cls._cfg_entity_map(cfg), schemas)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 实体通道失败: {e}")
            return []

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

    @classmethod
    async def _semantic_tables(cls, question: str, schema: dict | None = None,
                               metrics: list[dict] | None = None,
                               terms: list[dict] | None = None,
                               datasource: str | None = None) -> list[str]:
        """分层检索（带**记忆缓存**）。

        同一个问题在一次问答里会被问两次——`_build_schema_context` 拼 prompt、
        `_recall_grounding` 做溯源——而这条路径会走向量检索。
        不缓存就是白跑一次检索（实测收尾阶段因此花掉 1.2~1.8 秒）。
        缓存 key **含数据源**：否则两个数据源互相串结果。
        """
        key = _retrieval_cache_key(question, datasource)
        hit = _RETRIEVAL_CACHE.get(key)
        if hit and time.time() - hit[0] <= _RETRIEVAL_CACHE_TTL:
            return list(hit[1])
        out = await cls._semantic_tables_uncached(question, schema, metrics, terms)
        if len(_RETRIEVAL_CACHE) >= _RETRIEVAL_CACHE_MAX:
            for k in list(_RETRIEVAL_CACHE)[: max(1, _RETRIEVAL_CACHE_MAX // 10)]:
                _RETRIEVAL_CACHE.pop(k, None)
        _RETRIEVAL_CACHE[key] = (time.time(), list(out))
        return out

    @classmethod
    async def _semantic_tables_uncached(cls, question: str, schema: dict | None = None,
                                        metrics: list[dict] | None = None,
                                        terms: list[dict] | None = None) -> list[str]:
        """多路并行召回 + RRF 融合 + 阈值 + **按分数取 top_k**（阶段1）。

        取代旧实现的「分级短路 + 字典序截断」：四个通道**并行**执行、互不短路，
        用 RRF（只用排名，免跨通道归一化）融合后按分数截断。
        ``recall_enabled=false`` 时退回 ``_semantic_tables_legacy``，便于灰度回滚。
        """
        import asyncio

        cfg = await cls._cfg()
        if not cls._cfg_bool(cfg, "recall_enabled", True):
            return await cls._semantic_tables_legacy(question, schema, metrics, terms)

        from .recall import CORE_TABLES, DEFAULT_WEIGHTS, fuse_rrf

        top_k = cls._cfg_int(cfg, "recall_top_k", 12)
        top_n = max(8, top_k * 2)
        # schema 是**本次问答的数据源**的表结构（外部源时由调用方传入）：
        # 关键词/实体通道必须用它，否则对外部数据源（如 ds:4 燃煤库）失效。
        try:
            schema_map = schema if schema is not None else await cls._system_schema()
        except Exception as e:  # noqa: BLE001 - 取不到 schema 不阻断召回
            log.warning(f"[query][recall] 取 schema 失败（通道将为空）: {e}")
            schema_map = schema or {}

        results = await asyncio.gather(
            cls._recall_vector(question, top_n),
            cls._recall_keyword(question, schema_map),
            cls._recall_ontology(question),
            cls._recall_entity(question, schema_map),
            return_exceptions=True,
        )
        channels: dict[str, list[str]] = {}
        for name, res in zip(("vector", "keyword", "ontology", "entity"), results, strict=False):
            channels[name] = [] if isinstance(res, BaseException) else list(res or [])

        weights = {
            "vector": cls._cfg_float(cfg, "recall_w_vector", DEFAULT_WEIGHTS["vector"]),
            "keyword": cls._cfg_float(cfg, "recall_w_keyword", DEFAULT_WEIGHTS["keyword"]),
            "ontology": cls._cfg_float(cfg, "recall_w_ontology", DEFAULT_WEIGHTS["ontology"]),
            "entity": cls._cfg_float(cfg, "recall_w_entity", DEFAULT_WEIGHTS["entity"]),
        }
        fused = fuse_rrf(channels, weights)
        min_score = cls._cfg_float(cfg, "recall_min_score", 0.0)
        # **数据源隔离**：只保留本次数据源 schema 里的表。
        # 向量/本体通道是**全局**的（不认数据源），实测 ds:4 的问题被召回到
        # video_*/ai_* 等 system 表 → prompt 里没有真正的业务表 → 模型**编表名** → 空 SQL。
        ranked = [t for t, s in fused if s >= min_score]
        picked = scope_tables_to_schema(ranked, schema_map, CORE_TABLES, top_k)

        # 关系/KG/AGE 扩表：仅作**补充**、不参与计分。
        # ⚠️ 必须有上限：无限制追加会把 prompt 撑大，实测让生成 P50 从 7.9s 涨到 9.0s。
        try:
            if cls._cfg_bool(cfg, "kg_enabled", True):
                from .agno_kg import _ensure, age_expand_tables, kg_tables

                limit = top_k + max(0, cls._cfg_int(cfg, "recall_expand_cap", 4))
                kg = await _ensure()
                extra: list[str] = []
                if kg:
                    extra.extend(kg_tables(question) or [])
                if picked:
                    extra.extend(await age_expand_tables(sorted(picked)) or [])
                for t in extra:
                    if len(picked) >= limit:
                        break
                    if t in schema_map and t not in picked:
                        picked.append(t)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query][recall] 扩表失败（忽略）: {e}")
        return picked

    @classmethod
    async def _semantic_tables_legacy(cls, question: str, schema: dict | None = None,
                                      metrics: list[dict] | None = None,
                                      terms: list[dict] | None = None) -> list[str]:
        """【旧实现，仅作 recall_enabled=false 的回退】分层检索 + 关键词 + 实体表基线，合并出联表所需的表集合。

        优先 pgvector，回退内存融合(jieba+embedding)；再并上关键词相关表，
        并按「实体名词→表」映射把联表取名称所需的 name 承载表兜底加入；
        最后按 token 量裁剪到前 16 张，避免 prompt 过大。
        """
        global _VECTOR_SEEDED
        cfg = await cls._cfg()
        if schema is None:
            schema = await cls._system_schema()
        if metrics is None:
            metrics = await cls.list_metrics(SYSTEM_DS)
        if terms is None:
            terms = await cls.list_terms(SYSTEM_DS)
        top_k = cls._cfg_int(cfg, "schema_top_k", 16)
        tables: set[str] = set()
        # 1) 语义召回：优先走 Agno 框架(Knowledge+PgVector)
        if cls._cfg_bool(cfg, "agno_semantic_enabled", True):
            try:
                at = await cls._agno_search_tables(question, schema, top_k)
                tables.update(at)
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] Agno 语义检索失败，回退 pgvector: {e}")
        # 2) 回退：pgvector / 内存融合
        if not tables:
            try:
                if not _VECTOR_SEEDED:
                    try:
                        n = await cls._seed_vectors()
                        _VECTOR_SEEDED = True
                        log.info(f"[query] 资产向量已落 pgvector: {n} 条")
                    except Exception as e:  # noqa: BLE001
                        log.warning(f"[query] pgvector 播种失败: {e}")
                rows = await cls._pgv_search(question, top_k=top_k)
                tables.update(rows)
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] pgvector 检索失败: {e}")
        # 3) 内存融合回退
        if not tables:
            try:
                index = await cls._semantic_index()
                if index:
                    from . import retrieval as _ret

                    units = [
                        {"text": u["text"], "vector": u.get("vector"), "meta": u["tables"]}
                        for u in index
                    ]
                    top = await _ret.retrieve(
                        question, units, top_k=top_k,
                        semantic_weight=cls._cfg_float(cfg, "schema_semantic_weight", 0.6),
                        keyword_weight=cls._cfg_float(cfg, "schema_keyword_weight", 0.4),
                        embed_model_id=await cls._embedding_mid(),
                    )
                    for u in top:
                        tables.update(u.get("meta") or set())
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 语义检索失败: {e}")
        # 3) 关键词相关表
        try:
            tables.update(cls._relevant_tables(question, schema, metrics, terms))
        except Exception:  # noqa: BLE001
            pass
        # 3.5) **本体别名 → 表**（本体是唯一语义源，检索也必须用上）
        #
        # 真实踩过：问「各部门的销售额是多少」，本体里有对象「销售订单」
        # （表 demo_sales，属性「销售额」），但检索只认**表名**，demo_sales 没被召回，
        # 模型只好拿 `ai_call_logs.cost` 当"销售额"，返回 0。
        #
        # ⚠️ 只匹配**别名**，不匹配对象名：对象名（如"告警记录表"）含"告警"这种
        # 通用词，会给大量无关问题塞进额外表 —— 实测这让 prompt 变大、
        # 生成 p50 从 3147ms 涨到 6483ms（精度还降了）。别名是人工登记的强信号。
        try:
            from app.plugin.module_ai.ontology import semantic as _sem

            ctx = await _sem.semantic_context(include_properties=False)
            tmap = await _sem.object_table_map()
            code_of: dict[str, str] = {}
            for tbl, code in tmap.items():
                code_of.setdefault(code, tbl)
            q_low = (question or "").lower()
            added = 0
            for o in ctx["objects"]:
                if added >= _ONT_ALIAS_MAX_TABLES:
                    break
                hits = [a for a in (o.get("aliases") or [])
                        if a and len(str(a)) >= 2 and str(a).lower() in q_low]
                if not hits:
                    continue
                tbl = code_of.get(o["code"]) or o["table"]
                if tbl in schema and tbl not in tables:
                    tables.add(tbl)
                    added += 1
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 本体别名检索失败: {e}")
        # 4) 实体名词 → 表 基线（保证联表取名称的表在上下文）
        if cls._cfg_bool(cfg, "entity_enabled", True):
            entity_map = cls._cfg_entity_map(cfg)
            for noun, ts in entity_map.items():
                if noun in question:
                    tables.update(t for t in ts if t in schema)
        # 5) 知识图谱图遍历：补上向量/关键词检索漏掉的关联表与联表路径
        try:
            if cls._cfg_bool(cfg, "kg_enabled", True):
                from .agno_kg import _ensure, kg_tables

                kg = await _ensure()
                if kg:
                    tables.update(t for t in kg_tables(question) if t in schema)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 知识图谱召回失败: {e}")
        # 6) AGE 图库多跳扩表：从已命中表经 Cypher 扩展关联表
        try:
            if cls._cfg_bool(cfg, "kg_enabled", True) and tables:
                from .agno_kg import age_expand_tables

                tables.update(t for t in await age_expand_tables(sorted(tables)) if t in schema)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] AGE 扩表失败: {e}")
        return sorted(tables)[:top_k]

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
        """查询口径规范：统一业务口径，减少 LLM 生成 SQL 时的歧义（时间/用户/联表/占比）。"""
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

    @classmethod
    async def _ds_schema_map(cls, datasource: str) -> dict[str, list[str]]:
        """自定义数据源已同步的表结构：``{表名: [列标签]}``。

        与 ``_system_schema`` 同形，方便复用同一套关键词检索（``_relevant_tables``）。
        带进程内缓存——331 张表的同步结果每次问答都读库太浪费。
        """
        global _DS_SCHEMA_CACHE
        key = str(datasource or "")
        hit = _DS_SCHEMA_CACHE.get(key)
        if hit and time.time() - hit[0] <= _DS_SCHEMA_TTL:
            return hit[1]
        out: dict[str, list[str]] = {}
        try:
            ds_id = int(key.split(":")[-1])
            # **只取已纳入资产目录的表**：范围收敛到关键业务表，
            # 避免 SYS_*/_BAK 等技术表混进检索与 prompt（实测污染召回）。
            rows = await list_ds_schema(ds_id, included_only=True)
            for r in rows:
                cols = []
                # 表注释放第一位，形如 `FUEL_CB_COALBALANCE(燃煤采购结算主表)`：
                # 既让检索能按中文表名命中，也让模型在 prompt 里看到业务含义
                tcmt = str(r.get("comment") or "").strip()
                if tcmt:
                    cols.append(f"{r['table']}({tcmt})")
                for c in (r.get("columns") or []):
                    if not isinstance(c, dict) or not c.get("name"):
                        continue
                    label = str(c["name"])
                    if c.get("comment"):
                        label += f"({c['comment']})"
                    cols.append(label)
                out[r["table"]] = cols
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 读取数据源 {key} 表结构失败: {e}")
            return {}
        if len(_DS_SCHEMA_CACHE) >= 20:
            _DS_SCHEMA_CACHE.clear()
        _DS_SCHEMA_CACHE[key] = (time.time(), out)
        return out

    @classmethod
    async def _build_schema_context(cls, question: str, datasource: str, metrics: list[dict], terms: list[dict]) -> str:
        lines = []
        # 当前对象上下文：**确定性注入**（对齐 Palantir Retrieval Context），放在最前面。
        octx = _OBJECT_CTX.get()
        if octx:
            lines.append(octx)
        lines.append("【可用指标】")
        for m in metrics:
            if m["enabled"]:
                lines.append(f"- {m['key']}: {m['name']} ({m['description']})")
        lines.append("【术语】")
        for t in terms:
            lines.append(f"- {t['term']} -> {t['metric_key'] or t['field_path']}")
        t_c0 = time.perf_counter()
        conc = await cls._concept_context()
        t_c1 = time.perf_counter()
        if conc:
            lines.append(conc)
        lines.append("【可查询表及字段】")
        if datasource in (SYSTEM_DS, None):
            schema = await cls._system_schema()
            tmeta = await cls._asset_tmeta()
            # **先检索、再拼 prompt**：`_semantic_tables` 是本地检索（关键词+语义加权，
            # top_k=16）。旧实现先把**全部 85 个对象、1500+ 属性**塞进本体块
            # （实测 37517 字符），再把检索结果拼在后面——LLM 的前缀计算大半花在
            # 与问题无关的对象上，又慢又干扰判断。现在只带检索命中的表。
            t_r0 = time.perf_counter()
            rel = await cls._semantic_tables(question, schema, metrics, terms, datasource)
            t_r1 = time.perf_counter()
            ont = await cls._ont_ctx_block(only_tables=set(rel))
            t_r2 = time.perf_counter()
            log.warning("[schema] 分段：概念={}ms 召回={}ms 本体块={}ms",
                        int((t_c1 - t_c0) * 1000), int((t_r1 - t_r0) * 1000),
                        int((t_r2 - t_r1) * 1000))
            if ont:
                lines.append(ont)
            for t in rel:
                cols = schema.get(t, [])
                meta = tmeta.get(t) or {}
                desc = meta.get("description") or ""
                scen = meta.get("business_scenarios") or ""
                nm = meta.get("alias") or ""
                dom = meta.get("domain") or ""
                head = t
                extras = []
                if nm:
                    extras.append(f"中文名:{nm}")
                if dom:
                    extras.append(f"业务域:{dom}")
                if desc:
                    extras.append(f"描述:{desc}")
                if scen:
                    extras.append(f"业务场景:{scen}")
                if extras:
                    head = f"{t}【" + "；".join(extras) + "】"
                lines.append(f"- {head}: {', '.join(cols) if cols else ''}")
            lines.append(cls._query_conventions())
        else:
            # **自定义数据源**：原先这里**什么都不加** —— 模型对 ds:{id} 一张表、
            # 一个字段都不知道，只能瞎猜，问数必然答不对。
            # 这里把该数据源**已同步的表结构**按问题检索后注入。
            # 331 张表不能全塞，所以复用同一套关键词打分只取 top_k。
            ds_schema = await cls._ds_schema_map(datasource)
            if ds_schema:
                # 复用**统一的召回服务**（并行四路 + RRF + 阈值），
                # 而不是旧的单路关键词 —— 否则新召回只对 system 数据源生效。
                rel = await cls._semantic_tables_uncached(question, ds_schema, metrics, terms)
                lines.append(
                    f"（数据源 {datasource}，共 {len(ds_schema)} 张表，"
                    f"下面是与问题最相关的 {len(rel)} 张）")
                for t in rel:
                    cols = ds_schema.get(t, [])
                    lines.append(f"- {t}: {', '.join(cols) if cols else ''}")
                lines.append(cls._query_conventions())
                # 该库表名/字段名为英文大写且大小写敏感：不加双引号会被 PG 小写化 → 找不到表。
                lines.append(
                    "【标识符大小写】本数据源的表名/字段名为**英文大写且大小写敏感**，"
                    'SQL 中必须用双引号引用：如 FROM "FUEL_CB_COALBALANCE"、SUM("COALMONEY")。'
                )
        lines.append("【示例问题→SQL】")
        for eg in await cls._dynamic_fewshots(question, datasource):
            lines.append(f"问：{eg['q']}")
            lines.append(f"SQL：{eg['sql']}")
        return "\n".join(lines)

    @classmethod
    async def _get_runtime(cls) -> dict:
        from app.plugin.module_ai.models.service import AiModelService

        # 顺序很关键：`get_runtime_model(usage)` 会把 **usage 为空**的模型也算命中
        # （"通用"语义，兼容旧数据），于是专门为 chat 配的本地模型根本不参与，
        # 问数被顶到那个"通用"模型上——而它可能是额度受限的外部网关，
        # 表现为模型返回一段错误文本，最后报成「仅允许 SELECT 查询」，
        # 完全看不出真实原因。所以这里要求**精确匹配用途**优先。
        first = None
        for u in ("query", "chat"):
            r = await AiModelService.get_runtime_model(u)
            first = first or r
            if r and r.get("usage") == u:
                return r
        if first:
            return first
        runtime = await AiModelService.get_runtime_model()
        if not runtime:
            raise CustomException(msg="未配置可用的 chat 模型")
        return runtime

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
    async def _save_message(cls, session_id: int, question: str, **kw) -> AiQueryMessageModel:
        async with async_db_session.begin() as db:
            m = AiQueryMessageModel(
                session_id=session_id, question=question,
                path=kw.get("path", "fast"), datasource=kw.get("datasource", SYSTEM_DS),
                sql=kw.get("sql", ""), columns=kw.get("columns") or [],
                rows=kw.get("rows") or [], summary=kw.get("summary", ""),
                result_rows=kw.get("result_rows", 0), took_ms=kw.get("took_ms", 0),
                cached=kw.get("cached", False), usage=kw.get("usage"),
                is_error=kw.get("is_error", False),
                grounding=kw.get("grounding"),
            )
            db.add(m)
            await db.flush()
            return m

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
    async def _recall_grounding(cls, question: str, datasource: str | None = None) -> dict | None:
        """Grounding 可观测：返回本次混合检索锁定的表 + 关键字段，供前端展示「召回表/字段」。

        **必须传数据源**：否则 ds:4 的问题会用 system 源的 schema 去检索，
        召回到 video_*/ai_* 表 → prompt 里没有真正的业务表 → 模型**编表名** → 空 SQL（实测）。
        """
        try:
            if (datasource or SYSTEM_DS) == SYSTEM_DS:
                schema = await cls._system_schema()
            else:
                schema = await cls._ds_schema_map(datasource)
            metrics = await cls.list_metrics(datasource)
            terms = await cls.list_terms(datasource)
            rel_tables = await cls._semantic_tables(
                question, schema, metrics, terms, datasource
            )
            fields = {t: [lab.split("(")[0] for lab in schema.get(t, [])][:8]
                      for t in rel_tables}
            return {"tables": rel_tables, "fields": fields}
        except Exception:  # noqa: BLE001
            return None

    @classmethod
    async def _dq_warning_for_sql(cls, sql: str) -> list[dict]:
        """DQ 联动：若问数 SQL 涉及 DQ 风险对象表（健康分 <60），返回警告（温和提示，不硬拦）。"""
        if not sql:
            return []
        try:
            overview = await cls.dq_overview()
        except Exception:  # noqa: BLE001
            return []
        risk = {x.get("table"): x.get("score") for x in overview.get("items", [])
                if (x.get("score") or 0) < 60}
        if not risk:
            return []
        used = [t for t in risk if t in sql]
        return [{"table": t, "score": risk[t]} for t in used]

    @classmethod
    async def run_metric(cls, metric_key: str, datasource: str | None, params: dict, auth) -> dict:
        metrics = await cls.list_metrics(datasource)
        metric = next((m for m in metrics if m["key"] == metric_key), None)
        if not metric:
            raise CustomException(msg=f"指标「{metric_key}」不存在")
        res = await _execute_metric(metric, params or {}, auth)
        return res

    # ---- 反馈 ----
    @classmethod
    async def feedback(cls, message_id: int, feedback: str, correct_sql: str | None, auth) -> dict:
        import uuid as _uuid

        from sqlalchemy import select as _sel

        async with async_db_session.begin() as db:
            m = await db.get(AiQueryMessageModel, message_id)
            if not m:
                raise CustomException(msg="记录不存在")
            m.feedback = feedback
            m.updated_id = auth.user.id
            sunk = False
            reason = ""
            if correct_sql:
                # ① **先存下来**：人工修正的 SQL 本身就是最宝贵的样本，
                #    绝不能因为"没通过校验/沉淀失败"就丢掉（旧实现在这里 return，直接丢了）
                m.correct_sql = correct_sql
                # ② 再尝试沉淀成 few-shot：按**该消息的数据源**校验
                #    （旧实现永远用系统白名单 → ds:4 的修正 SQL 一律被判非法）
                if cls._cfg_bool(await cls._cfg(), "fewshot_auto_curate", True):
                    try:
                        if (m.datasource or SYSTEM_DS) == SYSTEM_DS:
                            validate_sql(correct_sql, await _system_allowed())
                        else:
                            _ds_id = int(str(m.datasource).split(":")[-1])
                            _rows = await list_ds_schema(_ds_id, included_only=True)
                            validate_sql(correct_sql, {r["table"] for r in _rows})
                    except Exception as e:  # noqa: BLE001
                        reason = f"SQL 未通过校验，已保存但未沉淀：{getattr(e, 'msg', e)}"
                    else:
                        exists = (
                            await db.execute(
                                _sel(AiQueryFewshotModel).where(
                                    AiQueryFewshotModel.question == m.question,
                                    AiQueryFewshotModel.is_deleted.is_(False),
                                )
                            )
                        ).scalar_one_or_none()
                        if not exists:
                            # ⚠️ uuid/status 是 NOT NULL：旧实现没赋值 →
                            #    插入报错 → **整个事务回滚** → 连反馈都存不下（实测 0 条反馈的真因之一）
                            db.add(
                                AiQueryFewshotModel(
                                    datasource=m.datasource, question=m.question,
                                    sql=correct_sql, enabled=True, status="0",
                                    uuid=_uuid.uuid4().hex,
                                    created_id=auth.user.id, updated_id=auth.user.id,
                                )
                            )
                            sunk = True
            await db.flush()
            return {"id": m.id, "feedback": feedback, "sunk": sunk, "reason": reason}
