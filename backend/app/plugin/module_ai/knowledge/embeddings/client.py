"""嵌入客户端：批量、超时、重试、长文本分片、进程内缓存。

约束（AGENTS.md）：AI 调用一律走 agno，因此实际请求仍由
``agno.knowledge.embedder.openai_like.OpenAILikeEmbedder`` 发出；本模块只负责
调用前后的工程逻辑（分批、分片、缓存、失败策略）。

失败策略：
- 批量失败 → 降级逐条（第一条仍失败则立即抛出，避免 N 次无效重试）；
- 最终失败 → ``allow_hash_fallback`` 为真才用确定性哈希向量，否则抛出，
  由调用方（入库任务）把错误暴露出来，不再静默产出废向量。
"""
from __future__ import annotations

import hashlib
import math
import os
import time

from app.core.logger import log

from .. import config as _cfg
from .cache import embedding_cache
from .dims import ResolvedEmbedder, resolve_embedder

#: 回退哈希向量维度（与历史实现保持一致）
FALLBACK_DIM = 256
#: 知识库向量入库的统一维度（``smbs/Embedding-4B`` 实测 2560）
EMBED_DIM = 2560

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _allow_fallback() -> bool:
    """运行期读取回退开关（便于测试/运维不重启就切换）。"""
    raw = os.getenv("RAG_ALLOW_HASH_FALLBACK")
    if raw is None or not raw.strip():
        return bool(_cfg.rag_config.allow_hash_fallback)
    return raw.strip().lower() in _TRUE_VALUES


def _split_long(value: str, limit: int | None = None) -> list[str]:
    """超长文本按字符窗切分（避免网关拒绝超长输入）。"""
    limit = int(limit or _cfg.rag_config.embed_max_chars)
    if limit <= 0 or len(value) <= limit:
        return [value]
    return [value[i : i + limit] for i in range(0, len(value), limit)]


def _mean_norm(vectors: list[list[float]]) -> list[float]:
    """多片向量取均值后 L2 归一化，作为整块向量。"""
    if not vectors:
        return []
    if len(vectors) == 1:
        return list(vectors[0])
    dim = len(vectors[0])
    acc = [0.0] * dim
    for vec in vectors:
        for i in range(min(dim, len(vec))):
            acc[i] += float(vec[i])
    count = float(len(vectors))
    acc = [x / count for x in acc]
    norm = math.sqrt(sum(x * x for x in acc))
    if norm <= 0:
        return acc
    return [x / norm for x in acc]


async def _embed_batch(texts: list[str], model_id: int | None = None) -> list[list[float]]:
    """批量嵌入（agno 客户端；批量失败逐条降级）。"""
    if not texts:
        return []
    resolved = await resolve_embedder(model_id)
    from agno.knowledge.embedder.openai_like import OpenAILikeEmbedder
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        default_headers=resolved.headers or None,
        timeout=resolved.timeout,
        max_retries=2,
    )
    embedder = OpenAILikeEmbedder(id=resolved.model, async_client=client)
    out: list[list[float]] = []
    batch = max(1, int(_cfg.rag_config.embed_batch))
    for start in range(0, len(texts), batch):
        part = texts[start : start + batch]
        try:
            vectors, _usage = await embedder.async_get_embeddings_batch_and_usage(part)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[RAG] 批量嵌入失败，降级逐条（{len(part)} 条）：{e}")
            first, _u = await embedder.async_get_embeddings_batch_and_usage([part[0]])
            vectors = list(first)
            for text in part[1:]:
                one, _u = await embedder.async_get_embeddings_batch_and_usage([text])
                vectors.extend(one)
        out.extend([[float(x) for x in vec] for vec in vectors])
    return out


def _hash_embed(text: str) -> list[float]:
    """确定性特征哈希向量（仅在允许回退时使用）。"""
    vec = [0.0] * FALLBACK_DIM
    for token in _tokenize(text):
        digest = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        vec[digest % FALLBACK_DIM] += 1.0 if (digest >> 8) % 2 == 0 else -1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm <= 0:
        return vec
    return [x / norm for x in vec]


def _tokenize(text: str) -> list[str]:
    """jieba 分词 + 2-gram（jieba 不可用时退回正则切分）。"""
    import re

    tokens: list[str] = []
    try:
        import jieba

        for word in jieba.cut(text or ""):
            word = word.strip()
            if word and re.search(r"[\w\u4e00-\u9fa5]", word):
                tokens.append(word)
    except Exception:  # noqa: BLE001
        tokens = [p for p in re.split(r"[\s\W_]+", text or "", flags=re.UNICODE) if p]
    compact = "".join(tokens)
    for i in range(len(compact) - 1):
        tokens.append(compact[i : i + 2])
    return tokens


#: 兼容历史私有名
hash_embed = _hash_embed


async def embed_texts_with_stats(
    texts: list[str], model_id: int | None = None
) -> tuple[list[list[float]], dict]:
    """嵌入文本并返回统计信息（模型/维度/批次数/缓存命中/耗时）。"""
    started = time.perf_counter()
    if not texts:
        return [], {"model": "", "dim": 0, "batches": 0, "cache_hits": 0, "ms": 0.0}

    model_name = "unknown"
    try:
        model_name = (await resolve_embedder(model_id)).model
    except Exception:  # noqa: BLE001
        model_name = "unknown"

    result: list[list[float] | None] = [embedding_cache.get(model_name, t) for t in texts]
    cache_hits = sum(1 for item in result if item is not None)
    pending = [(i, t) for i, (t, item) in enumerate(zip(texts, result, strict=False)) if item is None]

    batches = 0
    if pending:
        flattened: list[tuple[int, str]] = []
        for index, text in pending:
            for piece in _split_long(text):
                flattened.append((index, piece))
        batches = max(1, math.ceil(len(flattened) / max(1, int(_cfg.rag_config.embed_batch))))
        try:
            vectors = await _embed_batch([piece for _, piece in flattened], model_id)
        except Exception as e:  # noqa: BLE001
            if not _allow_fallback():
                raise RuntimeError(
                    f"嵌入失败（model={model_name}，共 {len(flattened)} 片）：{e}"
                ) from e
            log.warning(f"[RAG] 嵌入失败，按开关启用哈希回退：{e}")
            vectors = [_hash_embed(piece) for _, piece in flattened]
        if len(vectors) != len(flattened):
            raise RuntimeError(
                f"嵌入返回数量不匹配：请求 {len(flattened)} 片，返回 {len(vectors)} 片"
            )
        grouped: dict[int, list[list[float]]] = {}
        for (index, _piece), vec in zip(flattened, vectors, strict=False):
            grouped.setdefault(index, []).append(vec)
        for index, pieces in grouped.items():
            merged = _mean_norm(pieces)
            result[index] = merged
            embedding_cache.put(model_name, texts[index], merged)

    missing = [i for i, item in enumerate(result) if not item]
    if missing:  # pragma: no cover - 理论上不会发生
        raise RuntimeError(f"嵌入结果缺失：索引 {missing}")

    final = [item or [] for item in result]
    stats = {
        "model": model_name,
        "dim": len(final[0]) if final else 0,
        "batches": batches,
        "cache_hits": cache_hits,
        "ms": round((time.perf_counter() - started) * 1000, 1),
    }
    return final, stats


async def embed_texts(texts: list[str], model_id: int | None = None) -> list[list[float]]:
    """嵌入文本列表（薄封装，保持历史签名）。"""
    vectors, _stats = await embed_texts_with_stats(texts, model_id)
    return vectors


async def embed_query(text: str, model_id: int | None = None) -> list[float]:
    """嵌入单条查询。"""
    vectors = await embed_texts([text], model_id)
    return vectors[0] if vectors else []


async def current_model_name(model_id: int | None = None) -> str | None:
    """当前嵌入模型名（解析不到返回 None，供换模型失效判定）。"""
    try:
        resolved: ResolvedEmbedder = await resolve_embedder(model_id)
        return resolved.model
    except Exception:  # noqa: BLE001
        return None
