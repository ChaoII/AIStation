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

from .catalog import (
    get_scene,
    is_edge_implementable,
    list_scenes,
    scene_blockers,
    scene_configurability,
)
from .leaves import get_capabilities

SceneRouter = APIRouter(route_class=OperationLogRoute, prefix="/scene", tags=["场景目录"])


def _scene_dict(scene) -> dict:
    """场景序列化：附加前端置灰所需的诚实标记。

    - ``edge_supported``：所需模型族是否由边缘 Agent 上报（历史字段，语义不变）；
    - ``configurable``：综合「模型族 + 外部资产 + 分类契约 + 默认规则叶子」后可选中并保存成功；
    - ``unsupported_reason``：不可配置的中文原因（置灰时提示用户，而非静默失败）；
    - ``blockers``：结构化原因清单（缺族/缺资产/缺叶子），前端逐条展示。
    """
    data = asdict(scene)
    data["edge_supported"] = is_edge_implementable(scene)
    configurable, reason = scene_configurability(scene)
    data["configurable"] = configurable
    data["unsupported_reason"] = reason
    data["blockers"] = scene_blockers(scene)
    return data


@SceneRouter.get("/catalog", summary="查询任务类型目录")
async def list_scene_catalog_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:algorithm:query"]))],
    category: Annotated[str | None, Query(description="场景分类过滤")] = None,
) -> JSONResponse:
    """列出全部场景（任务类型）定义，可按 category 过滤。"""
    items = [_scene_dict(s) for s in list_scenes(category=category)]
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
    return SuccessResponse(data=_scene_dict(s), msg="查询成功")


@SceneRouter.get("/rule-capabilities", summary="规则叶子能力")
async def rule_capabilities_controller(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_video:algorithm:query"]))],
) -> JSONResponse:
    """返回逻辑算子与全部叶子能力描述（前端条件树据此渲染，spec §4.2/§4.5）。"""
    return SuccessResponse(data=get_capabilities(), msg="获取成功")
