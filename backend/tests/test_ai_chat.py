"""AI 聊天（/ai/chat）：会话存储收敛到规范 `ai_sessions` 仓库 + 共享 Agno Agent。"""
import asyncio

from app.plugin.module_ai.sessions.service import AiSessionService


def _patch_runtime(monkeypatch) -> None:
    from app.plugin.module_ai.provider.service import AiModelService

    async def _runtime(usage=None, model_id=None):
        return {
            "base_url": "http://x",
            "api_key": "k",
            "model": "pytest-chat-model",
            "temperature": 0.7,
            "max_tokens": 64,
        }

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))


def _patch_build_agent(monkeypatch, captured: dict) -> None:
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
    """/ai-chat 非流式：会话并入 ai_sessions，且问答落 ai_messages。"""
    _patch_runtime(monkeypatch)
    _patch_build_agent(monkeypatch, {})

    try:
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
    finally:
        # 清理已建会话
        pass


def test_chat_session_crud_converged(test_client, auth_headers):
    """/chat 会话 CRUD 走 ai_sessions，与 /sessions 同一仓库。"""
    # 先直接经 ai_sessions 建一个，再经 /chat 取回，验证同仓库
    created = asyncio.run(
        AiSessionService.create("收敛测试", None, 1)
    )
    sid = created["id"]

    try:
        lst = test_client.get(
            "/api/v1/ai/chat/list?page_no=1&page_size=10", headers=auth_headers
        ).json()["data"]
        item_ids = [i["id"] for i in (lst["items"] or [])]
        assert sid in item_ids

        detail = test_client.get(
            f"/api/v1/ai/chat/detail/{sid}", headers=auth_headers
        ).json()["data"]
        assert detail["id"] == sid
        assert detail["title"] == "收敛测试"
    finally:
        asyncio.run(AiSessionService.delete([sid]))


def test_chat_session_rename_delete(test_client, auth_headers):
    """重命名 / 删除会话（ai_sessions）。"""
    created = asyncio.run(AiSessionService.create("原名", None, 1))
    sid = created["id"]
    try:
        up = test_client.put(
            f"/api/v1/ai/chat/update/{sid}", json={"title": "改名"}, headers=auth_headers
        )
        assert up.status_code == 200, up.text
        got = asyncio.run(AiSessionService.get_session(sid))
        assert got["title"] == "改名"
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/chat/delete", json=[sid], headers=auth_headers
        )
        assert asyncio.run(AiSessionService.get_session(sid)) is None
