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
