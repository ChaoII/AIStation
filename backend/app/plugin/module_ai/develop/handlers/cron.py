"""开放面能力 handler —— 定时任务（cron 品类）。

复用 ``WorkspaceService`` 的定时任务 CRUD 与运行。调度执行消耗资源，删/跑置
``requires_approval``。
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..registry import Capability, register
from ._common import OPEN_AUTH, bad_request, need_int, not_found, require_confirm


async def _cron_list(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.workspace.service import WorkspaceService

    result = await WorkspaceService.list_cron()
    items = result.get("items", []) if isinstance(result, dict) else result
    return {"items": items, "total": len(items)}


async def _cron_create(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.workspace.schema import WorkspaceCronCreateSchema
    from app.plugin.module_ai.workspace.service import WorkspaceService

    try:
        data = WorkspaceCronCreateSchema(**payload)
    except ValidationError as exc:
        raise bad_request(exc) from exc
    return await WorkspaceService.create_cron(data, OPEN_AUTH)


async def _cron_update(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.workspace.schema import WorkspaceCronUpdateSchema
    from app.plugin.module_ai.workspace.service import WorkspaceService

    cron_id = need_int(payload, "cron_id")
    try:
        data = WorkspaceCronUpdateSchema(**{k: v for k, v in payload.items() if k != "cron_id"})
    except ValidationError as exc:
        raise bad_request(exc) from exc
    row = await WorkspaceService.update_cron(cron_id, data, OPEN_AUTH)
    if row is None:
        raise not_found("定时任务")
    return row


async def _cron_delete(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.workspace.service import WorkspaceService

    cron_id = need_int(payload, "cron_id")
    require_confirm(payload, "删除定时任务")
    await WorkspaceService.delete_cron(cron_id, OPEN_AUTH)
    return {"deleted": cron_id}


async def _cron_run(*, app_ctx: Any, payload: dict) -> dict:
    # run_scheduled_workspace_cron 为模块级函数（非类方法），直接 await 执行（与调度器同路径）。
    from app.plugin.module_ai.workspace.service import run_scheduled_workspace_cron

    cron_id = need_int(payload, "cron_id")
    await run_scheduled_workspace_cron(cron_id)
    return {"cron_id": cron_id, "status": "queued"}


async def _cron_runs(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.workspace.service import WorkspaceService

    cron_id = need_int(payload, "cron_id")
    limit = payload.get("limit", 50)
    items = await WorkspaceService.list_cron_runs(cron_id, limit=max(1, min(int(limit), 100)))
    return {"items": items, "total": len(items)}


def register_cron_capabilities() -> None:
    """注册定时任务品类能力。"""
    defs = [
        ("cron.list", "integration:cron:query", "定时任务列表", "列出全部定时任务", {}, "items: array, total: int", _cron_list, False),
        ("cron.create", "integration:cron:create", "创建定时任务", "创建一个定时任务", {"type": "object", "properties": {}, "additionalProperties": True}, "定时任务对象（含 id）", _cron_create, False),
        ("cron.update", "integration:cron:update", "更新定时任务", "更新定时任务", {"type": "object", "properties": {"cron_id": {"type": "integer"}}, "required": ["cron_id"]}, "更新后的定时任务对象", _cron_update, False),
        ("cron.delete", "integration:cron:delete", "删除定时任务", "删除定时任务（须 confirm=true）", {"type": "object", "properties": {"cron_id": {"type": "integer"}, "confirm": {"type": "boolean"}}, "required": ["cron_id", "confirm"]}, "deleted: int", _cron_delete, True),
        ("cron.run", "integration:cron:run", "立即执行", "立即执行定时任务", {"type": "object", "properties": {"cron_id": {"type": "integer"}}, "required": ["cron_id"]}, "cron_id / status", _cron_run, True),
        ("cron.runs", "integration:cron:query", "执行记录", "列出定时任务的执行记录", {"type": "object", "properties": {"cron_id": {"type": "integer"}}, "required": ["cron_id"]}, "items: array, total: int", _cron_runs, False),
    ]
    for code, perm, name, desc, schema, returns, handler, approval in defs:
        register(
            Capability(
                code=code,
                category="cron",
                perm=perm,
                name=name,
                description=desc,
                input_schema=schema,
                returns=returns,
                handler=handler,
                mcp_tool=code.replace(".", "_"),
                requires_approval=approval,
            )
        )
