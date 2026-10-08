"""Agno 原生事件流助手测试：验证统一工具注册 + Agno 原生 SSE 协议。"""
import asyncio


def _patch_runtime(monkeypatch):
    from app.plugin.module_ai.models.service import AiModelService

    async def _runtime(usage=None, model_id=None):
        return {
            "base_url": "http://x",
            "api_key": "k",
            "model": "m",
            "temperature": 0.1,
            "max_tokens": 64,
        }

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))


def _patch_build_agent(monkeypatch):
    """替换 build_agent，返回产出真实 Agno 事件对象的假 agent。"""
    from agno.run.agent import (
        RunCompletedEvent,
        RunContentEvent,
        RunStartedEvent,
        RunEvent,
    )

    async def _agen():
        yield RunStartedEvent(event=RunEvent.run_started.value, model="m")
        yield RunContentEvent(event=RunEvent.run_content.value, content="你好，来自 Agno")
        yield RunCompletedEvent(event=RunEvent.run_completed.value, content="你好，来自 Agno")

    class _FakeAgent:
        @property
        def tools(self):
            return []

        def arun(self, *a, **k):
            return _agen()

    import app.plugin.module_ai.agno_tools.agent_factory as af

    monkeypatch.setattr(af, "build_agent", lambda **k: _FakeAgent())


async def _collect(sse_frames):
    out = []
    async for f in sse_frames:
        out.append(f)
    return out


def test_run_agno_stream_emits_native_events(monkeypatch):
    """Agno 驱动产出含 RunContent 的原生 SSE 事件流。"""
    _patch_runtime(monkeypatch)
    _patch_build_agent(monkeypatch)

    from app.plugin.module_ai.assistant.agno_service import run_agno_stream

    msgs = [{"role": "user", "parts": [{"type": "text", "text": "你好"}]}]
    auth = type("A", (), {"user": type("U", (), {"id": 1})()})()
    frames = asyncio.run(_collect(run_agno_stream(messages=msgs, auth=auth, user_id=1)))
    joined = "".join(frames)
    assert "event: RunStarted" in joined
    assert "event: RunContent" in joined
    assert "你好，来自 Agno" in joined
    assert "event: RunCompleted" in joined


def test_business_tools_registered_in_agent(monkeypatch):
    """Agent 工厂装配的业务工具应包含核心导航/问数工具。"""
    from app.plugin.module_ai.agno_tools.agent_factory import build_agent

    agent = build_agent()
    names = {t.name for t in (agent.tools or [])}
    assert "navigate" in names
    assert "ai_query" in names


def test_agno_stream_response_headers():
    """Agno 原生流的响应头应禁用代理缓冲。"""
    from app.plugin.module_ai.assistant.agno_service import agno_stream_response

    async def _gen():
        yield ": keepalive\n\n"

    resp = agno_stream_response(_gen())
    assert resp.media_type == "text/event-stream"
    assert resp.headers["X-Accel-Buffering"] == "no"
    assert resp.headers["Cache-Control"] == "no-cache, no-transform"
