"""智能体控制器：分类 + 实体 CRUD + 流式运行。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute
from app.plugin.module_ai.streaming import ui_stream_response

from .schema import (
    AiAgentCategoryCreateSchema,
    AiAgentCategoryUpdateSchema,
    AiAgentCreateSchema,
    AiAgentRunSchema,
    AiAgentSkillBindSchema,
    AiAgentUpdateSchema,
)
from .service import AiAgentService

AiAgentRouter = APIRouter(route_class=OperationLogRoute, prefix="/agents", tags=["AI-智能体"])


# ---------------------------------------------------------------- #
# 分类
# ---------------------------------------------------------------- #
@AiAgentRouter.get("/categories/list", summary="智能体分类列表")
async def list_categories(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiAgentService.list_categories(), msg="查询成功")


@AiAgentRouter.post("/categories/create", summary="新增智能体分类")
async def create_category(
    data: AiAgentCategoryCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiAgentService.create_category(data, auth), msg="创建成功")


@AiAgentRouter.put("/categories/update/{cat_id}", summary="编辑智能体分类")
async def update_category(
    cat_id: int,
    data: AiAgentCategoryUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:update"]))],
) -> JSONResponse:
    result = await AiAgentService.update_category(cat_id, data, auth)
    if not result:
        return ErrorResponse(msg="分类不存在")
    return SuccessResponse(data=result, msg="修改成功")


@AiAgentRouter.delete("/categories/delete", summary="删除智能体分类")
async def delete_category(
    cat_id: Annotated[int, Body(description="分类ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:delete"]))],
) -> JSONResponse:
    await AiAgentService.delete_category(cat_id)
    return SuccessResponse(msg="删除成功")


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


@AiAgentRouter.post("/{agent_id}/run/stream", summary="运行智能体（AI SDK UI Message Stream）")
async def run_agent_stream(
    agent_id: int,
    data: AiAgentRunSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:agent:query"]))],
) -> StreamingResponse:
    return ui_stream_response(
        AiAgentService.run_ui_stream(
            agent_id, data.messages, auth, data.variables, data.session_id
        )
    )
