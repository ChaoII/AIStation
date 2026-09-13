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
