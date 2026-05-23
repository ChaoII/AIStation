from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse

from app.common.response import SuccessResponse
from app.core.dependencies import get_current_user
from app.core.base_params import PaginationQueryParam
from app.core.media_server import media_server
from app.api.v1.module_system.auth.schema import AuthSchema
from .service import PreviewService

PreviewRouter = APIRouter(prefix="/preview", tags=["实时预览"])


@PreviewRouter.get("/urls/{camera_id}", summary="获取摄像机播放地址")
async def get_play_urls_controller(
    camera_id: int = Path(..., description="摄像机ID"),
    auth: AuthSchema = Depends(get_current_user),
) -> JSONResponse:
    result = await PreviewService.get_play_urls_service(camera_id=camera_id, auth=auth)
    return SuccessResponse(data=result, msg="获取成功")


@PreviewRouter.get("/snap/{camera_id}", summary="获取摄像机截图")
async def get_snap_controller(
    camera_id: int = Path(..., description="摄像机ID"),
    auth: AuthSchema = Depends(get_current_user),
) -> JSONResponse:
    from fastapi.responses import Response
    snap_data = await PreviewService.get_snap_service(camera_id=camera_id, auth=auth)
    return Response(content=snap_data, media_type="image/jpeg")
