from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from ..dataset.service import DatasetService
from ..task.service import TaskService
from .schema import AnnotationSaveSchema
from .service import AnnotationService

AnnotationRouter = APIRouter(route_class=OperationLogRoute, prefix="/anno", tags=["数据标注-标注操作"])


async def _verify_task_access(task_id: int, auth: AuthSchema) -> None:
    """Verify user has access to this task's workbench."""
    if not await TaskService.check_workbench_access(task_id, auth.user.id, auth.user.is_superuser):
        raise HTTPException(status_code=403, detail="无权访问该任务的工作台")


@AnnotationRouter.get("/image/{image_id}/annotations", summary="获取标注数据")
async def get_annotations(
    task_id: int,
    image_id: int,
    auth: AuthSchema = Depends(AuthPermission(["annotation:workbench:query"])),
) -> JSONResponse:
    await _verify_task_access(task_id, auth)
    data = await AnnotationService.get_annotations(task_id, image_id)
    return SuccessResponse(data=data or [])


@AnnotationRouter.put("/image/{image_id}/annotations", summary="保存标注数据")
async def save_annotations(
    image_id: int,
    data: AnnotationSaveSchema,
    auth: AuthSchema = Depends(AuthPermission(["annotation:workbench:query"])),
) -> JSONResponse:
    await _verify_task_access(data.task_id, auth)
    result = await AnnotationService.save_annotations(data.task_id, image_id, data.annotation_data, auth)
    return SuccessResponse(data=result, msg="保存成功")


@AnnotationRouter.get("/image/{image_id}/history", summary="标注历史版本")
async def get_annotation_history(
    task_id: int,
    image_id: int,
    auth: AuthSchema = Depends(AuthPermission(["annotation:workbench:query"])),
) -> JSONResponse:
    await _verify_task_access(task_id, auth)
    history = await AnnotationService.get_annotation_history(task_id, image_id)
    return SuccessResponse(data=history)


@AnnotationRouter.get("/image/{image_id}/presigned-url", summary="获取图片访问URL")
async def get_image_url(
    image_id: int,
    task_id: int | None = None,
    auth: AuthSchema = Depends(AuthPermission(["annotation:workbench:query"])),
) -> JSONResponse:
    if task_id:
        await _verify_task_access(task_id, auth)
    url = await DatasetService.get_presigned_url(image_id)
    return SuccessResponse(data={"url": url})


@AnnotationRouter.post("/image/{image_id}/lock", summary="锁定图片")
async def lock_image(
    image_id: int,
    task_id: int,
    auth: AuthSchema = Depends(AuthPermission(["annotation:workbench:query"])),
) -> JSONResponse:
    await _verify_task_access(task_id, auth)
    result = await AnnotationService.lock_image(image_id, auth.user.id)
    return SuccessResponse(data=result)


@AnnotationRouter.post("/image/{image_id}/unlock", summary="解锁图片")
async def unlock_image(
    image_id: int,
    task_id: int,
    auth: AuthSchema = Depends(AuthPermission(["annotation:workbench:query"])),
) -> JSONResponse:
    await _verify_task_access(task_id, auth)
    await AnnotationService.unlock_image(image_id, auth.user.id)
    return SuccessResponse()
