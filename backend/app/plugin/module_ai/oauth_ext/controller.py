"""AI 集成开放平台 —— 阶段 3a：外部 OAuth 服务控制器。

- 管理面（``AuthPermission(["module_ai:develop:*"])``）：外部服务 CRUD。
- 用户面（``Depends(get_current_user)``）：connect/callback/refresh/revoke/status
  （在 Task 3/4 中追加）。
- 前缀 ``/oauth-ext``，挂动态路由（``module_ai`` 下自动发现）。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission, get_current_user

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


# ---------------------------------------------------------------------- #
# 用户面：授权（connect / callback），每个用户走 get_current_user。
# ---------------------------------------------------------------------- #
@OAuthExtRouter.get("/connect/{service_id}", summary="发起连接外部服务（生成state并跳转）")
async def oauth_ext_connect(
    service_id: int,
    user: Annotated[AuthSchema, Depends(get_current_user)],
) -> SuccessResponse:
    user_id = getattr(user, "user", None)
    uid = getattr(user_id, "id", None) if user_id else None
    return SuccessResponse(data=await OAuthExtService.connect_redirect(service_id, uid), msg="请前往授权")


@OAuthExtRouter.get("/callback", summary="外部 OAuth 授权回调（换token并落库）")
async def oauth_ext_callback(
    user: Annotated[AuthSchema, Depends(get_current_user)],
    service_id: int,
    code: Annotated[str, Query()],
    state: Annotated[str, Query()],
    error: Annotated[str | None, Query()] = None,
    redirect_uri: Annotated[str | None, Query()] = None,
) -> SuccessResponse:
    uid = getattr(getattr(user, "user", None), "id", None)
    if error:
        return SuccessResponse(data={"connected": False, "error": error}, msg="授权失败")
    if uid is None:
        from app.core.exceptions import CustomException

        raise CustomException(msg="登录态无效", code=10401, status_code=401)
    result = await OAuthExtService.handle_callback(service_id, uid, code, state, redirect_uri=redirect_uri)
    return SuccessResponse(data=result, msg="已连接")


@OAuthExtRouter.get("/status/{service_id}", summary="查询连接状态（用户）")
async def oauth_ext_status(
    service_id: int,
    user: Annotated[AuthSchema, Depends(get_current_user)],
) -> SuccessResponse:
    uid = getattr(getattr(user, "user", None), "id", None)
    data = await OAuthExtService.connection_status(service_id, uid)
    return SuccessResponse(data=data, msg="查询成功")


@OAuthExtRouter.post("/revoke/{service_id}", summary="撤销外部服务授权（用户）")
async def oauth_ext_revoke(
    service_id: int,
    user: Annotated[AuthSchema, Depends(get_current_user)],
) -> SuccessResponse:
    uid = getattr(getattr(user, "user", None), "id", None)
    data = await OAuthExtService.revoke(service_id, uid)
    return SuccessResponse(data=data, msg="已撤销")
