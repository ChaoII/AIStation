"""开放面能力 handler —— 训练任务（train 品类）。

复用 ``TrainService``：开放面创建的训练任务打 ``source_app_id`` 归属，
查询/启停只能作用于**本应用**创建的任务（跨应用 → 404）。退场框架
（ultralytics / paddlex）由 ``retired.ensure_active`` 拒绝，文案原样透出。
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import CustomException
from app.plugin.module_train.schema import TrainTaskCreateSchema
from app.plugin.module_train.service import TrainService

from ..auth import AppContext
from ..registry import Capability, register

_OPEN_AUTH = SimpleNamespace(user=None)


def _bad_request(exc: ValidationError) -> CustomException:
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(p) for p in first.get("loc", ()))
    return CustomException(
        msg=f"参数不合法：{loc} {first.get('msg', '')}".strip(), code=10400, status_code=400
    )


def _need_int(payload: dict, key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CustomException(msg=f"参数不合法：{key} 必须为整数", code=10400, status_code=400)
    return value


async def _train_list(*, app_ctx: AppContext, payload: dict) -> dict:
    params = {"source_app_id": app_ctx.app_id}
    if isinstance(payload.get("status"), str) and payload["status"]:
        params["status"] = payload["status"]
    if isinstance(payload.get("page_no"), int):
        params["page_no"] = payload["page_no"]
    if isinstance(payload.get("page_size"), int):
        params["page_size"] = payload["page_size"]
    items, total = await TrainService.list_tasks(params)
    return {"items": items, "total": total}


async def _train_get(*, app_ctx: AppContext, payload: dict) -> dict:
    task_id = _need_int(payload, "task_id")
    task = await TrainService.get_task(task_id, source_app_id=app_ctx.app_id)
    if task is None:
        raise CustomException(msg="训练任务不存在", code=10404, status_code=404)
    task.pop("metrics_log", None)  # 逐步指标不进开放面响应（体积大）
    return task


async def _ensure_dataset(dataset_id: int) -> None:
    """校验数据集存在且未删除（否则开放面会创建出指向不存在数据集的训练任务）。"""
    from app.api.v1.module_annotation.dataset.model import DatasetModel
    from app.core.database import async_db_session

    async with async_db_session() as db:
        row = await db.get(DatasetModel, dataset_id)
    if row is None or getattr(row, "is_deleted", False):
        raise CustomException(msg="数据集不存在", code=10404, status_code=404)


async def _ensure_related(data) -> None:
    """校验关联的标注任务 / 基础模型存在（可选字段，传了就必须存在）。"""
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel
    from app.core.database import async_db_session
    from app.plugin.module_train.model import TrainModel

    async with async_db_session() as db:
        if getattr(data, "annotation_task_id", None):
            row = await db.get(AnnotationTaskModel, data.annotation_task_id)
            if row is None or getattr(row, "is_deleted", False):
                raise CustomException(msg="标注任务不存在", code=10404, status_code=404)
        if getattr(data, "base_model_id", None):
            row = await db.get(TrainModel, data.base_model_id)
            if row is None:
                raise CustomException(msg="基础模型不存在", code=10404, status_code=404)


async def _train_create(*, app_ctx: AppContext, payload: dict) -> dict:
    body = {
        k: v
        for k, v in payload.items()
        if k in {"name", "framework", "dataset_id", "annotation_task_id", "base_model_id", "hyperparams"}
    }
    try:
        data = TrainTaskCreateSchema(**body)
    except ValidationError as exc:
        raise _bad_request(exc) from exc
    # 退场框架（ultralytics / paddlex）当场拒绝，给出与平台内部一致的明确文案
    from app.plugin.module_train.retired import is_retired, retired_message

    if is_retired(data.framework):
        raise CustomException(msg=retired_message(data.framework, "训练"), code=10400, status_code=400)
    await _ensure_dataset(data.dataset_id)
    await _ensure_related(data)
    result = await TrainService.create_task(data, _OPEN_AUTH, source_app_id=app_ctx.app_id)
    return {"task_id": result["id"], "source_app_id": app_ctx.app_id}


async def _own_task(app_ctx: AppContext, task_id: int) -> dict:
    task = await TrainService.get_task(task_id, source_app_id=app_ctx.app_id)
    if task is None:
        raise CustomException(msg="训练任务不存在", code=10404, status_code=404)
    return task


async def _train_start(*, app_ctx: AppContext, payload: dict) -> dict:
    task_id = _need_int(payload, "task_id")
    await _own_task(app_ctx, task_id)
    from app.plugin.module_train.scheduler import start_training

    await start_training(task_id)
    return {"task_id": task_id, "status": "running"}


async def _train_stop(*, app_ctx: AppContext, payload: dict) -> dict:
    task_id = _need_int(payload, "task_id")
    await _own_task(app_ctx, task_id)
    result = await TrainService.stop_task(task_id)
    return {"task_id": task_id, "result": result}


def register_train_capabilities() -> None:
    """注册 train 品类能力。"""
    defs: list[tuple[str, str, str, str, dict, str, Any, str]] = [
        (
            "train.list",
            "integration:train:query",
            "查询训练任务",
            "列出本应用创建的训练任务",
            {
                "type": "object",
                "properties": {
                    "status": {"type": "string"},
                    "page_no": {"type": "integer"},
                    "page_size": {"type": "integer"},
                },
            },
            "items: array, total: int",
            _train_list,
            "train_list",
        ),
        (
            "train.get",
            "integration:train:query",
            "查询训练任务详情",
            "按 ID 查询本应用创建的训练任务（跨应用 404）",
            {
                "type": "object",
                "properties": {"task_id": {"type": "integer"}},
                "required": ["task_id"],
            },
            "训练任务对象",
            _train_get,
            "train_get",
        ),
        (
            "train.create",
            "integration:train:create",
            "创建训练任务",
            "创建一个归属本应用的训练任务（退场框架会被拒绝）",
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "framework": {"type": "string"},
                    "dataset_id": {"type": "integer"},
                    "annotation_task_id": {"type": "integer"},
                    "base_model_id": {"type": "integer"},
                    "hyperparams": {"type": "object"},
                },
                "required": ["name", "framework", "dataset_id"],
            },
            "task_id: int, source_app_id: int",
            _train_create,
            "train_create",
        ),
        (
            "train.start",
            "integration:train:start",
            "启动训练任务",
            "启动本应用创建的训练任务",
            {
                "type": "object",
                "properties": {"task_id": {"type": "integer"}},
                "required": ["task_id"],
            },
            "task_id: int, status: str",
            _train_start,
            "train_start",
        ),
        (
            "train.stop",
            "integration:train:stop",
            "停止训练任务",
            "停止本应用创建的训练任务",
            {
                "type": "object",
                "properties": {"task_id": {"type": "integer"}},
                "required": ["task_id"],
            },
            "task_id: int, result: object",
            _train_stop,
            "train_stop",
        ),
    ]
    for code, perm, name, desc, schema, returns, handler, tool in defs:
        register(
            Capability(
                code=code,
                category="train",
                perm=perm,
                name=name,
                description=desc,
                input_schema=schema,
                returns=returns,
                handler=handler,
                mcp_tool=tool,
                # 训练任务创建/启停消耗 GPU 与容器资源：应用开启 requires_approval 时先走审批
                requires_approval=code in {"train.create", "train.start", "train.stop"},
            )
        )
