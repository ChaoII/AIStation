from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import AnnotationSaveSchema
from .service import AnnotationService
from ..dataset.service import DatasetService

AnnotationRouter = APIRouter(route_class=OperationLogRoute, prefix="/anno", tags=["数据标注-标注操作"])


@AnnotationRouter.get("/image/{image_id}/annotations", summary="获取标注数据")
async def get_annotations(
    task_id: int,
    image_id: int,
    auth: AuthSchema = Depends(AuthPermission(["annotation:workbench:query"])),
) -> JSONResponse:
    data = await AnnotationService.get_annotations(task_id, image_id)
    return SuccessResponse(data=data or [])


@AnnotationRouter.put("/image/{image_id}/annotations", summary="保存标注数据")
async def save_annotations(
    image_id: int,
    data: AnnotationSaveSchema,
    auth: AuthSchema = Depends(AuthPermission(["annotation:workbench:query"])),
) -> JSONResponse:
    result = await AnnotationService.save_annotations(data.task_id, image_id, data.annotation_data, auth)
    return SuccessResponse(data=result, msg="保存成功")


@AnnotationRouter.get("/image/{image_id}/history", summary="标注历史版本")
async def get_annotation_history(
    task_id: int,
    image_id: int,
    auth: AuthSchema = Depends(AuthPermission(["annotation:workbench:query"])),
) -> JSONResponse:
    history = await AnnotationService.get_annotation_history(task_id, image_id)
    return SuccessResponse(data=history)


@AnnotationRouter.get("/image/{image_id}/presigned-url", summary="获取图片访问URL")
async def get_image_url(
    image_id: int,
    auth: AuthSchema = Depends(AuthPermission(["annotation:workbench:query"])),
) -> JSONResponse:
    url = await DatasetService.get_presigned_url(image_id)
    return SuccessResponse(data={"url": url})