from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import (
    AiToolCreateSchema,
    AiToolFormatScriptSchema,
    AiToolInspectScriptSchema,
    AiToolTestScriptSchema,
    AiToolToggleSchema,
    AiToolUpdateSchema,
)
from .service import AiToolService

AiToolRouter = APIRouter(route_class=OperationLogRoute, prefix="/tools", tags=["AI-工具"])


@AiToolRouter.get("/list", summary="工具列表")
async def list_tools(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:tool:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiToolService.list_tools(), msg="查询成功")


@AiToolRouter.get("/agno", summary="Agno 精选工具规格")
async def list_agno_tools(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:tool:query"]))],
) -> JSONResponse:
    from app.plugin.module_ai.agno_tools.service import get_tool_specs

    # 结合各工具行已存 config 判定 ready/reason（如 openweather 缺 api_key）
    config_map = await AiToolService.get_agno_config_map()
    return SuccessResponse(data=get_tool_specs(config_map), msg="查询成功")


@AiToolRouter.post("/create", summary="新增工具")
async def create_tool(
    data: AiToolCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:tool:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiToolService.create(data, auth), msg="创建成功")


@AiToolRouter.put("/update/{tool_id}", summary="编辑工具")
async def update_tool(
    tool_id: int,
    data: AiToolUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:tool:update"]))],
) -> JSONResponse:
    result = await AiToolService.update(tool_id, data, auth)
    if not result:
        return ErrorResponse(msg="工具不存在")
    return SuccessResponse(data=result, msg="修改成功")


@AiToolRouter.delete("/delete", summary="删除工具")
async def delete_tools(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:tool:delete"]))],
) -> JSONResponse:
    await AiToolService.delete(ids)
    return SuccessResponse(msg="删除成功")


@AiToolRouter.put("/batch/status", summary="批量启用/停用工具")
async def batch_tool_status(
    body: dict,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:tool:update"]))],
) -> JSONResponse:
    ids = [int(x) for x in (body.get("ids") or [])]
    enabled = bool(body.get("enabled"))
    count = await AiToolService.batch_status(ids, enabled, auth)
    return SuccessResponse(
        data={"count": count}, msg=f"已{'启用' if enabled else '停用'} {count} 个工具"
    )


@AiToolRouter.put("/toggle/{tool_id}", summary="启停工具")
async def toggle_tool(
    tool_id: int,
    data: AiToolToggleSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:tool:update"]))],
) -> JSONResponse:
    result = await AiToolService.toggle(tool_id, data.enabled, auth)
    if not result:
        return ErrorResponse(msg="工具不存在")
    return SuccessResponse(data=result, msg="修改成功")


@AiToolRouter.post("/test/{tool_id}", summary="测试工具")
async def test_tool(
    tool_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:tool:update"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiToolService.test(tool_id), msg="测试成功")


@AiToolRouter.post("/test-script/{tool_id}", summary="试运行脚本工具")
async def test_script_tool(
    tool_id: int,
    data: AiToolTestScriptSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:tool:update"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiToolService.test_script(tool_id, data.args), msg="试运行完成"
    )


@AiToolRouter.post("/inspect-script", summary="解析脚本签名，提取参数")
async def inspect_script_tool(
    data: AiToolInspectScriptSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:tool:update"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiToolService.inspect_script(data.code), msg="解析成功")


@AiToolRouter.post("/format-script", summary="格式化脚本代码")
async def format_script_tool(
    data: AiToolFormatScriptSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:tool:update"]))],
) -> JSONResponse:
    return SuccessResponse(data={"code": await AiToolService.format_script(data.code)}, msg="格式化完成")
