"""开放面能力 handler —— 智能体（agent 品类）。

复用 ``AiAgentService``：开放面创建/查询/更新/删除的智能体一律打
``source_app_id`` 归属，且只能操作**本应用**创建的智能体（跨应用 → 404，
与「资源不存在」同一响应，避免枚举他人资源 id）。
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pydantic import ValidationError

from app.core.exceptions import CustomException
from app.plugin.module_ai.agent.schema import AiAgentCreateSchema, AiAgentUpdateSchema
from app.plugin.module_ai.agent.service import AiAgentService

from ..auth import AppContext
from ..registry import Capability, register

#: 开放面调用既有 service 时的「无平台用户」身份（资源归属由 source_app_id 表达）。
_OPEN_AUTH = SimpleNamespace(user=None)


def _bad_request(exc: ValidationError) -> CustomException:
    """把 Pydantic 校验错误转成 400（只回第一处错误，避免泄露整份 schema）。"""
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(p) for p in first.get("loc", ()))
    return CustomException(
        msg=f"参数不合法：{loc} {first.get('msg', '')}".strip(), code=10400, status_code=400
    )


def _need_int(payload: dict, key: str) -> int:
    """取必填整数字段，缺失/非数字抛 400。"""
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CustomException(msg=f"参数不合法：{key} 必须为整数", code=10400, status_code=400)
    return value


async def _agent_list(*, app_ctx: AppContext, payload: dict) -> dict:
    items = await AiAgentService.list_agents(source_app_id=app_ctx.app_id)
    return {"items": items, "total": len(items)}


async def _agent_get(*, app_ctx: AppContext, payload: dict) -> dict:
    agent_id = _need_int(payload, "agent_id")
    agent = await AiAgentService.get_agent(agent_id, source_app_id=app_ctx.app_id)
    if agent is None:
        raise CustomException(msg="智能体不存在", code=10404, status_code=404)
    return agent


async def _agent_create(*, app_ctx: AppContext, payload: dict) -> dict:
    try:
        data = AiAgentCreateSchema(**payload)
    except ValidationError as exc:
        raise _bad_request(exc) from exc
    return await AiAgentService.create(data, _OPEN_AUTH, source_app_id=app_ctx.app_id)


async def _agent_update(*, app_ctx: AppContext, payload: dict) -> dict:
    agent_id = _need_int(payload, "agent_id")
    body = {k: v for k, v in payload.items() if k != "agent_id"}
    if await AiAgentService.get_agent(agent_id, source_app_id=app_ctx.app_id) is None:
        raise CustomException(msg="智能体不存在", code=10404, status_code=404)
    try:
        data = AiAgentUpdateSchema(**body)
    except ValidationError as exc:
        raise _bad_request(exc) from exc
    updated = await AiAgentService.update(agent_id, data, _OPEN_AUTH)
    if updated is None:
        raise CustomException(msg="智能体不存在", code=10404, status_code=404)
    return updated


async def _agent_delete(*, app_ctx: AppContext, payload: dict) -> dict:
    agent_id = _need_int(payload, "agent_id")
    if await AiAgentService.get_agent(agent_id, source_app_id=app_ctx.app_id) is None:
        raise CustomException(msg="智能体不存在", code=10404, status_code=404)
    await AiAgentService.delete([agent_id])
    return {"deleted": agent_id}


_ITEM_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": True}


def register_agent_capabilities() -> None:
    """注册 agent 品类能力（幂等由 registry.register 的重复校验兜底）。"""
    defs: list[tuple[str, str, str, str, dict, str, Any, str]] = [
        (
            "agent.list",
            "integration:agent:query",
            "查询智能体列表",
            "列出本应用创建的智能体（不含平台内部智能体）",
            {"type": "object", "properties": {}},
            "items: array, total: int",
            _agent_list,
            "agent_list",
        ),
        (
            "agent.get",
            "integration:agent:query",
            "查询智能体详情",
            "按 ID 查询本应用创建的智能体",
            {
                "type": "object",
                "properties": {"agent_id": {"type": "integer"}},
                "required": ["agent_id"],
            },
            "智能体对象",
            _agent_get,
            "agent_get",
        ),
        (
            "agent.create",
            "integration:agent:create",
            "创建智能体",
            "创建一个归属本应用的智能体",
            {
                "type": "object",
                "properties": {
                    "agent_name": {"type": "string"},
                    "agent_role": {"type": "string"},
                    "description": {"type": "string"},
                    "model_id": {"type": "integer"},
                    "prompt_id": {"type": "integer"},
                    "workflow_id": {"type": "integer"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["agent_name"],
            },
            "智能体对象（含 id / source_app_id）",
            _agent_create,
            "agent_create",
        ),
        (
            "agent.update",
            "integration:agent:update",
            "更新智能体",
            "更新本应用创建的智能体（跨应用 404）",
            {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "integer"},
                    "agent_name": {"type": "string"},
                    "agent_role": {"type": "string"},
                    "description": {"type": "string"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["agent_id"],
            },
            "更新后的智能体对象",
            _agent_update,
            "agent_update",
        ),
        (
            "agent.delete",
            "integration:agent:delete",
            "删除智能体",
            "删除本应用创建的智能体（跨应用 404）",
            {
                "type": "object",
                "properties": {"agent_id": {"type": "integer"}},
                "required": ["agent_id"],
            },
            "deleted: int",
            _agent_delete,
            "agent_delete",
        ),
    ]
    for code, perm, name, desc, schema, returns, handler, tool in defs:
        register(
            Capability(
                code=code,
                category="agent",
                perm=perm,
                name=name,
                description=desc,
                input_schema=schema,
                returns=returns,
                handler=handler,
                mcp_tool=tool,
            )
        )
