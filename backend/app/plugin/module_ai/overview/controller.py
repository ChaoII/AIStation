from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .service import AiOverviewService

AiOverviewRouter = APIRouter(route_class=OperationLogRoute, prefix="/overview", tags=["AI-概览"])


@AiOverviewRouter.get("/stats", summary="AI 控制台概览统计")
async def overview_stats(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiOverviewService.stats(), msg="查询成功")
