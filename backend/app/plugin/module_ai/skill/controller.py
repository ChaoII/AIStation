"""技能广场控制器。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import AiSkillCreateSchema, AiSkillUpdateSchema
from .service import AiSkillService

AiSkillRouter = APIRouter(route_class=OperationLogRoute, prefix="/skills", tags=["AI-技能"])


@AiSkillRouter.get("/list", summary="技能列表")
async def list_skills(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:query"]))],
    category: str | None = None,
    skill_type: str | None = None,
) -> JSONResponse:
    return SuccessResponse(
        data=await AiSkillService.list_skills(category, skill_type), msg="查询成功"
    )


@AiSkillRouter.get("/categories", summary="技能分类统计")
async def skill_categories(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiSkillService.categories(), msg="查询成功")


@AiSkillRouter.get("/detail/{skill_id}", summary="技能详情")
async def get_skill(
    skill_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:query"]))],
) -> JSONResponse:
    data = await AiSkillService.get_skill(skill_id)
    if not data:
        return ErrorResponse(msg="技能不存在")
    return SuccessResponse(data=data, msg="查询成功")


@AiSkillRouter.post("/create", summary="新增技能")
async def create_skill(
    data: AiSkillCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiSkillService.create(data, auth), msg="创建成功")


@AiSkillRouter.put("/update/{skill_id}", summary="编辑技能")
async def update_skill(
    skill_id: int,
    data: AiSkillUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:update"]))],
) -> JSONResponse:
    result = await AiSkillService.update(skill_id, data, auth)
    if not result:
        return ErrorResponse(msg="技能不存在")
    return SuccessResponse(data=result, msg="修改成功")


@AiSkillRouter.delete("/delete", summary="删除技能")
async def delete_skills(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:delete"]))],
) -> JSONResponse:
    await AiSkillService.delete(ids)
    return SuccessResponse(msg="删除成功")


@AiSkillRouter.put("/toggle/{skill_id}", summary="切换精选")
async def toggle_featured(
    skill_id: int,
    featured: Annotated[bool, Query()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:skill:update"]))],
) -> JSONResponse:
    result = await AiSkillService.toggle_featured(skill_id, featured, auth)
    if not result:
        return ErrorResponse(msg="技能不存在")
    return SuccessResponse(data=result, msg="修改成功")
