"""Rerank：把融合后的候选交给网关 ``/rerank`` 做跨编码器精排。

降级策略：未配置模型 / 超时 / 非 200 → ``status="skipped"``，保持原顺序并截断，
主链路不受影响（日志里能看到 ``rerank=skipped``，不做「假重排」）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from app.core.logger import log

from ..config import rag_config


@dataclass(frozen=True)
class ResolvedRerank:
    base_url: str
    api_key: str
    headers: dict
    model: str


@dataclass
class RerankOutcome:
    items: list[dict] = field(default_factory=list)
    status: str = "skipped"  # applied | skipped | empty


async def resolve_rerank(*, model_id: int | None = None) -> ResolvedRerank:
    """解析 rerank 端点：优先 ``usage=rerank`` 模型，否则复用嵌入模型端点。"""
    from app.plugin.module_ai.models.service import AiModelService, build_headers

    runtime = await AiModelService.get_runtime_model(usage="rerank")
    if not runtime:
        from ..embeddings.dims import resolve_embedder

        resolved = await resolve_embedder(model_id)
        return ResolvedRerank(
            base_url=resolved.base_url,
            api_key=resolved.api_key,
            headers=resolved.headers,
            model=resolved.model,
        )
    base_url = str(runtime.get("base_url") or "").rstrip("/")
    headers = build_headers(base_url, runtime.get("extra_headers"), "aistation-rerank") or {}
    return ResolvedRerank(
        base_url=base_url,
        api_key=str(runtime.get("api_key") or "sk-none"),
        headers=dict(headers),
        model=str(runtime["model"]),
    )


async def _post_rerank(
    base_url: str,
    api_key: str,
    headers: dict,
    model: str,
    query: str,
    documents: list[str],
    top_n: int,
) -> list[dict]:
    """调用 OpenAI 兼容 ``/rerank``，返回 ``[{index, relevance_score}]``。"""
    async with httpx.AsyncClient(timeout=float(rag_config.rerank_timeout)) as client:
        response = await client.post(
            f"{base_url}/rerank",
            headers={"Authorization": f"Bearer {api_key}", **(headers or {})},
            json={"model": model, "query": query, "documents": documents, "top_n": top_n},
        )
        response.raise_for_status()
        payload = response.json()
    results = payload.get("results") or []
    return [
        {"index": int(item["index"]), "relevance_score": float(item["relevance_score"])}
        for item in results
        if "index" in item and "relevance_score" in item
    ]


async def rerank(
    query: str,
    candidates: list[dict],
    top_n: int,
    *,
    model_id: int | None = None,
) -> RerankOutcome:
    """对候选做精排；失败时降级为原顺序截断。"""
    if not candidates:
        return RerankOutcome(items=[], status="empty")
    limited = candidates[: max(1, int(top_n))]
    try:
        resolved = await resolve_rerank(model_id=model_id)
        ranked = await _post_rerank(
            resolved.base_url,
            resolved.api_key,
            resolved.headers,
            resolved.model,
            query,
            [str(item.get("content") or "") for item in candidates],
            len(candidates),
        )
    except Exception as e:  # noqa: BLE001
        log.warning(f"[RAG] rerank 跳过（{type(e).__name__}: {e}）")
        return RerankOutcome(items=limited, status="skipped")

    by_index = {int(item["index"]): float(item["relevance_score"]) for item in ranked}
    if not by_index:
        return RerankOutcome(items=limited, status="skipped")

    decorated: list[dict] = []
    for index, item in enumerate(candidates):
        if index not in by_index:
            continue
        decorated.append({**item, "rerank_score": round(by_index[index], 4)})
    decorated.sort(key=lambda item: item["rerank_score"], reverse=True)
    return RerankOutcome(items=decorated[: max(1, int(top_n))], status="applied")
