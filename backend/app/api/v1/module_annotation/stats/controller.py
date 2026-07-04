from fastapi import APIRouter, Depends

from app.core.dependencies import AuthPermission
from app.common.response import SuccessResponse

from .service import StatsService

StatsRouter = APIRouter(prefix="/stats", tags=["数据标注-统计"])


@StatsRouter.get("/overview", summary="工作量概览")
async def get_overview(
    auth=Depends(AuthPermission(["annotation:stats:query"])),
):
    data = await StatsService.get_overview()
    return SuccessResponse(data=data)
