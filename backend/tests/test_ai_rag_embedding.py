"""嵌入链路测试：模型解析、维度预检、缓存与降级。"""
import asyncio


def test_verify_dimension_raises_on_mismatch(monkeypatch):
    """维度不一致必须显式报错（不再静默截断/补零）。"""
    from app.plugin.module_ai.knowledge.embeddings import dims

    async def fake_probe(model_id=None):
        return 8

    monkeypatch.setattr(dims, "get_dimension", fake_probe)
    assert asyncio.run(dims.verify_dimension(8)) == 8
    try:
        asyncio.run(dims.verify_dimension(2560))
    except dims.EmbeddingDimensionError as e:
        assert "2560" in str(e) and "8" in str(e)
    else:  # pragma: no cover
        raise AssertionError("维度不符时应抛 EmbeddingDimensionError")


def test_get_dimension_caches_probe(monkeypatch):
    """维度探测只做一次（进程内缓存）。"""
    from app.plugin.module_ai.knowledge.embeddings import dims

    calls = {"n": 0}

    async def fake_resolve(model_id=None):
        return dims.ResolvedEmbedder(
            base_url="http://gw/v1", api_key="k", model="m", headers={}, timeout=1.0
        )

    async def fake_probe(resolved):
        calls["n"] += 1
        return 2560

    monkeypatch.setattr(dims, "resolve_embedder", fake_resolve)
    monkeypatch.setattr(dims, "_probe_dimension", fake_probe)
    dims.reset_dim_cache()
    assert asyncio.run(dims.get_dimension()) == 2560
    assert asyncio.run(dims.get_dimension()) == 2560
    assert calls["n"] == 1


def test_resolve_embedder_requires_model(monkeypatch):
    """没有可用嵌入模型时必须报错，而不是悄悄退化为哈希向量。"""
    from app.plugin.module_ai.knowledge.embeddings import dims

    async def no_model(**kwargs):
        return None

    monkeypatch.setattr(
        "app.plugin.module_ai.models.service.AiModelService.get_runtime_model", no_model
    )
    try:
        asyncio.run(dims.resolve_embedder())
    except RuntimeError as e:
        assert "未配置嵌入模型" in str(e)
    else:  # pragma: no cover
        raise AssertionError("无嵌入模型时应抛 RuntimeError")


def test_cache_dedupes_identical_texts(monkeypatch):
    """同一段文本第二次应命中缓存，不再打网关。"""
    from app.plugin.module_ai.knowledge.embeddings import cache, client

    cache.embedding_cache.clear()
    calls = {"n": 0}

    async def fake(texts, model_id=None):
        calls["n"] += 1
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(client, "_embed_batch", fake)
    v1 = asyncio.run(client.embed_texts(["同一段"]))
    v2 = asyncio.run(client.embed_texts(["同一段"]))
    assert v1 == v2 == [[1.0, 0.0]]
    assert calls["n"] == 1, "第二次应命中缓存"
    assert cache.embedding_cache.hits >= 1


def test_failure_raises_when_fallback_disabled(monkeypatch):
    """未开启回退时，嵌入失败必须抛出（不得静默产出哈希向量）。"""
    from app.plugin.module_ai.knowledge.embeddings import client

    async def boom(texts, model_id=None):
        raise TimeoutError("网关超时")

    monkeypatch.setattr(client, "_embed_batch", boom)
    monkeypatch.setenv("RAG_ALLOW_HASH_FALLBACK", "false")
    try:
        asyncio.run(client.embed_texts(["x"]))
    except RuntimeError as e:
        assert "嵌入失败" in str(e)
    else:  # pragma: no cover
        raise AssertionError("失败时应抛出 RuntimeError")


def test_failure_falls_back_to_hash_when_enabled(monkeypatch):
    """显式开启回退时，才允许用确定性哈希向量（维度 FALLBACK_DIM）。"""
    from app.plugin.module_ai.knowledge.embeddings import client

    async def boom(texts, model_id=None):
        raise TimeoutError("网关超时")

    monkeypatch.setattr(client, "_embed_batch", boom)
    monkeypatch.setenv("RAG_ALLOW_HASH_FALLBACK", "true")
    vectors = asyncio.run(client.embed_texts(["回退向量"]))
    assert len(vectors) == 1
    assert len(vectors[0]) == client.FALLBACK_DIM


def test_long_text_is_split_and_averaged(monkeypatch):
    """超长文本按 embed_max_chars 分片，向量取归一化均值。"""
    from app.plugin.module_ai.knowledge.embeddings import cache, client

    cache.embedding_cache.clear()
    seen: list[str] = []

    async def fake(texts, model_id=None):
        seen.extend(texts)
        # 每片给不同向量，均值应落在中间且模长为 1
        return [[1.0, 0.0] if i % 2 == 0 else [0.0, 1.0] for i in range(len(texts))]

    monkeypatch.setattr(client, "_embed_batch", fake)
    monkeypatch.setenv("RAG_EMBED_MAX_CHARS", "10")
    import importlib

    from app.plugin.module_ai.knowledge import config as cfg

    importlib.reload(cfg)
    vectors = asyncio.run(client.embed_texts(["A" * 25]))
    importlib.reload(cfg)
    assert len(seen) == 3, f"25 字符 / 每片 10 字符应切 3 片，实际 {seen}"
    assert len(vectors[0]) == 2
    assert abs(sum(x * x for x in vectors[0]) - 1.0) < 1e-6


def test_stats_report_cache_hits(monkeypatch):
    """统计信息应包含模型、维度、批次数与缓存命中。"""
    from app.plugin.module_ai.knowledge.embeddings import cache, client

    cache.embedding_cache.clear()

    async def fake(texts, model_id=None):
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(client, "_embed_batch", fake)
    _v1, s1 = asyncio.run(client.embed_texts_with_stats(["统计"]))
    _v2, s2 = asyncio.run(client.embed_texts_with_stats(["统计"]))
    assert s1["cache_hits"] == 0 and s2["cache_hits"] == 1
    assert s1["dim"] == 2 and s1["batches"] >= 1
    assert s1["ms"] >= 0.0


def test_model_change_marks_rebuild_needed(test_client, auth_headers, monkeypatch):
    """换嵌入模型后，质量接口必须提示「需要重建索引」。"""
    import uuid

    from app.plugin.module_ai.knowledge import embedding as emb

    async def fake_embed(texts, model_id=None):
        return [[1.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(emb, "embed_texts", fake_embed)
    kb_id = test_client.post(
        "/api/v1/ai/knowledge/bases/create",
        json={"name": f"pytest_rebuild_{uuid.uuid4().hex[:8]}", "enabled": True},
        headers=auth_headers,
    ).json()["data"]["id"]
    try:
        test_client.post(
            f"/api/v1/ai/knowledge/bases/{kb_id}/ingest",
            json={"file_name": "m.txt", "content": "换模型需要重建索引"},
            headers=auth_headers,
        )
        before = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/quality", headers=auth_headers
        ).json()["data"]
        assert before["needs_rebuild"] is False, before
        assert before["vector_model"]

        test_client.put(
            f"/api/v1/ai/knowledge/bases/update/{kb_id}",
            json={"model_id": 999999},
            headers=auth_headers,
        )
        after = test_client.get(
            f"/api/v1/ai/knowledge/bases/{kb_id}/quality", headers=auth_headers
        ).json()["data"]
        assert after["needs_rebuild"] is True, after
    finally:
        test_client.request(
            "DELETE",
            "/api/v1/ai/knowledge/bases/delete",
            json=[kb_id],
            headers=auth_headers,
        )
