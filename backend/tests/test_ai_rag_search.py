"""检索链路测试：召回引擎、融合、重排、上下文与管线。"""
import asyncio


def _run(coro):
    return asyncio.run(coro)


def _seed_kb(test_client, auth_headers, monkeypatch):
    """建库并入库两条可区分语义的文本（嵌入用假向量）。"""
    import uuid

    from app.plugin.module_ai.knowledge import embedding as emb

    async def fake_embed(texts, model_id=None):
        vectors = []
        for text in texts:
            vec = [0.0, 0.0]
            vec[0 if "智能体" in text else 1] = 1.0
            vectors.append(vec)
        return vectors

    monkeypatch.setattr(emb, "embed_texts", fake_embed)
    kb_id = test_client.post(
        "/api/v1/ai/knowledge/bases/create",
        json={"name": f"pytest_search_{uuid.uuid4().hex[:8]}", "enabled": True},
        headers=auth_headers,
    ).json()["data"]["id"]
    for name, text in (("a.txt", "智能体编排说明"), ("b.txt", "传感器安装说明")):
        test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/ingest",
            json={"file_name": name, "content": text},
            headers=auth_headers,
        )
    return kb_id


def _drop_kb(test_client, auth_headers, kb_id):
    test_client.request(
        "DELETE",
        "/api/v1/ai/knowledge/bases/delete",
        json=[kb_id],
        headers=auth_headers,
    )


def test_vector_search_without_pg(test_client, auth_headers, monkeypatch):
    """非 PG（测试用 SQLite）必须走 Python 余弦，且过滤/阈值生效。"""
    from app.plugin.module_ai.knowledge.search import engines

    kb_id = _seed_kb(test_client, auth_headers, monkeypatch)
    try:
        rows = _run(engines.vector_search([kb_id], "智能体", 5))
        assert rows and "智能体" in rows[0]["content"]
        assert rows[0]["engine"] in ("pyvector", "pgvector")

        filtered = _run(
            engines.vector_search([kb_id], "智能体", 5, filters={"file_name": "b.txt"})
        )
        assert all(r["file_name"] == "b.txt" for r in filtered)

        low = _run(engines.vector_search([kb_id], "智能体", 5, min_score=0.99))
        assert all(r["score"] >= 0.99 for r in low)
    finally:
        _drop_kb(test_client, auth_headers, kb_id)


def test_fulltext_unavailable_falls_back_empty(test_client, auth_headers, monkeypatch):
    """除 PG 外全文召回返回空（管线随后自动补 grep），不能抛错。"""
    import os

    from app.plugin.module_ai.knowledge.search import engines

    kb_id = _seed_kb(test_client, auth_headers, monkeypatch)
    try:
        if (os.getenv("DATABASE_TYPE") or "").lower() == "sqlite":
            assert _run(engines.fulltext_search([kb_id], "智能体", 5)) == []
        grep = _run(engines.grep_search([kb_id], "智能体", 5))
        assert grep and "智能体" in grep[0]["content"]
    finally:
        _drop_kb(test_client, auth_headers, kb_id)


def test_rrf_orders_by_reciprocal_rank():
    from app.plugin.module_ai.knowledge.search.fusion import rrf

    a = [
        {"chunk_id": 1, "content": "a1", "score": 0.9},
        {"chunk_id": 2, "content": "a2", "score": 0.8},
    ]
    b = [
        {"chunk_id": 2, "content": "a2", "score": 0.7},
        {"chunk_id": 3, "content": "a3", "score": 0.6},
    ]
    out = rrf([a, b])
    assert out[0]["chunk_id"] == 2, "两路都命中的应排第一"
    assert out[0]["score"] == round(1 / 62 + 1 / 61, 4)
    assert {row["engine"] for row in out} == {"hybrid"}


def test_weighted_respects_weights():
    from app.plugin.module_ai.knowledge.search.fusion import weighted

    a = [{"chunk_id": 1, "content": "a", "score": 1.0}]
    b = [{"chunk_id": 2, "content": "b", "score": 1.0}]
    assert weighted([a, b], [0.9, 0.1])[0]["chunk_id"] == 1
    assert weighted([a, b], [0.1, 0.9])[0]["chunk_id"] == 2


def test_rerank_orders_and_scores(monkeypatch):
    from app.plugin.module_ai.knowledge.search import rerank as rr

    async def fake_resolve(model_id=None):
        return rr.ResolvedRerank(base_url="http://x", api_key="k", headers={}, model="m")

    async def fake_post(base_url, api_key, headers, model, query, documents, top_n):
        return [{"index": 1, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.2}]

    monkeypatch.setattr(rr, "resolve_rerank", fake_resolve)
    monkeypatch.setattr(rr, "_post_rerank", fake_post)
    cands = [{"chunk_id": 1, "content": "第一"}, {"chunk_id": 2, "content": "第二"}]
    out = _run(rr.rerank("问题", cands, 2))
    assert out.status == "applied"
    assert [item["chunk_id"] for item in out.items] == [2, 1]
    assert out.items[0]["rerank_score"] == 0.9


def test_rerank_degrades_on_error(monkeypatch):
    from app.plugin.module_ai.knowledge.search import rerank as rr

    async def boom_resolve(*args, **kwargs):
        raise TimeoutError("超时")

    monkeypatch.setattr(rr, "resolve_rerank", boom_resolve)
    cands = [{"chunk_id": 1, "content": "x"}]
    out = _run(rr.rerank("q", cands, 5))
    assert out.status == "skipped"
    assert [item["chunk_id"] for item in out.items] == [1]


def test_assemble_uses_neighbor_and_budget(test_client, auth_headers, monkeypatch):
    from app.plugin.module_ai.knowledge.search import context

    kb_id = _seed_kb(test_client, auth_headers, monkeypatch)
    try:
        chunks = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"]
        items = [
            {
                "chunk_id": chunks[0]["id"],
                "knowledge_base_id": kb_id,
                "file_name": chunks[0].get("file_name") or "a.txt",
                "chunk_index": chunks[0].get("chunk_index") or 0,
                "content": chunks[0]["content"],
                "score": 0.9,
            },
            {
                "chunk_id": chunks[1]["id"],
                "knowledge_base_id": kb_id,
                "file_name": chunks[1].get("file_name") or "b.txt",
                "chunk_index": chunks[1].get("chunk_index") or 0,
                "content": chunks[1]["content"],
                "score": 0.8,
            },
            {
                "chunk_id": chunks[1]["id"],
                "knowledge_base_id": kb_id,
                "file_name": chunks[1].get("file_name") or "b.txt",
                "chunk_index": chunks[1].get("chunk_index") or 0,
                "content": chunks[1]["content"],
                "score": 0.8,
            },
        ]
        out = _run(context.assemble(items, top_k=5, context_tokens=10))
        assert len(out) == 2, "重复项应被去掉"
        assert all(item["context"] for item in out)
        assert all("context" in item for item in out)
    finally:
        _drop_kb(test_client, auth_headers, kb_id)


def test_pipeline_end_to_end_and_logged(test_client, auth_headers, monkeypatch):
    """service.search 走统一管线，并自动写检索日志（含耗时/引擎）。"""
    from sqlalchemy import select

    from app.core.database import async_db_session
    from app.plugin.module_ai.knowledge.model import AiSearchLogModel
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    kb_id = _seed_kb(test_client, auth_headers, monkeypatch)
    try:
        rows = _run(AiKnowledgeService.search([kb_id], "智能体", 3, use_rerank=False))
        assert rows and "智能体" in rows[0]["content"]
        assert "context" in rows[0] and "timings" in rows[0]
        assert rows[0]["timings"]["rerank"] == "off"

        rows2 = _run(
            AiKnowledgeService.search(
                [kb_id], "智能体", 3, use_rerank=False, filters={"file_name": "b.txt"}
            )
        )
        assert all(row["file_name"] == "b.txt" for row in rows2)

        async def _logs():
            async with async_db_session() as db:
                return (
                    (
                        await db.execute(
                            select(AiSearchLogModel).where(
                                AiSearchLogModel.knowledge_base_id == kb_id
                            )
                        )
                    )
                    .scalars()
                    .all()
                )

        logs = _run(_logs())
        assert len(logs) >= 2, "直接调用 service.search 也应写检索日志"
        payload = logs[0].engines
        assert isinstance(payload, dict) and "embed_ms" in payload
        assert "engine_counts" in payload
    finally:
        _drop_kb(test_client, auth_headers, kb_id)
