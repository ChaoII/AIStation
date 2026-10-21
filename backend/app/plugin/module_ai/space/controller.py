"""个人工作空间控制器：文件夹/文件 CRUD、上传/下载/预览、配额。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute

from .schema import (
    SpaceFileMoveSchema,
    SpaceFileRenameSchema,
    SpaceFolderCreateSchema,
    SpaceFolderUpdateSchema,
    SpaceQuotaRequestSchema,
    SpaceQuotaReviewSchema,
)
from .service import SpaceService

SpaceRouter = APIRouter(
    route_class=OperationLogRoute, prefix="/space", tags=["AI-个人空间"]
)


def _uid(auth: AuthSchema) -> int:
    return auth.user.id


# ---------------------------------------------------------------- #
# 文件夹
# ---------------------------------------------------------------- #
@SpaceRouter.get("/folders/tree", summary="个人空间文件夹树")
async def folder_tree(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await SpaceService.folder_tree(_uid(auth)), msg="查询成功")


@SpaceRouter.post("/folders/create", summary="新建文件夹")
async def folder_create(
    data: SpaceFolderCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:manage"]))],
) -> JSONResponse:
    try:
        return SuccessResponse(
            data=await SpaceService.create_folder(data.name, data.parent_id, _uid(auth)),
            msg="创建成功",
        )
    except Exception as e:
        return ErrorResponse(msg=str(e), status_code=400)


@SpaceRouter.put("/folders/update/{folder_id}", summary="重命名文件夹")
async def folder_update(
    folder_id: int,
    data: SpaceFolderUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:manage"]))],
) -> JSONResponse:
    result = await SpaceService.rename_folder(folder_id, data.name, _uid(auth))
    if not result:
        return ErrorResponse(msg="文件夹不存在")
    return SuccessResponse(data=result, msg="修改成功")


@SpaceRouter.delete("/folders/delete", summary="删除文件夹（级联删除内容）")
async def folder_delete(
    folder_id: Annotated[int, Body(description="文件夹ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:delete"]))],
) -> JSONResponse:
    try:
        result = await SpaceService.delete_folder(folder_id, _uid(auth))
        return SuccessResponse(data=result, msg="删除成功")
    except Exception as e:
        return ErrorResponse(msg=str(e), status_code=400)


# ---------------------------------------------------------------- #
# 文件
# ---------------------------------------------------------------- #
@SpaceRouter.get("/files/list", summary="文件列表（分页/目录/关键词/类型）")
async def file_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:query"]))],
    folder_id: int | None = None,
    keyword: str | None = None,
    file_type: str | None = None,
    page_no: int = 1,
    page_size: int = 20,
) -> JSONResponse:
    return SuccessResponse(
        data=await SpaceService.list_files(
            _uid(auth), folder_id, keyword, file_type, page_no, page_size
        ),
        msg="查询成功",
    )


@SpaceRouter.post("/files/upload", summary="上传文件到个人空间")
async def file_upload(
    file: Annotated[UploadFile, File(...)],
    folder_id: Annotated[int | None, Form()] = None,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:upload"]))] = None,
) -> JSONResponse:
    data = await file.read()
    try:
        result = await SpaceService.upload_file(
            _uid(auth), file.filename or "", data, folder_id=folder_id, source="upload"
        )
        return SuccessResponse(data=result, msg="上传成功")
    except Exception as e:
        return ErrorResponse(msg=str(e), status_code=400)


@SpaceRouter.get("/files/{file_id}/download", summary="下载文件")
async def file_download(
    file_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:download"]))],
):
    try:
        meta = await SpaceService.download_file(file_id, _uid(auth))
    except ValueError as e:
        return ErrorResponse(msg=str(e), status_code=404)
    import asyncio
    from urllib.parse import quote

    from app.utils.s3_client import s3_client

    obj = await asyncio.to_thread(s3_client.get_object, meta["object_key"])
    body = obj["Body"]

    async def _gen():
        while True:
            chunk = await asyncio.to_thread(body.read, 65536)
            if not chunk:
                break
            yield chunk

    return StreamingResponse(
        _gen(),
        media_type=meta["mime_type"] or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(meta['name'])}"},
    )


@SpaceRouter.get("/files/{file_id}/preview", summary="在线预览（文本内容/类型标记）")
async def file_preview(
    file_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:query"]))],
):
    try:
        result = await SpaceService.preview_file(file_id, _uid(auth))
    except ValueError as e:
        return ErrorResponse(msg=str(e), status_code=404)
    if result["kind"] == "text":
        return SuccessResponse(data=result, msg="查询成功")
    if result["kind"] in ("image", "pdf", "docx"):
        # 二进制内容走下载流，前端按类型渲染（img / vue-pdf-embed / mammoth）
        meta = await SpaceService.download_file(file_id, _uid(auth))
        import asyncio

        from app.utils.s3_client import s3_client

        obj = await asyncio.to_thread(s3_client.get_object, meta["object_key"])
        body = obj["Body"]

        async def _gen():
            while True:
                chunk = await asyncio.to_thread(body.read, 65536)
                if not chunk:
                    break
                yield chunk

        return StreamingResponse(_gen(), media_type=meta["mime_type"] or "application/octet-stream")
    return ErrorResponse(msg="该类型暂不支持预览，请下载后查看", status_code=400)


@SpaceRouter.put("/files/rename", summary="重命名文件")
async def file_rename(
    data: SpaceFileRenameSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:manage"]))],
) -> JSONResponse:
    result = await SpaceService.rename_file(data.file_id, data.name, _uid(auth))
    if not result:
        return ErrorResponse(msg="文件不存在")
    return SuccessResponse(data=result, msg="修改成功")


@SpaceRouter.post("/files/move", summary="移动文件到文件夹")
async def file_move(
    data: SpaceFileMoveSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:manage"]))],
) -> JSONResponse:
    try:
        result = await SpaceService.move_file(data.file_id, data.folder_id, _uid(auth))
    except Exception as e:
        return ErrorResponse(msg=str(e), status_code=400)
    if not result:
        return ErrorResponse(msg="文件不存在")
    return SuccessResponse(data=result, msg="移动成功")


@SpaceRouter.delete("/files/delete", summary="批量删除文件")
async def file_delete(
    file_ids: Annotated[list[int], Body(description="文件ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:delete"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await SpaceService.delete_files(file_ids, _uid(auth)), msg="删除成功"
    )


@SpaceRouter.get("/quota", summary="个人空间配额")
async def space_quota(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await SpaceService.quota(_uid(auth)), msg="查询成功")


# ---------------------------------------------------------------- #
# 扩容申请与审核
# ---------------------------------------------------------------- #
@SpaceRouter.post("/quota/request", summary="提交扩容申请")
async def quota_request(
    data: SpaceQuotaRequestSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:query"]))],
) -> JSONResponse:
    try:
        result = await SpaceService.submit_request(_uid(auth), data.target_mb, data.reason)
        return SuccessResponse(data=result, msg=result.get("msg", "已提交"))
    except CustomException as e:
        return ErrorResponse(msg=str(e), status_code=e.status_code or 400)


@SpaceRouter.get("/quota/requests/mine", summary="我的扩容申请")
async def quota_requests_mine(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await SpaceService.list_requests(_uid(auth)), msg="查询成功")


@SpaceRouter.get("/quota/requests", summary="全部扩容申请（管理员）")
async def quota_requests_all(
    status: str | None = None,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:quota_review"]))] = None,
) -> JSONResponse:
    return SuccessResponse(data=await SpaceService.list_all_requests(status), msg="查询成功")


@SpaceRouter.post("/quota/requests/{request_id}/review", summary="审核扩容申请（管理员）")
async def quota_request_review(
    request_id: int,
    data: SpaceQuotaReviewSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:space:quota_review"]))],
) -> JSONResponse:
    try:
        result = await SpaceService.review_request(
            request_id, data.approve, data.quota_mb, data.note, _uid(auth)
        )
        return SuccessResponse(data=result, msg=result.get("msg", "已处理"))
    except CustomException as e:
        return ErrorResponse(msg=str(e), status_code=e.status_code or 400)
