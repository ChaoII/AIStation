"""Agno 原生 Embedder：对接项目配置的 OpenAI 兼容嵌入模型。

说明：项目以 Agno 为 AI 运行时框架，向量化应走 Agno 的 ``Embedder`` 抽象，
而不是各模块手写 httpx。本类在 ``create`` 时异步解析嵌入模型配置并缓存在
实例上，``get_embedding`` 则用**同步** httpx 调用（Agno 的 Knowledge/PgVector
是同步检索，不能在运行中的事件循环里再 ``run_until_complete``）。
"""
from __future__ import annotations

import asyncio
from typing import Any

from agno.knowledge.embedder import Embedder


class SmbsEmbedder(Embedder):
    """基于 OpenAI 兼容 ``/v1/embeddings`` 的 Agno Embedder。"""

    def __init__(self, runtime: dict | None = None, dimensions: int = 2560,
                 model_id: int | None = None, **kw: Any):
        super().__init__(dimensions=dimensions, **kw)
        self._runtime = runtime
        self.model_id = model_id

    @staticmethod
    async def _fetch_runtime(model_id: int | None) -> dict | None:
        from app.plugin.module_ai.models.service import AiModelService

        runtime = await AiModelService.get_runtime_model(usage="embedding")
        if runtime is None and model_id is not None:
            runtime = await AiModelService.get_runtime_model(model_id=model_id)
        return runtime

    @classmethod
    async def create(cls, model_id: int | None = None, dimensions: int = 2560) -> SmbsEmbedder:
        runtime = await cls._fetch_runtime(model_id)
        return cls(runtime=runtime, dimensions=dimensions, model_id=model_id)

    def _headers(self) -> dict:
        from app.plugin.module_ai.models.service import build_headers

        base = (self._runtime or {}).get("base_url") or ""
        return {
            "Authorization": f"Bearer {(self._runtime or {}).get('api_key') or 'sk-none'}",
            **build_headers(base, (self._runtime or {}).get("extra_headers"), "aistation-rag"),
        }

    def _url(self) -> str:
        return f"{(self._runtime or {}).get('base_url', '').rstrip('/')}/embeddings"

    def _embed_list(self, texts: list[str]) -> list[list[float]]:
        import httpx

        resp = httpx.post(
            self._url(),
            headers=self._headers(),
            json={"model": (self._runtime or {}).get("model"), "input": texts},
            timeout=60,
        )
        resp.raise_for_status()
        return [item["embedding"] for item in resp.json()["data"]]

    def get_embedding(self, text: str) -> list[float]:
        return self._embed_list([text])[0]

    def get_embedding_and_usage(self, text: str) -> tuple[list[float], dict | None]:
        return self.get_embedding(text), None

    async def async_get_embedding(self, text: str) -> list[float]:
        return await asyncio.to_thread(self.get_embedding, text)

    async def async_get_embedding_and_usage(self, text: str) -> tuple[list[float], dict | None]:
        return await self.async_get_embedding(text), None
