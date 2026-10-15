"""AI 能力插件路由：列表/新增/编辑/删除/启停。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import PluginCreateSchema, PluginToggleSchema, PluginUpdateSchema
from .service import PluginService

PluginRouter = APIRouter(route_class=OperationLogRoute, prefix="/plugins", tags=["AI-插件"])


@PluginRouter.get("/list", summary="能力插件列表")
async def list_plugins(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:plugin:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await PluginService.list_plugins(), msg="查询成功")


@PluginRouter.post("/create", summary="新增能力插件")
async def create_plugin(
    data: PluginCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:plugin:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await PluginService.create(data, auth), msg="创建成功")


@PluginRouter.put("/update/{plugin_id}", summary="编辑能力插件")
async def update_plugin(
    plugin_id: int,
    data: PluginUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:plugin:update"]))],
) -> JSONResponse:
    result = await PluginService.update(plugin_id, data, auth)
    if not result:
        return ErrorResponse(msg="插件不存在")
    return SuccessResponse(data=result, msg="修改成功")


@PluginRouter.delete("/delete", summary="删除能力插件")
async def delete_plugins(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:plugin:delete"]))],
) -> JSONResponse:
    await PluginService.delete(ids)
    return SuccessResponse(msg="删除成功")


@PluginRouter.put("/toggle/{plugin_id}", summary="启停能力插件")
async def toggle_plugin(
    plugin_id: int,
    data: PluginToggleSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:plugin:update"]))],
) -> JSONResponse:
    result = await PluginService.toggle(plugin_id, data.enabled, auth)
    if not result:
        return ErrorResponse(msg="插件不存在")
    return SuccessResponse(data=result, msg="修改成功")
