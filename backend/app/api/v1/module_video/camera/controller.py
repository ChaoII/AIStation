from fastapi import APIRouter, Body, Depends, Path
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.request import PaginationService
from app.common.response import SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.media_server import media_server
from app.core.router_class import OperationLogRoute

from .param import CameraQueryParam
from .schema import (
    CameraCreateSchema,
    CameraGroupCreateSchema,
    CameraGroupUpdateSchema,
    CameraUpdateSchema,
)
from .service import CameraService

CameraRouter = APIRouter(route_class=OperationLogRoute, prefix="/camera", tags=["摄像机管理"])


@CameraRouter.get("/list", summary="查询摄像机列表")
async def get_camera_list_controller(
    page: PaginationQueryParam = Depends(),
    search: CameraQueryParam = Depends(),
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:query"])),
) -> JSONResponse:
    result_list = await CameraService.get_camera_list_service(search=search, auth=auth, order_by=page.order_by)
    result = await PaginationService.paginate(data_list=result_list, page_no=page.page_no, page_size=page.page_size)
    return SuccessResponse(data=result, msg="查询成功")


@CameraRouter.get("/detail/{id}", summary="查询摄像机详情")
async def get_camera_detail_controller(
    id: int = Path(..., description="摄像机ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:query"])),
) -> JSONResponse:
    result = await CameraService.get_detail_by_id_service(id=id, auth=auth)
    return SuccessResponse(data=result, msg="查询成功")


@CameraRouter.post("/create", summary="创建摄像机")
async def create_camera_controller(
    data: CameraCreateSchema,
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:create"])),
) -> JSONResponse:
    result = await CameraService.create_camera_service(data=data, auth=auth)
    return SuccessResponse(data=result, msg="创建成功")


@CameraRouter.put("/update/{id}", summary="修改摄像机")
async def update_camera_controller(
    data: CameraUpdateSchema,
    id: int = Path(..., description="摄像机ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:update"])),
) -> JSONResponse:
    result = await CameraService.update_camera_service(id=id, data=data, auth=auth)
    return SuccessResponse(data=result, msg="修改成功")


@CameraRouter.delete("/delete", summary="删除摄像机")
async def delete_camera_controller(
    ids: list[int] = Body(..., description="ID列表"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:delete"])),
) -> JSONResponse:
    await CameraService.delete_camera_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")


@CameraRouter.post("/stream/start/{id}", summary="启动推流")
async def start_stream_controller(
    id: int = Path(..., description="摄像机ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:update"])),
) -> JSONResponse:
    result = await CameraService.start_stream_service(id=id, auth=auth)
    return SuccessResponse(data=result, msg="推流启动成功")


@CameraRouter.post("/stream/stop/{id}", summary="停止推流")
async def stop_stream_controller(
    id: int = Path(..., description="摄像机ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:update"])),
) -> JSONResponse:
    await CameraService.stop_stream_service(id=id, auth=auth)
    return SuccessResponse(msg="推流已停止")


@CameraRouter.get("/stream/urls/{id}", summary="获取播放地址")
async def get_stream_urls_controller(
    id: int = Path(..., description="摄像机ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:query"])),
) -> JSONResponse:
    result = await CameraService.get_stream_urls_service(id=id, auth=auth)
    return SuccessResponse(data=result, msg="获取成功")


@CameraRouter.post("/webrtc/signaling", summary="WebRTC 信令代理")
async def webrtc_signaling_controller(
    data: dict = Body(...),
) -> JSONResponse:
    stream_id = data.get("stream_id", "")
    sdp = data.get("sdp", "")
    result = await media_server.webrtc_signaling(stream_id=stream_id, sdp_offer=sdp)
    return JSONResponse(result)


@CameraRouter.get("/stream/online/{id}", summary="查询流是否在线")
async def check_stream_online_controller(
    id: int = Path(..., description="摄像机ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:query"])),
) -> JSONResponse:
    online = await CameraService.check_stream_online_service(id=id, auth=auth)
    return SuccessResponse(data={"online": online})


# ---- 分组管理 ----

@CameraRouter.get("/group/list", summary="查询分组列表")
async def get_group_list_controller(
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:query"])),
) -> JSONResponse:
    result = await CameraService.get_group_list_service(auth=auth)
    return SuccessResponse(data=result, msg="查询成功")


@CameraRouter.post("/group/create", summary="创建分组")
async def create_group_controller(
    data: CameraGroupCreateSchema,
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:create"])),
) -> JSONResponse:
    result = await CameraService.create_group_service(data=data, auth=auth)
    return SuccessResponse(data=result, msg="创建成功")


@CameraRouter.put("/group/update/{id}", summary="修改分组")
async def update_group_controller(
    data: CameraGroupUpdateSchema,
    id: int = Path(..., description="分组ID"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:update"])),
) -> JSONResponse:
    result = await CameraService.update_group_service(id=id, data=data, auth=auth)
    return SuccessResponse(data=result, msg="修改成功")


@CameraRouter.delete("/group/delete", summary="删除分组")
async def delete_group_controller(
    ids: list[int] = Body(..., description="ID列表"),
    auth: AuthSchema = Depends(AuthPermission(["module_video:camera:delete"])),
) -> JSONResponse:
    await CameraService.delete_group_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")
