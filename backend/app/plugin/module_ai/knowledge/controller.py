"""知识库 / 数据源 RAG 控制器。"""
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile
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
    AiKnowledgeChunkAnnotateSchema,
    AiKnowledgeEntityBindSchema,
    AiKnowledgeGraphEntitySchema,
    AiKnowledgeGraphLayoutSchema,
    AiKnowledgeGraphRelationSchema,
    AiKnowledgeGraphRelationUpdateSchema,
    AiKnowledgeIngestSchema,
    AiKnowledgeSearchSchema,
    AiKnowledgeUpdateChunkSchema,
    AiRelationTypeCreateSchema,
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


@KnowledgeRouter.post("/bases/{kb_id}/copy", summary="复制知识库")
async def copy_kb(
    kb_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:create"]))],
) -> JSONResponse:
    try:
        data = await AiKnowledgeService.copy_kb(kb_id, auth)
        return SuccessResponse(data=data, msg="复制成功")
    except ValueError as e:
        return ErrorResponse(msg=str(e))


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
        [kb_id],
        data.query,
        data.top_k,
        use_graph=data.use_graph,
        mode=data.mode,
        vector_weight=data.vector_weight,
        fulltext_weight=data.fulltext_weight,
    )
    # 记录检索日志（供检索趋势统计）
    await AiKnowledgeService.log_search(
        kb_id, data.query, data.mode, data.top_k, results, user_id=auth.user.id
    )
    return SuccessResponse(data=results, msg="检索成功")


@KnowledgeRouter.post("/bases/{kb_id}/ask", summary="引用溯源问答")
async def ask(
    kb_id: int,
    body: dict,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    try:
        data = await AiKnowledgeService.ask(
            kb_id,
            body.get("query") or "",
            top_k=int(body.get("top_k") or 6),
            auth=auth,
            mode=body.get("mode") or "hybrid",
        )
        return SuccessResponse(data=data, msg="问答成功")
    except ValueError as e:
        return ErrorResponse(msg=str(e))


@KnowledgeRouter.get("/bases/{kb_id}/search-stats", summary="检索统计")
async def get_search_stats(
    kb_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
    days: int = 30,
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.search_stats(kb_id, days), msg="查询成功"
    )


@KnowledgeRouter.get("/bases/{kb_id}/quality", summary="知识库质量治理")
async def get_kb_quality(
    kb_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiKnowledgeService.kb_quality(kb_id), msg="查询成功")


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


@KnowledgeRouter.put("/bases/{kb_id}/graph/relation/{rel_id}", summary="编辑图谱关系")
async def update_graph_relation(
    kb_id: int,
    rel_id: int,
    data: AiKnowledgeGraphRelationUpdateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    r = await AiKnowledgeService.update_graph_relation(kb_id, rel_id, data)
    if not r:
        return ErrorResponse(msg="关系不存在")
    return SuccessResponse(data=r, msg="已更新关系")


@KnowledgeRouter.put("/bases/{kb_id}/graph/layout", summary="保存图谱布局")
async def save_graph_layout(
    kb_id: int,
    data: AiKnowledgeGraphLayoutSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    return SuccessResponse(
        data={"saved": await AiKnowledgeService.save_graph_layout(kb_id, data.items)},
        msg="已保存布局",
    )


@KnowledgeRouter.delete("/bases/{kb_id}/graph/layout", summary="清除布局记忆")
async def clear_graph_layout(
    kb_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    return SuccessResponse(
        data={"cleared": await AiKnowledgeService.clear_graph_layout(kb_id)},
        msg="已清除布局",
    )


# ---------- 关系类型模板（可维护） ----------
@KnowledgeRouter.get("/relation-types", summary="关系类型模板列表")
async def list_relation_types(
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiKnowledgeService.list_relation_types(), msg="查询成功")


@KnowledgeRouter.post("/relation-types", summary="新增关系类型模板")
async def create_relation_type(
    data: AiRelationTypeCreateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.create_relation_type(data.name, data.color),
        msg="已新增关系类型",
    )


@KnowledgeRouter.delete("/relation-types/{rid}", summary="删除关系类型模板")
async def delete_relation_type(
    rid: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    await AiKnowledgeService.delete_relation_type(rid)
    return SuccessResponse(msg="已删除")


# ---------- 文档管理（wikiLLM / ima 式） ----------
@KnowledgeRouter.get("/bases/{kb_id}/documents", summary="文档列表")
async def list_documents(
    kb_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    return SuccessResponse(data=await AiKnowledgeService.list_documents(kb_id), msg="查询成功")


@KnowledgeRouter.post("/bases/{kb_id}/documents/upload", summary="上传文档并索引")
async def upload_document(
    kb_id: int,
    file: Annotated[UploadFile, File(...)],
    chunk_size: Annotated[int, Form()] = 500,
    overlap: Annotated[int, Form()] = 50,
    strategy: Annotated[str, Form()] = "fixed",
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))] = None,
) -> JSONResponse:
    data = await file.read()
    try:
        result = await AiKnowledgeService.upload_document(
            kb_id, file.filename or "文档", data, auth,
            chunk_size=chunk_size, overlap=overlap, strategy=strategy,
        )
    except ValueError as e:
        return ErrorResponse(msg=str(e))
    return SuccessResponse(data=result, msg="已上传并索引")


@KnowledgeRouter.delete("/bases/{kb_id}/documents/{doc_id}", summary="删除文档")
async def delete_document(
    kb_id: int,
    doc_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:delete"]))],
) -> JSONResponse:
    await AiKnowledgeService.delete_document(kb_id, doc_id)
    return SuccessResponse(msg="已删除")


@KnowledgeRouter.get("/bases/{kb_id}/documents/{doc_id}/content", summary="文档内容(在线预览)")
async def get_document_content(
    kb_id: int,
    doc_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    try:
        return SuccessResponse(
            data=await AiKnowledgeService.get_document_content(kb_id, doc_id), msg="查询成功"
        )
    except ValueError as e:
        return ErrorResponse(msg=str(e))


@KnowledgeRouter.post("/bases/{kb_id}/documents/{doc_id}/reparse", summary="重新解析文档")
async def reparse_document(
    kb_id: int,
    doc_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    try:
        return SuccessResponse(
            data=await AiKnowledgeService.reparse_document(kb_id, doc_id, auth),
            msg="已重新解析并索引",
        )
    except ValueError as e:
        return ErrorResponse(msg=str(e))


@KnowledgeRouter.get("/bases/{kb_id}/documents/{doc_id}/download", summary="下载原始文档")
async def download_document(
    kb_id: int,
    doc_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    try:
        r = await AiKnowledgeService.download_document(kb_id, doc_id)
        import asyncio
        from urllib.parse import quote

        from fastapi.responses import StreamingResponse

        from app.utils.s3_client import s3_client

        obj = await asyncio.to_thread(s3_client.get_object, r["object_key"])
        body = obj["Body"]

        async def _gen():
            while True:
                chunk = await asyncio.to_thread(body.read, 65536)
                if not chunk:
                    break
                yield chunk

        media = {
            "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "md": "text/markdown",
            "txt": "text/plain",
            "csv": "text/csv",
            "json": "application/json",
        }.get(r["file_type"], "application/octet-stream")
        return StreamingResponse(
            _gen(),
            media_type=media,
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{quote(r['name'])}"
            },
        )
    except ValueError as e:
        return ErrorResponse(msg=str(e))


@KnowledgeRouter.get("/bases/{kb_id}/faq", summary="导出 FAQ 缓存")
async def export_faq(
    kb_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
    format: str = "json",
) -> JSONResponse:
    data = await AiKnowledgeService.export_faq(kb_id)
    if format == "md":
        lines = [f"# 知识库 FAQ（{data['count']} 条）\n"]
        for it in data["items"]:
            lines.append(f"## Q：{it['question']}\n来源：{it['file']}\n\n{it['answer']}\n")
        return SuccessResponse(data={"count": data["count"], "markdown": "\n".join(lines)}, msg="导出成功")
    return SuccessResponse(data=data, msg="导出成功")


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


# ---------- 分块标注（提升换说法召回） ----------
@KnowledgeRouter.post("/bases/{kb_id}/chunks/{chunk_id}/annotations", summary="添加分块标注")
async def add_chunk_annotation(
    kb_id: int,
    chunk_id: int,
    data: AiKnowledgeChunkAnnotateSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.add_chunk_annotation(
            kb_id, chunk_id, data.text, data.kind,
            query=data.query, source=data.source, user_id=auth.user.id,
        ),
        msg="已添加标注并更新索引",
    )


@KnowledgeRouter.delete("/bases/{kb_id}/chunks/{chunk_id}/annotations/{index}", summary="删除分块标注")
async def remove_chunk_annotation(
    kb_id: int,
    chunk_id: int,
    index: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.remove_chunk_annotation(
            kb_id, chunk_id, index, user_id=auth.user.id,
        ),
        msg="已删除标注并更新索引",
    )


@KnowledgeRouter.get("/bases/{kb_id}/annotation-logs", summary="标注台账")
async def list_annotation_logs(
    kb_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.list_annotation_logs(kb_id), msg="查询成功"
    )


@KnowledgeRouter.get("/bases/{kb_id}/suggest-annotate", summary="检索失败建议标注")
async def suggest_annotate(
    kb_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
    query: str = "",
    top_n: int = 5,
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.suggest_annotate(kb_id, query, top_n),
        msg="查询成功",
    )


@KnowledgeRouter.get("/bases/{kb_id}/chunks/{chunk_id}/entities", summary="分块绑定的实体")
async def get_chunk_entities(
    kb_id: int,
    chunk_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.get_chunk_entities(kb_id, chunk_id), msg="查询成功"
    )


# ---------- 实体 ↔ 分块 绑定 ----------
@KnowledgeRouter.get("/bases/{kb_id}/entities/{entity_id}/chunks", summary="实体绑定的分块")
async def get_entity_chunks(
    kb_id: int,
    entity_id: int,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:query"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.get_entity_chunks(kb_id, entity_id), msg="查询成功"
    )


@KnowledgeRouter.post("/bases/{kb_id}/entities/{entity_id}/bind", summary="实体绑定分块")
async def bind_entity_chunks(
    kb_id: int,
    entity_id: int,
    data: AiKnowledgeEntityBindSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.bind_entity_chunks(kb_id, entity_id, data.chunk_ids),
        msg="已绑定",
    )


@KnowledgeRouter.post("/bases/{kb_id}/entities/{entity_id}/unbind", summary="实体解绑分块")
async def unbind_entity_chunks(
    kb_id: int,
    entity_id: int,
    data: AiKnowledgeEntityBindSchema,
    auth: Annotated[AuthSchema, Depends(AuthPermission(["module_ai:knowledge:update"]))],
) -> JSONResponse:
    return SuccessResponse(
        data=await AiKnowledgeService.unbind_entity_chunks(kb_id, entity_id, data.chunk_ids),
        msg="已解绑",
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
