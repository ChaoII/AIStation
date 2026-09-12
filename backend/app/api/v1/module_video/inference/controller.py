"""视频推理相关受控文件路由（快照展示）。"""
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .snapshot import safe_local_snapshot

SnapshotRouter = APIRouter(route_class=OperationLogRoute, prefix="/detections", tags=["视频快照"])

_MEDIA_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


@SnapshotRouter.get(
    "/{file_path:path}",
    summary="读取推理快照",
    include_in_schema=False,
    response_model=None,
)
async def get_snapshot_controller(
    file_path: Annotated[str, PathParam(..., description="DETECTIONS_DIR 下的相对路径")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:alarm:query"]))],
) -> FileResponse | JSONResponse:
    """按相对路径返回 DETECTIONS_DIR 下的快照文件（受告警查看权限保护）。"""
    target = safe_local_snapshot(file_path)
    if target is None:
        return JSONResponse(status_code=404, content={"code": 404, "msg": "快照不存在"})
    media_type = _MEDIA_TYPES.get(target.suffix.lower(), "application/octet-stream")
    return FileResponse(str(target), media_type=media_type)
