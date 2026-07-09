from fastapi import APIRouter, Depends

from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission

from .service import StatsService

StatsRouter = APIRouter(prefix="/stats", tags=["数据标注-统计"])


@StatsRouter.get("/overview", summary="标注工作量概览")
async def get_overview(
    auth=Depends(AuthPermission(["annotation:stats:query"])),
):
    data = await StatsService.get_overview()
    return SuccessResponse(data=data)


@StatsRouter.get("/dataset/{dataset_id}", summary="数据集详细统计")
async def get_dataset_stats(
    dataset_id: int,
    auth=Depends(AuthPermission(["annotation:stats:query"])),
):
    data = await StatsService.get_dataset_stats(dataset_id)
    if data is None:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg="数据集不存在")
    return SuccessResponse(data=data)
