"""RAG 任务处理器注册表（worker 按 ``kind`` 分派）。"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

#: ``kind -> handler``；handler 接收任务字典，内部负责进度上报与取消检查
JOB_HANDLERS: dict[str, Callable[[dict], Awaitable[None]]] = {}


def register(kind: str, handler: Callable[[dict], Awaitable[None]]) -> None:
    """注册任务处理器（重复注册以最后一次为准，便于测试覆盖）。"""
    JOB_HANDLERS[kind] = handler


def get_handler(kind: str) -> Callable[[dict], Awaitable[None]] | None:
    return JOB_HANDLERS.get(kind)


# ---------------------------------------------------------------------------
# 具体任务处理器
# ---------------------------------------------------------------------------


async def job_document_ingest(task: dict) -> None:
    """文档入库：读取原始文件 → 解析 → 切分 → 向量化 → 入库 → 图谱。"""
    import asyncio

    from app.core.database import async_db_session
    from app.utils.s3_client import s3_client

    from ..model import AiKnowledgeDocumentModel
    from ..service import AiKnowledgeService
    from . import report_progress

    payload = task.get("payload") or {}
    kb_id = int(task["kb_id"])
    doc_id = int(task["document_id"])

    await report_progress(task["id"], progress=5, step="读取文档")
    async with async_db_session() as db:
        doc = await db.get(AiKnowledgeDocumentModel, doc_id)
        if not doc or doc.is_deleted:
            raise ValueError("文档不存在")
        name = doc.name or "文档"
        text = doc.content or ""
        object_key = doc.object_key

    if not text.strip() and object_key:
        buf = await asyncio.to_thread(s3_client.download_fileobj, object_key)
        raw = buf.getvalue()
        await report_progress(task["id"], progress=20, step="解析文档")
        text, page_offsets = await asyncio.to_thread(
            AiKnowledgeService._extract_doc, name, raw
        )
    else:
        page_offsets = payload.get("page_offsets") or [0]
    if not text.strip():
        raise ValueError("文档无有效文本（扫描件请开启 OCR 解析）")

    await report_progress(task["id"], progress=40, step="切分入库")
    from ..service import chunk_text

    chunk_size = int(payload.get("chunk_size") or 500)
    overlap = int(payload.get("overlap") or 50)
    strategy = str(payload.get("strategy") or "fixed")
    chunks = chunk_text(text, chunk_size, overlap, strategy)
    start_lines, pages = AiKnowledgeService._chunk_spans(text, chunks, page_offsets)
    result = await AiKnowledgeService.ingest_text(
        kb_id,
        text,
        name,
        auth=None,
        chunk_size=chunk_size,
        overlap=overlap,
        strategy=strategy,
        document_id=doc_id,
        start_lines=start_lines,
        pages=pages,
        rebuild_graph=False,
        parent_child=bool(payload.get("parent_child")),
        chunk_unit=str(payload.get("chunk_unit") or "char"),
        page_offsets=page_offsets,
    )
    await report_progress(task["id"], progress=90, step="重建图谱")
    await AiKnowledgeService._rebuild_graph(kb_id)

    async with async_db_session.begin() as db:
        doc = await db.get(AiKnowledgeDocumentModel, doc_id)
        if doc:
            doc.content = text
            doc.chunk_count = int(result.get("chunks", 0))
            doc.doc_status = "ready"
    await report_progress(task["id"], progress=100, step="完成")


async def job_kb_rebuild(task: dict) -> None:
    """整库重建：重新向量化全部子分块 + 重建图谱。"""
    from ..service import AiKnowledgeService
    from . import report_progress

    kb_id = int(task["kb_id"])
    await report_progress(task["id"], progress=10, step="重新向量化")
    result = await AiKnowledgeService._rebuild_index_sync(kb_id)
    await report_progress(
        task["id"],
        progress=100,
        step="完成（{} 块）".format(int(result.get("chunks", 0))),
    )


async def job_datasource_sync(task: dict) -> None:
    """数据源同步：批量入库，图谱只在末尾重建一次。"""
    from ..service import AiKnowledgeService
    from . import report_progress

    payload = task.get("payload") or {}
    await report_progress(task["id"], progress=10, step="拉取数据")
    result = await AiKnowledgeService._sync_datasource_rows(
        int(payload["ds_id"]),
        table=payload.get("table"),
        limit=int(payload.get("limit") or 50),
    )
    await report_progress(
        task["id"],
        progress=100,
        step="完成",
        message=f"同步 {result['rows']} 行 / {result['chunks']} 块",
    )


register("document_ingest", job_document_ingest)
register("kb_rebuild", job_kb_rebuild)
register("datasource_sync", job_datasource_sync)
