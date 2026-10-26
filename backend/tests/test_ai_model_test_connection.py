"""`test_connection` 必须按模型用途(usage)分流到正确的连通性探测端点。

回归守卫：此前无论用途如何，`test_connection` 都固定走 `chat.completions`，
导致 embedding / rerank / tts / asr 模型用聊天补全去测试，接口对不上、结果无意义。
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.plugin.module_ai.models.schema import AiModelTestSchema
from app.plugin.module_ai.models.service import AiModelService


class _OpenAIRec:
    """记录 AsyncOpenAI 各端点调用并返回预置结果。"""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def _make(self, key):
        async def create(**kwargs):
            self.calls.append((key, kwargs))
            if key == "chat.completions":
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="pong"))]
                )
            if key == "embeddings":
                return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])
            return b"bytes"

        return create

    def build_client(self):
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=self._make("chat.completions"))
            ),
            embeddings=SimpleNamespace(create=self._make("embeddings")),
            audio=SimpleNamespace(
                speech=SimpleNamespace(create=self._make("audio.speech")),
                transcriptions=SimpleNamespace(create=self._make("audio.transcriptions")),
            ),
        )


class _HttpxRec:
    def __init__(self):
        self.posts: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"results": [{"index": 0, "relevance_score": 0.9}]},
        )


@pytest.fixture
def openai_rec(monkeypatch):
    rec = _OpenAIRec()
    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", lambda **kw: rec.build_client())
    return rec


@pytest.fixture
def httpx_rec(monkeypatch):
    rec = _HttpxRec()
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: rec)
    return rec


def _schema(usage: str):
    return AiModelTestSchema(
        base_url="http://test.local/v1",
        api_key="sk-test",
        model="model-x",
        usage=usage,
    )


def test_chat_routes_to_chat_completions(openai_rec):
    res = asyncio.run(AiModelService.test_connection(_schema("chat")))
    assert openai_rec.calls[0][0] == "chat.completions"
    assert openai_rec.calls[0][1]["messages"][0]["content"] == "ping，请只回复 pong"
    assert res["ok"] is True
    assert res["reply"] == "pong"


def test_embedding_routes_to_embeddings(openai_rec):
    res = asyncio.run(AiModelService.test_connection(_schema("embedding")))
    assert openai_rec.calls[0][0] == "embeddings"
    assert res["reply"] == "3 维"


def test_rerank_routes_to_rerank(httpx_rec):
    asyncio.run(AiModelService.test_connection(_schema("rerank")))
    assert httpx_rec.posts, "rerank 应调用 /rerank 端点"
    url, kwargs = httpx_rec.posts[0]
    assert url == "http://test.local/v1/rerank"
    assert kwargs["json"]["model"] == "model-x"
    assert kwargs["json"]["query"] == "ping"


def test_tts_routes_to_audio_speech(httpx_rec):
    res = asyncio.run(AiModelService.test_connection(_schema("tts")))
    assert httpx_rec.posts, "tts 应调用 /audio/speech 端点"
    assert httpx_rec.posts[0][0] == "http://test.local/v1/audio/speech"
    assert res["ok"] is True


def test_asr_routes_to_audio_transcriptions(httpx_rec):
    res = asyncio.run(AiModelService.test_connection(_schema("asr")))
    assert httpx_rec.posts, "asr 应调用 /audio/transcriptions 端点"
    assert httpx_rec.posts[0][0] == "http://test.local/v1/audio/transcriptions"
    assert res["ok"] is True


def test_usage_resolved_from_saved_model(openai_rec):
    """带 id 且省略 usage 时，应取已保存配置的 usage 决定测试端点。"""
    from app.core.database import async_db_session
    from app.plugin.module_ai.models.model import AiModelModel

    async def setup():
        async with async_db_session.begin() as db:
            m = AiModelModel(
                name="pytest-usage-model",
                base_url="http://t.local/v1",
                api_key="sk-aaaaaaaaaaaa",
                model="emb-model",
                usage="embedding",
            )
            db.add(m)
            await db.flush()
            return m.id

    mid = asyncio.run(setup())
    try:
        res = asyncio.run(AiModelService.test_connection(AiModelTestSchema(id=mid)))
        assert res["ok"] is True
        assert openai_rec.calls[0][0] == "embeddings"
    finally:

        async def cleanup():
            async with async_db_session.begin() as db:
                m = await db.get(AiModelModel, mid)
                if m:
                    await db.delete(m)

        asyncio.run(cleanup())
