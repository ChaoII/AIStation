from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute
from app.plugin.module_ai.streaming import ui_stream_response

from .schema import AiAppCreateSchema, AiAppRunSchema, AiAppUpdateSchema
from .service import AiAppService, run_app_ui_stream

AiAppRouter = APIRouter(route_class=OperationLogRoute, prefix="/apps", tags=["AI-应用"])


@AiAppRouter.get("/list", summary="应用列表")
async def list_apps(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:app:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiAppService.list_apps(), msg="查询成功")


@AiAppRouter.get("/detail/{app_id}", summary="应用详情")
async def get_app(
    app_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:app:query"]))],
) -> JSONResponse:
    data = await AiAppService.get_app(app_id)
    if not data:
        return ErrorResponse(msg="应用不存在")
    return SuccessResponse(data=data, msg="查询成功")


@AiAppRouter.post("/create", summary="新增应用")
async def create_app(
    data: AiAppCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:app:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiAppService.create(data, auth), msg="创建成功")


@AiAppRouter.put("/update/{app_id}", summary="编辑应用")
async def update_app(
    app_id: int,
    data: AiAppUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:app:update"]))],
) -> JSONResponse:
    result = await AiAppService.update(app_id, data, auth)
    if not result:
        return ErrorResponse(msg="应用不存在")
    return SuccessResponse(data=result, msg="修改成功")


@AiAppRouter.delete("/delete", summary="删除应用")
async def delete_apps(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:app:delete"]))],
) -> JSONResponse:
    await AiAppService.delete(ids)
    return SuccessResponse(msg="删除成功")


@AiAppRouter.post("/{app_id}/run/stream", summary="运行应用（AI SDK UI Message Stream）")
async def run_app_stream(
    app_id: int,
    data: AiAppRunSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:app:query"]))],
) -> StreamingResponse:
    return ui_stream_response(
        run_app_ui_stream(app_id, data.messages, auth, data.variables, data.session_id)
    )
