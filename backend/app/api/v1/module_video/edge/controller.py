from fastapi import APIRouter, Body, Depends, Path
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.config.setting import settings
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute

from .param import EdgeQueryParam
from .schema import EdgeDeviceCreateSchema, EdgeDeviceUpdateSchema
from .service import EdgeService

EdgeRouter = APIRouter(route_class=OperationLogRoute, prefix="/edge", tags=["边缘设备"])


@EdgeRouter.get("/list", summary="查询边缘设备列表")
async def get_edge_list_controller(
    page: PaginationQueryParam = Depends(),
    search: EdgeQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["module_video:edge:query"])),
) -> JSONResponse:
    result_list = await EdgeService.get_edge_list_service(search=search, auth=auth, order_by=page.order_by)
    return SuccessResponse(data=result_list, msg="查询成功")


@EdgeRouter.get("/detail/{id}", summary="查询边缘设备详情")
async def get_edge_detail_controller(
    id: int = Path(..., description="边缘设备ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:edge:query"])),
) -> JSONResponse:
    result = await EdgeService.get_edge_detail_service(id=id, auth=auth)
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
