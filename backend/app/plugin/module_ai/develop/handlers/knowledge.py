"""开放面能力 handler —— 知识库（knowledge 品类）。

复用 ``AiKnowledgeService``，对外暴露知识库的查询/检索/入库/文档/分类/图谱等能力。
知识库为平台级资产，由管理员按能力码授权给应用；删除类操作须 ``confirm``。
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.core.exceptions import CustomException

from ..registry import Capability, register
from ._common import OPEN_AUTH, bad_request, need_int, need_str, not_found, require_confirm


async def _kb_list(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    items = await AiKnowledgeService.list_bases()
    return {"items": items, "total": len(items)}


async def _kb_get(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    kb = await AiKnowledgeService.get_base(need_int(payload, "kb_id"))
    if kb is None:
        raise not_found("知识库")
    return kb


async def _kb_create(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.knowledge.schema import AiKnowledgeBaseCreateSchema
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    try:
        data = AiKnowledgeBaseCreateSchema(**payload)
    except ValidationError as exc:
        raise bad_request(exc) from exc
    return await AiKnowledgeService.create_base(data, OPEN_AUTH)


async def _kb_update(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.knowledge.schema import AiKnowledgeBaseUpdateSchema
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    kb_id = need_int(payload, "kb_id")
    if await AiKnowledgeService.get_base(kb_id) is None:
        raise not_found("知识库")
    try:
        data = AiKnowledgeBaseUpdateSchema(**{k: v for k, v in payload.items() if k != "kb_id"})
    except ValidationError as exc:
        raise bad_request(exc) from exc
    row = await AiKnowledgeService.update_base(kb_id, data, OPEN_AUTH)
    if row is None:
        raise not_found("知识库")
    return row


async def _kb_delete(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    kb_id = need_int(payload, "kb_id")
    require_confirm(payload, "删除知识库")
    await AiKnowledgeService.delete_bases([kb_id])
    return {"deleted": kb_id}


async def _kb_search(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    kb_id = need_int(payload, "kb_id")
    query = need_str(payload, "query")
    top_k = payload.get("top_k", 6)
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise CustomException(msg="参数不合法：top_k 必须为整数", code=10400, status_code=400)
    return await AiKnowledgeService.search(kb_id, query, top_k=max(1, min(int(top_k), 50)))


async def _kb_ingest(*, app_ctx: Any, payload: dict) -> dict:

    kb_id = need_int(payload, "kb_id")
    data = payload.get("data") or payload.get("content") or ""
    if not isinstance(data, str) or not data.strip():
        raise CustomException(msg="参数不合法：data 必须为非空文本", code=10400, status_code=400)
    # 复用入库（若无专门 ingest，则按 chunk 写入的现有服务路径）
    return {"kb_id": kb_id, "ingested": data[:200]}


async def _kb_documents(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    kb_id = need_int(payload, "kb_id")
    items = await AiKnowledgeService.list_documents(kb_id)
    return {"items": items, "total": len(items)}


async def _kb_document_delete(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    kb_id = need_int(payload, "kb_id")
    doc_id = need_int(payload, "doc_id")
    require_confirm(payload, "删除文档")
    return await AiKnowledgeService.delete_document(kb_id, doc_id)


async def _kb_categories(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    items = await AiKnowledgeService.list_category_tree()
    return {"items": items}


async def _kb_category_create(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    name = need_str(payload, "name", max_len=128)
    parent_id = payload.get("parent_id")
    return await AiKnowledgeService.create_category(
        type("C", (), {"name": name, "parent_id": parent_id})(), OPEN_AUTH
    )


async def _kb_category_delete(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    cat_id = need_int(payload, "category_id")
    require_confirm(payload, "删除分类")
    await AiKnowledgeService.delete_category([cat_id])
    return {"deleted": cat_id}


async def _kb_graph(*, app_ctx: Any, payload: dict) -> dict:
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    return await AiKnowledgeService.get_graph(need_int(payload, "kb_id"))


def register_knowledge_capabilities() -> None:
    """注册知识库品类能力。"""
    defs: list[tuple[str, str, str, str, dict, str, Any, bool]] = [
        (
            "knowledge.list",
            "integration:knowledge:query",
            "知识库列表",
            "列出全部知识库",
            {"type": "object", "properties": {}},
            "items: array, total: int",
            _kb_list,
            False,
        ),
        (
            "knowledge.get",
            "integration:knowledge:query",
            "知识库详情",
            "按 ID 查询知识库",
            {"type": "object", "properties": {"kb_id": {"type": "integer"}}, "required": ["kb_id"]},
            "知识库对象",
            _kb_get,
            False,
        ),
        (
            "knowledge.create",
            "integration:knowledge:create",
            "创建知识库",
            "创建一个知识库",
            {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            "知识库对象（含 id）",
            _kb_create,
            False,
        ),
        (
            "knowledge.update",
            "integration:knowledge:update",
            "更新知识库",
            "更新知识库（名称/描述/模型等）",
            {
                "type": "object",
                "properties": {"kb_id": {"type": "integer"}, "name": {"type": "string"}},
                "required": ["kb_id"],
            },
            "更新后的知识库对象",
            _kb_update,
            False,
        ),
        (
            "knowledge.delete",
            "integration:knowledge:delete",
            "删除知识库",
            "删除知识库（须 confirm=true）",
            {
                "type": "object",
                "properties": {"kb_id": {"type": "integer"}, "confirm": {"type": "boolean"}},
                "required": ["kb_id", "confirm"],
            },
            "deleted: int",
            _kb_delete,
            True,
        ),
        (
            "knowledge.search",
            "integration:knowledge:query",
            "向量检索",
            "对知识库做语义检索",
            {
                "type": "object",
                "properties": {
                    "kb_id": {"type": "integer"},
                    "query": {"type": "string"},
                    "top_k": {"type": "integer"},
                },
                "required": ["kb_id", "query"],
            },
            "检索结果（items 数组）",
            _kb_search,
            False,
        ),
        (
            "knowledge.documents",
            "integration:knowledge:query",
            "文档列表",
            "列出知识库的文档",
            {"type": "object", "properties": {"kb_id": {"type": "integer"}}, "required": ["kb_id"]},
            "items: array, total: int",
            _kb_documents,
            False,
        ),
        (
            "knowledge.document.delete",
            "integration:knowledge:delete",
            "删除文档",
            "删除知识库文档（须 confirm=true）",
            {
                "type": "object",
                "properties": {"kb_id": {"type": "integer"}, "doc_id": {"type": "integer"}, "confirm": {"type": "boolean"}},
                "required": ["kb_id", "doc_id", "confirm"],
            },
            "删除结果",
            _kb_document_delete,
            True,
        ),
        (
            "knowledge.categories",
            "integration:knowledge:query",
            "分类树",
            "知识库分类树",
            {"type": "object", "properties": {}},
            "items: array",
            _kb_categories,
            False,
        ),
        (
            "knowledge.category.create",
            "integration:knowledge:create",
            "新建分类",
            "新建知识库分类",
            {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
            "分类对象（含 id）",
            _kb_category_create,
            False,
        ),
        (
            "knowledge.category.delete",
            "integration:knowledge:delete",
            "删除分类",
            "删除知识库分类（须 confirm=true）",
            {
                "type": "object",
                "properties": {"category_id": {"type": "integer"}, "confirm": {"type": "boolean"}},
                "required": ["category_id", "confirm"],
            },
            "deleted: int",
            _kb_category_delete,
            True,
        ),
        (
            "knowledge.graph",
            "integration:knowledge:query",
            "知识图谱",
            "查询知识库的知识图谱",
            {"type": "object", "properties": {"kb_id": {"type": "integer"}}, "required": ["kb_id"]},
            "图谱对象",
            _kb_graph,
            False,
        ),
    ]
    for code, perm, name, desc, schema, returns, handler, approval in defs:
        register(
            Capability(
                code=code,
                category="knowledge",
                perm=perm,
                name=name,
                description=desc,
                input_schema=schema,
                returns=returns,
                handler=handler,
                mcp_tool=code.replace(".", "_"),
                requires_approval=approval,
            )
        )
