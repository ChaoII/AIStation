"""AI 集成开放平台 —— 控制器（开放数据面 + 内部管理面）。

本模块包含两个顶层 APIRouter（均被动态路由自动发现，容器前缀 ``/ai``）：

- :data:`OpenApiRouter`：**开放数据面**，前缀 ``/develop-api``，供外部平台
  直接调用。不带后台登录态，改用 ``Authorization: Bearer <appid>:<appkey>``
  应用凭证鉴权；需要授权的端点再叠加 :func:`require_capability`（能力码 + 出口）。
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
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Form, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.database import async_db_session
from app.core.dependencies import AuthPermission, get_current_user
from app.core.exceptions import CustomException
from app.core.router_class import OperationLogRoute

# 导入 handler 包即注册全部开放能力（REST 与 MCP 共用注册表）。
from . import handlers as _handlers  # noqa: F401
from .approvals import ApprovalService, review_one
from .auth import AppContext, get_app_api_auth
from .model import (
    AiIntegrationAppModel,
    AiIntegrationCallLogModel,
    AiIntegrationMcpSessionModel,
)
from .oauth_auth import get_oauth_api_auth
from .oauth_schema import OAuthAuthorizeSchema, OAuthClientCreateSchema, OAuthClientUpdateSchema
from .openapi import invoke_capability
from .registry import (
    all_capabilities,
    capabilities_for_codes,
    get_capability,
    is_granted,
    to_public_dict,
)
from .schema import (
    ApprovalBatchReviewSchema,
    ApprovalReviewSchema,
    CapabilityInvokeSchema,
    CapabilityTrySchema,
    DevelopApplyReviewSchema,
    DevelopApplySchema,
    DevelopApplyUpdateSchema,
    DevelopCreateSchema,
    DevelopUpdateSchema,
    NotifyConfigSchema,
    ResourcePublicApplyReviewSchema,
    ResourcePublicApplySchema,
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


# ---------------------------------------------------------------------- #
# 模式 C：OAuth 2.1 用户委托 server（授权 / 取token / 撤销 / userinfo）。
# 管理面 client CRUD 用 AuthPermission(module_ai:develop:*)；OAuth 端点本身
# 不依赖后台登录态（token 换取等用 client 凭证 / PKCE）。
# ---------------------------------------------------------------------- #
OAuthRouter = APIRouter(
    route_class=OperationLogRoute,
    prefix="/develop/oauth",
    tags=["AI-集成OAuth"],
)


@OpenApiRouter.get("/auth/verify", summary="鉴权验证")
async def auth_verify(
    ctx: Annotated[AppContext, Depends(get_app_api_auth)],
) -> SuccessResponse:
    """校验应用凭证并返回应用信息。

    依赖 :func:`get_app_api_auth`：解析 ``Authorization: Bearer <appid>:<appkey>``，
    校验失败统一抛 401（由全局异常处理器转换）。成功返回应用身份、**授权能力码**
    （``grants`` 排序列表）、按品类分组（``categories``）、各能力出口（``channels``）、
    过期时间、启停状态；同时写入一条 ``auth/verify`` 调用审计。
    """
    grants = sorted(ctx.grants)
    data = {
        "appid": ctx.appid,
        "name": ctx.app["name"],
        "grants": grants,
        "perms": grants,  # 兼容旧字段名（现为能力码而非权限点）
        "channels": {code: sorted(ch) for code, ch in ctx.channels.items()},
        "categories": _group_categories(grants),
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


# ---------------------------------------------------------------------- #
# 开放数据面（OpenApiRouter）：统一能力入口。
# 鉴权走 Bearer appid:appkey；能力元数据从注册表读取，按授权权限点过滤；
# 调用统一经 openapi.invoke_capability（权限 → 限流/配额 → 执行 → 审计）。
# ---------------------------------------------------------------------- #
@OpenApiRouter.get("/capabilities", summary="开放能力清单（按授权过滤）")
async def open_capabilities(
    ctx: Annotated[AppContext, Depends(get_app_api_auth)],
) -> SuccessResponse:
    """返回**当前应用已授权且开放 REST 出口**的能力元数据（未授权/未开放不出现）。

    该端点为开放数据面 REST 出口，故只返回 ``rest`` 通道已开放的授权能力。
    """
    caps = [
        c
        for c in capabilities_for_codes(ctx.grants)
        if is_granted(ctx.grants, ctx.channels, c.code, "rest")
    ]
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

    核心语义在 ``approvals.review_one``（与批量审批共用）；执行失败不抛给管理员，
    状态置 ``failed`` 并回传错误，便于在列表里看到真实结果。
    """
    row = await ApprovalService.get(approval_id)
    if row is None:
        raise CustomException(msg="审批记录不存在", code=10404, status_code=404)
    # 已处理的审批不得重复执行（批准/拒绝都只允许一次）
    if row.status != "pending":
        raise CustomException(msg="该审批已处理", code=10400, status_code=400)
    reviewer_id = getattr(getattr(auth, "user", None), "id", None)
    result, msg = await review_one(
        row,
        approve=data.approve,
        note=data.note,
        reviewer_id=reviewer_id,
        redis=getattr(request.app.state, "redis", None),
    )
    return SuccessResponse(data=result, msg=msg)


@DevelopRouter.post("/approvals/batch-review", summary="批量批准审批")
async def develop_approvals_batch_review(
    data: ApprovalBatchReviewSchema,
    request: Request,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:approve"]))],
) -> JSONResponse:
    """批量批准（≤50 条/次，逐条独立执行，单条失败不中断）。拒绝请逐条操作。"""
    from .approvals import review_batch

    reviewer_id = getattr(getattr(auth, "user", None), "id", None)
    result = await review_batch(
        data.ids,
        approve=True,
        note=data.note,
        reviewer_id=reviewer_id,
        redis=getattr(request.app.state, "redis", None),
    )
    failed_n = len(result["failed"])
    msg = f"已批准 {len(result['ok'])} 条" + (f"，失败 {failed_n} 条" if failed_n else "")
    return SuccessResponse(data=result, msg=msg)


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


# --------------------------------------------------------------------------- #
# 模式 B：用户自助申请应用（普通用户走 get_current_user，无需 module_ai:develop:*）
# --------------------------------------------------------------------------- #
@DevelopRouter.get("/self/apps", summary="我的应用申请单（用户自助，模式B）")
async def self_apply_list(
    auth: Annotated[AuthSchema, Depends(get_current_user)],
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
) -> JSONResponse:
    """列出当前用户自己的应用申请单。普通用户可访问（不要求 develop 管理权限）。"""
    from .self_apps import SelfApplyService

    if auth.user is None:
        raise CustomException(msg="登录态无效", code=10401, status_code=401)
    return SuccessResponse(
        data=await SelfApplyService.list_mine(auth.user, page=page_no, page_size=page_size),
        msg="查询成功",
    )


@DevelopRouter.post("/self/apps", summary="提交应用申请（用户自助，模式B）")
async def self_apply_submit(
    data: DevelopApplySchema,
    auth: Annotated[AuthSchema, Depends(get_current_user)],
) -> JSONResponse:
    """用户自助申请 appid/appkey；能力清单不得超出自身角色权限，提交后管理员审核。"""
    from .self_apps import SelfApplyService

    if auth.user is None:
        raise CustomException(msg="登录态无效", code=10401, status_code=401)
    return SuccessResponse(
        data=await SelfApplyService.submit(auth.user, data),
        msg="申请已提交，等待管理员审核",
    )


@DevelopRouter.put("/self/apps/{apply_id}", summary="修改我的申请单（用户自助，模式B）")
async def self_apply_update(
    apply_id: int,
    data: DevelopApplyUpdateSchema,
    auth: Annotated[AuthSchema, Depends(get_current_user)],
) -> JSONResponse:
    from .self_apps import SelfApplyService

    if auth.user is None:
        raise CustomException(msg="登录态无效", code=10401, status_code=401)
    return SuccessResponse(
        data=await SelfApplyService.update(auth.user, apply_id, data),
        msg="更新成功",
    )


@DevelopRouter.delete("/self/apps/{apply_id}", summary="撤销我的申请单（用户自助，模式B）")
async def self_apply_cancel(
    apply_id: int,
    auth: Annotated[AuthSchema, Depends(get_current_user)],
) -> JSONResponse:
    from .self_apps import SelfApplyService

    if auth.user is None:
        raise CustomException(msg="登录态无效", code=10401, status_code=401)
    await SelfApplyService.cancel(auth.user, apply_id)
    return SuccessResponse(msg="已撤销")


@DevelopRouter.get("/self/apps/all", summary="全部应用申请单（管理员审核用）")
async def self_apply_list_all(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:approve"]))],
    apply_status: Annotated[str | None, Query(description="按状态过滤 pending/approved/rejected")] = None,
    applicant_id: Annotated[int | None, Query(description="按申请者用户ID过滤")] = None,
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
) -> JSONResponse:
    from .self_apps import SelfApplyService

    return SuccessResponse(
        data=await SelfApplyService.list_all(
            apply_status=apply_status,
            applicant_id=applicant_id,
            page=page_no,
            page_size=page_size,
        ),
        msg="查询成功",
    )


@DevelopRouter.post("/self/apps/{apply_id}/review", summary="审核用户应用申请（批准/驳回）")
async def self_apply_review(
    apply_id: int,
    data: DevelopApplyReviewSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:approve"]))],
) -> JSONResponse:
    """批准：生成应用（source_type= self，绑定申请者）并返回 appid/appkey 一次；驳回则记意见。"""
    from .self_apps import SelfApplyService

    result = await SelfApplyService.review(
        apply_id,
        approve=data.approve,
        reviewer_id=auth.user.id if auth.user else None,
        note=data.note,
    )
    return SuccessResponse(data=result, msg="已批准" if data.approve else "已驳回")


# --------------------------------------------------------------------------- #
# 阶段 1.5：资源公开申请（主动公开治理）
# --------------------------------------------------------------------------- #
@DevelopRouter.get("/self/public-apps", summary="我的资源公开申请单（用户自助）")
async def self_public_apply_list(
    auth: Annotated[AuthSchema, Depends(get_current_user)],
    apply_status: Annotated[str | None, Query(description="按状态过滤 pending/approved/rejected")] = None,
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
) -> JSONResponse:
    """列出当前用户自己的资源公开申请单。普通用户可访问。"""
    from .public_apps import PublicApplyService

    if auth.user is None:
        raise CustomException(msg="登录态无效", code=10401, status_code=401)
    return SuccessResponse(
        data=await PublicApplyService.list_mine(
            auth.user, apply_status=apply_status, page=page_no, page_size=page_size
        ),
        msg="查询成功",
    )


@DevelopRouter.post("/self/public-apps", summary="提交资源公开申请（用户自助）")
async def self_public_apply_submit(
    data: ResourcePublicApplySchema,
    auth: Annotated[AuthSchema, Depends(get_current_user)],
) -> JSONResponse:
    """用户对自己默认不公开的私有资源发起公开申请，等待管理员审核。"""
    from .public_apps import PublicApplyService

    if auth.user is None:
        raise CustomException(msg="登录态无效", code=10401, status_code=401)
    return SuccessResponse(
        data=await PublicApplyService.submit(
            auth.user,
            resource_type=data.resource_type,
            resource_id=data.resource_id,
            reason=data.reason,
        ),
        msg="公开申请已提交，等待管理员审核",
    )


@DevelopRouter.delete("/self/public-apps/{auth_id}", summary="撤销我的资源公开申请")
async def self_public_apply_cancel(
    auth_id: int,
    auth: Annotated[AuthSchema, Depends(get_current_user)],
) -> JSONResponse:
    from .public_apps import PublicApplyService

    if auth.user is None:
        raise CustomException(msg="登录态无效", code=10401, status_code=401)
    await PublicApplyService.cancel(auth.user, auth_id)
    return SuccessResponse(msg="已撤销")


@DevelopRouter.get("/self/public-apps/all", summary="全部资源公开申请（管理员审核用）")
async def self_public_apply_list_all(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:approve"]))],
    apply_status: Annotated[str | None, Query(description="按状态过滤 pending/approved/rejected")] = None,
    resource_type: Annotated[str | None, Query(description="按资源品类过滤")] = None,
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
) -> JSONResponse:
    from .public_apps import PublicApplyService

    return SuccessResponse(
        data=await PublicApplyService.list_all(
            apply_status=apply_status,
            resource_type=resource_type,
            page=page_no,
            page_size=page_size,
        ),
        msg="查询成功",
    )


@DevelopRouter.post("/self/public-apps/{auth_id}/review", summary="审核资源公开申请（批准/驳回）")
async def self_public_apply_review(
    auth_id: int,
    data: ResourcePublicApplyReviewSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:approve"]))],
) -> JSONResponse:
    """批准：写回资源 is_public=true 并生效；驳回则记意见。"""
    from .public_apps import PublicApplyService

    result = await PublicApplyService.review(
        auth_id,
        approve=data.approve,
        reviewer_id=auth.user.id if auth.user else None,
        note=data.note,
    )
    return SuccessResponse(data=result, msg="已批准" if data.approve else "已驳回")


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
    status: Annotated[str | None, Query(description="按状态过滤 success/failed/denied/pending")] = None,
    start_time: Annotated[str | None, Query(description="起始时间 YYYY-MM-DD HH:mm:ss")] = None,
    end_time: Annotated[str | None, Query(description="结束时间 YYYY-MM-DD HH:mm:ss")] = None,
    capability: Annotated[str | None, Query(description="按能力码精确过滤（下钻）")] = None,
    page_no: Annotated[int, Query(ge=1, description="页码")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="每页条数")] = 20,
) -> JSONResponse:
    return SuccessResponse(
        data=await _query_call_logs(
            app_id,
            category,
            method,
            status,
            page_no,
            page_size,
            start_time,
            end_time,
            capability,
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


@DevelopRouter.get("/notify-config", summary="审批通知配置（开关 + 通道参数）")
async def develop_notify_config(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
) -> JSONResponse:
    from .approvals import get_notify_config

    return SuccessResponse(data=await get_notify_config(), msg="查询成功")


@DevelopRouter.put("/notify-config", summary="保存审批通知配置")
async def develop_notify_config_save(
    data: NotifyConfigSchema,
    request: Request,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:update"]))],
) -> JSONResponse:
    from .approvals import save_notify_config

    result = await save_notify_config(
        data.channels, data.configs, getattr(request.app.state, "redis", None)
    )
    return SuccessResponse(data=result, msg="已保存")


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


@DevelopRouter.get("/usage-report/export", summary="导出用量报告 CSV")
async def develop_usage_report_export(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
    days: Annotated[int, Query(ge=1, le=90, description="统计天数")] = 7,
) -> StreamingResponse:
    from .insights import usage_report_csv

    content = await usage_report_csv(days)
    filename = f"ai-usage-report-{datetime.now().strftime('%Y%m%d%H%M%S')}.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@DevelopRouter.get("/mcp-stats", summary="MCP 会话概览（近 N 天趋势）")
async def develop_mcp_stats(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
    days: Annotated[int, Query(ge=1, le=30, description="趋势天数")] = 7,
) -> JSONResponse:
    from .insights import mcp_stats

    return SuccessResponse(data=await mcp_stats(days), msg="查询成功")


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


def _mcp_session_to_dict(row: AiIntegrationMcpSessionModel, tools: list | None = None) -> dict:
    """MCP 会话行 → 对外 dict（连接级监控 + 会话内工具调用明细，只读）。"""
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
        "tools": tools or [],
    }


def _group_categories(grants: list[str]) -> dict[str, list[str]]:
    """把授权能力码按所属品类分组（``auth/verify`` 返回用，非法码丢弃）。"""
    out: dict[str, list[str]] = {}
    for code in grants:
        cap = get_capability(code)
        if cap is not None:
            out.setdefault(cap.category, []).append(code)
    for codes in out.values():
        codes.sort()
    return out


def _classify_status(status: str | None, error: str | None) -> str:
    """把调用日志 ``status`` + ``error`` 归类为更细的结果类别。

    供会话工具明细聚合使用：``denied`` 里再区分「限流 / 配额命中 / 无权限」，
    让管理端一眼看清是哪个环节被拦。
    """
    if status == "success":
        return "success"
    if status == "pending":
        return "pending"
    if status == "denied":
        err = error or ""
        if "频繁" in err or "稍后再试" in err:
            return "rate_limited"
        if "配额" in err:
            return "quota_hit"
        return "denied"
    return "failed"


async def _session_tools_map(db, session_ids: list[str]) -> dict[str, list[dict]]:
    """按 MCP 会话聚合调用日志，得到每个会话的「工具调用明细」。

    只取本页会话涉及的工具调用（``method='MCP'`` 且 ``session_id`` 命中），
    按能力聚合次数并分结果类别（成功/待审批/无权限/限流/配额命中/失败）。
    """
    result: dict[str, dict[str, dict]] = {}
    if not session_ids:
        return {}
    rows = (
        await db.execute(
            select(
                AiIntegrationCallLogModel.session_id,
                AiIntegrationCallLogModel.capability,
                AiIntegrationCallLogModel.status,
                AiIntegrationCallLogModel.error,
            ).where(
                AiIntegrationCallLogModel.session_id.in_(session_ids),
                AiIntegrationCallLogModel.method == "MCP",
            )
        )
    ).all()
    for sid, cap_code, status, error in rows:
        entry = result.setdefault(sid, {})
        tool = entry.setdefault(
            cap_code,
            {
                "capability": cap_code,
                "name": (get_capability(cap_code).name if get_capability(cap_code) else cap_code),
                "calls": 0,
                "success": 0,
                "pending": 0,
                "denied": 0,
                "rate_limited": 0,
                "quota_hit": 0,
                "failed": 0,
            },
        )
        tool["calls"] += 1
        cat = _classify_status(status, error)
        tool[cat] = tool.get(cat, 0) + 1
    return {sid: list(tools.values()) for sid, tools in result.items()}


async def _query_call_logs(
    app_id: int | None,
    category: str | None,
    method: str | None,
    status: str | None,
    page_no: int,
    page_size: int,
    start_time: str | None = None,
    end_time: str | None = None,
    capability: str | None = None,
) -> dict:
    """按 app_id/category/method/status 过滤调用日志，分页返回。"""
    page_no = max(int(page_no or 1), 1)
    page_size = max(int(page_size or 20), 1)
    # 嵌入域已剥离（method=EMBED 写入独立 ai_asset_embed_logs），开发平台审计不再展示旧 EMBED 记录
    wheres = [AiIntegrationCallLogModel.method != "EMBED"]
    if app_id is not None:
        wheres.append(AiIntegrationCallLogModel.app_id == app_id)
    if category:
        wheres.append(AiIntegrationCallLogModel.category == category)
    if method:
        wheres.append(AiIntegrationCallLogModel.method == method)
    if status:
        wheres.append(AiIntegrationCallLogModel.status == status)
    if capability:
        wheres.append(AiIntegrationCallLogModel.capability == capability)
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
        tools_map = await _session_tools_map(db, [r.session_id for r in rows])
        return {
            "page_no": page_no,
            "page_size": page_size,
            "total": total,
            "has_next": page_no * page_size < total,
            "items": [_mcp_session_to_dict(r, tools_map.get(r.session_id)) for r in rows],
        }


# ---------------------------------------------------------------------- #
# 模式 C：OAuth 2.1 用户委托 —— OAuth server 端点。
# ---------------------------------------------------------------------- #
@OAuthRouter.get("/clients", summary="OAuth客户端列表（管理员）")
async def oauth_clients(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:query"]))],
) -> JSONResponse:
    from .oauth_server import OAuthClientService

    return SuccessResponse(
        data={"items": await OAuthClientService.list_clients(), "total": len(await OAuthClientService.list_clients())},
        msg="查询成功",
    )


@OAuthRouter.post("/clients", summary="创建OAuth客户端（管理员）")
async def oauth_client_create(
    data: OAuthClientCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:create"]))],
) -> JSONResponse:
    from .oauth_server import OAuthClientService

    return SuccessResponse(data=await OAuthClientService.create_client(data, auth), msg="创建成功")


@OAuthRouter.put("/clients/{client_id}", summary="更新OAuth客户端（管理员）")
async def oauth_client_update(
    client_id: str,
    data: OAuthClientUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:develop:update"]))],
) -> JSONResponse:
    from .oauth_server import OAuthClientService

    row = await OAuthClientService.get_client(client_id)
    if row is None:
        return ErrorResponse(msg="客户端不存在")
    return SuccessResponse(data=await OAuthClientService.update_client(client_id, data, auth), msg="更新成功")


@OAuthRouter.post("/authorize", summary="用户同意授权，签发授权码")
async def oauth_authorize(
    data: OAuthAuthorizeSchema,
    user: Annotated[AuthSchema, Depends(get_current_user)],
) -> JSONResponse:
    """用户授权页确认后，校验 client / scope / redirect_uri / PKCE，签发一次性授权码。

    返回 ``{code, state}``，由前端拼接 ``redirect_uri?code=...&state=...`` 重定向。
    """
    from .oauth_server import OAuthClientService

    if user.user is None:
        raise CustomException(msg="登录态无效", code=10401, status_code=401)
    client = await OAuthClientService.get_client(data.client_id)
    if client is None or not client.enabled:
        raise CustomException(msg="客户端不存在或已停用", code=10400, status_code=400)
    result = await OAuthClientService.issue_authorization_code(
        client,
        user.user.id,
        scope=data.scope,
        redirect_uri=data.redirect_uri,
        code_challenge=data.code_challenge,
        code_challenge_method=data.code_challenge_method,
    )
    return SuccessResponse(data={"code": result["code"], "state": data.state}, msg="授权成功")


@OAuthRouter.post("/token", summary="授权码换取token（OAuth 2.1 token端点）")
async def oauth_token(
    grant_type: Annotated[str, Form()],
    code: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    client_id: Annotated[str | None, Form()] = None,
    client_secret: Annotated[str | None, Form()] = None,
    refresh_token: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
) -> JSONResponse:
    from .oauth_server import OAuthTokenService

    if grant_type == "authorization_code":
        if not code or not client_id:
            raise CustomException(msg="授权参数不完整", code=10400, status_code=400)
        result = await OAuthTokenService.exchange_code(
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
    elif grant_type == "refresh_token":
        if not refresh_token or not client_id:
            raise CustomException(msg="授权参数不完整", code=10400, status_code=400)
        result = await OAuthTokenService.refresh(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
        )
    else:
        raise CustomException(msg="不支持的授权类型", code=10400, status_code=400)
    return JSONResponse(content=result)


@OAuthRouter.post("/revoke", summary="撤销委托token")
async def oauth_revoke(
    token: Annotated[str, Form()],
) -> JSONResponse:
    from .oauth_server import OAuthTokenService

    await OAuthTokenService.revoke(token)
    return JSONResponse(content={"revoked": True})


@OAuthRouter.get("/userinfo", summary="委托token信息（OAuth userinfo）")
async def oauth_userinfo(
    ctx: Annotated[AppContext, Depends(get_oauth_api_auth)],
) -> SuccessResponse:
    """返回委托 token 对应的被委托用户（``sub``）与授权 scope。"""
    return SuccessResponse(
        data={
            "sub": ctx.user_id,
            "client_id": ctx.appid,
            "scope": sorted(ctx.oauth_scope or []),
        },
        msg="ok",
    )


# ---------------------------------------------------------------------- #
# 模式 C：OAuth 数据面（REST）—— 用委托 Bearer token 调用能力。
# ---------------------------------------------------------------------- #
@OpenApiRouter.post("/oauth/capabilities/{code}", summary="OAuth委托调用开放能力")
async def oauth_capability_invoke(
    code: str,
    data: CapabilityInvokeSchema,
    request: Request,
    ctx: Annotated[AppContext, Depends(get_oauth_api_auth)],
) -> JSONResponse:
    """OAuth 数据面：``POST /ai/develop-api/oauth/capabilities/{code}``，body ``{"payload": {...}}``。

    与 ``/capabilities/{code}``（应用凭证）同一管道，仅鉴权换成委托 Bearer token；
    数据可见性由 ``ctx.owner_user_id``（= token.sub）复用现有 visible 过滤。
    """
    result = await invoke_capability(
        ctx,
        code,
        data.payload,
        method="REST",
        redis=getattr(request.app.state, "redis", None),
        request_path=f"/oauth/capabilities/{code}",
        ip=request.client.host if request.client else "",
    )
    return SuccessResponse(data=result, msg="调用成功")
