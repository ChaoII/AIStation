"""AI 集成开放平台 —— 开放数据面（Open Data Plane）控制器。

本模块提供供外部平台直接调用的开放 API：不带后台登录态，改用
``Authorization: Bearer <appid>:<appkey>`` 应用凭证鉴权。

- :data:`OpenApiRouter`：路由前缀 ``/develop-api``（容器前缀 ``/ai`` 之下，
  完整路径 ``/api/v1/ai/develop-api/...``），每个端点经 :func:`get_app_api_auth`
  鉴权；需要权限点的端点再叠加 :func:`require_app_perm`。
- ``GET /auth/verify``：鉴权验证端点——成功返回应用身份、授权能力与按品类分组，
  并写入一条调用审计（``DevelopService.log_call``）。

说明：``log_call`` 的 ``app`` 形参需要 :class:`AiIntegrationAppModel`（访问
``.id`` / ``.appid``），而 ``ctx.app`` 是对外 dict（不含 ``appkey_hash``），
故此处按 ``ctx.app_id`` 重新取一次模型再调用。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.common.response import SuccessResponse
from app.core.database import async_db_session
from app.core.router_class import OperationLogRoute

from .auth import AppContext, get_app_api_auth
from .capabilities import permissions_by_category
from .model import AiIntegrationAppModel
from .service import DevelopService

OpenApiRouter = APIRouter(
    route_class=OperationLogRoute,
    prefix="/develop-api",
    tags=["AI-集成开放API"],
)


@OpenApiRouter.get("/auth/verify", summary="鉴权验证")
async def auth_verify(
    ctx: Annotated[AppContext, Depends(get_app_api_auth)],
) -> SuccessResponse:
    """校验应用凭证并返回应用信息。

    依赖 :func:`get_app_api_auth`：解析 ``Authorization: Bearer <appid>:<appkey>``，
    校验失败统一抛 401（由全局异常处理器转换）。成功返回应用身份、授权能力
    （``perms`` 排序列表）与按品类分组（``categories``）、过期时间、启停状态；
    同时写入一条 ``auth/verify`` 调用审计（更新应用 ``last_call_at`` / ``call_count``）。
    """
    perms = sorted(ctx.perms)
    data = {
        "appid": ctx.appid,
        "name": ctx.app["name"],
        "perms": perms,
        "categories": permissions_by_category(perms),
        "expire_at": ctx.app["expire_at"],
        "enabled": ctx.app["enabled"],
    }
    # 重新按主键取模型，交给 log_call（其形参需要 ORM 模型而非对外 dict）。
    async with async_db_session() as db:
        row = await db.get(AiIntegrationAppModel, ctx.app_id)
    if row is not None:
        await DevelopService.log_call(
            row,
            category="auth",
            capability="verify",
            method="REST",
            request_path="/auth/verify",
            status="success",
        )
    return SuccessResponse(data=data, msg="校验成功")
