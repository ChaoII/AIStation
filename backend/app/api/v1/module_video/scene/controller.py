from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi import Path as PathParam
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute

from .catalog import get_scene, list_scenes

SceneRouter = APIRouter(route_class=OperationLogRoute, prefix="/scene", tags=["场景目录"])


@SceneRouter.get("/catalog", summary="查询任务类型目录")
async def list_scene_catalog_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:algorithm:query"]))],
    category: Annotated[str | None, Query(description="场景分类过滤")] = None,
) -> JSONResponse:
    """列出全部场景（任务类型）定义，可按 category 过滤。"""
    items = [asdict(s) for s in list_scenes(category=category)]
    return SuccessResponse(data={"items": items, "total": len(items)}, msg="查询成功")


@SceneRouter.get("/catalog/{code}", summary="查询场景详情")
async def get_scene_controller(
    code: Annotated[str, PathParam(..., description="场景码")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:algorithm:query"]))],
) -> JSONResponse:
    """按场景码查询详情，缺失返回 404。"""
    s = get_scene(code)
    if s is None:
        raise CustomException(msg="场景不存在", code=404, status_code=404)
    return SuccessResponse(data=asdict(s), msg="查询成功")
