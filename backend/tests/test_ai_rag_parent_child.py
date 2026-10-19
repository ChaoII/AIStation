"""父子分块：父块只存文本、子块参与召回，检索时回填父块上下文。"""
import asyncio
import uuid


def test_parent_child_ingest_and_backfill(test_client, auth_headers, monkeypatch):
    from app.plugin.module_ai.knowledge import embedding as emb
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    async def fake_embed(texts, model_id=None):
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(emb, "embed_texts", fake_embed)
    kb_id = test_client.post(
        "/api/v1/ai/knowledge/bases/create",
        json={"name": f"pytest_pc_{uuid.uuid4().hex[:8]}", "enabled": True},
        headers=auth_headers,
    ).json()["data"]["id"]
    try:
        text = "# 标题\n\n" + ("知识库父子块内容。" * 80)
        r = test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/ingest",
            json={
                "file_name": "pc.md",
                "content": text,
                "chunk_size": 100,
                "overlap": 0,
                "strategy": "heading",
                "parent_child": True,
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        child_count = r.json()["data"]["chunks"]
        assert child_count >= 2

        chunks = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"]
        parents = [c for c in chunks if c.get("is_parent")]
        children = [c for c in chunks if not c.get("is_parent")]
        assert len(parents) >= 1
        assert len(children) == child_count
        assert all(child.get("parent_id") for child in children)

        quality = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/quality", headers=auth_headers
        ).json()["data"]
        assert quality["parents"] == len(parents)
        assert quality["chunks"] == child_count, "父块不计入 chunks/嵌入率"

        results = asyncio.run(
            AiKnowledgeService.search([kb_id], "父子块", 3, use_rerank=False)
        )
        assert results
        assert "知识库父子块内容" in results[0]["context"]
    finally:
        test_client.request(
            "DELETE",
            "/api/v1/ai/knowledge/bases/delete",
            json=[kb_id],
            headers=auth_headers,
        )
