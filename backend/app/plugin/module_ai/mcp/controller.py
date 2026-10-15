"""MCP 服务器管理路由：配置 CRUD + 连接测试。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import McpCreateSchema, McpToggleSchema, McpUpdateSchema
from .service import McpService

McpRouter = APIRouter(route_class=OperationLogRoute, prefix="/mcp", tags=["AI-MCP"])


@McpRouter.get("/list", summary="MCP 服务器列表")
async def list_mcp(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:mcp:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await McpService.list_servers(auth.user.id), msg="查询成功")


@McpRouter.get("/detail/{server_id}", summary="MCP 服务器详情")
async def get_mcp(
    server_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:mcp:query"]))],
) -> JSONResponse:
    result = await McpService.get(server_id, auth.user.id)
    if not result:
        return ErrorResponse(msg="MCP 服务器不存在")
    return SuccessResponse(data=result, msg="查询成功")


@McpRouter.post("/create", summary="新增 MCP 服务器")
async def create_mcp(
    data: McpCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:mcp:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await McpService.create(data, auth), msg="创建成功")


@McpRouter.put("/update/{server_id}", summary="编辑 MCP 服务器")
async def update_mcp(
    server_id: int,
    data: McpUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:mcp:update"]))],
) -> JSONResponse:
    result = await McpService.update(server_id, data, auth)
    if not result:
        return ErrorResponse(msg="MCP 服务器不存在")
    return SuccessResponse(data=result, msg="修改成功")


@McpRouter.delete("/delete", summary="删除 MCP 服务器")
async def delete_mcp(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:mcp:delete"]))],
) -> JSONResponse:
    await McpService.delete(ids, auth.user.id)
    return SuccessResponse(msg="删除成功")


@McpRouter.put("/toggle/{server_id}", summary="启停 MCP 服务器")
async def toggle_mcp(
    server_id: int,
    data: McpToggleSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:mcp:update"]))],
) -> JSONResponse:
    result = await McpService.toggle(server_id, data.enabled, auth)
    if not result:
        return ErrorResponse(msg="MCP 服务器不存在")
    return SuccessResponse(data=result, msg="修改成功")


@McpRouter.post("/test/{server_id}", summary="测试 MCP 连接")
async def test_mcp(
    server_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:mcp:update"]))],
) -> JSONResponse:
    return SuccessResponse(data=await McpService.test(server_id, auth.user.id), msg="测试完成")
