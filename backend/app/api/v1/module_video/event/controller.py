from fastapi import APIRouter, Body, Depends, Path
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.request import PaginationService
from app.common.response import SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .param import EventQueryParam
from .schema import EventCreateSchema, EventUpdateSchema
from .service import EventService

EventRouter = APIRouter(route_class=OperationLogRoute, prefix="/event", tags=["事件联动"])


@EventRouter.get("/list", summary="查询事件联动列表")
async def get_event_list_controller(
    page: PaginationQueryParam = Depends(),
    search: EventQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["module_video:event:query"])),
) -> JSONResponse:
    result_list = await EventService.get_event_list_service(search=search, auth=auth, order_by=page.order_by)
    result = await PaginationService.paginate(data_list=result_list, page_no=page.page_no, page_size=page.page_size)
    return SuccessResponse(data=result, msg="查询成功")


@EventRouter.get("/detail/{id}", summary="查询事件联动详情")
async def get_event_detail_controller(
    id: int = Path(..., description="联动ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:event:query"])),
) -> JSONResponse:
    result = await EventService.get_event_list_service(auth=auth)
    item = next((x for x in result if x.get("id") == id), None)
    return SuccessResponse(data=item, msg="查询成功")


@EventRouter.post("/create", summary="创建事件联动")
async def create_event_controller(
    data: EventCreateSchema,
    auth: AuthSchema = Depends(AuthPermission(["module_video:event:create"])),
) -> JSONResponse:
    result = await EventService.create_event_service(data=data, auth=auth)
    return SuccessResponse(data=result, msg="创建成功")


@EventRouter.put("/update/{id}", summary="修改事件联动")
async def update_event_controller(
    data: EventUpdateSchema,
    id: int = Path(..., description="联动ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:event:update"])),
) -> JSONResponse:
    result = await EventService.update_event_service(id=id, data=data, auth=auth)
    return SuccessResponse(data=result, msg="修改成功")


@EventRouter.delete("/delete", summary="删除事件联动")
async def delete_event_controller(
    ids: list[int] = Body(..., description="ID列表"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:event:delete"])),
) -> JSONResponse:
    await EventService.delete_event_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")
