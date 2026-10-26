from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .service import AiLogService

AiLogsRouter = APIRouter(route_class=OperationLogRoute, prefix="/logs", tags=["AI-调用日志"])


@AiLogsRouter.get("/list", summary="调用日志分页列表")
async def list_logs(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, description="每页数量")] = 10,
    usage: Annotated[str | None, Query(description="用途精确匹配")] = None,
    result: Annotated[str | None, Query(description="success/error")] = None,
    keyword: Annotated[str | None, Query(description="模型名或错误信息模糊匹配")] = None,
) -> JSONResponse:
    data = await AiLogService.page(
        page_no=page_no,
        page_size=page_size,
        usage=usage,
        result=result,
        keyword=keyword,
    )
    return SuccessResponse(data=data, msg="查询成功")


@AiLogsRouter.get("/tool-calls", summary="工具调用时间线（谁调了哪个工具/多久/成败）")
async def tool_calls(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
    agent_id: Annotated[int | None, Query(description="智能体 ID")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="条数")] = 20,
) -> JSONResponse:
    from .tool_calls import list_calls

    return SuccessResponse(data=await list_calls(agent_id, limit), msg="查询成功")


@AiLogsRouter.get("/stats", summary="调用日志统计")
async def log_stats(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
    days: Annotated[int, Query(ge=1, le=90, description="统计天数")] = 7,
) -> JSONResponse:
    return SuccessResponse(data=await AiLogService.stats(days), msg="查询成功")


@AiLogsRouter.get("/recent", summary="最近运行明细（AI 办公室流水条）")
async def recent_logs(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:office:query"]))],
    limit: Annotated[int, Query(ge=1, le=50, description="条数")] = 6,
) -> JSONResponse:
    return SuccessResponse(data=await AiLogService.recent_runs(limit), msg="查询成功")


@AiLogsRouter.get("/export", summary="导出调用日志(CSV)")
async def export_logs(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
    days: Annotated[int, Query(ge=1, le=365, description="天数")] = 30,
    usage: Annotated[str | None, Query(description="用途过滤")] = None,
    result: Annotated[str | None, Query(description="success/error")] = None,
) -> JSONResponse:
    return SuccessResponse(data=await AiLogService.export(days, usage, result), msg="查询成功")
