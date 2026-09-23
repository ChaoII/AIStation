"""音频接口 controller：上传/列表/详情/播放地址/锁定。

镜像 ``document_controller.py`` 的结构与鉴权语义；上传因 ``AudioService.upload_audio``
接受外部 ``db`` 会话（只 flush 不 commit），由控制器包裹 ``begin()`` 事务，
并在提交失败时补偿删除已上传的 RustFS 对象。
"""
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.database import async_db_session
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .audio_service import AudioService

AudioRouter = APIRouter(route_class=OperationLogRoute, prefix="/audio", tags=["数据标注-音频"])


@AudioRouter.post("/upload", summary="上传音频")
async def upload_audio(
    dataset_id: Annotated[int, Query(description="数据集ID")],
    file: Annotated[UploadFile, File(...)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:create"]))],
) -> JSONResponse:
    # AudioService.upload_audio 接受外部 db 会话，内部仅 flush 不 commit；
    # 由本控制器包裹 begin() 事务，保证提交正常收口；提交失败则补偿删除对象。
    import asyncio

    from app.utils.s3_client import s3_client

    async with async_db_session() as db:
        object_key = None
        try:
            async with db.begin():
                audio = await AudioService.upload_audio(db, dataset_id, file, auth)
                object_key = audio.object_key
        except Exception:
            if object_key:
                try:
                    await asyncio.to_thread(s3_client.delete_object, object_key)
                except Exception as e2:  # noqa: BLE001
                    from app.core.logger import log
                    log.warning(f"[音频上传] 提交失败补偿删除对象失败: {e2}")
            raise
        return SuccessResponse(data=AudioService.audio_out(audio), msg="上传成功")


@AudioRouter.get("/list", summary="查询数据集下的音频列表")
async def list_audios(
    dataset_id: Annotated[int, Query(description="数据集ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    items = await AudioService.list_audios(dataset_id)
    return SuccessResponse(data={"items": items})


@AudioRouter.get("/detail/{audio_id}", summary="查询音频详情")
async def audio_detail(
    audio_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    audio = await AudioService.get_audio(audio_id)
    return SuccessResponse(data=audio)


@AudioRouter.get("/play-url/{audio_id}", summary="获取音频播放地址")
async def get_play_url(
    audio_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    url = await AudioService.get_play_url(audio_id)
    return SuccessResponse(data={"play_url": url})


@AudioRouter.get("/content/{audio_id}", summary="获取音频原始内容（同源流式）")
async def audio_content(
    audio_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> StreamingResponse:
    """从 RustFS 流式返回音频原始字节（供前端同源加载波形，无 CORS）。

    以 ``StreamingResponse`` 逐块返回，``Content-Type`` 依扩展名（如 audio/wav、
    audio/mpeg），``Content-Disposition: inline`` 指示内联展示，``Content-Length``
    来自已入库的 ``size_bytes``。
    """
    chunks, size_bytes, content_type = await AudioService.stream_audio_content(audio_id)
    return StreamingResponse(
        chunks,
        media_type=content_type,
        headers={
            "Content-Disposition": "inline",
            "Content-Length": str(size_bytes),
        },
    )


@AudioRouter.post("/lock/{audio_id}", summary="锁定音频")
async def lock_audio(
    audio_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    result = await AudioService.lock_audio(audio_id, auth.user.id)
    return SuccessResponse(data=result)


@AudioRouter.post("/unlock/{audio_id}", summary="解锁音频")
async def unlock_audio(
    audio_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    await AudioService.unlock_audio(audio_id, auth.user.id)
    return SuccessResponse()
