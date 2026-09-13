"""AI 助手的 AI SDK UI Message Stream 协议与调用日志落库。"""
import asyncio
import json
from types import SimpleNamespace

from app.plugin.module_ai.assistant.service import extract_openai_messages


def test_extract_openai_messages():
    """只取 user/assistant 的 text part，忽略其他 role 与 part，保留多轮。"""
    ui = [
        {
            "role": "user",
            "parts": [
                {"type": "text", "text": "你好"},
                {"type": "file", "url": "http://x/a.png"},
            ],
        },
        {
            "role": "assistant",
            "parts": [
                {"type": "text", "text": "在的"},
                {"type": "tool-navigate", "state": "output-available"},
            ],
        },
        {"role": "system", "parts": [{"type": "text", "text": "应忽略"}]},
        {"role": "user", "parts": [{"type": "text", "text": ""}]},
    ]
    out = extract_openai_messages(ui)
    assert out == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "在的"},
    ]
    assert extract_openai_messages([]) == []
    assert extract_openai_messages(None) == []


class _FakeDelta:
    def __init__(self, content=None, reasoning_content=None, tool_calls=None):
        self.content = content
        self.reasoning_content = reasoning_content
        self.tool_calls = tool_calls


class _FakeChunk:
    def __init__(self, delta):
        self.choices = [SimpleNamespace(delta=delta)]


class _FakeFunctionDelta:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _FakeToolCallDelta:
    def __init__(self, name, args, index=0, call_id="call_1"):
        self.index = index
        self.id = call_id
        self.function = _FakeFunctionDelta(name, json.dumps(args))


def _make_stream_client(rounds):
    """构造假 AsyncOpenAI：create(stream=True) 每轮返回一个异步生成器。"""

    class _Completions:
        def __init__(self):
            self.calls = 0

        async def create(self, **kwargs):
            chunks = rounds[self.calls]
            self.calls += 1

            async def _gen():
                for c in chunks:
                    yield c

            return _gen()

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _Client:
        def __init__(self, *a, **k):
            self.chat = _Chat()

    return _Client


def _patch_runtime(monkeypatch):
    from app.plugin.module_ai.provider.service import AiModelService

    async def _runtime(usage=None, model_id=None):
        return {
            "base_url": "http://x",
            "api_key": "k",
            "model": "m",
            "temperature": 0.1,
            "max_tokens": 64,
        }

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))


def test_ui_stream_reasoning_and_text(monkeypatch, test_client, auth_headers):
    import openai

    rounds = [
        [
            _FakeChunk(_FakeDelta(reasoning_content="思考中")),
            _FakeChunk(_FakeDelta(content="你好")),
            _FakeChunk(_FakeDelta(content="世界")),
        ]
    ]
    monkeypatch.setattr(openai, "AsyncOpenAI", _make_stream_client(rounds))
    _patch_runtime(monkeypatch)

    r = test_client.post(
        "/api/v1/ai/assistant/stream",
        json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "你好"}]}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert '"type": "reasoning-delta"' in body
    assert '"type": "text-delta"' in body
    assert '"type": "finish"' in body
    assert "data: [DONE]" in body
    assert r.headers["x-vercel-ai-ui-message-stream"] == "v1"


def test_ui_stream_tool_then_text(monkeypatch, test_client, auth_headers):
    import openai

    rounds = [
        [_FakeChunk(_FakeDelta(tool_calls=[_FakeToolCallDelta("navigate", {"path": "/ai/report", "reason": "t"})]))],
        [_FakeChunk(_FakeDelta(content="已为你打开报告页"))],
    ]
    monkeypatch.setattr(openai, "AsyncOpenAI", _make_stream_client(rounds))
    _patch_runtime(monkeypatch)

    r = test_client.post(
        "/api/v1/ai/assistant/stream",
        json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "打开报告页"}]}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert '"type": "tool-input-available"' in body
    assert '"type": "tool-output-available"' in body
    assert '"toolName": "navigate"' in body
    assert "data: [DONE]" in body


def test_add_log_persists_user_id(test_client, auth_headers):
    """回归：旧实现写不存在的 created_id 导致日志静默丢失。"""
    from sqlalchemy import select

    from app.core.database import async_db_session
    from app.plugin.module_ai.overview.model import AiCallLogModel
    from app.plugin.module_ai.overview.service import AiOverviewService

    asyncio.run(
        AiOverviewService.add_log("pytest-uilog", "chat", 12, "success", user_id=424242)
    )

    async def _count() -> int:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiCallLogModel).where(
                        AiCallLogModel.model_name == "pytest-uilog",
                        AiCallLogModel.user_id == 424242,
                    )
                )
            ).scalars().all()
            return len(rows)

    assert asyncio.run(_count()) >= 1
