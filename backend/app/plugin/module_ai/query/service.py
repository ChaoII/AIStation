"""智能问数服务：语义层 + 快慢双路径 + 安全查询引擎 + 会话/反馈。

设计要点：
- 语义层(指标/术语/维度)是两条路径共享的知识底座。
- 高频问题命中指标模板 → 快路径(秒级)；未命中 → LLM NL2SQL 慢路径(精准兜底)。
- 所有执行只读 + 白名单表/字段 + 超时 + LIMIT，权限不可绕过。
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from sqlalchemy import text

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log

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
# Agno 向量库是否已播种语义单元
_AGNO_SEEDED = False
# Agno 语义单元是否正在后台播种
_AGNO_SEEDING = False
# 进程级缓存：工程配置（UI 保存时失效）
_SETTINGS_CACHE: dict | None = None
# 进程级缓存：表级资产元数据（中文名/业务域/描述/业务场景）
_ASSET_TMETA: dict | None = None


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
    "ai_call_logs", "ai_messages", "ai_sessions", "ai_apps", "ai_agents",
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


async def test_datasource_conn(datasource_id: int) -> dict:
    ds = await _load_ds(datasource_id)
    from . import executor as _ex

    return await _ex.test_connection(_ds_cfg_from_model(ds))


async def sync_datasource_schema(datasource_id: int) -> dict:
    ds = await _load_ds(datasource_id)
    from . import executor as _ex

    tables = await _ex.introspect_schema(_ds_cfg_from_model(ds))
    code = _ds_code(datasource_id)
    async with async_db_session.begin() as db:
        from sqlalchemy import delete

        await db.execute(
            delete(AiQuerySchemaModel).where(AiQuerySchemaModel.datasource == code)
        )
        for t in tables:
            db.add(
                AiQuerySchemaModel(
                    datasource=code, table_name=t["table"], columns=t["columns"]
                )
            )
    return {"tables": len(tables)}


async def list_ds_schema(datasource_id: int) -> list[dict]:
    code = _ds_code(datasource_id)
    async with async_db_session() as db:
        from sqlalchemy import select

        rows = (
            await db.execute(
                select(AiQuerySchemaModel).where(
                    AiQuerySchemaModel.datasource == code,
                    AiQuerySchemaModel.is_deleted.is_(False),
                )
            )
        ).scalars().all()
    return [{"table": r.table_name, "columns": r.columns or []} for r in rows]


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

    sql = validate_sql(sql, allowed)
    return await _ex.execute_select(_ds_cfg_from_model(ds), sql)


def _to_metric_dict(m: AiQueryMetricModel) -> dict:
    return {
        "id": m.id, "datasource": m.datasource, "key": m.key, "name": m.name,
        "description": m.description or "", "sql_template": m.sql_template,
        "params": m.params or [], "dimensions": m.dimensions or [], "agg": m.agg,
        "unit": m.unit or "", "permission_tag": m.permission_tag or "",
        "enabled": m.enabled, "sort": m.sort or 0, "cache_ttl": m.cache_ttl or 0,
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
def validate_sql(sql: str, allowed_tables: set[str]) -> str:
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
    # 白名单表
    from_src = re.findall(
        r"\bfrom\s+([A-Za-z_][A-Za-z0-9_\.]*)", removed_semis, re.IGNORECASE
    )
    for tbl in from_src:
        base = tbl.split(".")[-1].strip().strip('"')
        if allowed_tables and base not in allowed_tables:
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
    # 限制行数
    if not re.search(r"\blimit\s+\d+", removed_semis, re.IGNORECASE):
        removed_semis = removed_semis + f" LIMIT {MAX_ROWS}"
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


async def _execute_metric(metric: dict, params: dict[str, Any], auth=None) -> dict:
    sql = _render_template(metric["sql_template"], params)
    ds_code = metric.get("datasource") or SYSTEM_DS
    if ds_code == SYSTEM_DS:
        sql = validate_sql(sql, SYSTEM_ALLOWED_TABLES)
        res = await _execute_sql(sql)
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


def _match_metric(question: str, metrics: list[dict], terms: list[dict]) -> dict | None:
    """按得分选指标：名词/key/术语命中 + 时间语境对齐。

    时间语境：问句带明确时间（本月→month / 今天→today / 最近7天→days）时，
    优先选择时间维度一致且未带其它时间限制的指标，避免「本月报警」被默认
    「今日告警」抢占。
    """
    q = question.lower()
    frame = _detect_time_frame(question)
    best = None
    best_score = 0
    for m in metrics:
        if not m["enabled"]:
            continue
        score = 0
        name = (m.get("name") or "").lower()
        key = (m.get("key") or "").lower()
        desc = (m.get("description") or "").lower()
        if name and name in q:
            score += 5
        if key and key in q:
            score += 4
        for t in terms:
            if t.get("metric_key") == m["key"] and t.get("term") and t["term"].lower() in q:
                score += 3
        # 名称/描述关键词重叠（如「按告警类型分布」↔ 指标名「按告警类型的分布」）
        for kw in ("类型", "分布", "按", "占比", "趋势", "数量", "多少", "各类"):
            if kw in q and (kw in name or kw in desc):
                score += 2
        # 时间语境对齐
        mtime = _metric_time_hint(m)
        if frame:
            if frame == mtime:
                score += 4
            elif mtime and frame != mtime:
                score -= 2  # 问本月却选了「今日」指标 → 减分
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
# 语义层 CRUD + 种子
# ---------------------------------------------------------------------------
class AiQueryService:

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
                          "agg", "unit", "permission_tag", "enabled", "sort", "cache_ttl"):
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
                    created_id=auth.user.id, updated_id=auth.user.id,
                )
                db.add(obj)
            await db.flush()
            return _to_metric_dict(obj)

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
        async with async_db_session() as db:
            from sqlalchemy import select

            rows = (
                await db.execute(
                    select(AiQueryAssetModel)
                    .where(AiQueryAssetModel.is_deleted.is_(False))
                    .order_by(AiQueryAssetModel.table_name)
                )
            ).scalars().all()
            out = []
            for a in rows:
                cnt = (await db.execute(
                    select(AiQueryAssetColumnModel)
                    .where(
                        AiQueryAssetColumnModel.table_name == a.table_name,
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                    )
                )).scalars().all()
                out.append({
                    "table_name": a.table_name, "alias": a.alias or "",
                    "domain": a.domain or "", "description": a.description or "",
                    "business_scenarios": a.business_scenarios or "",
                    "included": a.included, "remark": a.remark or "",
                    "column_count": len(cnt),
                    "included_columns": sum(1 for c in cnt if c.included),
                })
            return out

    @classmethod
    async def list_asset_columns(cls, table_name: str) -> list[dict]:
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
            return [
                {"table_name": c.table_name, "column_name": c.column_name,
                 "description": c.description or "",
                 "business_scenarios": c.business_scenarios or "",
                 "related_table": c.related_table or "",
                 "related_field": c.related_field or "",
                 "included": c.included, "sensitive": c.sensitive}
                for c in rows
            ]

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
                existing.updated_id = auth.user.id
            else:
                db.add(AiQueryAssetModel(table_name=data.table_name, alias=data.alias,
                                         domain=data.domain, description=data.description,
                                         business_scenarios=data.business_scenarios,
                                         included=data.included, remark=data.remark,
                                         created_id=auth.user.id, updated_id=auth.user.id))
            await db.flush()
        _SCHEMA_CACHE = None
        _SEMANTIC_INDEX = None
        _ASSET_TMETA = None
        return {"table_name": data.table_name, "included": data.included}

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
        runtime = await cls._get_runtime()
        try:
            from openai import AsyncOpenAI

            from app.plugin.module_ai.provider.service import build_headers

            client = AsyncOpenAI(
                base_url=runtime["base_url"], api_key=runtime["api_key"] or "sk-none",
                default_headers=build_headers(runtime["base_url"], runtime.get("extra_headers"), "aistation-dict"),
            )
        except Exception as e:  # noqa: BLE001
            raise CustomException(msg=f"问答模型不可用：{e}")
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
                "（每个不超过30字，只说业务含义）。严格返回 JSON，格式："
                "{\"table\":\"<表描述>\",\"columns\":{\"字段名\":\"<字段描述>\"}}。\n"
                f"表名：{tname}\n字段：{', '.join(cols)}\n数据画像：\n" + "\n".join(prof_lines)
            )
            try:
                resp = await client.chat.completions.create(
                    model=runtime["model"], messages=[{"role": "user", "content": prompt}],
                    temperature=0, max_tokens=800,
                )
                text = (resp.choices[0].message.content or "")
                data = cls._parse_dict(text)
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
        # 2) LLM 生成建议
        runtime = await cls._get_runtime()
        try:
            from openai import AsyncOpenAI

            from app.plugin.module_ai.provider.service import build_headers

            client = AsyncOpenAI(
                base_url=runtime["base_url"], api_key=runtime["api_key"] or "sk-none",
                default_headers=build_headers(runtime["base_url"], runtime.get("extra_headers"), "aistation-suggest"),
            )
            data: dict = {}
            for attempt in range(2):
                prompt = (
                    "你是数据分析师。根据下面的数据库表/字段中文词典，推荐 6~10 个高频业务指标和 6~10 个业务术语。"
                    "指标必须是常见统计口径(总数/某类型数量/平均/分布)，且能用给出的表/字段实现。"
                    "**只返回一个 JSON 对象，不要任何解释、不要 markdown 代码块**，格式严格为："
                    '{"metrics":[{"name":"<指标名>","sql":"<SELECT COUNT/AVG> FROM <表>...","agg":"count|avg|group"}],'
                    '"terms":[{"term":"<口语叫法>","type":"metric|dimension","target":"<指标名或 表.字段>"}]}'
                    + ("\n\n注意：你上次输出不是合法 JSON，请严格按上面的 JSON 结构重新输出，不要多余文字。\n" if attempt else "")
                    + f"\n数据字典：\n{dict_text}"
                )
                resp = await client.chat.completions.create(
                    model=runtime["model"], messages=[{"role": "user", "content": prompt}],
                    temperature=0.2, max_tokens=1600,
                )
                data = cls._parse_dict(resp.choices[0].message.content or "")
                if data or attempt == 1:
                    break
        except Exception as e:  # noqa: BLE001
            raise CustomException(msg=f"推荐失败：{e}")
        return {
            "metrics": data.get("metrics") or [],
            "terms": data.get("terms") or [],
        }

    @staticmethod
    def _parse_dict(text: str) -> dict:
        import json
        import re

        text = re.sub(r"```(?:json)?", "", text).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        try:
            return json.loads(text)
        except Exception:  # noqa: BLE001
            return {}

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

            existing = (
                await db.execute(
                    select(AiQueryAssetColumnModel).where(
                        AiQueryAssetColumnModel.table_name == data.table_name,
                        AiQueryAssetColumnModel.column_name == data.column_name,
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.description = data.description
                existing.business_scenarios = data.business_scenarios
                existing.related_table = data.related_table
                existing.related_field = data.related_field
                existing.included = data.included
                existing.sensitive = data.sensitive
                existing.updated_id = auth.user.id
            else:
                db.add(AiQueryAssetColumnModel(table_name=data.table_name, column_name=data.column_name,
                                               description=data.description,
                                               business_scenarios=data.business_scenarios,
                                               related_table=data.related_table,
                                               related_field=data.related_field,
                                               included=data.included, sensitive=data.sensitive,
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

            for t in tables:
                inc = t in SYSTEM_ALLOWED_TABLES
                exists = (
                    await db.execute(select(AiQueryAssetModel).where(AiQueryAssetModel.table_name == t))
                ).scalar_one_or_none()
                if not exists:
                    db.add(AiQueryAssetModel(table_name=t, description="", included=inc,
                                             remark="", created_id=auth.user.id, updated_id=auth.user.id))
                    upserted += 1
            for t, c in cols:
                exists = (
                    await db.execute(select(AiQueryAssetColumnModel).where(
                        AiQueryAssetColumnModel.table_name == t,
                        AiQueryAssetColumnModel.column_name == c))
                ).scalar_one_or_none()
                if not exists:
                    db.add(AiQueryAssetColumnModel(table_name=t, column_name=c, description="",
                                                   included=True, sensitive=False,
                                                   created_id=auth.user.id, updated_id=auth.user.id))
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
                    .order_by(AiQueryFewshotModel.id)
                    .limit(300)
                )
            ).scalars().all()
        raw_q = re.findall(r"[\w\u4e00-\u9fa5]{2,}", question.lower())
        scored = []
        for f in rows:
            fq = f.question.lower()
            s = sum(1 for tok in raw_q if tok in fq)
            if f.datasource == datasource or datasource is None or datasource == SYSTEM_DS:
                s += 1
            scored.append((s, f))
        scored.sort(key=lambda x: -x[0])
        return [{"q": f.question, "sql": f.sql} for _, f in scored[:4]]

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
            "decomposed_planning": "true",           # 分解式规划提示(单表/联表/嵌套)
            "empty_self_correct": "true",            # 结果为空时自纠错重生成
            "agno_tool_agent": "true",               # 工具化 Agent(模型自主调用 schema/fewshots/cost)
            "kg_enabled": "true",                    # 知识图谱图遍历召回(补关联表/联表路径)
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
        v = str(cfg.get(key, "true")).strip().lower()
        if v in ("0", "false", "no", "off", ""):
            return False
        return default

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

    @classmethod
    async def list_roles(cls) -> list[dict]:
        """获取系统角色（用于数据源授权选择）。"""
        try:
            from app.api.v1.module_system.role.model import RoleModel

            async with async_db_session() as db:
                from sqlalchemy import select

                rows = (
                    await db.execute(
                        select(RoleModel).where(RoleModel.is_deleted.is_(False))
                        .order_by(RoleModel.id)
                        .limit(200)
                    )
                ).scalars().all()
                return [
                    {"id": r.id, "name": r.name, "code": getattr(r, "code", "") or r.name}
                    for r in rows
                ]
        except Exception as e:  # noqa: BLE001
            log.warning(f"[query] 获取角色列表失败: {e}")
            return []

    # ---- 数据源 ----
    @classmethod
    async def list_datasources(cls) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import select

            rows = (
                await db.execute(
                    select(AiQueryDatasourceModel)
                    .where(AiQueryDatasourceModel.is_deleted.is_(False))
                    .order_by(AiQueryDatasourceModel.id.desc())
                )
            ).scalars().all()
            return [
                {"id": d.id, "name": d.name, "code": d.code, "type": d.type,
                 "host": d.host, "port": d.port, "database": d.database,
                 "username": d.username, "read_only": d.read_only, "default": d.default,
                 "enabled": d.enabled, "allowed_roles": d.allowed_roles or [],
                 "remark": d.remark or ""}
                for d in rows
            ]

    @classmethod
    async def upsert_datasource(cls, data, auth) -> dict:
        # 密码加密由上层/前端处理，这里仅透传（演示环境明文存，生产应加密）
        async with async_db_session.begin() as db:
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
    async def list_messages(cls, session_id: int) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import select

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
    async def delete_session(cls, session_id: int) -> None:
        async with async_db_session.begin() as db:
            s = await db.get(AiQuerySessionModel, session_id)
            if s:
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
            "created_time": m.created_time,
        }

    # ---- 核心：问答入口 ----
    @classmethod
    async def ask(cls, question: str, auth, session_id: int | None = None,
                  datasource: str | None = None, redis=None, force_slow: bool = False) -> dict:
        """主入口：意图路由 → 快/慢路径 → 执行 → 落库。"""
        await cls.ensure_system_seed()
        question = (question or "").strip()
        if not question:
            raise CustomException(msg="请输入要查询的问题")

        sess = await cls.get_or_create_session(session_id, question[:30], auth)

        metrics = await cls.list_metrics(datasource or None)
        terms = await cls.list_terms(datasource or None)

        # 评测强制慢路径：跳过模板匹配，直接用 LLM 生成 SQL
        if force_slow:
            return await cls._slow_path(question, sess["id"], datasource or SYSTEM_DS, auth)

        # 列举类问题不走指标模板（快路径只认指标聚合），强制走 NL2SQL
        if not _is_listing_question(question):
            metric = _match_metric(question, metrics, terms)
        else:
            metric = None
        if metric:
            params = _build_params(metric, question)
            try:
                cache_key, cached, res = None, False, None
                ttl = metric.get("cache_ttl") or 0
                if redis and ttl:
                    cache_key = cls._cache_key(metric, params)
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
                    result_rows=len(res["rows"]), took_ms=res["took_ms"], cached=cached,
                    summary=cls._summarize(metric, res),
                )
                return cls._answer(msg, metric=metric)
            except CustomException as e:
                # 快路径执行失败 → 记录错误并尝试慢路径
                await cls._save_message(
                    sess["id"], question, path="fast", datasource=metric["datasource"],
                    sql=metric["sql_template"], rows=[], is_error=True,
                    summary=f"快路径执行失败：{e.msg}",
                )
                return await cls._slow_path(question, sess["id"], metric["datasource"], auth)

        # 慢路径
        return await cls._slow_path(question, sess["id"], datasource or SYSTEM_DS, auth)

    @staticmethod
    def _cache_key(metric: dict, params: dict) -> str:
        import hashlib
        import json

        raw = json.dumps(
            {"ds": metric.get("datasource"), "key": metric.get("key"),
             "params": sorted(params.items())},
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
        return await _execute_sql(sql)

    @classmethod
    async def _explain_rows(cls, sql: str) -> int:
        """EXPLAIN 预估结果行数（用于查询代价护栏）。"""
        from sqlalchemy import text as _t

        async with async_db_session() as db:
            row = (await db.execute(_t(f"EXPLAIN (FORMAT JSON) {sql.rstrip(';')}"))).scalar()
            plan = row[0] if isinstance(row, list) else row
            return int((plan.get("Plan") or {}).get("Plan Rows") or 0)

    @classmethod
    async def _slow_path(cls, question: str, session_id: int, datasource: str, auth) -> dict:
        """Agno 生成 SQL；自一致性多候选 + EXPLAIN 代价护栏 + 自纠错重试。"""
        cfg = await cls._cfg()
        n = cls._cfg_int(cfg, "self_consistency_n", 1)
        cost_enabled = cls._cfg_bool(cfg, "query_cost_enabled", True)
        max_rows = cls._cfg_int(cfg, "query_cost_max_rows", 50000)
        last_err: str | None = None
        sql = ""
        for attempt in range(2):
            candidate_sqls: list[str] = []
            try:
                for i in range(max(n, 1)):
                    # 自一致性：不同候选用不同温度增加多样性
                    temp = round(0.2 * i, 2) if n > 1 else 0.0
                    candidate_sqls.append(
                        await cls._nl2sql(question, datasource, prev_error=last_err, temperature=temp)
                    )
            except CustomException as e:
                last_err = e.msg
                log.warning(f"[query] NL2SQL 生成/校验失败第 {attempt + 1} 轮: {e.msg}")
                continue
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
                # 优先非空结果；多数一致组内取第一候选；全空则按多数
                if any(c[1]["rows"] for c in results):
                    nonempty_ids = {c for c, res in results if res["rows"]}
                    base = max((g for g in groups.values() if set(g) & nonempty_ids), key=len)
                    sql = base[0]
                else:
                    sql = max(groups.values(), key=len)[0]
                res = next(r for (c, r) in results if c == sql)
                # 执行反馈自纠错：结果为空且还有重试机会 → 携带空结果提示二次生成
                if not res["rows"] and attempt == 0 and cls._cfg_bool(cfg, "empty_self_correct", True):
                    last_err = "上一轮查询返回结果为空，可能是条件/表/字段选择不准确，请检查后再重新生成一条 SQL。"
                    continue
                msg = await cls._save_message(
                    session_id, question, path="slow", datasource=datasource,
                    sql=sql, columns=res["columns"], rows=res["rows"],
                    result_rows=len(res["rows"]), took_ms=res["took_ms"], cached=False,
                    summary="以下是根据你的问题生成的结果：",
                )
                return cls._answer(msg, sql=sql)
        await cls._save_message(
            session_id, question, path="slow", datasource=datasource,
            sql=sql, rows=[], is_error=True, summary=f"查询失败：{last_err}",
        )
        return {"path": "slow", "is_error": True, "answer": f"查询失败：{last_err}", "sql": sql}

    @classmethod
    async def _nl2sql(cls, question: str, datasource: str, prev_error: str | None = None,
                      temperature: float = 0.0) -> str:
        """Agno Agent 生成 SQL（慢路径）。prev_error 为上一次执行报错，用于自纠错。"""
        try:
            runtime = await cls._get_runtime()
        except Exception as e:  # noqa: BLE001
            raise CustomException(msg=f"未配置可用的问答模型：{e}")
        metrics = await cls.list_metrics(datasource or None)
        terms = await cls.list_terms(datasource or None)
        schema_ctx = await cls._build_schema_context(question, datasource, metrics, terms)
        cfg = await cls._cfg()
        rules = []
        if cls._cfg_bool(cfg, "entity_name_rule", True):
            rules.append("（1）问题要求按实体（摄像头/设备/算法/数据集/规则等）展示时，"
                         "应 JOIN 对应表用其「name」列，而不是直接返回外键 id；")
        if cls._cfg_bool(cfg, "enum_hint_enabled", True):
            rules.append("（2）status/framework/severity/task_type 等枚举字段必须使用【取值】里给出的原始值；")
        rules.append("（3）占比用“COUNT(*) * 100.0 / 总数”或“FILTER (WHERE ...)”计算；")
        rules.append("（4）多行 SQL 直接换行输出即可，不要加注释。")
        if cls._cfg_bool(cfg, "decomposed_planning", True):
            rules.append("（5）先判断问题属于「单表聚合 / 多表联查 / 嵌套子查询」，再按此规划生成 SQL；")
        extra = ""
        if cls._cfg_bool(cfg, "full_entity_no_limit", True):
            extra = ("注意：问题若要求列出/统计全量实体（每个摄像头/每台设备/每个数据集/每类…），"
                     "不要为了省事写 LIMIT 截断，应返回全部（系统最多保留 1000 行）。\n")
        system_prompt = (
            "你是 PostgreSQL 数据库查询助手。根据用户问题生成只读 SELECT 查询。"
            "必须使用 PostgreSQL 语法（日期用 CURRENT_DATE / date_trunc，别用 CURDATE）。"
            "必须写 FROM 子句并只使用给定的表/字段。只返回一条 SQL，不要多余解释，"
            "不要使用 DELETE/UPDATE/INSERT/DDL。\n注意：" + "".join(rules) + "\n" + extra
            + schema_ctx
        )
        user_msg = question
        if prev_error:
            user_msg = (
                f"{question}\n\n注意：你上次的 SQL 存在问题：\n{prev_error}\n"
                "请修正 SQL（补全 FROM、改用正确表/列名、修正条件）后重新只返回一条 SQL。"
            )
        try:
            from agno.agent import Agent
            from agno.models.openai.like import OpenAILike

            model = OpenAILike(
                id=runtime["model"], base_url=runtime["base_url"],
                api_key=runtime["api_key"] or "sk-none",
                temperature=temperature, max_tokens=2000,
            )
            tool_agent = cls._cfg_bool(cfg, "agno_tool_agent", True)
            if tool_agent:
                # 工具化 Agent：让模型自主决定何时调用 schema/fewshots/cost 工具
                from .agno_query_tools import QUERY_TOOLS

                agent = Agent(
                    model=model,
                    tools=list(QUERY_TOOLS),
                    tool_call_limit=6, instructions=(
                        "你是 PostgreSQL 数据库查询助手，生成只读 SELECT。"
                        "先调用 search_schema(question) 获取相关表/字段，必要时再调用 "
                        "get_fewshots(question) 参考样例、check_cost(候选SQL) 评估代价；"
                        "获取足够上下文后，最终消息必须直接输出一条 SELECT SQL（不要调用工具、不要多余解释）。"
                        "禁止 DELETE/UPDATE/INSERT/DDL。\n注意："
                        + "".join(rules)
                    ),
                )
            else:
                agent = Agent(model=model, instructions=system_prompt)
            resp = await agent.arun(user_msg)
            sql = (resp.content or "").strip()
            sql = cls._extract_sql(sql)
            table = SYSTEM_ALLOWED_TABLES if datasource in (SYSTEM_DS, None) else None
            try:
                return validate_sql(sql, table or set())
            except Exception:
                # 工具化模式若模型未取到 schema 导致校验失败，回退到提示版完整上下文重新生成
                if not tool_agent:
                    raise
                fallback = Agent(model=model, instructions=system_prompt)
                resp2 = await fallback.arun(user_msg)
                sql2 = cls._extract_sql((resp2.content or "").strip())
                return validate_sql(sql2, table or set())
        except Exception as e:  # noqa: BLE001
            raise CustomException(msg=f"问答模型(Agno)调用失败：{e}")

    @classmethod
    async def ask_stream(cls, question: str, auth, session_id: int | None = None,
                         datasource: str | None = None) -> None:
        """流式问数：产出思考过程/工具调用/输出/最终结果的事件（作为 SSE 下发）。

        事件类型：meta / reasoning_start / reasoning / reasoning_done /
        tool_start / tool_result / tool_error / sql_delta / sql_final /
        result / done / error / answer。
        """
        from .agno_query_tools import QUERY_TOOLS

        await cls.ensure_system_seed()
        question = (question or "").strip()
        if not question:
            yield {"type": "error", "message": "请输入要查询的问题"}
            return
        sess = await cls.get_or_create_session(session_id, question[:30], auth)
        datasource = datasource or SYSTEM_DS
        yield {"type": "meta", "session_id": sess["id"], "datasource": datasource,
               "question": question}

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
        if cls._cfg_bool(cfg, "decomposed_planning", True):
            rules.append("（5）先判断问题属于「单表聚合 / 多表联查 / 嵌套子查询」，再按此规划生成 SQL；")
        extra = ""
        if cls._cfg_bool(cfg, "full_entity_no_limit", True):
            extra = ("注意：问题若要求列出/统计全量实体（每个摄像头/每台设备/每个数据集/每类…），"
                     "不要为了省事写 LIMIT 截断，应返回全部（系统最多保留 1000 行）。\n")
        schema_ctx = await cls._build_schema_context(question, datasource,
                                                     await cls.list_metrics(datasource),
                                                     await cls.list_terms(datasource))
        system_prompt = (
            "你是 PostgreSQL 数据库查询助手。根据用户问题生成只读 SELECT 查询。"
            "必须使用 PostgreSQL 语法（日期用 CURRENT_DATE / date_trunc，别用 CURDATE）。"
            "必须写 FROM 子句并只使用给定的表/字段。只返回一条 SQL，不要多余解释，"
            "不要使用 DELETE/UPDATE/INSERT/DDL。\n注意：" + "".join(rules) + "\n" + extra
            + schema_ctx
        )

        from agno.agent import Agent
        from agno.models.openai.like import OpenAILike

        model = OpenAILike(
            id=runtime["model"], base_url=runtime["base_url"],
            api_key=runtime["api_key"] or "sk-none",
            temperature=0.0, max_tokens=2000,
        )
        if cls._cfg_bool(cfg, "agno_tool_agent", True):
            agent = Agent(
                model=model, tools=list(QUERY_TOOLS), tool_call_limit=6,
                instructions=(
                    "你是 PostgreSQL 数据库查询助手，生成只读 SELECT。"
                    "先调用 search_schema(question) 获取相关表/字段，可再用 "
                    "semantic_search(question) 做向量语义检索、table_metadata(表) 查看元数据标注、"
                    "get_fewshots(question) 参考样例、check_cost(候选SQL) 评估代价；"
                    "获取足够上下文后，最终消息必须直接输出一条 SELECT SQL（不要调用工具、不要多余解释）。"
                    "禁止 DELETE/UPDATE/INSERT/DDL。\n注意：" + "".join(rules)
                ),
            )
        else:
            agent = Agent(model=model, instructions=system_prompt)

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
        table = SYSTEM_ALLOWED_TABLES if datasource in (SYSTEM_DS, None) else None
        try:
            sql = validate_sql(sql, table or set())
        except Exception as e:  # noqa: BLE001
            yield {"type": "error", "message": f"SQL 校验失败：{e}"}
            return
        yield {"type": "sql_final", "sql": sql}

        # ---- 执行并返回结果 ----
        try:
            res = await cls._execute_one(sql, datasource, auth)
            cols = res.get("columns") or []
            rows = res.get("rows") or []
            await cls._save_message(
                sess["id"], question, path="slow", datasource=datasource,
                sql=sql, columns=cols, rows=rows,
                result_rows=len(rows), took_ms=res.get("took_ms", 0), cached=False,
                summary="以下是根据你的问题生成的结果：",
            )
            yield {"type": "result", "columns": cols, "rows": rows, "result_rows": len(rows)}
            yield {"type": "answer", "summary": "以下是根据你的问题生成的结果："}
            yield {"type": "done"}
        except Exception as e:  # noqa: BLE001
            await cls._save_message(sess["id"], question, path="slow", datasource=datasource,
                                    sql=sql, rows=[], is_error=True, summary=f"查询失败：{e}")
            yield {"type": "error", "message": f"查询失败：{e}"}
            return

    @classmethod
    def _extract_sql(cls, s: str) -> str:
        # 去除 markdown 代码块围栏
        s = re.sub(r"```[a-zA-Z]*", "", s or "").strip()
        # 取第一个 SELECT 开始
        idx = s.lower().find("select")
        if idx >= 0:
            s = s[idx:]
        # 截到第一个分号，保留多行 SQL（JOIN/GROUP BY/窗口函数通常跨行）
        s = re.split(r";", s, maxsplit=1)[0].strip()
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
                               terms: list[dict] | None = None) -> list[str]:
        """分层检索 + 关键词 + 实体表基线，合并出联表所需的表集合。

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
        return sorted(tables)[:top_k]

    @staticmethod
    def _relevant_tables(question: str, schema: dict, metrics: list[dict], terms: list[dict]) -> list[str]:
        """依据问题关键词，只挑相关的表（列名/表名命中），控制注入 token 并聚焦。"""
        q = question.lower()
        scores: dict[str, float] = {}
        for t in schema:
            s = 0.0
            tname = t.lower()
            if tname in q:
                s += 6.0
            for col in schema[t]:
                colname = col.split("(")[0].lower()
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
    async def _build_schema_context(cls, question: str, datasource: str, metrics: list[dict], terms: list[dict]) -> str:
        lines = ["【可用指标】"]
        for m in metrics:
            if m["enabled"]:
                lines.append(f"- {m['key']}: {m['name']} ({m['description']})")
        lines.append("【术语】")
        for t in terms:
            lines.append(f"- {t['term']} -> {t['metric_key'] or t['field_path']}")
        lines.append("【可查询表及字段】")
        if datasource in (SYSTEM_DS, None):
            schema = await cls._system_schema()
            tmeta = await cls._asset_tmeta()
            rel = await cls._semantic_tables(question, schema, metrics, terms)
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
        lines.append("【示例问题→SQL】")
        for eg in await cls._dynamic_fewshots(question, datasource):
            lines.append(f"问：{eg['q']}")
            lines.append(f"SQL：{eg['sql']}")
        return "\n".join(lines)

    @classmethod
    async def _get_runtime(cls) -> dict:
        from app.plugin.module_ai.provider.service import AiModelService

        runtime = await AiModelService.get_runtime_model("chat")
        runtime = runtime or await AiModelService.get_runtime_model()
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
            )
            db.add(m)
            await db.flush()
            return m

    @classmethod
    def _answer(cls, msg: AiQueryMessageModel, metric: dict | None = None, sql: str | None = None) -> dict:
        return {
            "id": msg.id, "session_id": msg.session_id, "path": msg.path,
            "datasource": msg.datasource, "sql": msg.sql or sql or "",
            "columns": msg.columns or [], "rows": msg.rows or [],
            "summary": msg.summary or "", "result_rows": msg.result_rows or 0,
            "took_ms": msg.took_ms or 0, "cached": msg.cached, "is_error": msg.is_error,
            "metric": metric,
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
    @classmethod
    async def feedback(cls, message_id: int, feedback: str, correct_sql: str | None, auth) -> dict:
        from sqlalchemy import select as _sel

        async with async_db_session.begin() as db:
            m = await db.get(AiQueryMessageModel, message_id)
            if not m:
                raise CustomException(msg="记录不存在")
            m.feedback = feedback
            m.updated_id = auth.user.id
            sunk = False
            if correct_sql and cls._cfg_bool(await cls._cfg(), "fewshot_auto_curate", True):
                # 校验正确 SQL 合法后才沉淀，避免把错误 SQL 推进 few-shot
                try:
                    validate_sql(correct_sql, SYSTEM_ALLOWED_TABLES)
                except Exception:  # noqa: BLE001
                    return {"id": m.id, "feedback": feedback, "sunk": False, "reason": "SQL 非法未入库"}
                m.correct_sql = correct_sql
                # 反馈闭环：把用户修正的正确 SQL 沉淀进示例库，后续可被动态 few-shot 复用
                exists = (
                    await db.execute(
                        _sel(AiQueryFewshotModel).where(
                            AiQueryFewshotModel.question == m.question,
                            AiQueryFewshotModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if not exists:
                    db.add(
                        AiQueryFewshotModel(
                            datasource=m.datasource, question=m.question,
                            sql=correct_sql, enabled=True,
                            created_id=auth.user.id, updated_id=auth.user.id,
                        )
                    )
                    sunk = True
            elif correct_sql:
                m.correct_sql = correct_sql
            await db.flush()
            return {"id": m.id, "feedback": feedback, "sunk": sunk}
