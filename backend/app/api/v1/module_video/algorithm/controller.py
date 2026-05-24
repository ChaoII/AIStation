from fastapi import APIRouter, Body, Depends, Path
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.request import PaginationService
from app.common.response import SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .param import AlgorithmQueryParam, AlgorithmTaskQueryParam
from .schema import (
    AlgorithmCreateSchema,
    AlgorithmTaskCreateSchema,
    AlgorithmTaskUpdateSchema,
    AlgorithmUpdateSchema,
)
from .service import AlgorithmService

AlgorithmRouter = APIRouter(route_class=OperationLogRoute, prefix="/algorithm", tags=["算法管理"])


@AlgorithmRouter.get("/list", summary="查询算法列表")
async def get_algorithm_list_controller(
    page: PaginationQueryParam = Depends(),
    search: AlgorithmQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:query"])),
) -> JSONResponse:
    result_list = await AlgorithmService.get_algorithm_list_service(search=search, auth=auth, order_by=page.order_by)
    result = await PaginationService.paginate(data_list=result_list, page_no=page.page_no, page_size=page.page_size)
    return SuccessResponse(data=result, msg="查询成功")


@AlgorithmRouter.get("/detail/{id}", summary="查询算法详情")
async def get_algorithm_detail_controller(
    id: int = Path(..., description="算法ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:query"])),
) -> JSONResponse:
    result = await AlgorithmService.get_algorithm_list_service(auth=auth)
    item = next((x for x in result if x.get("id") == id), None)
    return SuccessResponse(data=item, msg="查询成功")


@AlgorithmRouter.post("/create", summary="创建算法")
async def create_algorithm_controller(
    data: AlgorithmCreateSchema,
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:create"])),
) -> JSONResponse:
    result = await AlgorithmService.create_algorithm_service(data=data, auth=auth)
    return SuccessResponse(data=result, msg="创建成功")


@AlgorithmRouter.put("/update/{id}", summary="修改算法")
async def update_algorithm_controller(
    data: AlgorithmUpdateSchema,
    id: int = Path(..., description="算法ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:update"])),
) -> JSONResponse:
    result = await AlgorithmService.update_algorithm_service(id=id, data=data, auth=auth)
    return SuccessResponse(data=result, msg="修改成功")


@AlgorithmRouter.delete("/delete", summary="删除算法")
async def delete_algorithm_controller(
    ids: list[int] = Body(..., description="ID列表"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:delete"])),
) -> JSONResponse:
    await AlgorithmService.delete_algorithm_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")


@AlgorithmRouter.get("/task/list", summary="查询算法任务列表")
async def get_task_list_controller(
    page: PaginationQueryParam = Depends(),
    search: AlgorithmTaskQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:query"])),
) -> JSONResponse:
    result_list = await AlgorithmService.get_task_list_service(search=search, auth=auth, order_by=page.order_by)
    result = await PaginationService.paginate(data_list=result_list, page_no=page.page_no, page_size=page.page_size)
    return SuccessResponse(data=result, msg="查询成功")


@AlgorithmRouter.post("/task/create", summary="创建算法任务")
async def create_task_controller(
    data: AlgorithmTaskCreateSchema,
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:create"])),
) -> JSONResponse:
    result = await AlgorithmService.create_task_service(data=data, auth=auth)
    return SuccessResponse(data=result, msg="创建成功")


@AlgorithmRouter.put("/task/update/{id}", summary="修改算法任务")
async def update_task_controller(
    data: AlgorithmTaskUpdateSchema,
    id: int = Path(..., description="任务ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:update"])),
) -> JSONResponse:
    result = await AlgorithmService.update_task_service(id=id, data=data, auth=auth)
    return SuccessResponse(data=result, msg="修改成功")


@AlgorithmRouter.delete("/task/delete", summary="删除算法任务")
async def delete_task_controller(
    ids: list[int] = Body(..., description="ID列表"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:algorithm:delete"])),
) -> JSONResponse:
    await AlgorithmService.delete_task_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")
