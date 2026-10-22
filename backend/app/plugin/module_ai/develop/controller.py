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

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.database import async_db_session
from app.core.dependencies import AuthPermission
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute
from app.plugin.module_ai.assistant.agno_service import agno_stream_response
from app.plugin.module_ai.streaming import ui_stream_response

# 导入 handler 包即注册全部开放能力（REST 与 MCP 共用注册表）。
from . import handlers as _handlers  # noqa: F401
from .approvals import ApprovalService
from .auth import AppContext, EmbedContext, get_app_api_auth, get_embed_ctx, require_app_perm
from .capabilities import permissions_by_category
from .embed import EmbedService
from .model import (
    AiIntegrationAppModel,
    AiIntegrationCallLogModel,
    AiIntegrationMcpSessionModel,
)
from .openapi import audit_call, invoke_capability
from .registry import all_capabilities, capabilities_for, to_public_dict
from .schema import (
    ApprovalReviewSchema,
    CapabilityInvokeSchema,
    CapabilityTrySchema,
    DevelopCreateSchema,
    DevelopUpdateSchema,
    EmbedMintSchema,
    EmbedRunSchema,
    EmbedTokenIssueSchema,
)
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
            "appid": ctx.appid,
            "kind": ctx.kind,
            "target_id": ctx.target_id,
            "name": target["name"],
            "welcome": target["description"] or "",
            "expire_at": ctx.expires_at.strftime("%Y-%m-%d %H:%M:%S"),
        },
        msg="查询成功",
    )


@EmbedRouter.post("/run", summary="嵌入对话（流式）")
async def embed_run(
    data: EmbedRunSchema,
    request: Request,
    ctx: Annotated[EmbedContext, Depends(get_embed_ctx)],
) -> StreamingResponse:
    """嵌入对话主通道：``Bearer <token>``，请求体仅 ``sid`` + ``message``。

    校验顺序（全部在返回流之前完成，错误以 JSON 返回而非 SSE 帧）：
    权限点 → 会话绑定（403）→ 生成流。审计在流结束时写入 ``method=EMBED``。
    """
    async with async_db_session() as db:
        app_row = await db.get(AiIntegrationAppModel, ctx.app_id)
    if app_row is None:
        raise CustomException(msg="鉴权失败", code=10401, status_code=401)
    if "integration:embed:use" not in ctx.perms:
        await DevelopService.log_call(
            app_row,
            category="embed",
            capability="run",
            method="EMBED",
            transport="sse",
            request_path="/run",
            request_body={"sid": data.sid, "kind": ctx.kind, "target_id": ctx.target_id},
            status="denied",
            error="无权限操作",
        )
        raise CustomException(msg="无权限操作", code=10403, status_code=403)
    await EmbedService.check_limits(
        getattr(request.app.state, "redis", None),
        ctx,
        request.client.host if request.client else "",
    )
    session_id, session_reset = await EmbedService.prepare_session(ctx, data.sid)
    gen = EmbedService.run_stream(
        ctx,
        data.sid,
        app_row,
        session_id,
        session_reset,
        data.message,
        redis=getattr(request.app.state, "redis", None),
    )
    # 与已登录端点保持同一协议包装：工作流走 UI Message Stream，agent/app 走 Agno 事件流
    if ctx.kind == "workflow":
        return ui_stream_response(gen)
    return agno_stream_response(gen)


@EmbedRouter.get("/sdk.js", summary="嵌入 SDK 脚本")
async def embed_sdk() -> PlainTextResponse:
    """返回嵌入 SDK 静态脚本。

    本端点**无鉴权**：返回的是纯代码、不含任何凭证；实质鉴权发生在 ``/embed/run``
    等业务端点（Bearer access_token）。请勿在此文件中放入任何密钥。
    """
    path = Path(__file__).parent / "static" / "ai-assistant.js"
    return PlainTextResponse(
        path.read_text(encoding="utf-8"),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
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
    request: Request,
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
    # 换票限流（appid + IP 双键）：防无限铸票
    await EmbedService.check_issue_limit(
        getattr(request.app.state, "redis", None),
        ctx.appid,
        request.client.host if request.client else "",
    )
    target = await EmbedService.get_target(data.kind, data.target_id)
    if target is None:
        await _audit("denied", error="嵌入目标不存在")
        raise CustomException(msg="嵌入目标不存在", code=10404, status_code=404)
    if not target["enabled"]:
        await _audit("denied", error="嵌入目标未启用")
        raise CustomException(msg="嵌入目标未启用", code=10400, status_code=400)
    result = await EmbedService.issue_token(
        row, kind=data.kind, target_id=data.target_id, ttl=data.ttl, issued_by="exchange"
    )
    await _audit("success", summary=f"{data.kind}:{data.target_id}")
    return SuccessResponse(data=result, msg="令牌已签发")


# ---------------------------------------------------------------------- #
# 开放数据面（OpenApiRouter）：统一能力入口。
# 鉴权走 Bearer appid:appkey；能力元数据从注册表读取，按授权权限点过滤；
# 调用统一经 openapi.invoke_capability（权限 → 限流/配额 → 执行 → 审计）。
# ---------------------------------------------------------------------- #
@OpenApiRouter.get("/capabilities", summary="开放能力清单（按授权过滤）")
async def open_capabilities(
    ctx: Annotated[AppContext, Depends(get_app_api_auth)],
) -> SuccessResponse:
    """返回**当前应用已授权**的能力元数据（未授权能力不出现，避免暴露能力面）。"""
    caps = capabilities_for(ctx.perms)
    return SuccessResponse(
        data={"items": [to_public_dict(c) for c in caps], "total": len(caps)}, msg="查询成功"
    )


@OpenApiRouter.post("/capabilities/{code}", summary="调用开放能力")
async def open_capability_invoke(
    code: str,
    data: CapabilityInvokeSchema,
    request: Request,
    ctx: Annotated[AppContext, Depends(get_app_api_auth)],
) -> JSONResponse:
    """统一调用入口：``POST /ai/develop-api/capabilities/{code}``，body ``{"payload": {...}}``。

    错误语义：401（凭证）→ 403（未授权能力，写 denied 审计）→ 404（能力不存在）
    → 429（限流/配额）→ 400/500（handler 业务错误）。
    """
    result = await invoke_capability(
        ctx,
        code,
        data.payload,
        method="REST",
        redis=getattr(request.app.state, "redis", None),
        request_path=f"/capabilities/{code}",
        ip=request.client.host if request.client else "",
    )
    return SuccessResponse(data=result, msg="调用成功")


# ---------------------------------------------------------------------- #
# 内部管理面：调用审批（敏感能力「先审批后执行」）
# ---------------------------------------------------------------------- #
@DevelopRouter.get("/approvals", summary="分页查询调用审批")
async def develop_approvals(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
    status: Annotated[str | None, Query(description="状态: pending/approved/rejected/failed")] = None,
    app_id: Annotated[int | None, Query(description="按应用过滤")] = None,
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
) -> JSONResponse:
    return SuccessResponse(
        data=await ApprovalService.list(
            status=status, app_id=app_id, page_no=page_no, page_size=page_size
        ),
        msg="查询成功",
    )


@DevelopRouter.post("/approvals/{approval_id}/review", summary="审批调用（批准即执行）")
async def develop_approval_review(
    approval_id: int,
    data: ApprovalReviewSchema,
    request: Request,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:approve"]))],
) -> JSONResponse:
    """批准 → 以**原应用身份**执行被拦截的调用并把结果写回审批行；拒绝 → 只记意见。

    执行失败不抛给管理员（审批动作本身已成功），而是把状态置为 ``failed`` 并回传错误，
    便于在审批列表里看到真实结果。
    """
    row = await ApprovalService.get(approval_id)
    if row is None:
        raise CustomException(msg="审批记录不存在", code=10404, status_code=404)
    # 已处理的审批不得重复执行（批准/拒绝都只允许一次）
    if row.status != "pending":
        raise CustomException(msg="该审批已处理", code=10400, status_code=400)
    reviewer_id = getattr(getattr(auth, "user", None), "id", None)
    ctx = await ApprovalService.app_context(row.app_id)

    if not data.approve:
        result = await ApprovalService.mark_rejected(
            approval_id, reviewer_id=reviewer_id, note=data.note
        )
        await audit_call(
            ctx,
            category=row.category,
            capability=row.capability,
            method="REST",
            status="rejected",
            error=(data.note or "管理员拒绝")[:255],
            request_path=f"/approvals/{approval_id}",
        )
        return SuccessResponse(data=result, msg="已拒绝")

    error: str | None = None
    executed: object = None
    try:
        executed = await invoke_capability(
            ctx,
            row.capability,
            row.payload or {},
            method="REST",
            redis=getattr(request.app.state, "redis", None),
            request_path=f"/approvals/{approval_id}",
            bypass_approval=True,
        )
    except CustomException as e:  # noqa: PERF203 - 执行失败也要回写状态
        error = e.msg
    except Exception as e:  # noqa: BLE001 - 兜底：审批动作不能 500
        error = str(e)

    result = await ApprovalService.mark_executed(
        approval_id, reviewer_id=reviewer_id, note=data.note, result=executed, error=error
    )
    await audit_call(
        ctx,
        category=row.category,
        capability=row.capability,
        method="REST",
        status="failed" if error else "approved",
        error=error,
        request_path=f"/approvals/{approval_id}",
    )
    return SuccessResponse(
        data=result, msg=f"已批准，执行失败：{error}" if error else "已批准并执行完成"
    )


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


@DevelopRouter.get("/capabilities", summary="开放能力清单（管理面，全量）")
async def develop_capabilities(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
) -> JSONResponse:
    """返回全部已注册的开放能力元数据（接入文档用；与授权无关）。

    与 ``GET /ai/develop-api/capabilities``（开放面，按应用授权过滤）不同：
    本端点面向平台管理员，用于展示「有哪些能力可授权」。
    """
    items = [to_public_dict(cap) for cap in all_capabilities()]
    return SuccessResponse(data={"items": items, "total": len(items)}, msg="查询成功")


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


@DevelopRouter.get("/tokens", summary="嵌入令牌列表")
async def develop_list_tokens(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
    app_id: Annotated[int, Query(description="应用ID")],
) -> JSONResponse:
    """列出某应用的嵌入令牌元信息（不含明文/散列），供管理弹窗展示与吊销。"""
    return SuccessResponse(
        data={"items": await DevelopService.list_tokens(app_id)}, msg="查询成功"
    )


@DevelopRouter.post("/tokens", summary="签发体验令牌（2小时）")
async def develop_mint_token(
    data: EmbedMintSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:create"]))],
) -> JSONResponse:
    """管理端签发体验票：issued_by=admin、有效期固定 2 小时，明文仅此响应一次。"""
    async with async_db_session() as db:
        app_row = await db.get(AiIntegrationAppModel, data.app_id)
    if app_row is None or app_row.is_deleted:
        return ErrorResponse(msg="应用不存在")
    if await EmbedService.get_target(data.kind, data.target_id) is None:
        raise CustomException(msg="嵌入目标不存在", code=10404, status_code=404)
    result = await EmbedService.issue_token(
        app_row,
        kind=data.kind,
        target_id=data.target_id,
        ttl=7200,
        issued_by="admin",
    )
    return SuccessResponse(data=result, msg="已签发（有效期 2 小时）")


@DevelopRouter.put("/tokens/{token_id}/revoke", summary="吊销嵌入令牌")
async def develop_revoke_token(
    token_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:update"]))],
) -> JSONResponse:
    """吊销后令牌立即失效（软语义：置 revoked，保留审计行）。"""
    if not await DevelopService.revoke_token(token_id):
        return ErrorResponse(msg="令牌不存在")
    return SuccessResponse(msg="已吊销")


@DevelopRouter.get("/call-logs", summary="分页查询调用日志")
async def develop_call_logs(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
    app_id: Annotated[int | None, Query(description="按应用ID过滤")] = None,
    category: Annotated[str | None, Query(description="按品类过滤")] = None,
    method: Annotated[str | None, Query(description="按出海口过滤 REST/MCP/EMBED")] = None,
    status: Annotated[str | None, Query(description="按状态过滤 success/failed/denied/pending")] = None,
    start_time: Annotated[str | None, Query(description="起始时间 YYYY-MM-DD HH:mm:ss")] = None,
    end_time: Annotated[str | None, Query(description="结束时间 YYYY-MM-DD HH:mm:ss")] = None,
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
) -> JSONResponse:
    return SuccessResponse(
        data=await _query_call_logs(
            app_id, category, method, status, page_no, page_size, start_time, end_time
        ),
        msg="查询成功",
    )


@DevelopRouter.get("/stats", summary="调用概览（今日/趋势/Top能力）")
async def develop_stats(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
    days: Annotated[int, Query(ge=1, le=30, description="趋势天数")] = 7,
) -> JSONResponse:
    from .insights import DevelopInsights

    return SuccessResponse(data=await DevelopInsights.stats(days), msg="查询成功")


@DevelopRouter.get("/apps/{app_id}/usage", summary="应用当日配额用量")
async def develop_app_usage(
    app_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
) -> JSONResponse:
    from .insights import DevelopInsights

    app = await DevelopService.get_app(app_id)
    if not app:
        return ErrorResponse(msg="应用不存在")
    usage = await DevelopInsights.usage(app_id)
    usage["quota"] = app.get("quota") or {}
    return SuccessResponse(data=usage, msg="查询成功")


@DevelopRouter.get("/usage-report", summary="用量报告（按应用，近 N 天）")
async def develop_usage_report(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
    days: Annotated[int, Query(ge=1, le=90, description="统计天数")] = 7,
) -> JSONResponse:
    from .insights import usage_report

    return SuccessResponse(data=await usage_report(days), msg="查询成功")


@DevelopRouter.get("/call-logs/export", summary="导出调用日志 CSV")
async def develop_call_logs_export(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
    app_id: Annotated[int | None, Query(description="按应用ID过滤")] = None,
    category: Annotated[str | None, Query(description="按品类过滤")] = None,
    method: Annotated[str | None, Query(description="按出海口过滤")] = None,
    status: Annotated[str | None, Query(description="按状态过滤")] = None,
    start_time: Annotated[str | None, Query(description="起始时间 YYYY-MM-DD HH:mm:ss")] = None,
    end_time: Annotated[str | None, Query(description="结束时间 YYYY-MM-DD HH:mm:ss")] = None,
) -> StreamingResponse:
    """导出当前筛选条件下的调用日志（最近 5000 行，UTF-8 BOM CSV）。"""
    from .insights import DevelopInsights

    def _parse(raw: str | None) -> datetime | None:
        if not raw:
            return None
        try:
            return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError as exc:
            raise CustomException(
                msg="时间格式应为 YYYY-MM-DD HH:mm:ss", code=10400, status_code=400
            ) from exc

    content = await DevelopInsights.export_csv(
        app_id=app_id,
        category=category,
        method=method,
        status=status,
        start_time=_parse(start_time),
        end_time=_parse(end_time),
    )
    filename = f"ai-call-logs-{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@DevelopRouter.post("/apps/{app_id}/try", summary="能力试调（管理端）")
async def develop_try_capability(
    app_id: int,
    data: CapabilityTrySchema,
    request: Request,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
) -> JSONResponse:
    """以该应用身份调用一次能力，便于接入方自测。

    与开放面的区别：**跳过审批门禁**（试调属于管理员测试动作），但仍走权限、
    限流与审计（``request_path=/try``），因此不会产生待审批队列。
    """
    from .approvals import ApprovalService
    from .registry import get_capability

    if get_capability(data.capability) is None:
        raise CustomException(msg="能力不存在", code=10404, status_code=404)
    ctx = await ApprovalService.app_context(app_id)
    # 试调不加 try/except：权限 403、参数 400、内部错误 500 都交给全局处理器，
    # 前端按统一 envelope 展示（与开放面调用语义一致，便于对照排查）。
    result = await invoke_capability(
        ctx,
        data.capability,
        data.payload,
        method="REST",
        redis=getattr(request.app.state, "redis", None),
        request_path=f"/try/{data.capability}",
        bypass_approval=True,
    )
    return SuccessResponse(data=result, msg="调用成功")


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
    start_time: str | None = None,
    end_time: str | None = None,
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
    # 时间范围（"YYYY-MM-DD HH:mm:ss"，本地 naive 时间，与写入口径一致）
    for raw, op in ((start_time, "ge"), (end_time, "le")):
        if not raw:
            continue
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise CustomException(msg="时间格式应为 YYYY-MM-DD HH:mm:ss", code=10400, status_code=400)
        wheres.append(
            AiIntegrationCallLogModel.created_time >= parsed
            if op == "ge"
            else AiIntegrationCallLogModel.created_time <= parsed
        )

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
