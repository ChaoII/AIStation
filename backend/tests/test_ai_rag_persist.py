"""向量写入路径（唯一入口）纯逻辑测试。"""
from app.plugin.module_ai.knowledge.embeddings.persist import (
    build_search_text,
    chunk_hash,
    vector_literal,
)


def test_build_search_text_merges_annotations():
    assert build_search_text("正文", None) == "正文"
    assert build_search_text("正文", []) == "正文"
    assert build_search_text("正文", [{"text": "别名"}, {"kind": "note"}]) == "正文 别名"
    assert build_search_text("正文", [{"text": ""}, {"text": "第二"}]) == "正文 第二"


def test_vector_literal_formats_postgres_array():
    assert vector_literal([0.5, -1.0]) == "[0.5,-1.0]"
    assert vector_literal([]) == "[]"


def test_chunk_hash_is_stable_and_model_scoped():
    a = chunk_hash("同一段文本", "m1")
    assert a == chunk_hash("同一段文本", "m1")
    assert a != chunk_hash("同一段文本", "m2")
    assert a != chunk_hash("另一段文本", "m1")
    assert len(a) == 64
