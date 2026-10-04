"""智能问数服务：语义层 + 快慢双路径 + 安全查询引擎 + 会话/反馈。

设计要点：
- 语义层(指标/术语/维度)是两条路径共享的知识底座。
- 高频问题命中指标模板 → 快路径(秒级)；未命中 → LLM NL2SQL 慢路径(精准兜底)。
- 所有执行只读 + 白名单表/字段 + 超时 + LIMIT，权限不可绕过。
"""
from __future__ import annotations

import re
import time
from typing import Any

from sqlalchemy import text

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log

from .model import (
    AiQueryDatasourceModel,
    AiQueryDictionaryModel,
    AiQueryMessageModel,
    AiQueryMetricModel,
    AiQuerySchemaModel,
    AiQuerySessionModel,
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
        "sql": "SELECT COALESCE(c.name,'未知') AS 摄像头, COUNT(r.id) AS 告警数 FROM video_cameras c LEFT JOIN video_alarm_records r ON r.camera_id=c.id GROUP BY 摄像头 ORDER BY 告警数 DESC LIMIT 50",
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
    # 限制行数
    if not re.search(r"\blimit\s+\d+", removed_semis, re.IGNORECASE):
        removed_semis = removed_semis + f" LIMIT {MAX_ROWS}"
    return removed_semis


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
    data = [list(r) for r in rows[:MAX_ROWS]]
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

        # 快路径匹配
        metric = _match_metric(question, metrics, terms)
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
    async def _slow_path(cls, question: str, session_id: int, datasource: str, auth) -> dict:
        """LLM 生成 SQL + 自纠错重试（最多 2 轮）。"""
        last_err: str | None = None
        sql = ""
        for attempt in range(2):
            sql = await cls._nl2sql(question, datasource, prev_error=last_err)
            try:
                if datasource and datasource != SYSTEM_DS:
                    try:
                        ds_id = int(datasource.split(":")[-1])
                    except ValueError:
                        raise CustomException(msg="数据源编码异常")
                    res = await _execute_custom_ds_sql(ds_id, sql, auth)
                else:
                    res = await _execute_sql(sql)
                msg = await cls._save_message(
                    session_id, question, path="slow", datasource=datasource,
                    sql=sql, columns=res["columns"], rows=res["rows"],
                    result_rows=len(res["rows"]), took_ms=res["took_ms"], cached=False,
                    summary="以下是根据你的问题生成的结果：",
                )
                return cls._answer(msg, sql=sql)
            except CustomException as e:
                last_err = e.msg
                log.warning(f"[query] NL2SQL 自纠错第 {attempt + 1} 轮失败: {e.msg}")
                continue
        await cls._save_message(
            session_id, question, path="slow", datasource=datasource,
            sql=sql, rows=[], is_error=True, summary=f"查询失败：{last_err}",
        )
        return {"path": "slow", "is_error": True, "answer": f"查询失败：{last_err}", "sql": sql}

    @classmethod
    async def _nl2sql(cls, question: str, datasource: str, prev_error: str | None = None) -> str:
        """LLM 生成 SQL（慢路径）。prev_error 为上一次执行报错，用于自纠错。"""
        try:
            runtime = await cls._get_runtime()
        except Exception as e:  # noqa: BLE001
            raise CustomException(msg=f"未配置可用的问答模型：{e}")
        metrics = await cls.list_metrics(datasource or None)
        terms = await cls.list_terms(datasource or None)
        schema_ctx = await cls._build_schema_context(datasource, metrics, terms)
        system_prompt = (
            "你是 PostgreSQL 数据库查询助手。根据用户问题生成只读 SELECT 查询。"
            "必须使用 PostgreSQL 语法（日期用 CURRENT_DATE / date_trunc，别用 CURDATE）。"
            "必须写 FROM 子句并只使用给定的表/字段。只返回一条 SQL，不要多余解释，"
            f"不要使用 DELETE/UPDATE/INSERT/DDL。\n{schema_ctx}"
        )
        user_msg = question
        if prev_error:
            user_msg = (
                f"{question}\n\n注意：你上次生成的 SQL 执行失败，错误如下：\n{prev_error}\n"
                "请修正 SQL（补全 FROM、改用正确表/列名）后重新只返回一条 SQL。"
            )
        try:
            from openai import AsyncOpenAI

            from app.plugin.module_ai.provider.service import build_headers

            client = AsyncOpenAI(
                base_url=runtime["base_url"],
                api_key=runtime["api_key"] or "sk-none",
                default_headers=build_headers(
                    runtime["base_url"], runtime.get("extra_headers"), "aistation-query"
                ),
            )
            resp = await client.chat.completions.create(
                model=runtime["model"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                max_tokens=1200,
            )
            sql = (resp.choices[0].message.content or "").strip()
        except Exception as e:  # noqa: BLE001
            raise CustomException(msg=f"问答模型调用失败：{e}")
        sql = cls._extract_sql(sql)
        table = SYSTEM_ALLOWED_TABLES if datasource in (SYSTEM_DS, None) else None
        return validate_sql(sql, table or set())

    @classmethod
    def _extract_sql(cls, s: str) -> str:
        # 去除 markdown 代码块
        s = re.sub(r"```(?:sql)?", "", s).strip()
        # 取第一个 SELECT 起到行尾
        idx = s.lower().find("select")
        if idx >= 0:
            s = s[idx:]
        s = s.split("\n")[0].strip()
        return s.rstrip(";")

    @staticmethod
    async def _system_schema() -> dict:
        """一次性拉取系统可查表的真实列（带类型），缓存到进程级，供 LLM 生成准确 SQL。"""
        global _SCHEMA_CACHE
        if _SCHEMA_CACHE is not None:
            return _SCHEMA_CACHE
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
        for t, c, ty in rows:
            if t in SYSTEM_ALLOWED_TABLES:
                schema.setdefault(t, []).append(f"{c}({ty})")
        _SCHEMA_CACHE = schema
        return schema

    @classmethod
    async def _build_schema_context(cls, datasource: str, metrics: list[dict], terms: list[dict]) -> str:
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
            for t in sorted(SYSTEM_ALLOWED_TABLES):
                cols = schema.get(t, [])
                lines.append(f"- {t}: {', '.join(cols) if cols else '(无列信息)'}")
        lines.append("【示例问题→SQL】")
        for eg in _NL2SQL_FEWSHOT:
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
        async with async_db_session.begin() as db:
            m = await db.get(AiQueryMessageModel, message_id)
            if not m:
                raise CustomException(msg="记录不存在")
            m.feedback = feedback
            m.updated_id = auth.user.id
            if correct_sql:
                m.correct_sql = correct_sql
                # 反向沉淀：若 slow 且用户给出正确 SQL，可据此新增/修正指标
            await db.flush()
            return {"id": m.id, "feedback": feedback}
