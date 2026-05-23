from typing import Optional
from fastapi import APIRouter, Depends, Body, Path, Query
from fastapi.responses import JSONResponse

from app.common.response import SuccessResponse
from app.common.request import PaginationService
from app.core.router_class import OperationLogRoute
from app.core.dependencies import get_current_user, AuthPermission
from app.core.base_params import PaginationQueryParam
from app.core.logger import logger
from app.api.v1.module_system.auth.schema import AuthSchema
from .service import AlarmService
from .schema import AlarmRuleCreateSchema, AlarmRuleUpdateSchema, AlarmRecordConfirmSchema

AlarmRouter = APIRouter(route_class=OperationLogRoute, prefix="/alarm", tags=["告警管理"])


@AlarmRouter.get("/rule/list", summary="查询告警规则列表")
async def get_rule_list_controller(
    page: PaginationQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["module_video:alarm:query"])),
) -> JSONResponse:
    result_list = await AlarmService.get_rule_list_service(auth=auth)
    result = await PaginationService.paginate(data_list=result_list, page_no=page.page_no, page_size=page.page_size)
    return SuccessResponse(data=result, msg="查询成功")


@AlarmRouter.post("/rule/create", summary="创建告警规则")
async def create_rule_controller(
    data: AlarmRuleCreateSchema,
    auth: AuthSchema = Depends(AuthPermission(["module_video:alarm:create"])),
) -> JSONResponse:
    result = await AlarmService.create_rule_service(data=data, auth=auth)
    return SuccessResponse(data=result, msg="创建成功")


@AlarmRouter.put("/rule/update/{id}", summary="修改告警规则")
async def update_rule_controller(
    data: AlarmRuleUpdateSchema,
    id: int = Path(..., description="规则ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:alarm:update"])),
) -> JSONResponse:
    result = await AlarmService.update_rule_service(id=id, data=data, auth=auth)
    return SuccessResponse(data=result, msg="修改成功")


@AlarmRouter.delete("/rule/delete", summary="删除告警规则")
async def delete_rule_controller(
    ids: list[int] = Body(..., description="ID列表"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:alarm:delete"])),
) -> JSONResponse:
    await AlarmService.delete_rule_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")


@AlarmRouter.get("/record/list", summary="查询告警记录列表")
async def get_record_list_controller(
    page: PaginationQueryParam = Depends(),
    camera_id: Optional[int] = Query(None, description="摄像机ID"),
    alarm_type: Optional[str] = Query(None, description="告警类型"),
    severity: Optional[str] = Query(None, description="严重级别"),
    status: Optional[str] = Query(None, description="状态"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:alarm:query"])),
) -> JSONResponse:
    from .param import AlarmRecordQueryParam
    search = AlarmRecordQueryParam(
        camera_id=camera_id, alarm_type=alarm_type, severity=severity, status=status
    )
    result_list = await AlarmService.get_record_list_service(search=search, auth=auth)
    result = await PaginationService.paginate(data_list=result_list, page_no=page.page_no, page_size=page.page_size)
    return SuccessResponse(data=result, msg="查询成功")


@AlarmRouter.get("/record/realtime", summary="获取实时告警(最近100条)")
async def get_realtime_alarms_controller(
    auth: AuthSchema = Depends(get_current_user),
) -> JSONResponse:
    result = await AlarmService.get_realtime_alarms_service(auth=auth)
    return SuccessResponse(data=result, msg="查询成功")


@AlarmRouter.put("/record/confirm/{id}", summary="确认告警")
async def confirm_alarm_controller(
    data: AlarmRecordConfirmSchema,
    id: int = Path(..., description="告警记录ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:alarm:update"])),
) -> JSONResponse:
    result = await AlarmService.confirm_alarm_service(id=id, data=data, auth=auth)
    return SuccessResponse(data=result, msg="操作成功")


@AlarmRouter.delete("/record/delete", summary="删除告警记录")
async def delete_record_controller(
    ids: list[int] = Body(..., description="ID列表"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:alarm:delete"])),
) -> JSONResponse:
    await AlarmService.delete_record_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")
