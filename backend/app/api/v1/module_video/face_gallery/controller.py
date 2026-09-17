from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.request import PaginationService
from app.common.response import SuccessResponse
from app.core.base_params import PaginationQueryParam
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .param import FaceGalleryQueryParam
from .schema import FaceGalleryEnrollSchema, FaceGalleryMatchSchema
from .service import FaceGalleryService

FaceGalleryRouter = APIRouter(
    route_class=OperationLogRoute, prefix="/face-gallery", tags=["人脸底库"]
)


@FaceGalleryRouter.get("/list", summary="查询人脸底库列表")
async def get_face_gallery_list_controller(
    page: Annotated[PaginationQueryParam, Depends()],
    search: Annotated[FaceGalleryQueryParam, Depends()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:face_gallery:query"]))],
) -> JSONResponse:
    result_list = await FaceGalleryService.get_list_service(
        search=search, auth=auth, order_by=page.order_by
    )
    result = await PaginationService.paginate(
        data_list=result_list, page_no=page.page_no, page_size=page.page_size
    )
    return SuccessResponse(data=result, msg="查询成功")


@FaceGalleryRouter.post("/enroll", summary="录入/更新人脸底库（特征向量）")
async def enroll_face_gallery_controller(
    data: FaceGalleryEnrollSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:face_gallery:create"]))],
) -> JSONResponse:
    result = await FaceGalleryService.enroll_service(data=data, auth=auth)
    return SuccessResponse(data=result, msg="录入成功")


@FaceGalleryRouter.delete("/delete", summary="删除人脸底库条目")
async def delete_face_gallery_controller(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:face_gallery:delete"]))],
) -> JSONResponse:
    await FaceGalleryService.delete_service(ids=ids, auth=auth)
    return SuccessResponse(msg="删除成功")


@FaceGalleryRouter.post("/match", summary="人脸底库比对（余弦相似度 top-k）")
async def match_face_gallery_controller(
    data: FaceGalleryMatchSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:face_gallery:query"]))],
) -> JSONResponse:
    items = await FaceGalleryService.match_service(data=data)
    return SuccessResponse(data={"items": items, "total": len(items)}, msg="比对成功")
