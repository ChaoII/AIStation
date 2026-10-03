"""知识库 / 数据源 RAG 控制器。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.response import ErrorResponse, SuccessResponse
from app.core.dependencies import AuthPermission
from app.core.router_class import OperationLogRoute

from .schema import (
    AiDatasourceCreateSchema,
    AiDatasourceSyncSchema,
    AiDatasourceUpdateSchema,
    AiKnowledgeBaseCreateSchema,
    AiKnowledgeBaseUpdateSchema,
    AiKnowledgeGraphEntitySchema,
    AiKnowledgeGraphRelationSchema,
    AiKnowledgeIngestSchema,
    AiKnowledgeSearchSchema,
    AiKnowledgeUpdateChunkSchema,
)
from .service import AiKnowledgeService

KnowledgeRouter = APIRouter(
    route_class=OperationLogRoute, prefix="/knowledge", tags=["AI-知识库"]
)


# ---------------------------------------------------------------- #
# 知识库
# ---------------------------------------------------------------- #
@KnowledgeRouter.get("/bases/list", summary="知识库列表")
async def list_bases(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiKnowledgeService.list_bases(), msg="查询成功")


@KnowledgeRouter.get("/bases/detail/{kb_id}", summary="知识库详情")
async def get_base(
    kb_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    data = await AiKnowledgeService.get_base(kb_id)
    if not data:
        return ErrorResponse(msg="知识库不存在")
    return SuccessResponse(data=data, msg="查询成功")


@KnowledgeRouter.post("/bases/create", summary="新增知识库")
async def create_base(
    data: AiKnowledgeBaseCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiKnowledgeService.create_base(data, auth), msg="创建成功")


@KnowledgeRouter.put("/bases/update/{kb_id}", summary="编辑知识库")
async def update_base(
    kb_id: int,
    data: AiKnowledgeBaseUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    result = await AiKnowledgeService.update_base(kb_id, data, auth)
    if not result:
        return ErrorResponse(msg="知识库不存在")
    return SuccessResponse(data=result, msg="修改成功")


@KnowledgeRouter.delete("/bases/delete", summary="删除知识库")
async def delete_bases(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:delete"]))],
) -> JSONResponse:
    await AiKnowledgeService.delete_bases(ids)
    return SuccessResponse(msg="删除成功")


# ---------------------------------------------------------------- #
# 入库 / 检索 / 分块
# ---------------------------------------------------------------- #
@KnowledgeRouter.post("/bases/{kb_id}/ingest", summary="文本入库（分块+向量化）")
async def ingest(
    kb_id: int,
    data: AiKnowledgeIngestSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    try:
        result = await AiKnowledgeService.ingest(kb_id, data, auth)
        return SuccessResponse(data=result, msg="入库成功")
    except ValueError as e:
        return ErrorResponse(msg=str(e))


@KnowledgeRouter.post("/bases/{kb_id}/search", summary="知识检索")
async def search(
    kb_id: int,
    data: AiKnowledgeSearchSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    results = await AiKnowledgeService.search(
        [kb_id], data.query, data.top_k, use_graph=data.use_graph, mode=data.mode
    )
    return SuccessResponse(data=results, msg="检索成功")


@KnowledgeRouter.get("/bases/{kb_id}/graph", summary="知识图谱（GraphRAG）")
async def get_graph(
    kb_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiKnowledgeService.get_graph(kb_id), msg="查询成功")


@KnowledgeRouter.post("/bases/{kb_id}/graph/entity", summary="新增图谱实体")
async def create_graph_entity(
    kb_id: int,
    data: AiKnowledgeGraphEntitySchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.create_graph_entity(kb_id, data), msg="已新增实体"
    )


@KnowledgeRouter.put("/bases/{kb_id}/graph/entity/{entity_id}", summary="更新图谱实体")
async def update_graph_entity(
    kb_id: int,
    entity_id: int,
    data: AiKnowledgeGraphEntitySchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    r = await AiKnowledgeService.update_graph_entity(kb_id, entity_id, data)
    if not r:
        return ErrorResponse(msg="实体不存在")
    return SuccessResponse(data=r, msg="已更新")


@KnowledgeRouter.delete("/bases/{kb_id}/graph/entity", summary="删除图谱实体")
async def delete_graph_entities(
    kb_id: int,
    ids: list[int],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    await AiKnowledgeService.delete_graph_entities(kb_id, ids)
    return SuccessResponse(data=None, msg="已删除")


@KnowledgeRouter.post("/bases/{kb_id}/graph/relation", summary="新增图谱关系")
async def create_graph_relation(
    kb_id: int,
    data: AiKnowledgeGraphRelationSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.create_graph_relation(kb_id, data), msg="已新增关系"
    )


@KnowledgeRouter.delete("/bases/{kb_id}/graph/relation", summary="删除图谱关系")
async def delete_graph_relations(
    kb_id: int,
    ids: list[int],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    await AiKnowledgeService.delete_graph_relations(kb_id, ids)
    return SuccessResponse(data=None, msg="已删除")


@KnowledgeRouter.post("/bases/{kb_id}/rebuild", summary="重建索引（重新向量化+重建图谱）")
async def rebuild_index(
    kb_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.rebuild_index(kb_id), msg="重建完成"
    )


@KnowledgeRouter.get("/bases/{kb_id}/chunks", summary="分块列表")
async def list_chunks(
    kb_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiKnowledgeService.list_chunks(kb_id), msg="查询成功")


@KnowledgeRouter.delete("/bases/{kb_id}/chunks/{chunk_id}", summary="删除分块")
async def delete_chunk(
    kb_id: int,
    chunk_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:delete"]))],
) -> JSONResponse:
    await AiKnowledgeService.delete_chunk(chunk_id)
    return SuccessResponse(msg="删除成功")


@KnowledgeRouter.put("/bases/{kb_id}/chunks/{chunk_id}", summary="编辑分块并重向量化")
async def update_chunk(
    kb_id: int,
    chunk_id: int,
    data: AiKnowledgeUpdateChunkSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.update_chunk(kb_id, chunk_id, data.content),
        msg="已更新并重向量化",
    )


# ---------------------------------------------------------------- #
# 数据源
# ---------------------------------------------------------------- #
@KnowledgeRouter.get("/datasources/list", summary="数据源列表")
async def list_datasources(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiKnowledgeService.list_datasources(), msg="查询成功")


@KnowledgeRouter.post("/datasources/create", summary="新增数据源")
async def create_datasource(
    data: AiDatasourceCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:create"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiKnowledgeService.create_datasource(data, auth), msg="创建成功")


@KnowledgeRouter.put("/datasources/update/{ds_id}", summary="编辑数据源")
async def update_datasource(
    ds_id: int,
    data: AiDatasourceUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    result = await AiKnowledgeService.update_datasource(ds_id, data, auth)
    if not result:
        return ErrorResponse(msg="数据源不存在")
    return SuccessResponse(data=result, msg="修改成功")


@KnowledgeRouter.delete("/datasources/delete", summary="删除数据源")
async def delete_datasources(
    ids: Annotated[list[int], Body(description="ID列表")],
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:delete"]))],
) -> JSONResponse:
    await AiKnowledgeService.delete_datasources(ids)
    return SuccessResponse(msg="删除成功")


@KnowledgeRouter.post("/datasources/{ds_id}/test", summary="测试数据源连接")
async def test_datasource(
    ds_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    try:
        result = await AiKnowledgeService.test_datasource(ds_id)
        return SuccessResponse(data=result, msg="测试完成")
    except ValueError as e:
        return ErrorResponse(msg=str(e))


@KnowledgeRouter.post("/datasources/{ds_id}/sync", summary="数据源同步入库")
async def sync_datasource(
    ds_id: int,
    data: AiDatasourceSyncSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    try:
        result = await AiKnowledgeService.sync_datasource(ds_id, data, auth)
        return SuccessResponse(data=result, msg="同步成功")
    except ValueError as e:
        return ErrorResponse(msg=str(e))
