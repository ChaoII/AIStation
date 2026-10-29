"""AI 集成开放平台 —— 阶段 3a：外部 OAuth 服务控制器。

- 管理面（``AuthPermission(["module_ai:develop:*"])``）：外部服务 CRUD。
- 用户面（``Depends(get_current_user)``）：connect/callback/refresh/revoke/status
  （在 Task 3/4 中追加）。
- 前缀 ``/oauth-ext``，挂动态路由（``module_ai`` 下自动发现）。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission

from .schema import (
    OAuthExtServiceCreateSchema,
    OAuthExtServiceUpdateSchema,
)
from .service import OAuthExtService

OAuthExtRouter = APIRouter(
    prefix="/oauth-ext",
    tags=["AI-集成外部OAuth"],
)


# ---------------------------------------------------------------------- #
# 管理面：外部服务 CRUD（复用 module_ai:develop:* 权限点）。
# ---------------------------------------------------------------------- #
@OAuthExtRouter.get("/services", summary="外部OAuth服务列表（管理员）")
async def oauth_ext_services_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
) -> SuccessResponse:
    items = await OAuthExtService.list_services()
    return SuccessResponse(data={"items": items, "total": len(items)}, msg="查询成功")


@OAuthExtRouter.post("/services", summary="登记外部OAuth服务（管理员）")
async def oauth_ext_service_create(
    data: OAuthExtServiceCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:create"]))],
) -> SuccessResponse:
    return SuccessResponse(data=await OAuthExtService.create_service(data, auth), msg="创建成功")


@OAuthExtRouter.put("/services/{service_id}", summary="更新外部OAuth服务（管理员）")
async def oauth_ext_service_update(
    service_id: int,
    data: OAuthExtServiceUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:update"]))],
) -> SuccessResponse:
    return SuccessResponse(data=await OAuthExtService.update_service(service_id, data, auth), msg="更新成功")


@OAuthExtRouter.delete("/services/{service_id}", summary="删除外部OAuth服务（管理员）")
async def oauth_ext_service_delete(
    service_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:delete"]))],
) -> SuccessResponse:
    await OAuthExtService.delete_service(service_id)
    return SuccessResponse(data=None, msg="删除成功")
