from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .video_service import VideoService

VideoRouter = APIRouter(route_class=OperationLogRoute, prefix="/video", tags=["数据标注-视频"])


@VideoRouter.post("/upload", summary="上传视频")
async def upload_video(
    dataset_id: Annotated[int, Query(description="数据集ID")],
    file: Annotated[UploadFile, File(...)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:create"]))],
) -> JSONResponse:
    result = await VideoService.upload_video(dataset_id, file, auth)
    return SuccessResponse(data=result, msg="上传成功")


@VideoRouter.get("/list", summary="查询数据集下的视频列表")
async def list_videos(
    dataset_id: Annotated[int, Query(description="数据集ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    items = await VideoService.list_videos(dataset_id)
    return SuccessResponse(data={"items": items})


@VideoRouter.get("/detail/{video_id}", summary="查询视频详情")
async def video_detail(
    video_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    video = await VideoService.get_video(video_id)
    return SuccessResponse(data=video)


@VideoRouter.get("/play-url/{video_id}", summary="获取视频播放地址")
async def get_play_url(
    video_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    url = await VideoService.get_play_url(video_id)
    return SuccessResponse(data={"play_url": url})


@VideoRouter.post("/lock/{video_id}", summary="锁定视频（帧锁，按视频整体）")
async def lock_video(
    video_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    result = await VideoService.lock_video(video_id, auth.user.id)
    return SuccessResponse(data=result)


@VideoRouter.post("/unlock/{video_id}", summary="解锁视频")
async def unlock_video(
    video_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    await VideoService.unlock_video(video_id, auth.user.id)
    return SuccessResponse()
