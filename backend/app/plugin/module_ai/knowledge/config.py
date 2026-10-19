"""RAG 检索链路可调参数。

环境变量优先，未配置时使用设计文档 §14 的默认值。集中在这里，
避免批量大小、召回倍数、rerank 候选数等魔法数字散落在各单元里。
"""
from __future__ import annotations

import os
from dataclasses import dataclass

_TRUE_VALUES = {"1", "true", "yes", "on"}
_REWRITE_VALUES = {"off", "multi_query", "hyde"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUE_VALUES


def _str(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip()


@dataclass(frozen=True)
class RagConfig:
    """RAG 链路参数（不可变，导入时读取一次环境变量）。"""

    # 嵌入
    embed_batch: int = 32
    embed_max_chars: int = 3500
    embed_timeout: float = 30.0
    allow_hash_fallback: bool = False
    # 召回与重排
    recall_mult: int = 4
    recall_min: int = 20
    rerank_candidates: int = 50
    rerank_timeout: float = 15.0
    context_tokens: int = 3000
    rewrite: str = "off"
    # 后台任务
    task_poll_seconds: float = 3.0
    # 向量索引（PG）
    hnsw_m: int = 16
    hnsw_ef_construction: int = 64
    hnsw_ef_search: int = 100
    # MinerU OCR（扫描件/图片）
    mineru_url: str = "http://172.168.100.146:8100/sse"
    mineru_backend: str = "pipeline"
    mineru_parse_method: str = "auto"
    mineru_lang_list: tuple[str, ...] = ("ch",)
    mineru_timeout: float = 1800.0
    # 管线开关（出问题可回退旧行为）
    pipeline_v2: bool = True


def _load() -> RagConfig:
    rewrite = _str("RAG_REWRITE", "off").lower()
    if rewrite not in _REWRITE_VALUES:
        rewrite = "off"
    return RagConfig(
        embed_batch=max(1, _int("RAG_EMBED_BATCH", 32)),
        embed_max_chars=max(1, _int("RAG_EMBED_MAX_CHARS", 3500)),
        embed_timeout=max(1.0, _float("RAG_EMBED_TIMEOUT", 30.0)),
        allow_hash_fallback=_bool("RAG_ALLOW_HASH_FALLBACK", False),
        recall_mult=max(1, _int("RAG_RECALL_MULT", 4)),
        recall_min=max(1, _int("RAG_RECALL_MIN", 20)),
        rerank_candidates=max(1, _int("RAG_RERANK_CANDIDATES", 50)),
        rerank_timeout=max(1.0, _float("RAG_RERANK_TIMEOUT", 15.0)),
        context_tokens=max(1, _int("RAG_CONTEXT_TOKENS", 3000)),
        rewrite=rewrite,
        task_poll_seconds=max(0.1, _float("RAG_TASK_POLL", 3.0)),
        hnsw_m=max(2, _int("RAG_HNSW_M", 16)),
        hnsw_ef_construction=max(1, _int("RAG_HNSW_EF_CONSTRUCTION", 64)),
        hnsw_ef_search=max(1, _int("RAG_HNSW_EF_SEARCH", 100)),
        mineru_url=_str("MINERU_MCP_URL", "http://172.168.100.146:8100/sse"),
        mineru_backend=_str("MINERU_BACKEND", "pipeline"),
        mineru_parse_method=_str("MINERU_PARSE_METHOD", "auto"),
        mineru_lang_list=tuple(
            part.strip() for part in _str("MINERU_LANG_LIST", "ch").split(",") if part.strip()
        ) or ("ch",),
        mineru_timeout=max(1.0, _float("MINERU_TIMEOUT", 1800.0)),
        pipeline_v2=_bool("RAG_PIPELINE_V2", True),
    )


rag_config: RagConfig = _load()
