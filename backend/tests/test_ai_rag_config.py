"""RAG 链路参数配置测试。"""
import importlib

from app.plugin.module_ai.knowledge import config


def test_defaults_match_spec():
    c = config.RagConfig()
    assert c.embed_batch == 32
    assert c.embed_max_chars == 3500
    assert c.embed_timeout == 30.0
    assert c.recall_mult == 4 and c.recall_min == 20
    assert c.rerank_candidates == 50
    assert c.rerank_timeout == 15.0
    assert c.context_tokens == 3000
    assert c.allow_hash_fallback is False
    assert c.rewrite == "off"
    assert c.task_poll_seconds == 3.0
    assert (c.hnsw_m, c.hnsw_ef_construction, c.hnsw_ef_search) == (16, 64, 100)
    assert c.pipeline_v2 is True


def test_env_override(monkeypatch):
    monkeypatch.setenv("RAG_EMBED_BATCH", "8")
    monkeypatch.setenv("RAG_ALLOW_HASH_FALLBACK", "true")
    monkeypatch.setenv("RAG_REWRITE", "hyde")
    importlib.reload(config)
    assert config.rag_config.embed_batch == 8
    assert config.rag_config.allow_hash_fallback is True
    assert config.rag_config.rewrite == "hyde"
    monkeypatch.undo()
    importlib.reload(config)


def test_invalid_rewrite_falls_back_to_off(monkeypatch):
    monkeypatch.setenv("RAG_REWRITE", "不存在的模式")
    importlib.reload(config)
    assert config.rag_config.rewrite == "off"
    monkeypatch.undo()
    importlib.reload(config)


def test_invalid_int_value_uses_default(monkeypatch):
    monkeypatch.setenv("RAG_RECALL_MULT", "abc")
    importlib.reload(config)
    assert config.rag_config.recall_mult == 4
    monkeypatch.undo()
    importlib.reload(config)
