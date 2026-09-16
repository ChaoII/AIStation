from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import AiPromptCreateSchema, AiPromptUpdateSchema
from .service import AiPromptService

AiPromptRouter = APIRouter(route_class=OperationLogRoute, prefix="/prompts", tags=["AI-提示词"])


@AiPromptRouter.get("/list", summary="提示词列表")
async def list_prompts(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:prompt:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiPromptService.list_prompts(), msg="查询成功")


@AiPromptRouter.get("/detail/{prompt_id}", summary="提示词详情")
async def get_prompt(
    prompt_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:prompt:query"]))],
) -> JSONResponse:
    data = await AiPromptService.get_prompt(prompt_id)
    if not data:
        return ErrorResponse(msg="提示词不存在")
    return SuccessResponse(data=data, msg="查询成功")


@AiPromptRouter.post("/create", summary="新增提示词")
async def create_prompt(
    data: AiPromptCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:prompt:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiPromptService.create(data, auth), msg="创建成功")


@AiPromptRouter.put("/update/{prompt_id}", summary="编辑提示词")
async def update_prompt(
    prompt_id: int,
    data: AiPromptUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:prompt:update"]))],
) -> JSONResponse:
    result = await AiPromptService.update(prompt_id, data, auth)
    if not result:
        return ErrorResponse(msg="提示词不存在")
    return SuccessResponse(data=result, msg="修改成功")


@AiPromptRouter.delete("/delete", summary="删除提示词")
async def delete_prompts(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:prompt:delete"]))],
) -> JSONResponse:
    await AiPromptService.delete(ids)
    return SuccessResponse(msg="删除成功")
