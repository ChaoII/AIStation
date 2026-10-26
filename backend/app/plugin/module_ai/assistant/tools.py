"""AI 助手工具：只读取数 + 导航 + 报告 + 待确认操作。

设计：不使用 NL→SQL；所有数据经受控只读查询/既有服务，避免注入。
变更类工具仅返回「待确认动作」，由前端二次确认后调用既有业务 API。
"""
from __future__ import annotations

import contextvars
from datetime import datetime

from sqlalchemy import desc, func, select

from app.core.database import async_db_session

#: 当前请求（Agent/应用运行）配置的问数数据源/场景，供 ai_query 工具读取
QUERY_DS_CONTEXT: contextvars.ContextVar[str] = contextvars.ContextVar(
    "query_datasource", default="system"
)

#: 当前对象上下文（``对象编码|实例主键``），供 ai_query 读取。
#: 对齐 Palantir Retrieval Context 的 Fixed Object Set：用户在某个对象上提问时，
#: 助手把该对象一并带给问数，用户不必重复说明「我说的是哪台摄像机」。
QUERY_OBJECT_CONTEXT: contextvars.ContextVar[str] = contextvars.ContextVar(
    "query_object", default=""
)

# 允许导航的系统页面（path -> 名称）
NAV_ALLOWLIST: dict[str, str] = {
    "/annotation/dataset": "数据集管理",
    "/annotation/task": "标注任务",
    "/annotation/stats": "工作量统计",
    "/train/task": "训练任务",
    "/train/repo": "模型仓库",
    "/train/eval": "模型评估",
    "/train/predict": "模型预测",
    "/train/deploy": "模型部署",
    "/video/live": "实时预览",
    "/video/camera": "相机管理",
    "/video/alarm": "告警管理",
    "/video/algorithm": "算法管理",
    "/video/deploy": "智能布控",
    "/video/edge": "边缘设备",
    "/ai/model": "模型配置",
    "/ai/report": "AI 报告",
}

TOOL_REGISTRY: dict[str, dict] = {}


def tool(name: str, description: str, parameters: dict, kind: str = "read"):
    """注册工具装饰器。"""

    def deco(fn):
        TOOL_REGISTRY[name] = {
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
            "fn": fn,
            "kind": kind,
        }
        return fn

    return deco


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
    }


# ---------------------------------------------------------------- 只读取数


@tool(
    "get_annotation_overview",
    "获取标注工作量总览（数据集数、任务数、图片数、标注数等）",
    _obj({}),
)
async def get_annotation_overview() -> dict:
    from app.api.v1.module_annotation.stats.service import StatsService

    return await StatsService.get_overview()


@tool(
    "get_dataset_stats",
    "获取某个数据集的详细统计",
    _obj({"dataset_id": {"type": "integer", "description": "数据集ID"}}, ["dataset_id"]),
)
async def get_dataset_stats(dataset_id: int) -> dict:
    from app.api.v1.module_annotation.stats.service import StatsService

    data = await StatsService.get_dataset_stats(dataset_id)
    return data or {"error": f"数据集 {dataset_id} 不存在"}


async def _rows(stmt, mapper, limit: int = 50) -> dict:
    """列表明细 + **真实总数**。

    为什么必须带 total：明细最多回 50 条（模型常传 limit=1000，整表回灌会撑爆上下文），
    但只给明细的话模型会把"返回了 50 条"当成"一共 50 个"，
    于是出现"数据集 50 个 / 273 个"这种自相矛盾的结论（实测踩过）。
    """
    async with async_db_session() as db:
        total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
        rows = (await db.execute(stmt.limit(max(1, min(limit, 50))))).scalars().all()
    items = [mapper(r) for r in rows]
    return {
        "total": int(total),
        "returned": len(items),
        "truncated": int(total) > len(items),
        "items": items,
    }


@tool("list_datasets", "列出数据集（ID/名称/图片数/时间）（返回 total=真实总数，items 最多 50 条明细）", _obj({"limit": {"type": "integer"}}))
async def list_datasets(limit: int = 50) -> dict:
    from app.api.v1.module_annotation.dataset.model import DatasetModel

    return await _rows(
        select(DatasetModel).where(DatasetModel.is_deleted.is_(False)).order_by(desc(DatasetModel.id)),
        lambda r: {
            "id": r.id,
            "name": r.name,
            "image_count": getattr(r, "image_count", None),
            "status": r.status,
        },
        limit,
    )


@tool("list_annotation_tasks", "列出标注任务（返回 total=真实总数，items 最多 50 条明细）", _obj({"limit": {"type": "integer"}}))
async def list_annotation_tasks(limit: int = 50) -> dict:
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel

    return await _rows(
        select(AnnotationTaskModel)
        .where(AnnotationTaskModel.is_deleted.is_(False))
        .order_by(desc(AnnotationTaskModel.id)),
        lambda r: {"id": r.id, "name": r.name, "task_type": r.task_type, "status": r.status},
        limit,
    )


@tool("list_train_tasks", "列出训练任务（返回 total=真实总数，items 最多 50 条明细）", _obj({"limit": {"type": "integer"}}))
async def list_train_tasks(limit: int = 50) -> dict:
    from app.plugin.module_train.model import TrainTask

    return await _rows(
        select(TrainTask).where(TrainTask.is_deleted.is_(False)).order_by(desc(TrainTask.id)),
        lambda r: {
            "id": r.id,
            "name": r.name,
            "framework": r.framework,
            "status": r.status,
            "progress": r.progress,
        },
        limit,
    )


@tool(
    "list_models",
    "列出**训练产出的模型**（模型仓库/版本，训练任务的结果文件）。"
    "注意：问「平台配置了哪些大模型 / 模型供应商下的模型」请用 list_ai_models。",
    _obj({"limit": {"type": "integer"}}),
)
async def list_models(limit: int = 50) -> dict:
    from app.plugin.module_train.model import TrainModel

    return await _rows(
        select(TrainModel).where(TrainModel.is_deleted.is_(False)).order_by(desc(TrainModel.id)),
        lambda r: {
            "id": r.id,
            "name": r.name,
            "version": r.version,
            "framework": r.framework,
            "status": r.status,
        },
        limit,
    )


@tool(
    "list_ai_models",
    "列出**平台已配置的大模型**（模型供应商下的模型配置，含用途/上下文长度）。"
    "问「系统有多少个大模型 / 有哪些模型可用」用这个；训练产出的模型用 list_models。",
    _obj({"limit": {"type": "integer"}}),
)
async def list_ai_models(limit: int = 50) -> dict:
    from app.plugin.module_ai.models.model import AiModelModel

    return await _rows(
        select(AiModelModel)
        .where(AiModelModel.is_deleted.is_(False))
        .order_by(desc(AiModelModel.id)),
        lambda r: {
            "id": r.id,
            "name": r.name,
            "usage": r.usage,
            "context_window": r.context_window,
        },
        limit,
    )


@tool("list_evals", "列出模型评估记录（返回 total=真实总数，items 最多 50 条明细）", _obj({"limit": {"type": "integer"}}))
async def list_evals(limit: int = 50) -> dict:
    from app.plugin.module_train.model import TrainEval

    return await _rows(
        select(TrainEval).where(TrainEval.is_deleted.is_(False)).order_by(desc(TrainEval.id)),
        lambda r: {
            "id": r.id,
            "model_id": r.model_id,
            "status": r.status,
            "metrics": r.metrics,
        },
        limit,
    )


@tool("list_predicts", "列出批量预测任务（返回 total=真实总数，items 最多 50 条明细）", _obj({"limit": {"type": "integer"}}))
async def list_predicts(limit: int = 50) -> dict:
    from app.plugin.module_train.model import TrainPredict

    return await _rows(
        select(TrainPredict).where(TrainPredict.is_deleted.is_(False)).order_by(desc(TrainPredict.id)),
        lambda r: {"id": r.id, "model_id": r.model_id, "status": r.status},
        limit,
    )


@tool("list_deploys", "列出模型部署（返回 total=真实总数，items 最多 50 条明细）", _obj({"limit": {"type": "integer"}}))
async def list_deploys(limit: int = 50) -> dict:
    from app.plugin.module_train.model import TrainDeploy

    return await _rows(
        select(TrainDeploy).where(TrainDeploy.is_deleted.is_(False)).order_by(desc(TrainDeploy.id)),
        lambda r: {"id": r.id, "name": r.name, "status": r.status, "host_port": r.host_port},
        limit,
    )


@tool("list_cameras", "列出摄像头（返回 total=真实总数，items 最多 50 条明细）", _obj({"limit": {"type": "integer"}}))
async def list_cameras(limit: int = 50) -> dict:
    from app.api.v1.module_video.camera.model import CameraModel

    return await _rows(
        select(CameraModel).where(CameraModel.is_deleted.is_(False)).order_by(desc(CameraModel.id)),
        lambda r: {"id": r.id, "name": r.name, "status": r.status},
        limit,
    )


@tool("list_algorithm_tasks", "列出视频布控任务（返回 total=真实总数，items 最多 50 条明细）", _obj({"limit": {"type": "integer"}}))
async def list_algorithm_tasks(limit: int = 50) -> dict:
    from app.api.v1.module_video.algorithm.model import AlgorithmTaskModel

    return await _rows(
        select(AlgorithmTaskModel)
        .where(AlgorithmTaskModel.is_deleted.is_(False))
        .order_by(desc(AlgorithmTaskModel.id)),
        lambda r: {"id": r.id, "camera_id": r.camera_id, "status": r.status},
        limit,
    )


@tool("list_alarm_records", "列出最近告警记录（返回 total=真实总数，items 最多 50 条明细）", _obj({"limit": {"type": "integer"}}))
async def list_alarm_records(limit: int = 50) -> dict:
    from app.api.v1.module_video.alarm.model import AlarmRecordModel

    return await _rows(
        select(AlarmRecordModel).order_by(desc(AlarmRecordModel.id)),
        lambda r: {
            "id": r.id,
            "camera_id": r.camera_id,
            "alarm_type": r.alarm_type,
            "severity": r.severity,
            "status": r.status,
            "alarm_time": r.alarm_time,
        },
        limit,
    )


@tool(
    "ai_query",
    "智能问数：把自然语言业务问题转成 SQL 并返回数据结果（表格/汇总）。"
    "用于回答基于系统数据的统计、占比、趋势、排名等问题，例如「今天告警数」「各类型告警占比」。",
    _obj({"question": {"type": "string", "description": "自然语言数据问题"}}, ["question"]),
    kind="read",
)
async def ai_query(question: str, user_id: int | None = None) -> dict:
    from types import SimpleNamespace

    from app.plugin.module_ai.query.service import AiQueryService

    auth = SimpleNamespace(user=SimpleNamespace(id=user_id))
    datasource = QUERY_DS_CONTEXT.get() or "system"
    # 当前对象上下文（``编码|主键``）；缺省为空 → 与旧行为完全一致
    _ocode, _, _okey = (QUERY_OBJECT_CONTEXT.get() or "").partition("|")
    try:
        res = await AiQueryService.ask(question, auth, None, datasource,
                                       object_code=_ocode or None,
                                       object_key=_okey or None)
    except Exception as e:  # noqa: BLE001
        return {"question": question, "error": str(getattr(e, "msg", e))}
    return {
        "question": question,
        "datasource": datasource,
        "columns": res.get("columns") or [],
        "rows": res.get("rows") or [],
        "sql": res.get("sql") or "",
        "summary": res.get("summary") or "",
    }


@tool(
    "resolve_object",
    "解析业务对象：根据业务实体名(如 摄像头/订单/设备/用户)和关键值，返回该对象的真实字段及关联邻居。"
    "用于回答「某个具体对象」的问题，如「摄像头0012341247是什么状态」，先调用本工具取真实对象，不要凭记忆编造。",
    _obj({"entity": {"type": "string", "description": "业务实体名，如 摄像头/订单/用户/算法"},
          "key": {"type": "string", "description": "对象关键值，如 摄像头编号/订单号/名称"}},
         ["entity", "key"]),
    kind="read",
)
async def resolve_object(entity: str, key: str, user_id: int | None = None) -> dict:
    from app.plugin.module_ai.query.service import AiQueryService

    try:
        res = await AiQueryService.resolve_entity_object(entity, key, user_id=user_id)
    except Exception as e:  # noqa: BLE001
        return {"entity": entity, "error": str(getattr(e, "msg", e))}
    if not res:
        return {"entity": entity, "error": "未找到对应业务对象，请确认实体名或改用 ai_query 问数"}
    return res


# ---------------------------------------------------------------- 报告 / 导航 / 操作


@tool(
    "generate_report",
    "基于系统数据生成一份 Markdown 报告并保存，返回 report_id",
    _obj(
        {
            "topic": {"type": "string", "description": "报告主题"},
            "scope": {
                "type": "string",
                "description": "范围关键词：annotation/train/video/all",
            },
        },
        ["topic"],
    ),
    kind="report",
)
async def generate_report(topic: str, scope: str = "all", user_id: int | None = None) -> dict:
    from app.plugin.module_ai.report.service import AiReportService

    lines = [f"# {topic}", "", f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
    source: dict = {"topic": topic, "scope": scope}

    if scope in ("annotation", "all"):
        try:
            ov = await get_annotation_overview()
            lines += ["## 标注概览", ""]
            for k, v in (ov or {}).items():
                lines.append(f"- {k}: {v}")
            lines.append("")
            source["annotation"] = ov
        except Exception as e:
            lines.append(f"（标注概览获取失败：{e}）\n")

    if scope in ("train", "all"):
        try:
            tasks = await list_train_tasks(10)
            lines += ["## 训练任务（最近 10 条）", "", "| ID | 名称 | 框架 | 状态 | 进度 |", "|---|---|---|---|---|"]
            for t in tasks:
                lines.append(
                    f"| {t.get('id')} | {t.get('name')} | {t.get('framework')} | {t.get('status')} | {t.get('progress')} |"
                )
            lines.append("")
            source["train_tasks"] = tasks
        except Exception as e:
            lines.append(f"（训练任务获取失败：{e}）\n")

    if scope in ("video", "all"):
        try:
            alarms = await list_alarm_records(10)
            lines += ["## 近期告警（最近 10 条）", "", "| ID | 相机 | 类型 | 级别 | 状态 |", "|---|---|---|---|---|"]
            for a in alarms:
                lines.append(
                    f"| {a.get('id')} | {a.get('camera_id')} | {a.get('alarm_type')} | {a.get('severity')} | {a.get('status')} |"
                )
            lines.append("")
            source["alarms"] = alarms
        except Exception as e:
            lines.append(f"（告警获取失败：{e}）\n")

    content = "\n".join(lines)
    saved = await AiReportService.create(topic, content, source, user_id)
    return {"__report_id__": saved["id"], "title": topic, "preview": content[:600]}


@tool(
    "navigate",
    "生成跳转动作，让前端导航到指定系统页面",
    _obj(
        {
            "path": {"type": "string", "description": "目标路由，如 /train/task"},
            "reason": {"type": "string", "description": "跳转原因"},
        },
        ["path"],
    ),
    kind="action",
)
async def navigate(path: str, reason: str = "") -> dict:
    if path not in NAV_ALLOWLIST:
        return {"error": f"不支持的页面：{path}", "allowed": list(NAV_ALLOWLIST.keys())}
    return {"__action__": {"type": "navigate", "path": path, "label": NAV_ALLOWLIST[path], "reason": reason}}


@tool(
    "propose_create_dataset",
    "提议创建数据集（需用户确认后由前端执行）",
    _obj({"name": {"type": "string"}}, ["name"]),
    kind="action",
)
async def propose_create_dataset(name: str) -> dict:
    return {
        "__action__": {
            "type": "confirm",
            "api": "createDataset",
            "label": f"创建数据集「{name}」",
            "payload": {"name": name},
        }
    }


@tool(
    "propose_create_annotation_task",
    "提议创建标注任务（需用户确认后由前端执行）",
    _obj(
        {
            "dataset_id": {"type": "integer"},
            "name": {"type": "string"},
            "task_type": {"type": "string"},
        },
        ["dataset_id", "name"],
    ),
    kind="action",
)
async def propose_create_annotation_task(
    dataset_id: int, name: str, task_type: str = "detection"
) -> dict:
    return {
        "__action__": {
            "type": "confirm",
            "api": "createAnnotationTask",
            "label": f"创建标注任务「{name}」",
            "payload": {"dataset_id": dataset_id, "name": name, "task_type": task_type},
        }
    }


# ---------------------------------------------------------------- 通用能力（内置工具）

# 说明：原先挂在「能力插件」下的 web_fetch / table_export 本质是内置工具，
# 现统一注册为内置工具（能力插件=能力包，见 market/seed.py 的 bundle）。


@tool(
    "web_fetch",
    "抓取指定 URL 的网页正文文本（只读，返回前 4000 字）",
    _obj({"url": {"type": "string", "description": "要抓取的网页地址"}}, ["url"]),
)
async def web_fetch(url: str) -> object:
    from app.plugin.module_ai.plugins.plugin_executor import run_web_fetch

    return await run_web_fetch({"url": url})


@tool(
    "table_export",
    "把结构化数据导出为 CSV 文本（不落盘，直接返回内容）",
    _obj(
        {
            "rows": {
                "type": "array",
                "description": "行数据，元素为对象（键为列名）",
                "items": {"type": "object"},
            },
            "columns": {
                "type": "array",
                "description": "列顺序（可选，缺省取首行的键）",
                "items": {"type": "string"},
            },
        },
        ["rows"],
    ),
)
async def table_export(rows: list, columns: list | None = None) -> object:
    from app.plugin.module_ai.plugins.plugin_executor import run_table_export

    return await run_table_export({"rows": rows, "columns": columns or []})


@tool(
    "email_send",
    "通过平台 SMTP 发送邮件给指定收件人（需平台已配置 SMTP）",
    _obj(
        {
            "to": {"type": "string", "description": "收件人邮箱，多个用逗号分隔"},
            "subject": {"type": "string", "description": "邮件主题"},
            "body": {"type": "string", "description": "邮件正文"},
        },
        ["to"],
    ),
)
async def email_send(to: str, subject: str = "", body: str = "", user_id: int | None = None) -> object:
    from app.plugin.module_ai.plugins.plugin_executor import run_email_send

    return await run_email_send({"to": to, "subject": subject, "body": body})


@tool(
    "report_generate",
    "把内容保存为结构化报告，返回 report_id",
    _obj(
        {
            "title": {"type": "string", "description": "报告标题"},
            "content": {"type": "string", "description": "报告正文（Markdown）"},
        },
        ["title"],
    ),
)
async def report_generate(title: str, content: str = "", user_id: int | None = None) -> object:
    from app.plugin.module_ai.plugins.plugin_executor import run_report_generate

    return await run_report_generate({"title": title, "content": content}, user_id=user_id)


@tool(
    "data_pipeline",
    "运行指定数据管道（ELT：拉取外部数据落库到目标对象）",
    _obj(
        {"pipeline_id": {"type": "integer", "description": "数据管道 ID"}},
        ["pipeline_id"],
    ),
)
async def data_pipeline(pipeline_id: int, user_id: int | None = None) -> object:
    from app.plugin.module_ai.plugins.plugin_executor import run_data_pipeline

    return await run_data_pipeline({"pipeline_id": pipeline_id})


# ---------------------------------------------------------------- 个人工作空间


@tool(
    "workspace_save_file",
    "把一段文本/代码/报告保存到用户的个人工作空间，返回文件ID与名称。"
    "适合保存输出结果、报告草稿、数据摘要等给用户留档。",
    _obj(
        {
            "name": {"type": "string", "description": "文件名（含扩展名，如 report.md / data.csv）"},
            "content": {"type": "string", "description": "文件内容（UTF-8 文本）"},
            "file_type": {"type": "string", "description": "可选：md/txt/csv/json 等；文件名无扩展名时用于补全"},
        },
        ["name", "content"],
    ),
    kind="action",
)
async def workspace_save_file(
    name: str, content: str, file_type: str | None = None, user_id: int | None = None
) -> dict:
    from app.plugin.module_ai.space.service import SpaceService

    try:
        result = await SpaceService.save_agent_file(user_id, name, content, file_type)
        return {
            "file_id": result["id"],
            "name": result["name"],
            "size": result["size"],
        }
    except Exception as exc:  # noqa: BLE001 工具失败以 error 返回，不阻断对话
        return {"error": f"保存到个人空间失败：{str(getattr(exc, 'msg', exc))[:200]}"}


@tool(
    "workspace_list_files",
    "列出用户个人工作空间中的文件（可按关键词过滤），返回文件ID、名称、类型、大小，"
    "供后续读取或引用。",
    _obj(
        {
            "keyword": {"type": "string", "description": "可选：文件名关键词"},
            "limit": {"type": "integer", "description": "可选：最多返回条数（默认20，最多50）"},
        },
    ),
    kind="read",
)
async def workspace_list_files(
    keyword: str | None = None, limit: int = 20, user_id: int | None = None
) -> list[dict]:
    from app.plugin.module_ai.space.service import SpaceService

    try:
        return await SpaceService.list_for_agent(user_id, keyword=keyword, limit=limit)
    except Exception as exc:  # noqa: BLE001
        return [{"error": f"查询个人空间失败：{str(getattr(exc, 'msg', exc))[:200]}"}]


@tool(
    "workspace_read_file",
    "读取用户在个人工作空间中某个文件的内容（文本类原文；PDF/Word 自动抽取文字；"
    "图片不支持文本读取）。超长内容会被截断。",
    _obj(
        {"file_id": {"type": "integer", "description": "文件ID（来自 workspace_list_files）"}},
        ["file_id"],
    ),
    kind="read",
)
async def workspace_read_file(file_id: int, user_id: int | None = None) -> str:
    from app.plugin.module_ai.space.service import SpaceService

    try:
        return await SpaceService.read_for_agent(user_id, file_id)
    except Exception as exc:  # noqa: BLE001
        return f"读取失败：{str(getattr(exc, 'msg', exc))[:200]}"


TOOL_SCHEMAS = [t["schema"] for t in TOOL_REGISTRY.values()]
