"""智能体控制器：分类 + 实体 CRUD + 流式运行。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute
from app.plugin.module_ai.assistant.agno_service import agno_stream_response

from .schema import (
    AiAgentCreateSchema,
    AiAgentRunSchema,
    AiAgentSkillBindSchema,
    AiAgentUpdateSchema,
)
from .service import AiAgentService

AiAgentRouter = APIRouter(route_class=OperationLogRoute, prefix="/agents", tags=["AI-智能体"])


# Agent 市场（模板一键创建）
@AiAgentRouter.get("/templates", summary="Agent 市场模板列表")
async def agent_templates(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiAgentService.agent_templates(), msg="查询成功")


@AiAgentRouter.post("/create-from-template", summary="从模板一键创建 Agent")
async def create_from_template(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    a = await AiAgentService.create_from_template(str(data.get("key", "")), str(data.get("name", "")), auth)
    return SuccessResponse(data=a, msg="创建成功")


# ---------------------------------------------------------------- #
# 智能体
# ---------------------------------------------------------------- #
@AiAgentRouter.get("/list", summary="智能体列表")
async def list_agents(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
    category_id: int | None = None,
) -> JSONResponse:
    return SuccessResponse(
        data=await AiAgentService.list_agents(category_id), msg="查询成功"
    )


@AiAgentRouter.get("/dashboard", summary="Agent 编排运行看板(运行量/错误率/延迟+绑定矩阵)")
async def agent_dashboard(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiAgentService.agent_dashboard(), msg="查询成功"
    )


@AiAgentRouter.post("/orchestrate", summary="多智能体协作编排(分解问题+匹配智能体)")
async def agent_orchestrate(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiAgentService.orchestrate(data.get("question", "")), msg="查询成功"
    )


@AiAgentRouter.get("/detail/{agent_id}", summary="智能体详情")
async def get_agent(
    agent_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
) -> JSONResponse:
    data = await AiAgentService.get_agent(agent_id)
    if not data:
        return ErrorResponse(msg="智能体不存在")
    return SuccessResponse(data=data, msg="查询成功")


@AiAgentRouter.post("/create", summary="新增智能体")
async def create_agent(
    data: AiAgentCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiAgentService.create(data, auth), msg="创建成功")


@AiAgentRouter.put("/update/{agent_id}", summary="编辑智能体")
async def update_agent(
    agent_id: int,
    data: AiAgentUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:update"]))],
) -> JSONResponse:
    result = await AiAgentService.update(agent_id, data, auth)
    if not result:
        return ErrorResponse(msg="智能体不存在")
    return SuccessResponse(data=result, msg="修改成功")


@AiAgentRouter.delete("/delete", summary="删除智能体")
async def delete_agents(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:delete"]))],
) -> JSONResponse:
    await AiAgentService.delete(ids)
    return SuccessResponse(msg="删除成功")


@AiAgentRouter.put("/batch/status", summary="批量启用/停用智能体")
async def batch_agent_status(
    body: dict,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:update"]))],
) -> JSONResponse:
    ids = [int(x) for x in (body.get("ids") or [])]
    enabled = bool(body.get("enabled"))
    count = await AiAgentService.batch_status(ids, enabled, auth)
    return SuccessResponse(
        data={"count": count}, msg=f"已{'启用' if enabled else '停用'} {count} 个智能体"
    )


@AiAgentRouter.post("/{agent_id}/install-skill", summary="安装技能到智能体")
async def install_skill(
    agent_id: int,
    data: AiAgentSkillBindSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:update"]))],
) -> JSONResponse:
    ok = await AiAgentService.install_skill(agent_id, data.skill_id, auth)
    if ok is None:
        return ErrorResponse(msg="智能体不存在")
    from app.plugin.module_ai.skill.service import AiSkillService

    await AiSkillService.bump_install([data.skill_id], 1)
    return SuccessResponse(msg="安装成功")


@AiAgentRouter.post("/{agent_id}/uninstall-skill", summary="卸载智能体上的技能")
async def uninstall_skill(
    agent_id: int,
    data: AiAgentSkillBindSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:update"]))],
) -> JSONResponse:
    ok = await AiAgentService.uninstall_skill(agent_id, data.skill_id, auth)
    if ok is None:
        return ErrorResponse(msg="智能体不存在")
    from app.plugin.module_ai.skill.service import AiSkillService

    await AiSkillService.bump_install([data.skill_id], -1)
    return SuccessResponse(msg="卸载成功")


@AiAgentRouter.post("/{agent_id}/run/stream", summary="运行智能体（Agno 原生事件流）")
async def run_agent_stream(
    agent_id: int,
    data: AiAgentRunSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
) -> StreamingResponse:
    return agno_stream_response(
        AiAgentService.run_ui_stream(
            agent_id, data.messages, auth, data.variables, data.session_id
        )
    )
