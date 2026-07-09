from fastapi import APIRouter, Depends

from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission

from .export_service import DatasetExportService

ExportRouter = APIRouter(prefix="/dataset/export", tags=["数据标注-数据集导出"])


@ExportRouter.get("/history/{dataset_id}", summary="导出历史")
async def get_export_history(
    dataset_id: int,
    auth=Depends(AuthPermission(["annotation:dataset:query"])),
):
    data = await DatasetExportService.list_exports(dataset_id)
    return SuccessResponse(data=data)
