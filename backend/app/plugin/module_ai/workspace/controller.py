"""AI 工作台控制器：分类树 CRUD + 聚合条目。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import WorkspaceCategoryCreateSchema, WorkspaceCategoryUpdateSchema
from .service import WorkspaceService

WorkspaceRouter = APIRouter(
    route_class=OperationLogRoute, prefix="/workspace", tags=["AI-工作台"]
)


@WorkspaceRouter.get("/categories/tree", summary="工作台分类树")
async def category_tree(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workspace:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await WorkspaceService.list_tree(), msg="查询成功")


@WorkspaceRouter.post("/categories/create", summary="新建分类")
async def category_create(
    data: WorkspaceCategoryCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workspace:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await WorkspaceService.create_category(data, auth), msg="创建成功")


@WorkspaceRouter.put("/categories/update/{cat_id}", summary="编辑分类")
async def category_update(
    cat_id: int,
    data: WorkspaceCategoryUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workspace:update"]))],
) -> JSONResponse:
    result = await WorkspaceService.update_category(cat_id, data, auth)
    if not result:
        return ErrorResponse(msg="分类不存在")
    return SuccessResponse(data=result, msg="修改成功")


@WorkspaceRouter.delete("/categories/delete", summary="删除分类")
async def category_delete(
    cat_id: Annotated[int, Body(description="分类ID")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workspace:delete"]))],
) -> JSONResponse:
    await WorkspaceService.delete_category(cat_id, auth)
    return SuccessResponse(msg="删除成功")


@WorkspaceRouter.get("/items", summary="工作台条目（按分类/类型聚合）")
async def workspace_items(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:workspace:query"]))],
    category_id: int | None = None,
    asset_type: str | None = None,
) -> JSONResponse:
    return SuccessResponse(
        data=await WorkspaceService.items(category_id, asset_type), msg="查询成功"
    )
