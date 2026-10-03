"""GraphRAG：基于 jieba 关键词建立轻量实体-关系图谱，检索时扩展邻居注入上下文。

可移植（不依赖 AGE/Neo4j），SQLite 亦可运行；实体/关系存自有表。
若 PostgreSQL 已启用 Apache AGE 扩展（aistation-pg-rag 镜像自带），
实体/关系会**同步写入 AGE 图库**，检索优先用 Cypher 做多跳邻居扩展。
"""
from __future__ import annotations

import re

from sqlalchemy import select, text

from app.core.database import async_db_session
from app.plugin.module_ai.knowledge.model import (
    AiKnowledgeChunkModel,
    AiKnowledgeEntityChunkModel,
    AiKnowledgeEntityModel,
    AiKnowledgeRelationModel,
)

_STOPWORDS = {
    "的", "了", "和", "是", "在", "与", "或", "及", "对", "为", "而", "等",
    "a", "an", "the", "of", "to", "and", "or", "in", "on", "for",
}


def _graph_name(kb_id: int) -> str:
    return f"kb_graph_{kb_id}"


async def _age_available() -> bool:
    """检测当前 DB 是否为 PostgreSQL 且已启用 age 扩展。"""
    try:
        async with async_db_session() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT count(*) FROM pg_extension WHERE extname = 'age'"
                    )
                )
            ).scalar()
        return bool(row)
    except Exception:  # noqa: BLE001  非 PostgreSQL / 无扩展则回退
        return False


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


async def age_sync_graph(kb_id: int) -> bool:
    """若 AGE 可用，把自有实体/关系表镜像写入 AGE 图库。"""
    if not await _age_available():
        return False
    async with async_db_session() as db:
        ents = (
            (
                await db.execute(
                    select(AiKnowledgeEntityModel).where(
                        AiKnowledgeEntityModel.knowledge_base_id == kb_id,
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
                        AiKnowledgeRelationModel.knowledge_base_id == kb_id,
                        AiKnowledgeRelationModel.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
    g = _graph_name(kb_id)
    try:
        async with async_db_session.begin() as db:
            await db.execute(text("LOAD 'age'"))
            await db.execute(text("SET search_path = public, ag_catalog"))
            # 建/清空图
            await db.execute(text(f"SELECT create_graph('{g}')"))
        async with async_db_session.begin() as db:
            await db.execute(text("LOAD 'age'"))
            await db.execute(text("SET search_path = public, ag_catalog"))
            await db.execute(
                text(f"SELECT * FROM cypher('{g}', $$ MATCH (n) DETACH DELETE n RETURN 1 $$) AS (x agtype)")
            )
            for e in ents:
                name = e.name.replace("'", "''")
                w = e.weight or 1
                await db.execute(
                    text(
                        f"SELECT * FROM cypher('{g}', $$ MERGE (n:Entity {{name:'{name}'}}) SET n.weight={w} RETURN n.name $$) AS (x agtype)"
                    )
                )
            for r in rels:
                s = r.source.replace("'", "''")
                t = r.target.replace("'", "''")
                w = r.weight or 1
                await db.execute(
                    text(
                        f"SELECT * FROM cypher('{g}', $$ MATCH (a:Entity {{name:'{s}'}}), (b:Entity {{name:'{t}'}}) MERGE (a)-[:REL {{weight:{w}}}]->(b) RETURN 1 $$) AS (x agtype)"
                    )
                )
        return True
    except Exception:  # noqa: BLE001  AGE 写失败回退自有表
        return False


async def _age_neighbors(kb_id: int, qwords: list[str], hops: int = 1) -> list[str]:
    """用 AGE Cypher 查询给定词实体的多跳邻居。"""
    if not await _age_available() or not qwords:
        return []
    g = _graph_name(kb_id)
    seed = "', '".join(w.replace("'", "''") for w in qwords)
    cypher = f"""
        MATCH (a:Entity) WHERE a.name IN ['{seed}']
        MATCH path = (a)-[:REL*1..{max(1, hops)}]-(b:Entity)
        RETURN b.name
    """
    try:
        async with async_db_session() as db:
            await db.execute(text("LOAD 'age'"))
            res = await db.execute(
                text(f"SELECT * FROM cypher('{g}', $${cypher}$$) AS (name agtype)")
            )
            rows = res.fetchall()
        out: list[str] = []
        for row in rows:
            val = row[0]
            # agtype 值是字符串（可能带双引号）
            out.append(str(val).strip('"'))
        return list(dict.fromkeys(out))
    except Exception:  # noqa: BLE001
        return []


async def sync_annotation_entities(kb_id: int, chunk_id: int, texts: list[str]) -> list[str]:
    """把分块标注文本的关键词作为图谱实体，并绑定到该分块（标注自动纳入图谱）。"""
    names: list[str] = []
    for t in texts or []:
        for kw in extract_keywords(t, topk=10):
            if len(kw) >= 2:
                names.append(kw)
    names = list(dict.fromkeys(names))
    if not names:
        return []
    async with async_db_session.begin() as db:
        ents = (
            (
                await db.execute(
                    select(AiKnowledgeEntityModel).where(
                        AiKnowledgeEntityModel.knowledge_base_id == kb_id,
                        AiKnowledgeEntityModel.is_deleted.is_(False),
                        AiKnowledgeEntityModel.name.in_(names),
                    )
                )
            )
            .scalars()
            .all()
        )
        ent_map = {e.name: e.id for e in ents}
        created = []
        for name in names:
            eid = ent_map.get(name)
            if eid is None:
                e = AiKnowledgeEntityModel(knowledge_base_id=kb_id, name=name, etype="annotation", weight=1)
                db.add(e)
                await db.flush()
                eid = e.id
                ent_map[name] = eid
                created.append(name)
            exists = (
                await db.execute(
                    select(AiKnowledgeEntityChunkModel.id).where(
                        AiKnowledgeEntityChunkModel.entity_id == eid,
                        AiKnowledgeEntityChunkModel.chunk_id == chunk_id,
                        AiKnowledgeEntityChunkModel.is_deleted.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if not exists:
                db.add(AiKnowledgeEntityChunkModel(entity_id=eid, chunk_id=chunk_id))
    await age_sync_graph(kb_id)
    return created


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
    # 扩展邻居：优先用 AGE Cypher 多跳；不可用则自有表共现扩展
    expanded: list[str] = list(hits)
    if hops >= 1:
        age_nbrs = await _age_neighbors(kb_ids[0], hits, hops)
        if age_nbrs:
            expanded += [n for n in age_nbrs if n not in expanded]
        else:
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
    # 实体 ↔ 分块绑定（图谱检索回溯到明确关联的分块，优于纯文本包含匹配）
    async with async_db_session() as db:
        binds = (
            (
                await db.execute(
                    select(AiKnowledgeEntityChunkModel).where(
                        AiKnowledgeEntityChunkModel.is_deleted.is_(False),
                    )
                )
            )
            .scalars()
            .all()
        )
    ent_id_to_name = {e.id: e.name for e in ents}
    bind_chunks: dict[int, list[int]] = {}
    for b in binds:
        bind_chunks.setdefault(b.entity_id, []).append(b.chunk_id)
    name_to_chunkids: dict[str, list[int]] = {}
    for eid, cids in bind_chunks.items():
        nm = ent_id_to_name.get(eid)
        if nm:
            name_to_chunkids.setdefault(nm, []).extend(cids)
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
    chunk_by_id = {ch.id: ch for ch in chunks}
    result: list[dict] = []
    for name in expanded:
        bound_ids = name_to_chunkids.get(name) or []
        c: list[dict] = []
        for cid in bound_ids:
            ch = chunk_by_id.get(cid)
            if ch and ch.knowledge_base_id in kb_ids:
                c.append({"chunk_id": ch.id, "content": ch.content, "file_name": ch.file_name})
        if not c:
            # 回退：实体名出现在正文中
            c = [
                {"chunk_id": ch.id, "content": ch.content, "file_name": ch.file_name}
                for ch in chunks
                if name in (ch.content or "")
            ]
        weight = ent_map.get(name).weight if ent_map.get(name) else 0
        result.append({"name": name, "weight": weight or 0, "chunks": c[:top_k]})
    result.sort(key=lambda x: x["weight"], reverse=True)
    return result[:top_k]
