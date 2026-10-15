"""AI 能力市场路由：首页/列表/详情/安装/收藏。"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import MarketItemQuerySchema
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
