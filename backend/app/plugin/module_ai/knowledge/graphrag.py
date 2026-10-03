"""GraphRAG：基于 jieba 关键词建立轻量实体-关系图谱，检索时扩展邻居注入上下文。

可移植（不依赖 AGE/Neo4j），SQLite 亦可运行；实体/关系存自有表。
"""
from __future__ import annotations

import re

from sqlalchemy import select

from app.core.database import async_db_session
from app.plugin.module_ai.knowledge.model import (
    AiKnowledgeChunkModel,
    AiKnowledgeEntityModel,
    AiKnowledgeRelationModel,
)

_STOPWORDS = {
    "的", "了", "和", "是", "在", "与", "或", "及", "对", "为", "而", "等",
    "a", "an", "the", "of", "to", "and", "or", "in", "on", "for",
}


def _cut(text: str) -> list[str]:
    import jieba

    words = jieba.cut(text or "")
    out: list[str] = []
    for w in words:
        w = w.strip()
        if not w or w in _STOPWORDS or len(w) < 2:
            continue
        if not re.search(r"[\w\u4e00-\u9fa5]", w):
            continue
        out.append(w)
    return out


def extract_keywords(text: str, topk: int = 20) -> list[str]:
    """jieba TF-IDF 关键词抽取。"""
    import jieba.analyse

    if not text:
        return []
    tags = jieba.analyse.extract_tags(text or "", topK=topk, withWeight=False)
    return [t for t in tags if len(t) >= 2]


async def build_graph(kb_id: int) -> int:
    """从某知识库全部 chunk 抽取实体与共现关系。返回关系数。"""
    async with async_db_session() as db:
        chunks = (
            (
                await db.execute(
                    select(AiKnowledgeChunkModel).where(
                        AiKnowledgeChunkModel.knowledge_base_id == kb_id,
                        AiKnowledgeChunkModel.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
    rel_count = 0
    for chunk in chunks:
        kws = extract_keywords(chunk.content, topk=20)
        if not kws:
            continue
        # 实体：去重
        names = list(dict.fromkeys(kws))
        # 共现关系（含窗口内相邻）
        pairs: set[tuple[str, str]] = set()
        for i in range(len(kws)):
            source = kws[i]
            for j in range(max(0, i - 3), min(len(kws), i + 4)):
                if i == j:
                    continue
                target = kws[j]
                pair = (source, target) if source < target else (target, source)
                pairs.add(pair)
        async with async_db_session() as db:
            for name in names:
                ent = (
                    await db.execute(
                        select(AiKnowledgeEntityModel).where(
                            AiKnowledgeEntityModel.knowledge_base_id == kb_id,
                            AiKnowledgeEntityModel.name == name,
                            AiKnowledgeEntityModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if ent:
                    ent.weight = (ent.weight or 0) + 1
                else:
                    db.add(
                        AiKnowledgeEntityModel(
                            knowledge_base_id=kb_id, name=name, etype="keyword", weight=1
                        )
                    )
            for s, tgt in pairs:
                rel = (
                    await db.execute(
                        select(AiKnowledgeRelationModel).where(
                            AiKnowledgeRelationModel.knowledge_base_id == kb_id,
                            AiKnowledgeRelationModel.source == s,
                            AiKnowledgeRelationModel.target == tgt,
                            AiKnowledgeRelationModel.is_deleted.is_(False),
                        )
                    )
                ).scalar_one_or_none()
                if rel:
                    rel.weight = (rel.weight or 0) + 1
                else:
                    db.add(
                        AiKnowledgeRelationModel(
                            knowledge_base_id=kb_id, source=s, target=tgt, weight=1
                        )
                    )
                    rel_count += 1
            await db.commit()
    return rel_count


async def graph_retrieve(kb_ids: list[int], query: str, top_k: int = 5, hops: int = 1) -> list[dict]:
    """图谱检索：查询词匹配实体 → 扩展邻居 → 收集相关实体及其所在分块。

    返回 [{name, weight, chunks:[..]}]。
    """
    async with async_db_session() as db:
        ents = (
            (
                await db.execute(
                    select(AiKnowledgeEntityModel).where(
                        AiKnowledgeEntityModel.knowledge_base_id.in_(kb_ids),
                        AiKnowledgeEntityModel.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
        rels = (
            (
                await db.execute(
                    select(AiKnowledgeRelationModel).where(
                        AiKnowledgeRelationModel.knowledge_base_id.in_(kb_ids),
                        AiKnowledgeRelationModel.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
    qkws = set(extract_keywords(query, topk=30)) | set(_cut(query))
    ent_map = {e.name: e for e in ents}
    # 命中实体
    hits = [n for n in qkws if n in ent_map]
    if not hits:
        # 退化为包含查询词的实体
        for e in ent_map.values():
            if any(q in e.name or e.name in q for q in qkws):
                hits.append(e.name)
    # 扩展邻居
    expanded: list[str] = list(hits)
    if hops >= 1:
        seed = set(hits)
        for _ in range(hops):
            nbrs: set[str] = set()
            for r in rels:
                if r.source in seed:
                    nbrs.add(r.target)
                if r.target in seed:
                    nbrs.add(r.source)
            new = nbrs - seed
            if not new:
                break
            seed |= new
            expanded += list(new)
    expanded = list(dict.fromkeys(expanded))
    # 取匹配实体（含扩展）所在分块
    async with async_db_session() as db:
        chunks = (
            (
                await db.execute(
                    select(AiKnowledgeChunkModel).where(
                        AiKnowledgeChunkModel.knowledge_base_id.in_(kb_ids),
                        AiKnowledgeChunkModel.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
    result: list[dict] = []
    for name in expanded:
        c = [
            {"chunk_id": ch.id, "content": ch.content, "file_name": ch.file_name}
            for ch in chunks
            if name in (ch.content or "")
        ]
        weight = ent_map.get(name).weight if ent_map.get(name) else 0
        result.append({"name": name, "weight": weight or 0, "chunks": c[:top_k]})
    result.sort(key=lambda x: x["weight"], reverse=True)
    return result[:top_k]
