"""上下文组装：父块回填 → 相邻块合并 → 去重 → token 预算截断。

检索返回的是「小块」（命中精准），但回答需要「大块」上下文：
- 有 ``parent_id`` 时取父块文本（真正的父子分块）；
- 没有父块时用同文件 ``chunk_index ± 1`` 近似回填（兼容历史数据）。
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.database import async_db_session

from ..config import rag_config
from ..model import AiKnowledgeChunkModel
from .filters import drop_duplicates


def _estimate_tokens(text: str) -> int:
    try:
        from ..chunking.tokens import estimate_tokens

        return int(estimate_tokens(text))
    except Exception:  # noqa: BLE001  token 模块未实现时用字符估算
        return max(1, len(text or "") // 2)


async def _load_context_rows(items: list[dict]) -> tuple[dict[int, str], dict[tuple, str]]:
    """批量取父块文本与邻居块文本。"""
    parent_ids = [int(item["parent_id"]) for item in items if item.get("parent_id")]
    kb_ids = {int(item["knowledge_base_id"]) for item in items if item.get("knowledge_base_id")}
    files = {str(item.get("file_name") or "") for item in items}
    index_range: list[int] = []
    for item in items:
        if item.get("chunk_index") is not None:
            index_range.append(int(item["chunk_index"]))

    parents: dict[int, str] = {}
    neighbours: dict[tuple, str] = {}
    if not kb_ids:
        return parents, neighbours
    async with async_db_session() as db:
        if parent_ids:
            rows = (
                await db.execute(
                    select(AiKnowledgeChunkModel.id, AiKnowledgeChunkModel.content).where(
                        AiKnowledgeChunkModel.id.in_(parent_ids)
                    )
                )
            ).all()
            parents = {int(r[0]): r[1] or "" for r in rows}
        if index_range:
            rows = (
                await db.execute(
                    select(
                        AiKnowledgeChunkModel.id,
                        AiKnowledgeChunkModel.knowledge_base_id,
                        AiKnowledgeChunkModel.file_name,
                        AiKnowledgeChunkModel.chunk_index,
                        AiKnowledgeChunkModel.content,
                    ).where(
                        AiKnowledgeChunkModel.knowledge_base_id.in_(kb_ids),
                        AiKnowledgeChunkModel.file_name.in_(files),
                        AiKnowledgeChunkModel.is_deleted.is_(False),
                        AiKnowledgeChunkModel.is_parent.is_not(True),
                        AiKnowledgeChunkModel.chunk_index >= min(index_range) - 1,
                        AiKnowledgeChunkModel.chunk_index <= max(index_range) + 1,
                    )
                )
            ).all()
            for chunk_id, kb_id, file_name, chunk_index, content in rows:
                neighbours[(int(kb_id), str(file_name or ""), int(chunk_index or 0))] = (
                    content or ""
                )
    return parents, neighbours


def _merge(*parts: str) -> str:
    """按顺序拼接，跳过被包含的重复片段。"""
    merged: list[str] = []
    for part in parts:
        part = (part or "").strip()
        if not part:
            continue
        if any(part in existing for existing in merged):
            continue
        if merged and merged[-1] in part:
            merged[-1] = part
            continue
        merged.append(part)
    return "\n".join(merged)


async def assemble(
    items: list[dict], *, top_k: int, context_tokens: int | None = None
) -> list[dict]:
    """为每条命中补充 ``context``，并应用 token 预算。"""
    if not items:
        return []
    budget = int(context_tokens or rag_config.context_tokens)
    deduped = drop_duplicates(items)[: max(1, int(top_k))]
    parents, neighbours = await _load_context_rows(deduped)

    out: list[dict] = []
    used = 0
    for item in deduped:
        parent_id = item.get("parent_id")
        if parent_id and parents.get(int(parent_id)):
            context = parents[int(parent_id)]
        else:
            index = int(item.get("chunk_index") or 0)
            kb_id = int(item.get("knowledge_base_id") or 0)
            file_name = str(item.get("file_name") or "")
            context = _merge(
                neighbours.get((kb_id, file_name, index - 1), ""),
                item.get("content") or "",
                neighbours.get((kb_id, file_name, index + 1), ""),
            )
        tokens = _estimate_tokens(context)
        truncated = False
        if used + tokens > budget:
            remaining = max(0, budget - used)
            if remaining <= 0 and out:
                continue
            context = context[: max(1, remaining * 2)]
            tokens = _estimate_tokens(context)
            truncated = True
        used += tokens
        out.append({**item, "context": context, "context_truncated": truncated})
    return out
