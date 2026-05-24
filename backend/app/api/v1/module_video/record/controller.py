from fastapi import APIRouter, Body, Depends, Path
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.request import PaginationService
from app.common.response import SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .param import RecordFileQueryParam, RecordPlanQueryParam
from .schema import RecordPlanCreateSchema, RecordPlanUpdateSchema
from .service import RecordService

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


@RecordRouter.get("/file/list", summary="查询录制文件列表")
async def get_file_list_controller(
    page: PaginationQueryParam = Depends(),
    search: RecordFileQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["module_video:record:query"])),
) -> JSONResponse:
    result_list = await RecordService.get_file_list_service(search=search, auth=auth, order_by=page.order_by)
    result = await PaginationService.paginate(data_list=result_list, page_no=page.page_no, page_size=page.page_size)
    return SuccessResponse(data=result, msg="查询成功")


@RecordRouter.get("/file/detail/{id}", summary="查询录制文件详情")
async def get_file_detail_controller(
    id: int = Path(..., description="文件ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:record:query"])),
) -> JSONResponse:
    result = await RecordService.get_file_detail_service(id=id, auth=auth)
    return SuccessResponse(data=result, msg="查询成功")


@RecordRouter.delete("/file/delete", summary="删除录制文件")
async def delete_file_controller(
    ids: list[int] = Body(..., description="ID列表"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:record:delete"])),
) -> JSONResponse:
    await RecordService.delete_file_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")
