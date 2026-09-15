from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query
from fastapi.responses import JSONResponse, Response

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.request import PaginationService
from app.common.response import SuccessResponse
from app.config.setting import settings
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute
from app.core.validator import DateTimeStr

from .param import EdgeQueryParam
from .schema import EdgeDeviceCreateSchema, EdgeDeviceUpdateSchema
from .service import EdgeService

EdgeRouter = APIRouter(route_class=OperationLogRoute, prefix="/edge", tags=["边缘设备"])


def edge_event_query_param(
    camera_id: Annotated[int | None, Query(description="相机ID")] = None,
    task_id: Annotated[int | None, Query(description="布控任务ID")] = None,
    algorithm_type: Annotated[str | None, Query(description="场景码")] = None,
    matched: Annotated[bool | None, Query(description="是否命中规则")] = None,
    start_time: Annotated[DateTimeStr | None, Query(description="事件起始时间（含）")] = None,
    end_time: Annotated[DateTimeStr | None, Query(description="事件结束时间（含）")] = None,
    keyword: Annotated[str | None, Query(description="目标 label/文本模糊")] = None,
) -> dict:
    """边缘事件列表查询参数（独立依赖，与设备查询参数区分语义）。"""
    return {
        "camera_id": camera_id,
        "task_id": task_id,
        "algorithm_type": algorithm_type,
        "matched": matched,
        "start_time": start_time,
        "end_time": end_time,
        "keyword": keyword,
    }


@EdgeRouter.get("/list", summary="查询边缘设备列表")
async def get_edge_list_controller(
    page: PaginationQueryParam = Depends(),
    search: EdgeQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["module_video:edge:query"])),
) -> JSONResponse:
    result_list = await EdgeService.get_edge_list_service(search=search, auth=auth, order_by=page.order_by)
    result = await PaginationService.paginate(data_list=result_list, page_no=page.page_no, page_size=page.page_size)
    return SuccessResponse(data=result, msg="查询成功")


@EdgeRouter.get("/detail/{id}", summary="查询边缘设备详情")
async def get_edge_detail_controller(
    id: int = Path(..., description="边缘设备ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:edge:query"])),
) -> JSONResponse:
    result = await EdgeService.get_edge_detail_service(id=id, auth=auth)
    return SuccessResponse(data=result, msg="查询成功")


@EdgeRouter.get("/event/list", summary="查询边缘事件列表")
async def get_edge_event_list_controller(
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[dict, Depends(edge_event_query_param)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:edge:query"]))],
) -> JSONResponse:
    result = await EdgeService.get_edge_event_page_service(
        auth=auth,
        page_no=page.page_no,
        page_size=page.page_size,
        order_by=page.order_by,
        **search,
    )
    return SuccessResponse(data=result, msg="查询成功")


@EdgeRouter.get("/event/detail/{id}", summary="查询边缘事件详情")
async def get_edge_event_detail_controller(
    id: Annotated[int, Path(description="边缘事件ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:edge:query"]))],
) -> JSONResponse:
    result = await EdgeService.get_edge_event_detail_service(id=id, auth=auth)
    return SuccessResponse(data=result, msg="查询成功")


@EdgeRouter.post("/create", summary="创建边缘设备")
async def create_edge_controller(
    data: EdgeDeviceCreateSchema,
    auth: AuthSchema = Depends(AuthPermission(["module_video:edge:create"])),
) -> JSONResponse:
    result = await EdgeService.create_edge_service(data=data, auth=auth)
    return SuccessResponse(data=result, msg="创建成功")


@EdgeRouter.put("/update/{id}", summary="修改边缘设备")
async def update_edge_controller(
    data: EdgeDeviceUpdateSchema,
    id: int = Path(..., description="边缘设备ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:edge:update"])),
) -> JSONResponse:
    result = await EdgeService.update_edge_service(id=id, data=data, auth=auth)
    return SuccessResponse(data=result, msg="修改成功")


@EdgeRouter.delete("/delete", summary="删除边缘设备")
async def delete_edge_controller(
    ids: list[int] = Body(..., description="ID列表"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:edge:delete"])),
) -> JSONResponse:
    await EdgeService.delete_edge_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")


@EdgeRouter.post("/heartbeat", summary="边缘设备心跳/能力上报")
async def edge_heartbeat_controller(
    body: dict = Body(..., description="心跳/能力上报"),
) -> JSONResponse:
    if settings.EDGE_CONTROL_TOKEN and body.get("token") != settings.EDGE_CONTROL_TOKEN:
        raise CustomException(msg="无效的设备凭证", code=403)
    await EdgeService.heartbeat(body)
    return SuccessResponse(msg="ok")


@EdgeRouter.get("/{device_id}/tasks/{task_id}/snapshot", summary="边缘任务快照预览")
async def get_edge_task_snapshot_controller(
    device_id: int = Path(..., description="边缘设备ID"),
    task_id: int = Path(..., description="布控任务ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:query"])),
) -> Response:
    content = await EdgeService.get_task_snapshot_service(device_id=device_id, task_id=task_id, auth=auth)
    return Response(content=content, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
