"""AI 对话（/ai/chat）：非流式执行复用共享 Agno Agent，会话统一并入规范 `ai_sessions`（单一口子）。"""
import asyncio

from app.plugin.module_ai.sessions.service import AiSessionService


def _patch_runtime(monkeypatch) -> None:
    from app.plugin.module_ai.models.service import AiModelService

    async def _runtime(usage=None, model_id=None):
        return {
            "base_url": "http://x",
            "api_key": "k",
            "model": "pytest-chat-model",
            "temperature": 0.7,
            "max_tokens": 64,
        }

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))


def _patch_build_agent(monkeypatch) -> None:
    """把 build_agent 替换为返回固定回复的假 agent（非流式 /ai-chat）。"""

    class _FakeResp:
        content = "来自 ai_sessions 会话的回复"
        tools: list = []

        def get_content_as_string(self) -> str:
            return "来自 ai_sessions 会话的回复"

    class _FakeAgent:
        async def arun(self, *a, **k):
            return _FakeResp()

    import app.plugin.module_ai.agno_tools.agent_factory as af

    monkeypatch.setattr(af, "build_agent", lambda **k: _FakeAgent())


def test_chat_ai_chat_persists_to_ai_sessions(monkeypatch, test_client, auth_headers):
    """/ai-chat 非流式：会话并入 ai_sessions，问答落 ai_messages，且经 /sessions 单一口子可见。"""
    _patch_runtime(monkeypatch)
    _patch_build_agent(monkeypatch)

    r = test_client.post(
        "/api/v1/ai/chat/ai-chat",
        json={"message": "你好"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    sid = data["session_id"]
    assert isinstance(sid, int)
    assert data["response"] == "来自 ai_sessions 会话的回复"

    # 会话与消息都落在规范 ai_sessions / ai_messages
    session = asyncio.run(AiSessionService.get_session(sid))
    assert session and session["title"]
    msgs = asyncio.run(AiSessionService.get_messages(sid))
    roles = [m["role"] for m in msgs]
    assert "user" in roles and "assistant" in roles
    assert all(m["parts"] for m in msgs)

    # 单一口子：经 /sessions 也能取到该会话与消息
    detail = test_client.get(
        f"/api/v1/ai/sessions/detail/{sid}", headers=auth_headers
    ).json()["data"]
    assert detail["id"] == sid
    assert any(m["role"] == "assistant" for m in (detail.get("messages") or []))

    # 清理
    asyncio.run(AiSessionService.delete([sid]))
