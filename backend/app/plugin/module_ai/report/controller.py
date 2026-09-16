from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .service import AiReportService

AiReportRouter = APIRouter(route_class=OperationLogRoute, prefix="/report", tags=["AI-报告"])


@AiReportRouter.get("/list", summary="AI 报告列表")
async def list_ai_reports(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:report:query"]))],
) -> JSONResponse:
    data = await AiReportService.list_reports()
    return SuccessResponse(data=data, msg="查询成功")


@AiReportRouter.get("/detail/{report_id}", summary="AI 报告详情")
async def get_ai_report(
    report_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:report:query"]))],
) -> JSONResponse:
    data = await AiReportService.get_report(report_id)
    if not data:
        return ErrorResponse(msg="报告不存在")
    return SuccessResponse(data=data, msg="查询成功")


@AiReportRouter.delete("/delete", summary="删除 AI 报告")
async def delete_ai_reports(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:report:delete"]))],
) -> JSONResponse:
    await AiReportService.delete(ids)
    return SuccessResponse(msg="删除成功")
