from fastapi import APIRouter, Depends, Body, Path
from fastapi.responses import JSONResponse

from app.common.response import SuccessResponse
from app.common.request import PaginationService
from app.core.router_class import OperationLogRoute
from app.core.dependencies import get_current_user, AuthPermission
from app.core.base_params import PaginationQueryParam
from app.api.v1.module_system.auth.schema import AuthSchema
from .service import RecordService
from .param import RecordPlanQueryParam
from .schema import RecordPlanCreateSchema, RecordPlanUpdateSchema

RecordRouter = APIRouter(route_class=OperationLogRoute, prefix="/record", tags=["录制管理"])


@RecordRouter.get("/plan/list", summary="查询录制计划列表")
async def get_plan_list_controller(
    page: PaginationQueryParam = Depends(),
    search: RecordPlanQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["module_video:record:query"])),
) -> JSONResponse:
    result_list = await RecordService.get_plan_list_service(search=search, auth=auth, order_by=page.order_by)
    result = await PaginationService.paginate(data_list=result_list, page_no=page.page_no, page_size=page.page_size)
    return SuccessResponse(data=result, msg="查询成功")


@RecordRouter.post("/plan/create", summary="创建录制计划")
async def create_plan_controller(
    data: RecordPlanCreateSchema,
    auth: AuthSchema = Depends(AuthPermission(["module_video:record:create"])),
) -> JSONResponse:
    result = await RecordService.create_plan_service(data=data, auth=auth)
    return SuccessResponse(data=result, msg="创建成功")


@RecordRouter.put("/plan/update/{id}", summary="修改录制计划")
async def update_plan_controller(
    data: RecordPlanUpdateSchema,
    id: int = Path(..., description="计划ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:record:update"])),
) -> JSONResponse:
    result = await RecordService.update_plan_service(id=id, data=data, auth=auth)
    return SuccessResponse(data=result, msg="修改成功")


@RecordRouter.delete("/plan/delete", summary="删除录制计划")
async def delete_plan_controller(
    ids: list[int] = Body(..., description="ID列表"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:record:delete"])),
) -> JSONResponse:
    await RecordService.delete_plan_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")


@RecordRouter.post("/start/{camera_id}/{stream_id}", summary="启动录制")
async def start_record_controller(
    camera_id: int = Path(..., description="摄像机ID"),
    stream_id: str = Path(..., description="流ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:record:update"])),
) -> JSONResponse:
    result = await RecordService.start_recording_service(camera_id=camera_id, stream_id=stream_id, auth=auth)
    return SuccessResponse(data=result, msg="录制已启动")


@RecordRouter.post("/stop/{stream_id}", summary="停止录制")
async def stop_record_controller(
    stream_id: str = Path(..., description="流ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:record:update"])),
) -> JSONResponse:
    result = await RecordService.stop_recording_service(stream_id=stream_id, auth=auth)
    return SuccessResponse(data=result, msg="录制已停止")
