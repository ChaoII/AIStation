"""知识分块嵌入：优先走 OpenAI 兼容 ``/embeddings``，失败回退确定性哈希向量。

回退向量用于离线 / 无嵌入模型 / 测试环境，保证 RAG 流水线始终可运行；
生产建议配置真正的 embedding 模型以提升语义召回质量。
"""
from __future__ import annotations

import hashlib
import math

#: 回退哈希向量的固定维度
FALLBACK_DIM = 256


async def embed_texts(texts: list[str], model_id: int | None = None) -> list[list[float]]:
    """把文本列表转为向量列表。

    优先用知识库配置的嵌入模型（OpenAI 兼容 ``/embeddings``）；
    任意环节失败则回退为确定性哈希向量（特征哈希 + L2 归一化）。
    """
    if not texts:
        return []
    try:
        vectors = await _embed_openai(texts, model_id)
        if vectors and any(v for v in vectors):
            return vectors
    except Exception:  # noqa: BLE001
        pass
    return [_hash_embed(t) for t in texts]


async def _embed_openai(texts: list[str], model_id: int | None) -> list[list[float]]:
    from app.plugin.module_ai.provider.service import (
        AiModelService,
        build_headers,
    )

    runtime = await AiModelService.get_runtime_model(model_id=model_id)
    if not runtime:
        raise RuntimeError("未配置嵌入模型")
    # 去掉 base_url 尾部斜杠，统一拼接 /embeddings
    base = runtime["base_url"].rstrip("/")
    url = f"{base}/embeddings"
    import httpx

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {runtime.get('api_key') or 'sk-none'}",
                **build_headers(base, runtime.get("extra_headers"), "aistation-rag"),
            },
            json={"model": runtime["model"], "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]


def _hash_embed(text: str) -> list[float]:
    """确定性特征哈希向量（bag-of-words 哈希 + 符号 + L2 归一化）。

    语义质量有限，但可移植、无需模型，保证检索链路可用。
    """
    vec = [0.0] * FALLBACK_DIM
    tokens = _tokenize(text)
    for tok in tokens:
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        idx = h % FALLBACK_DIM
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm <= 0.0:
        return vec
    return [v / norm for v in vec]


def _tokenize(text: str) -> list[str]:
    """简易分词：按非字母数字切分，也保留连续的中文子串。"""
    import re

    parts = re.split(r"[\s\W_]+", text or "", flags=re.UNICODE)
    tokens = [p for p in parts if p]
    # 补充 2-gram 以增强中文本地性
    compact = "".join(tokens)
    for i in range(len(compact) - 1):
        tokens.append(compact[i : i + 2])
    return tokens
