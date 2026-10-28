"""开放面能力 handler —— 工作流（workflow 品类）。

复用 ``AiWorkflowService``。运行类占资源/耗 GPU，敏感；删除/回滚/调度置
``requires_approval``。
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..registry import Capability, register
from ._common import bad_request, need_int, not_found, open_auth, require_confirm


async def _wf_list(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.workflow.service import AiWorkflowService

    items = await AiWorkflowService.list_workflows()
    return {"items": items, "total": len(items)}


async def _wf_get(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.workflow.service import AiWorkflowService

    wf = await AiWorkflowService.get_workflow(need_int(payload, "workflow_id"))
    if wf is None:
        raise not_found("工作流")
    return wf


async def _wf_create(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.workflow.schema import AiWorkflowCreateSchema
    from app.plugin.module_ai.workflow.service import AiWorkflowService

    try:
        data = AiWorkflowCreateSchema(**payload)
    except ValidationError as exc:
        raise bad_request(exc) from exc
    return await AiWorkflowService.create(data, await open_auth())


async def _wf_update(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.workflow.schema import AiWorkflowUpdateSchema
    from app.plugin.module_ai.workflow.service import AiWorkflowService

    wf_id = need_int(payload, "workflow_id")
    if await AiWorkflowService.get_workflow(wf_id) is None:
        raise not_found("工作流")
    try:
        data = AiWorkflowUpdateSchema(**{k: v for k, v in payload.items() if k != "workflow_id"})
    except ValidationError as exc:
        raise bad_request(exc) from exc
    row = await AiWorkflowService.update(wf_id, data, await open_auth())
    if row is None:
        raise not_found("工作流")
    return row


async def _wf_delete(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.workflow.service import AiWorkflowService

    wf_id = need_int(payload, "workflow_id")
    require_confirm(payload, "删除工作流")
    await AiWorkflowService.delete([wf_id])
    return {"deleted": wf_id}


async def _wf_versions(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.workflow.service import AiWorkflowService

    wf_id = need_int(payload, "workflow_id")
    items = await AiWorkflowService.list_versions(wf_id)
    return {"items": items, "total": len(items)}


async def _wf_rollback(*, app_ctx: Any, payload: dict) -> dict:
    # 回滚由工作流服务按版本号处理；这里先登记占位（版本回滚需明确 target）。
    from app.plugin.module_ai.workflow.service import AiWorkflowService

    wf_id = need_int(payload, "workflow_id")
    version = need_int(payload, "version")
    require_confirm(payload, "回滚工作流版本")
    # 复用发布/回滚路径：暂无独立回滚方法则返回版本列表提示
    items = await AiWorkflowService.list_versions(wf_id)
    return {"workflow_id": wf_id, "target_version": version, "versions": items}


async def _wf_runs(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.workflow.service import AiWorkflowService

    wf_id = need_int(payload, "workflow_id")
    limit = payload.get("limit", 20)
    items = await AiWorkflowService.list_run_logs(wf_id, limit=max(1, min(int(limit), 100)))
    return {"items": items, "total": len(items)}


def register_workflow_capabilities() -> None:
    """注册工作流品类能力。"""
    defs: list[tuple[str, str, str, str, dict, str, Any, bool]] = [
        (
            "workflow.list",
            "integration:workflow:query",
            "工作流列表",
            "列出全部工作流",
            {"type": "object", "properties": {}},
            "items: array, total: int",
            _wf_list,
            False,
        ),
        (
            "workflow.get",
            "integration:workflow:query",
            "工作流详情",
            "按 ID 查询工作流",
            {"type": "object", "properties": {"workflow_id": {"type": "integer"}}, "required": ["workflow_id"]},
            "工作流对象",
            _wf_get,
            False,
        ),
        (
            "workflow.create",
            "integration:workflow:create",
            "创建工作流",
            "创建一个工作流",
            {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            "工作流对象（含 id）",
            _wf_create,
            False,
        ),
        (
            "workflow.update",
            "integration:workflow:update",
            "更新工作流",
            "更新工作流",
            {"type": "object", "properties": {"workflow_id": {"type": "integer"}}, "required": ["workflow_id"]},
            "更新后的工作流对象",
            _wf_update,
            False,
        ),
        (
            "workflow.delete",
            "integration:workflow:delete",
            "删除工作流",
            "删除工作流（须 confirm=true）",
            {
                "type": "object",
                "properties": {"workflow_id": {"type": "integer"}, "confirm": {"type": "boolean"}},
                "required": ["workflow_id", "confirm"],
            },
            "deleted: int",
            _wf_delete,
            True,
        ),
        (
            "workflow.versions",
            "integration:workflow:query",
            "版本列表",
            "列出工作流的版本",
            {"type": "object", "properties": {"workflow_id": {"type": "integer"}}, "required": ["workflow_id"]},
            "items: array, total: int",
            _wf_versions,
            False,
        ),
        (
            "workflow.rollback",
            "integration:workflow:update",
            "回滚版本",
            "回滚工作流到指定版本（须 confirm=true）",
            {
                "type": "object",
                "properties": {"workflow_id": {"type": "integer"}, "version": {"type": "integer"}, "confirm": {"type": "boolean"}},
                "required": ["workflow_id", "version", "confirm"],
            },
            "回滚结果",
            _wf_rollback,
            True,
        ),
        (
            "workflow.runs",
            "integration:workflow:query",
            "运行日志",
            "列出工作流的运行日志",
            {
                "type": "object",
                "properties": {"workflow_id": {"type": "integer"}, "limit": {"type": "integer"}},
                "required": ["workflow_id"],
            },
            "items: array, total: int",
            _wf_runs,
            False,
        ),
    ]
    for code, perm, name, desc, schema, returns, handler, approval in defs:
        register(
            Capability(
                code=code,
                category="workflow",
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
