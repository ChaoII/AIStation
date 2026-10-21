"""AI 集成开放平台 —— 控制器（开放数据面 + 内部管理面）。

本模块包含两个顶层 APIRouter（均被动态路由自动发现，容器前缀 ``/ai``）：

- :data:`OpenApiRouter`：**开放数据面**，前缀 ``/develop-api``，供外部平台
  直接调用。不带后台登录态，改用 ``Authorization: Bearer <appid>:<appkey>``
  应用凭证鉴权；需要权限点的端点再叠加 :func:`require_app_perm`。
  ``GET /auth/verify`` 成功时写入一条调用审计（``DevelopService.log_call``）。
- :data:`DevelopRouter`：**内部管理面**，前缀 ``/develop``，供平台管理员管理
  AI 集成应用与审计查询。每个端点经 ``AuthPermission(["module_ai:develop:*"])``
  校验，响应统一用 :class:`SuccessResponse` / :class:`ErrorResponse` 包裹；
  应用明文 appkey 仅 ``create`` / ``reset-key`` 返回一次。

说明：``log_call`` 的 ``app`` 形参需要 :class:`AiIntegrationAppModel`（访问
``.id`` / ``.appid``），而 ``ctx.app`` 是对外 dict（不含 ``appkey_hash``），
故此处按 ``ctx.app_id`` 重新取一次模型再调用。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.database import async_db_session
from app.core.dependencies import AuthPermission
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute

from .auth import AppContext, EmbedContext, get_app_api_auth, get_embed_ctx, require_app_perm
from .capabilities import permissions_by_category
from .embed import EmbedService
from .model import (
    AiIntegrationAppModel,
    AiIntegrationCallLogModel,
    AiIntegrationMcpSessionModel,
)
from .schema import DevelopCreateSchema, DevelopUpdateSchema, EmbedTokenIssueSchema
from .service import DevelopService


class DevelopToggleSchema(BaseModel):
    """启停 AI 集成应用的请求体。"""

    enabled: bool = Field(..., description="是否启用")


OpenApiRouter = APIRouter(
    route_class=OperationLogRoute,
    prefix="/develop-api",
    tags=["AI-集成开放API"],
)

DevelopRouter = APIRouter(
    route_class=OperationLogRoute,
    prefix="/develop",
    tags=["AI-集成管理"],
)

EmbedRouter = APIRouter(
    route_class=OperationLogRoute,
    prefix="/embed",
    tags=["AI-嵌入"],
)


@EmbedRouter.get("/meta", summary="嵌入目标元信息")
async def embed_meta(
    ctx: Annotated[EmbedContext, Depends(get_embed_ctx)],
) -> SuccessResponse:
    """返回嵌入目标名称与欢迎语（嵌入页初始化用）。

    - 令牌缺/过期/吊销/app 停用 → 401（依赖层统一处理）；
    - 应用缺 ``integration:embed:use`` → 403（权限每请求重读，收回即时生效）；
    - 目标已删除 → 404。
    """
    if "integration:embed:use" not in ctx.perms:
        raise CustomException(msg="无权限操作", code=10403, status_code=403)
    target = await EmbedService.get_target(ctx.kind, ctx.target_id)
    if target is None:
        raise CustomException(msg="嵌入目标不存在", code=10404, status_code=404)
    return SuccessResponse(
        data={
            "kind": ctx.kind,
            "target_id": ctx.target_id,
            "name": target["name"],
            "welcome": target["description"] or "",
            "expire_at": ctx.expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        },
        msg="查询成功",
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


@OpenApiRouter.post("/auth/token", summary="换票签发嵌入短期令牌")
async def auth_token(
    data: EmbedTokenIssueSchema,
    ctx: Annotated[AppContext, Depends(get_app_api_auth)],
) -> SuccessResponse:
    """服务端换票：``appid:appkey`` → 绑定 ``app+kind+target`` 的短期 access_token。

    - 缺 ``integration:embed:use`` → 403 + denied 审计；
    - 目标不存在 → 404 + denied 审计；
    - 明文 token 仅本响应返回一次，库内只存 sha256（响应本身不写日志）。
    """
    async with async_db_session() as db:
        row = await db.get(AiIntegrationAppModel, ctx.app_id)
    if row is None:
        raise CustomException(msg="鉴权失败", code=10401, status_code=401)

    async def _audit(status: str, error: str | None = None, summary: str | None = None) -> None:
        """写一条换票审计（request_body 仅 kind/target，绝不含明文 token）。"""
        await DevelopService.log_call(
            row,
            category="embed",
            capability="token.issue",
            method="REST",
            request_path="/auth/token",
            request_body={"kind": data.kind, "target_id": data.target_id},
            status=status,
            error=error,
            result_summary=summary,
        )

    try:
        require_app_perm(ctx, "integration:embed:use")
    except CustomException as e:
        await _audit("denied", error=e.msg)
        raise
    if await EmbedService.get_target(data.kind, data.target_id) is None:
        await _audit("denied", error="嵌入目标不存在")
        raise CustomException(msg="嵌入目标不存在", code=10404, status_code=404)
    result = await EmbedService.issue_token(
        row, kind=data.kind, target_id=data.target_id, ttl=data.ttl, issued_by="exchange"
    )
    await _audit("success", summary=f"{data.kind}:{data.target_id}")
    return SuccessResponse(data=result, msg="令牌已签发")


# ---------------------------------------------------------------------- #
# 内部管理面（DevelopRouter）：供平台管理员管理 AI 集成应用与审计查询。
# 每个端点经 AuthPermission 校验（module_ai:develop:*），响应统一用
# SuccessResponse / ErrorResponse 包裹。应用明文 appkey 仅 create/reset-key
# 返回一次，列表/详情沿用 DevelopService 序列化（不含 appkey_hash）。
# ---------------------------------------------------------------------- #
@DevelopRouter.get("/list", summary="分页查询AI集成应用")
async def develop_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
    keyword: Annotated[str | None, Query(description="按名称/appid 模糊搜索")] = None,
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
) -> JSONResponse:
    return SuccessResponse(
        data=await DevelopService.list_apps(keyword, page_no, page_size), msg="查询成功"
    )


@DevelopRouter.get("/detail/{app_id}", summary="查询AI集成应用详情")
async def develop_detail(
    app_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
) -> JSONResponse:
    result = await DevelopService.get_app(app_id)
    if not result:
        return ErrorResponse(msg="应用不存在")
    return SuccessResponse(data=result, msg="查询成功")


@DevelopRouter.post("/create", summary="创建AI集成应用")
async def develop_create(
    data: DevelopCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await DevelopService.create_app(data, auth), msg="创建成功")


@DevelopRouter.put("/update/{app_id}", summary="更新AI集成应用")
async def develop_update(
    app_id: int,
    data: DevelopUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:update"]))],
) -> JSONResponse:
    result = await DevelopService.update_app(app_id, data, auth)
    if not result:
        return ErrorResponse(msg="应用不存在")
    return SuccessResponse(data=result, msg="更新成功")


@DevelopRouter.delete("/delete", summary="批量删除AI集成应用")
async def develop_delete(
    ids: Annotated[list[int], Body(description="应用ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:delete"]))],
) -> JSONResponse:
    await DevelopService.delete_app(ids, auth)
    return SuccessResponse(msg="删除成功")


@DevelopRouter.put("/toggle/{app_id}", summary="启停AI集成应用")
async def develop_toggle(
    app_id: int,
    data: DevelopToggleSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:update"]))],
) -> JSONResponse:
    result = await DevelopService.toggle_app(app_id, data.enabled, auth)
    if not result:
        return ErrorResponse(msg="应用不存在")
    return SuccessResponse(data=result, msg="已更新")


@DevelopRouter.post("/reset-key/{app_id}", summary="重置AI集成应用密钥")
async def develop_reset_key(
    app_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:reset"]))],
) -> JSONResponse:
    result = await DevelopService.reset_appkey(app_id, auth)
    return SuccessResponse(data=result, msg="重置成功")


@DevelopRouter.get("/call-logs", summary="分页查询调用日志")
async def develop_call_logs(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
    app_id: Annotated[int | None, Query(description="按应用ID过滤")] = None,
    category: Annotated[str | None, Query(description="按品类过滤")] = None,
    method: Annotated[str | None, Query(description="按出海口过滤 REST/MCP/EMBED")] = None,
    status: Annotated[str | None, Query(description="按状态过滤 success/failed/denied")] = None,
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
) -> JSONResponse:
    return SuccessResponse(
        data=await _query_call_logs(app_id, category, method, status, page_no, page_size),
        msg="查询成功",
    )


@DevelopRouter.get("/mcp-sessions", summary="分页查询MCP会话")
async def develop_mcp_sessions(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
    app_id: Annotated[int | None, Query(description="按应用ID过滤")] = None,
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
) -> JSONResponse:
    return SuccessResponse(
        data=await _query_mcp_sessions(app_id, page_no, page_size), msg="查询成功"
    )


def _call_log_to_dict(row: AiIntegrationCallLogModel) -> dict:
    """调用日志行 → 对外 dict（审计只读，含脱敏入参；不泄出任何密钥）。"""
    return {
        "id": row.id,
        "created_time": row.created_time,
        "app_id": row.app_id,
        "appid": row.appid,
        "category": row.category,
        "capability": row.capability,
        "log_type": row.log_type,
        "method": row.method,
        "transport": row.transport,
        "session_id": row.session_id,
        "client_info": row.client_info,
        "request_path": row.request_path,
        "request_body": row.request_body,
        "status": row.status,
        "error": row.error,
        "latency_ms": row.latency_ms,
        "cost_tokens": row.cost_tokens,
        "result_summary": row.result_summary,
    }


def _mcp_session_to_dict(row: AiIntegrationMcpSessionModel) -> dict:
    """MCP 会话行 → 对外 dict（连接级监控，只读）。"""
    return {
        "id": row.id,
        "created_time": row.created_time,
        "app_id": row.app_id,
        "appid": row.appid,
        "session_id": row.session_id,
        "transport": row.transport,
        "client_info": row.client_info,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "duration_s": row.duration_s,
        "tool_calls": row.tool_calls,
        "close_reason": row.close_reason,
    }


async def _query_call_logs(
    app_id: int | None,
    category: str | None,
    method: str | None,
    status: str | None,
    page_no: int,
    page_size: int,
) -> dict:
    """按 app_id/category/method/status 过滤调用日志，分页返回。"""
    page_no = max(int(page_no or 1), 1)
    page_size = max(int(page_size or 20), 1)
    wheres = []
    if app_id is not None:
        wheres.append(AiIntegrationCallLogModel.app_id == app_id)
    if category:
        wheres.append(AiIntegrationCallLogModel.category == category)
    if method:
        wheres.append(AiIntegrationCallLogModel.method == method)
    if status:
        wheres.append(AiIntegrationCallLogModel.status == status)

    async with async_db_session() as db:
        total = (
            await db.execute(
                select(func.count()).select_from(
                    select(AiIntegrationCallLogModel.id).where(*wheres).subquery()
                )
            )
        ).scalar() or 0
        rows = (
            await db.execute(
                select(AiIntegrationCallLogModel)
                .where(*wheres)
                .order_by(AiIntegrationCallLogModel.id.desc())
                .offset((page_no - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return {
            "page_no": page_no,
            "page_size": page_size,
            "total": total,
            "has_next": page_no * page_size < total,
            "items": [_call_log_to_dict(r) for r in rows],
        }


async def _query_mcp_sessions(
    app_id: int | None,
    page_no: int,
    page_size: int,
) -> dict:
    """按 app_id 过滤 MCP 会话，分页返回。"""
    page_no = max(int(page_no or 1), 1)
    page_size = max(int(page_size or 20), 1)
    wheres = []
    if app_id is not None:
        wheres.append(AiIntegrationMcpSessionModel.app_id == app_id)

    async with async_db_session() as db:
        total = (
            await db.execute(
                select(func.count()).select_from(
                    select(AiIntegrationMcpSessionModel.id).where(*wheres).subquery()
                )
            )
        ).scalar() or 0
        rows = (
            await db.execute(
                select(AiIntegrationMcpSessionModel)
                .where(*wheres)
                .order_by(AiIntegrationMcpSessionModel.id.desc())
                .offset((page_no - 1) * page_size)
                .limit(page_size)
            )
        ).scalars().all()
        return {
            "page_no": page_no,
            "page_size": page_size,
            "total": total,
            "has_next": page_no * page_size < total,
            "items": [_mcp_session_to_dict(r) for r in rows],
        }
