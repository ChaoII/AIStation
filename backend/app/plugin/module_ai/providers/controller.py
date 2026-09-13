from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import AiProviderCreateSchema, AiProviderUpdateSchema
from .service import AiProviderService

AiProviderRouter = APIRouter(
    route_class=OperationLogRoute, prefix="/providers", tags=["AI-提供商"]
)


@AiProviderRouter.get("/list", summary="提供商列表")
async def list_providers(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:provider:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiProviderService.list_providers(), msg="查询成功")


@AiProviderRouter.post("/create", summary="新增提供商")
async def create_provider(
    data: AiProviderCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:provider:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiProviderService.create(data, auth), msg="创建成功")


@AiProviderRouter.put("/update/{provider_id}", summary="编辑提供商")
async def update_provider(
    provider_id: int,
    data: AiProviderUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:provider:update"]))],
) -> JSONResponse:
    result = await AiProviderService.update(provider_id, data, auth)
    if not result:
        return ErrorResponse(msg="提供商不存在")
    return SuccessResponse(data=result, msg="修改成功")


@AiProviderRouter.delete("/delete", summary="删除提供商")
async def delete_providers(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:provider:delete"]))],
) -> JSONResponse:
    await AiProviderService.delete(ids)
    return SuccessResponse(msg="删除成功")


@AiProviderRouter.get("/remote-models/{provider_id}", summary="拉取远端模型列表")
async def remote_models(
    provider_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:provider:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiProviderService.remote_models(provider_id), msg="查询成功")
