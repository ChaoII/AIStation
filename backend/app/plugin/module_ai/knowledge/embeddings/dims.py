"""嵌入模型解析与维度预检。

- ``resolve_embedder``：按知识库/全局配置解析出 OpenAI 兼容端点（走既有
  ``AiModelService`` + ``build_headers``，不新造一套配置读取）。
- ``get_dimension``：探测真实维度并**进程内缓存**，避免每次入库都打一次网络。
- ``verify_dimension``：维度不一致直接报错（不再静默截断/补零）。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..config import rag_config

#: 维度探测缓存：``"{base_url}|{model}" -> dim``
_DIM_CACHE: dict[str, int] = {}


class EmbeddingDimensionError(RuntimeError):
    """嵌入向量维度与知识库内既有向量不一致。"""


@dataclass(frozen=True)
class ResolvedEmbedder:
    """解析后的嵌入端点配置。"""

    base_url: str
    api_key: str
    model: str
    headers: dict[str, str]
    timeout: float


async def resolve_embedder(model_id: int | None = None) -> ResolvedEmbedder:
    """解析嵌入模型端点。

    给定 ``model_id`` 时按该模型解析；否则取 ``usage="embedding"`` 的模型。
    解析不到时抛 ``RuntimeError``（调用方据此报错，而不是静默降级）。
    """
    from app.plugin.module_ai.models.service import AiModelService, build_headers

    runtime = (
        await AiModelService.get_runtime_model(model_id=model_id)
        if model_id is not None
        else await AiModelService.get_runtime_model(usage="embedding")
    )
    if not runtime:
        runtime = await AiModelService.get_runtime_model(model_id=model_id)
    if not runtime:
        raise RuntimeError("未配置嵌入模型")
    base = str(runtime.get("base_url") or "").rstrip("/")
    headers = build_headers(base, runtime.get("extra_headers"), "aistation-rag") or {}
    return ResolvedEmbedder(
        base_url=base,
        api_key=str(runtime.get("api_key") or "sk-none"),
        model=str(runtime["model"]),
        headers=dict(headers),
        timeout=float(rag_config.embed_timeout),
    )


async def _probe_dimension(resolved: ResolvedEmbedder) -> int:
    """真实调用一次 ``/embeddings`` 取维度。"""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        base_url=resolved.base_url,
        api_key=resolved.api_key,
        default_headers=resolved.headers or None,
        timeout=resolved.timeout,
        max_retries=2,
    )
    resp = await client.embeddings.create(model=resolved.model, input=["ping"])
    return len(resp.data[0].embedding)


async def get_dimension(model_id: int | None = None) -> int:
    """探测（并缓存）嵌入模型输出维度。"""
    resolved = await resolve_embedder(model_id)
    key = f"{resolved.base_url}|{resolved.model}"
    cached = _DIM_CACHE.get(key)
    if cached:
        return cached
    dim = int(await _probe_dimension(resolved))
    _DIM_CACHE[key] = dim
    return dim


async def verify_dimension(expected: int, model_id: int | None = None) -> int:
    """校验模型维度与预期一致，不一致抛 :class:`EmbeddingDimensionError`。"""
    actual = await get_dimension(model_id)
    if int(actual) != int(expected):
        raise EmbeddingDimensionError(
            f"嵌入模型维度与知识库不一致：库内向量 {int(expected)} 维，"
            f"当前模型输出 {actual} 维；请重建索引或改回原模型"
        )
    return int(actual)


def reset_dim_cache() -> None:
    """清空维度缓存（测试与换模型后使用）。"""
    _DIM_CACHE.clear()
