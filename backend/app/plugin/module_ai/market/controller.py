"""AI 能力市场路由：首页/列表/详情/安装/收藏。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import (
    MarketItemQuerySchema,
    MarketReviewBatchSchema,
    MarketReviewSchema,
    MarketShareSchema,
    MarketSubmitSchema,
)
from .service import MarketService

MarketRouter = APIRouter(route_class=OperationLogRoute, prefix="/market", tags=["AI-市场"])


@MarketRouter.get("/home", summary="市场首页（精选+分类）")
async def market_home(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:query"]))],
    asset_type: Annotated[str | None, Query(description="按资产类型联动精选与分类")] = None,
    shuffle: Annotated[bool, Query(description="精选随机排序（前端「换一换」）")] = False,
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.home(auth.user.id, asset_type, shuffle), msg="查询成功"
    )


@MarketRouter.get("/items", summary="市场商品列表")
async def market_items(
    query: Annotated[MarketItemQuerySchema, Query()],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await MarketService.list_items(query, auth.user.id), msg="查询成功")


@MarketRouter.get("/items/{item_id}", summary="商品详情")
async def market_item_detail(
    item_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:query"]))],
) -> JSONResponse:
    result = await MarketService.detail(item_id, auth.user.id)
    if not result:
        return ErrorResponse(msg="商品不存在")
    return SuccessResponse(data=result, msg="查询成功")


@MarketRouter.post("/items/{item_id}/install", summary="安装商品")
async def market_install(
    item_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:install"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.install(item_id, auth.user.id), msg="安装成功"
    )


@MarketRouter.post("/items/{item_id}/favorite", summary="收藏商品")
async def market_favorite(
    item_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:query"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.favorite(item_id, auth.user.id, True), msg="收藏成功"
    )


@MarketRouter.delete("/items/{item_id}/favorite", summary="取消收藏")
async def market_unfavorite(
    item_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:query"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.favorite(item_id, auth.user.id, False), msg="已取消收藏"
    )


@MarketRouter.post("/submit", summary="提交资产到市场")
async def market_submit(
    data: MarketSubmitSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:submit"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.submit(data, auth.user.id), msg="已提交，等待审核"
    )


@MarketRouter.put("/mine/{asset_type}/{real_id}/toggle", summary="启停我的资产")
async def market_toggle_asset(
    asset_type: str,
    real_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:query"]))],
    enabled: Annotated[bool, Query(description="是否启用")] = True,
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.toggle_asset(asset_type, real_id, enabled, auth.user.id),
        msg="已更新",
    )


@MarketRouter.delete("/mine/{asset_type}/{real_id}", summary="删除我的资产")
async def market_delete_asset(
    asset_type: str,
    real_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:query"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.delete_asset(asset_type, real_id, auth.user.id),
        msg="已删除",
    )


@MarketRouter.get("/mine", summary="我的资产（含市场状态）")
async def market_mine(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:query"]))],
    asset_type: Annotated[str | None, Query(description="资产类型过滤")] = None,
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.list_mine(auth.user.id, asset_type), msg="查询成功"
    )


@MarketRouter.post("/items/{item_id}/withdraw", summary="撤回我的商品")
async def market_withdraw(
    item_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:submit"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.withdraw(item_id, auth.user.id), msg="已撤回"
    )


@MarketRouter.get("/review/list", summary="审核列表")
async def market_review_list(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:review"]))],
    status: Annotated[str | None, Query(description="状态过滤，默认 pending")] = None,
    asset_type: Annotated[str | None, Query(description="资产类型过滤")] = None,
    page_no: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.review_list(status, asset_type, page_no, page_size), msg="查询成功"
    )


@MarketRouter.post("/review", summary="审核商品")
async def market_review(
    data: MarketReviewSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:review"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.review(data.item_id, data.action, data.remark or "", auth.user.id),
        msg="审核完成",
    )


@MarketRouter.post("/review/batch", summary="批量审核商品")
async def market_review_batch(
    data: MarketReviewBatchSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:review"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.review_batch(data.items, auth.user.id), msg="批量审核完成"
    )


@MarketRouter.post("/items/{item_id}/feature", summary="设置精选")
async def market_feature(
    item_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:review"]))],
    featured: Annotated[bool, Query(description="是否精选")] = True,
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.set_featured(item_id, featured), msg="设置成功"
    )


@MarketRouter.post("/shares/share", summary="分享商品/个人资产给用户")
async def market_share(
    data: MarketShareSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:share"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.share_item(data, auth.user.id),
        msg="分享成功",
    )


@MarketRouter.get("/shares", summary="分享列表（收件箱/发件箱）")
async def market_shares(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:query"]))],
    direction: Annotated[str, Query(description="in=收到的 out=发出的")] = "in",
    status: Annotated[str | None, Query(description="状态过滤")] = None,
    page_no: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.list_shares(auth.user.id, direction, status, page_no, page_size),
        msg="查询成功",
    )


@MarketRouter.post("/shares/{share_id}/accept", summary="接收分享")
async def market_share_accept(
    share_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:query"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.accept_share(share_id, auth.user.id), msg="已接收"
    )


@MarketRouter.post("/shares/{share_id}/reject", summary="拒绝分享")
async def market_share_reject(
    share_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:query"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.reject_share(share_id, auth.user.id), msg="已拒绝"
    )
