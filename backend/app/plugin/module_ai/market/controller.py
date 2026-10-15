"""AI 能力市场路由：首页/列表/详情/安装/收藏。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import MarketItemQuerySchema, MarketReviewSchema, MarketSubmitSchema
from .service import MarketService

MarketRouter = APIRouter(route_class=OperationLogRoute, prefix="/market", tags=["AI-市场"])


@MarketRouter.get("/home", summary="市场首页（精选+分类）")
async def market_home(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await MarketService.home(auth.user.id), msg="查询成功")


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
) -> JSONResponse:
    return SuccessResponse(data=await MarketService.review_list(status), msg="查询成功")


@MarketRouter.post("/review", summary="审核商品")
async def market_review(
    data: MarketReviewSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:market:review"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await MarketService.review(data.item_id, data.action, data.remark or "", auth.user.id),
        msg="审核完成",
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
