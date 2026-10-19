"""嵌入链路兼容门面（历史导入路径 ``knowledge.embedding``）。

实际实现已拆分到 ``knowledge/embeddings/``；本模块只做转发，保证：
- ``service`` / ``query`` 等既有调用点，以及测试里的
  ``monkeypatch.setattr(embedding, "embed_texts", ...)`` 继续有效；
- 取消旧的「静默截断补零 + 静默哈希降级」——失败会抛出，除非显式开启回退。
"""
from __future__ import annotations

from .embeddings.client import (  # noqa: F401  （兼容导出）
    EMBED_DIM,
    FALLBACK_DIM,
    _hash_embed,
    _tokenize,
    current_model_name,
    embed_query,
    embed_texts,
    embed_texts_with_stats,
    hash_embed,
)
from .embeddings.dims import (  # noqa: F401  （兼容导出）
    EmbeddingDimensionError,
    get_dimension,
    resolve_embedder,
    verify_dimension,
)

__all__ = [
    "EMBED_DIM",
    "FALLBACK_DIM",
    "EmbeddingDimensionError",
    "current_model_name",
    "embed_query",
    "embed_texts",
    "embed_texts_with_stats",
    "get_dimension",
    "hash_embed",
    "resolve_embedder",
    "verify_dimension",
]
