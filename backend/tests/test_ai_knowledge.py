"""AI 知识库 / 数据源 RAG：CRUD、入库分块、检索、数据源。"""
import uuid

from app.plugin.module_ai.knowledge.service import chunk_text


def _new_name(prefix: str = "pytest_kb") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _create_base(test_client, auth_headers, **overrides) -> int:
    r = test_client.post(
        "/api/v1/ai/knowledge/bases/create",
        json={"name": _new_name(), "description": "pytest 知识库", "enabled": True, **overrides},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _delete_base(test_client, auth_headers, ids) -> None:
    if ids:
        test_client.request(
            "DELETE", "/api/v1/ai/knowledge/bases/delete", json=ids, headers=auth_headers
        )


def test_chunk_text():
    """分块：按大小切分且带重叠，不做无谓分块。"""
    text = "ABCDEFGHIJ"
    chunks = chunk_text(text, chunk_size=4, overlap=1)
    assert chunks == ["ABCD", "DEFG", "GHIJ"]
    assert chunk_text("", 100) == []


def test_knowledge_base_crud(test_client, auth_headers):
    kb_id = _create_base(test_client, auth_headers)
    try:
        lst = test_client.get("/api/v1/ai/knowledge/bases/list", headers=auth_headers).json()["data"]
        assert any(b["id"] == kb_id for b in lst)

        detail = test_client.get(
            f"/api/v1/ai/knowledge/bases/detail/{kb_id}", headers=auth_headers
        )
        assert detail.status_code == 200, detail.text

        upd = test_client.put(
            f"/api/v1/ai/knowledge/bases/update/{kb_id}",
            json={"description": "updated", "enabled": False},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["data"]["description"] == "updated"
        assert upd.json()["data"]["enabled"] is False
    finally:
        _delete_base(test_client, auth_headers, [kb_id])

    lst2 = test_client.get("/api/v1/ai/knowledge/bases/list", headers=auth_headers).json()["data"]
    assert all(b["id"] != kb_id for b in lst2)


def test_ingest_and_search(test_client, auth_headers, monkeypatch):
    """入库→分块→检索：嵌入被 mock，按余弦命中相关分块。"""
    from app.plugin.module_ai.knowledge import embedding

    kb_id = _create_base(test_client, auth_headers)

    # mock 嵌入：按关键词直接返回可区分向量，保证检索可控
    async def _embed(texts, model_id=None):
        vecs = []
        for t in texts:
            v = [0.0] * 8
            if "智能体" in t:
                v[0] = 1.0
            elif "传感器" in t:
                v[1] = 1.0
            vecs.append(v)
        return vecs

    monkeypatch.setattr(embedding, "embed_texts", _embed)

    try:
        # 入库两段文本
        r1 = test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/ingest",
            json={"file_name": "a.txt", "content": "这是一个关于智能体编排的说明。"},
            headers=auth_headers,
        )
        assert r1.status_code == 200, r1.text
        assert r1.json()["data"]["chunks"] >= 1

        chunks = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"]
        assert len(chunks) >= 1
        assert chunks[0]["dimension"] == 8

        # 检索"智能体"应命中第一段
        search = test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/search",
            json={"query": "智能体", "top_k": 3},
            headers=auth_headers,
        ).json()["data"]
        assert search, "应检索到结果"
        assert "智能体" in search[0]["content"]
    finally:
        _delete_base(test_client, auth_headers, [kb_id])


def test_datasource_crud(test_client, auth_headers):
    r = test_client.post(
        "/api/v1/ai/knowledge/datasources/create",
        json={
            "name": _new_name("pytest_ds"),
            "ds_type": "api",
            "uri": "http://example.com/api",
            "api_config": {"method": "GET", "data_path": "data"},
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    ds_id = r.json()["data"]["id"]
    try:
        lst = test_client.get(
            "/api/v1/ai/knowledge/datasources/list", headers=auth_headers
        ).json()["data"]
        assert any(d["id"] == ds_id for d in lst)

        upd = test_client.put(
            f"/api/v1/ai/knowledge/datasources/update/{ds_id}",
            json={"name": "pytest_ds_updated"},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["data"]["name"] == "pytest_ds_updated"
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/knowledge/datasources/delete", json=[ds_id], headers=auth_headers
        )

    lst2 = test_client.get(
        "/api/v1/ai/knowledge/datasources/list", headers=auth_headers
    ).json()["data"]
    assert all(d["id"] != ds_id for d in lst2)


def test_knowledge_graphrag(test_client, auth_headers):
    """入库后生成图谱，/graph 应返回实体与关系，检索带 graph_entity 标记。"""
    kb_id = _create_base(test_client, auth_headers)
    try:
        test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/ingest",
            json={"file_name": "a.txt",
                  "content": "人工智能与机器学习密切相关，机器学习用于智能体编排。智能体和机器学习都涉及算法。"},
            headers=auth_headers,
        )
        g = test_client.get(f"/api/v1/ai/knowledge/bases/{kb_id}/graph", headers=auth_headers).json()["data"]
        assert g["nodes"], "应生成图谱节点"
        assert g["edges"] is not None
        # 检索开启图扩展（GraphRAG 路径不报错）
        res = test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/search",
            json={"query": "人工智能", "top_k": 3, "use_graph": True},
            headers=auth_headers,
        ).json()["data"]
        assert res, "应检索到结果"
    finally:
        _delete_base(test_client, auth_headers, [kb_id])


def test_kb_quality_returns_200(test_client, auth_headers):
    """质量接口：字段名修正后必须可用，并给出父块计数与需重建标记。"""
    kb_id = _create_base(test_client, auth_headers)
    try:
        test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/ingest",
            json={"file_name": "q.txt", "content": "知识库质量接口回归测试内容"},
            headers=auth_headers,
        )
        r = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/quality", headers=auth_headers
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["chunks"] >= 1
        assert data["parents"] == 0
        assert 0.0 <= data["embedded_rate"] <= 1.0
        assert isinstance(data["needs_rebuild"], bool)
        assert data["score"] >= 0.0
        assert isinstance(data["statuses"], dict)
    finally:
        _delete_base(test_client, auth_headers, [kb_id])


def test_delete_document_cascades_chunks(test_client, auth_headers):
    """删除文档必须级联清掉它的分块，否则孤儿分块会继续被检索命中。"""
    kb_id = _create_base(test_client, auth_headers)
    try:
        up = test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/documents/upload",
            files={"file": ("del.txt", b"delete me content for cascade", "text/plain")},
            data={"chunk_size": "100", "overlap": "0", "strategy": "fixed"},
            headers=auth_headers,
        )
        assert up.status_code == 200, up.text
        doc_id = up.json()["data"]["id"]

        before = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"]
        assert before, "上传后应有分块"

        d = test_client.delete(
            f"/api/v1/ai/knowledge/bases/{kb_id}/documents/{doc_id}", headers=auth_headers
        )
        assert d.status_code == 200, d.text
        assert d.json()["data"]["chunks"] == len(before)

        after = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/chunks", headers=auth_headers
        ).json()["data"]
        assert [c for c in after if c.get("document_id") == doc_id] == []
        assert after == [], "该库仅有此文档，删除后不应残留分块"
    finally:
        _delete_base(test_client, auth_headers, [kb_id])
