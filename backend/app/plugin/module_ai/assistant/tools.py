"""AI 助手工具：只读取数 + 导航 + 报告 + 待确认操作。

设计：不使用 NL→SQL；所有数据经受控只读查询/既有服务，避免注入。
变更类工具仅返回「待确认动作」，由前端二次确认后调用既有业务 API。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, select

from app.core.database import async_db_session

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


async def _rows(stmt, mapper, limit: int = 50) -> list[dict]:
    async with async_db_session() as db:
        rows = (await db.execute(stmt.limit(max(1, min(limit, 100))))).scalars().all()
    return [mapper(r) for r in rows]


@tool("list_datasets", "列出数据集（ID/名称/图片数/时间）", _obj({"limit": {"type": "integer"}}))
async def list_datasets(limit: int = 50) -> list[dict]:
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


@tool("list_annotation_tasks", "列出标注任务", _obj({"limit": {"type": "integer"}}))
async def list_annotation_tasks(limit: int = 50) -> list[dict]:
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel

    return await _rows(
        select(AnnotationTaskModel)
        .where(AnnotationTaskModel.is_deleted.is_(False))
        .order_by(desc(AnnotationTaskModel.id)),
        lambda r: {"id": r.id, "name": r.name, "task_type": r.task_type, "status": r.status},
        limit,
    )


@tool("list_train_tasks", "列出训练任务", _obj({"limit": {"type": "integer"}}))
async def list_train_tasks(limit: int = 50) -> list[dict]:
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


@tool("list_models", "列出模型仓库/版本", _obj({"limit": {"type": "integer"}}))
async def list_models(limit: int = 50) -> list[dict]:
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


@tool("list_evals", "列出模型评估记录", _obj({"limit": {"type": "integer"}}))
async def list_evals(limit: int = 50) -> list[dict]:
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


@tool("list_predicts", "列出批量预测任务", _obj({"limit": {"type": "integer"}}))
async def list_predicts(limit: int = 50) -> list[dict]:
    from app.plugin.module_train.model import TrainPredict

    return await _rows(
        select(TrainPredict).where(TrainPredict.is_deleted.is_(False)).order_by(desc(TrainPredict.id)),
        lambda r: {"id": r.id, "model_id": r.model_id, "status": r.status},
        limit,
    )


@tool("list_deploys", "列出模型部署", _obj({"limit": {"type": "integer"}}))
async def list_deploys(limit: int = 50) -> list[dict]:
    from app.plugin.module_train.model import TrainDeploy

    return await _rows(
        select(TrainDeploy).where(TrainDeploy.is_deleted.is_(False)).order_by(desc(TrainDeploy.id)),
        lambda r: {"id": r.id, "name": r.name, "status": r.status, "host_port": r.host_port},
        limit,
    )


@tool("list_cameras", "列出摄像头", _obj({"limit": {"type": "integer"}}))
async def list_cameras(limit: int = 50) -> list[dict]:
    from app.api.v1.module_video.camera.model import CameraModel

    return await _rows(
        select(CameraModel).where(CameraModel.is_deleted.is_(False)).order_by(desc(CameraModel.id)),
        lambda r: {"id": r.id, "name": r.name, "status": r.status},
        limit,
    )


@tool("list_algorithm_tasks", "列出视频布控任务", _obj({"limit": {"type": "integer"}}))
async def list_algorithm_tasks(limit: int = 50) -> list[dict]:
    from app.api.v1.module_video.algorithm.model import AlgorithmTaskModel

    return await _rows(
        select(AlgorithmTaskModel)
        .where(AlgorithmTaskModel.is_deleted.is_(False))
        .order_by(desc(AlgorithmTaskModel.id)),
        lambda r: {"id": r.id, "camera_id": r.camera_id, "status": r.status},
        limit,
    )


@tool("list_alarm_records", "列出最近告警记录", _obj({"limit": {"type": "integer"}}))
async def list_alarm_records(limit: int = 50) -> list[dict]:
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


TOOL_SCHEMAS = [t["schema"] for t in TOOL_REGISTRY.values()]
