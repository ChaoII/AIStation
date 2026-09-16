from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import AiModelCreateSchema, AiModelTestSchema, AiModelUpdateSchema
from .service import AiModelService

AiModelRouter = APIRouter(route_class=OperationLogRoute, prefix="/model", tags=["AI-模型配置"])


@AiModelRouter.get("/list", summary="大模型配置列表")
async def list_ai_models(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:model:query"]))],
) -> JSONResponse:
    data = await AiModelService.list_models()
    return SuccessResponse(data=data, msg="查询成功")


@AiModelRouter.post("/create", summary="新增大模型配置")
async def create_ai_model(
    data: AiModelCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:model:create"]))],
) -> JSONResponse:
    result = await AiModelService.create(data, auth)
    return SuccessResponse(data=result, msg="创建成功")


@AiModelRouter.put("/update/{model_id}", summary="编辑大模型配置")
async def update_ai_model(
    model_id: int,
    data: AiModelUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:model:update"]))],
) -> JSONResponse:
    result = await AiModelService.update(model_id, data, auth)
    if not result:
        from app.common.response import ErrorResponse

        return ErrorResponse(msg="配置不存在")
    return SuccessResponse(data=result, msg="修改成功")


@AiModelRouter.delete("/delete", summary="删除大模型配置")
async def delete_ai_model(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:model:delete"]))],
) -> JSONResponse:
    await AiModelService.delete(ids)
    return SuccessResponse(msg="删除成功")


@AiModelRouter.post("/set-default/{model_id}", summary="设为默认模型")
async def set_default_ai_model(
    model_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:model:update"]))],
) -> JSONResponse:
    result = await AiModelService.set_default(model_id)
    if not result:
        from app.common.response import ErrorResponse

        return ErrorResponse(msg="配置不存在")
    return SuccessResponse(data=result, msg="已设为默认")


@AiModelRouter.post("/test", summary="测试模型连接")
async def test_ai_model(
    data: AiModelTestSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:model:update"]))],
) -> JSONResponse:
    result = await AiModelService.test_connection(data)
    return SuccessResponse(data=result, msg="连接成功")
