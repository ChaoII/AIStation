"""AI 资产嵌入 —— 控制器（公开消费面 + 工作台管理面）。

本模块包含两个顶层 APIRouter（均被动态路由自动发现，容器前缀 ``/ai``）：

- :data:`AssetEmbedRouter`：**公开消费面**，前缀 ``/embed``。供外部网页凭**资产令牌**
  （``Authorization: Bearer <asset_token>``）消费单个 agent/工作流，无需登录态、无 appid/appkey。
  ``/sdk.js`` 无鉴权（纯代码，不含凭证）。
- :data:`AssetTokenRouter`：**工作台管理面**，前缀 ``/asset-embed``。供平台管理员对某资产
  签发/列出/吊销独立绑定该资产的令牌，经 ``AuthPermission(["module_ai:asset_embed:manage"])`` 校验。
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute
from app.plugin.module_ai.assistant.agno_service import agno_stream_response
from app.plugin.module_ai.streaming import ui_stream_response

from .auth import EmbedContext, get_embed_ctx
from .embed import AssetEmbedService
from .schema import AssetRunSchema, AssetTokenIssueSchema, AssetTokenUpdateSchema
from .service import AssetTokenService

AssetEmbedRouter = APIRouter(
    route_class=OperationLogRoute,
    prefix="/embed",
    tags=["AI-资产嵌入"],
)

AssetTokenRouter = APIRouter(
    route_class=OperationLogRoute,
    prefix="/asset-embed",
    tags=["AI-资产嵌入管理"],
)


@AssetEmbedRouter.get("/meta", summary="嵌入目标元信息")
async def embed_meta(
    ctx: Annotated[EmbedContext, Depends(get_embed_ctx)],
) -> SuccessResponse:
    """返回嵌入目标名称与欢迎语（嵌入页初始化用）。

    令牌缺/过期/吊销/目标停用 → 401（依赖层统一处理）；目标已删除 → 404。
    """
    target = await AssetEmbedService.get_target(ctx.kind, ctx.target_id)
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


@AssetEmbedRouter.post("/run", summary="嵌入对话（流式）")
async def embed_run(
    data: AssetRunSchema,
    request: Request,
    ctx: Annotated[EmbedContext, Depends(get_embed_ctx)],
) -> StreamingResponse:
    """嵌入对话主通道：``Bearer <asset_token>``，请求体仅 ``sid`` + ``message``。

    校验顺序（全部在返回流之前完成）：会话绑定 → 生成流。审计在流结束时写入
    ``ai_asset_embed_logs``（``method=EMBED`` 域）。
    """
    await AssetEmbedService.check_limits(
        getattr(request.app.state, "redis", None),
        ctx,
        request.client.host if request.client else "",
    )
    session_id, session_reset = await AssetEmbedService.prepare_session(ctx, data.sid)
    gen = AssetEmbedService.run_stream(
        ctx,
        data.sid,
        session_id,
        session_reset,
        data.message,
        redis=getattr(request.app.state, "redis", None),
    )
    # 与已登录端点保持同一协议包装：工作流走 UI Message Stream，agent 走 Agno 事件流
    if ctx.kind == "workflow":
        return ui_stream_response(gen)
    return agno_stream_response(gen)


@AssetEmbedRouter.get("/sdk.js", summary="嵌入 SDK 脚本")
async def embed_sdk() -> PlainTextResponse:
    """返回嵌入 SDK 静态脚本。

    本端点**无鉴权**：返回的是纯代码、不含任何凭证；实质鉴权发生在 ``/embed/run``
    等业务端点（Bearer asset_token）。请勿在此文件中放入任何密钥。
    """
    path = Path(__file__).parent / "static" / "ai-assistant.js"
    return PlainTextResponse(
        path.read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@AssetTokenRouter.post("/tokens", summary="签发资产嵌入令牌")
async def issue_asset_token(
    data: AssetTokenIssueSchema,
    _auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:asset_embed:manage"]))],
) -> SuccessResponse:
    """工作台侧为某 agent/工作流签发独立绑定该资产的短期令牌。明文仅返回一次。"""
    result = await AssetTokenService.issue_token(
        kind=data.kind,
        target_id=data.target_id,
        ttl=data.ttl,
        permanent=data.permanent,
        allow_domains=data.allow_domains,
        allow_ips=data.allow_ips,
        issued_by="admin",
    )
    return SuccessResponse(data=result, msg="签发成功")


@AssetTokenRouter.get("/tokens", summary="资产嵌入令牌列表")
async def list_asset_tokens(
    kind: Annotated[str, Query(description="嵌入形态 agent/workflow")],
    target_id: Annotated[int, Query(description="嵌入目标ID")],
    _auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:asset_embed:manage"]))],
) -> SuccessResponse:
    """列出某资产已签发令牌（只读元信息，不含明文/散列）。"""
    items = await AssetTokenService.list_tokens(kind, target_id)
    return SuccessResponse(data={"items": items}, msg="查询成功")


@AssetTokenRouter.put("/tokens/{token_id}/revoke", summary="吊销资产嵌入令牌")
async def revoke_asset_token(
    token_id: int,
    _auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:asset_embed:manage"]))],
) -> SuccessResponse:
    """吊销令牌（置 ``revoked=true``，立即生效；保留审计行不物理删）。"""
    if not await AssetTokenService.revoke_token(token_id):
        raise CustomException(msg="令牌不存在", code=10404, status_code=404)
    return SuccessResponse(data=None, msg="吊销成功")


@AssetTokenRouter.put("/tokens/{token_id}", summary="更新令牌白名单")
async def update_asset_token(
    token_id: int,
    data: AssetTokenUpdateSchema,
    _auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:asset_embed:manage"]))],
) -> SuccessResponse:
    """更新令牌白名单（域名 / IP）。字段未传表示不改；传空串表示清空为不限。"""
    fields = data.model_fields_set
    allow_domains = data.allow_domains if "allow_domains" in fields else None
    allow_ips = data.allow_ips if "allow_ips" in fields else None
    if not await AssetTokenService.update_token(token_id, allow_domains, allow_ips):
        raise CustomException(msg="令牌不存在", code=10404, status_code=404)
    return SuccessResponse(data=None, msg="更新成功")


@AssetTokenRouter.get("/tokens/{token_id}/logs", summary="令牌使用日志")
async def list_token_logs(
    token_id: int,
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
    _auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:asset_embed:manage"]))] = None,
) -> SuccessResponse:
    """分页查询某令牌的使用日志（按时间倒序）。"""
    result = await AssetTokenService.list_token_logs(token_id, page_no=page_no, page_size=page_size)
    return SuccessResponse(data=result, msg="查询成功")
