from fastapi import APIRouter, Body, Depends, Path
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.request import PaginationService
from app.common.response import SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .param import LayoutQueryParam
from .schema import LayoutCreateSchema, LayoutUpdateSchema
from .service import LayoutService

LayoutRouter = APIRouter(route_class=OperationLogRoute, prefix="/layout", tags=["布局管理"])


@LayoutRouter.get("/list", summary="查询布局列表")
async def get_layout_list_controller(
    page: PaginationQueryParam = Depends(),
    search: LayoutQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["module_video:layout:query"])),
) -> JSONResponse:
    result_list = await LayoutService.get_layout_list_service(search=search, auth=auth, order_by=page.order_by)
    result = await PaginationService.paginate(data_list=result_list, page_no=page.page_no, page_size=page.page_size)
    return SuccessResponse(data=result, msg="查询成功")


@LayoutRouter.get("/detail/{id}", summary="查询布局详情")
async def get_layout_detail_controller(
    id: int = Path(..., description="布局ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:layout:query"])),
) -> JSONResponse:
    result = await LayoutService.get_layout_detail_service(id=id, auth=auth)
    return SuccessResponse(data=result, msg="查询成功")


@LayoutRouter.post("/create", summary="创建布局")
async def create_layout_controller(
    data: LayoutCreateSchema,
    auth: AuthSchema = Depends(AuthPermission(["module_video:layout:create"])),
) -> JSONResponse:
    result = await LayoutService.create_layout_service(data=data, auth=auth)
    return SuccessResponse(data=result, msg="创建成功")


@LayoutRouter.put("/update/{id}", summary="修改布局")
async def update_layout_controller(
    data: LayoutUpdateSchema,
    id: int = Path(..., description="布局ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:layout:update"])),
) -> JSONResponse:
    result = await LayoutService.update_layout_service(id=id, data=data, auth=auth)
    return SuccessResponse(data=result, msg="修改成功")


@LayoutRouter.delete("/delete", summary="删除布局")
async def delete_layout_controller(
    ids: list[int] = Body(..., description="ID列表"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:layout:delete"])),
) -> JSONResponse:
    await LayoutService.delete_layout_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")
