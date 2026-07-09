from fastapi import APIRouter, Depends

from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission

from .service import CleanService

CleanRouter = APIRouter(prefix="/dataset/clean", tags=["数据标注-数据清洗"])


@CleanRouter.get("/check/{dataset_id}", summary="数据集健康检查")
async def check_dataset(
    dataset_id: int,
    auth=Depends(AuthPermission(["annotation:dataset:query"])),
):
    data = await CleanService.check_dataset(dataset_id)
    if data is None:
        from app.common.response import ErrorResponse
        return ErrorResponse(msg="数据集不存在")
    return SuccessResponse(data=data)


@CleanRouter.get("/duplicates/{dataset_id}", summary="检测重复图片")
async def detect_duplicates(
    dataset_id: int,
    auth=Depends(AuthPermission(["annotation:dataset:query"])),
):
    data = await CleanService.detect_duplicate_images(dataset_id)
    return SuccessResponse(data=data)


@CleanRouter.get("/anomalies/{dataset_id}", summary="检测异常标注")
async def detect_anomalies(
    dataset_id: int,
    auth=Depends(AuthPermission(["annotation:dataset:query"])),
):
    data = await CleanService.detect_anomalous_annotations(dataset_id)
    return SuccessResponse(data=data)
