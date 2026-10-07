from typing import Annotated

from fastapi import APIRouter, Body, Depends
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


@AiOverviewRouter.post("/eval", summary="AI 能力评估/影子回归(含关键断言判精度)")
async def overview_eval(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
    data: Annotated[dict, Body()],
) -> JSONResponse:
    samples = (data or {}).get("samples") or []
    return SuccessResponse(data=await AiOverviewService.run_eval(samples), msg="评估完成")


@AiOverviewRouter.get("/health", summary="AI 健康/异常监控")
async def overview_health(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
    days: int = 7,
) -> JSONResponse:
    return SuccessResponse(data=await AiOverviewService.health_check(days), msg="查询成功")


@AiOverviewRouter.get("/audit", summary="AI 调用合规审计")
async def overview_audit(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
    days: int = 7,
) -> JSONResponse:
    return SuccessResponse(data=await AiOverviewService.audit_check(days), msg="查询成功")


@AiOverviewRouter.get("/runtime", summary="系统运行监控(应用/工作流/模型/Agent/管道+AI健康)")
async def overview_runtime(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:assistant:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiOverviewService.runtime_status(), msg="查询成功")
