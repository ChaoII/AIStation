"""文档接口 controller：上传/列表/详情/全文/锁定。

镜像 ``video_controller.py`` 的结构与鉴权语义；上传因 ``DocumentService.upload_document``
接受外部 ``db`` 会话（只 flush 不 commit），由控制器包裹 ``begin()`` 事务，
并在提交失败时补偿删除已上传的 RustFS 对象。
"""
import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.database import async_db_session
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute
from app.utils.s3_client import s3_client

from .document_service import DocumentService

DocumentRouter = APIRouter(
    route_class=OperationLogRoute, prefix="/document", tags=["数据标注-文本文档"]
)


@DocumentRouter.post("/upload", summary="上传文本文档")
async def upload_document(
    dataset_id: Annotated[int, Query(description="数据集ID")],
    file: Annotated[UploadFile, File(...)],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:create"]))],
) -> JSONResponse:
    # DocumentService.upload_document 接受外部 db 会话，内部仅 flush 不 commit；
    # 由本控制器包裹 begin() 事务，保证提交正常收口；提交失败则补偿删除对象。
    async with async_db_session() as db:
        object_key = None
        try:
            async with db.begin():
                document = await DocumentService.upload_document(db, dataset_id, file, auth)
                object_key = document.object_key
        except Exception:
            if object_key:
                try:
                    await asyncio.to_thread(s3_client.delete_object, object_key)
                except Exception as e2:  # noqa: BLE001
                    from app.core.logger import log
                    log.warning(f"[文档上传] 提交失败补偿删除对象失败: {e2}")
            raise
        return SuccessResponse(data=DocumentService.document_out(document), msg="上传成功")


@DocumentRouter.get("/list", summary="查询数据集下的文本文档列表")
async def list_documents(
    dataset_id: Annotated[int, Query(description="数据集ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    items = await DocumentService.list_documents(dataset_id)
    return SuccessResponse(data={"items": items})


@DocumentRouter.get("/detail/{document_id}", summary="查询文本文档详情")
async def document_detail(
    document_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    document = await DocumentService.get_document(document_id)
    return SuccessResponse(data=document)


@DocumentRouter.get("/content/{document_id}", summary="获取文本文档全文")
async def document_content(
    document_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> Response:
    text = await DocumentService.get_document_content(document_id)
    return Response(content=text, media_type="text/plain; charset=utf-8")


@DocumentRouter.post("/lock/{document_id}", summary="锁定文本文档")
async def lock_document(
    document_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    result = await DocumentService.lock_document(document_id, auth.user.id)
    return SuccessResponse(data=result)


@DocumentRouter.post("/unlock/{document_id}", summary="解锁文本文档")
async def unlock_document(
    document_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["annotation:dataset:query"]))],
) -> JSONResponse:
    await DocumentService.unlock_document(document_id, auth.user.id)
    return SuccessResponse()
