"""AI 会话（ai_sessions/ai_messages）与调用日志查询。"""
import asyncio
import uuid
from types import SimpleNamespace


def _new_name(prefix: str = "pytest_log") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class _FakeDelta:
    def __init__(self, content=None, reasoning_content=None, tool_calls=None):
        self.content = content
        self.reasoning_content = reasoning_content
        self.tool_calls = tool_calls


class _FakeChunk:
    def __init__(self, delta):
        self.choices = [SimpleNamespace(delta=delta)]


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
            "model": "pytest-session-model",
            "temperature": 0.1,
            "max_tokens": 64,
        }

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))


def _make_raising_stream_client(chunks):
    """构造假 AsyncOpenAI：产出给定分片后抛异常，模拟流中途失败。"""

    class _Completions:
        async def create(self, **kwargs):
            async def _gen():
                for c in chunks:
                    yield c
                raise RuntimeError("stream boom")

            return _gen()

    class _Chat:
        def __init__(self):
            self.completions = _Completions()

    class _Client:
        def __init__(self, *a, **k):
            self.chat = _Chat()

    return _Client


def _create_session(test_client, auth_headers, title: str, app_id=None) -> int:
    r = test_client.post(
        "/api/v1/ai/sessions/create",
        json={"title": title, "app_id": app_id},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _delete_session(test_client, auth_headers, session_id: int) -> None:
    test_client.request(
        "DELETE", "/api/v1/ai/sessions/delete", json=[session_id], headers=auth_headers
    )


def test_session_crud(test_client, auth_headers):
    """创建 → 列表 → 详情（空消息）→ 删除。"""
    session_id = _create_session(test_client, auth_headers, "pytest 会话")
    try:
        lst = test_client.get("/api/v1/ai/sessions/list", headers=auth_headers).json()["data"]
        row = next(s for s in lst if s["id"] == session_id)
        assert row["title"] == "pytest 会话"
        assert row["user_id"] is not None
        assert row["message_count"] == 0

        detail = test_client.get(
            f"/api/v1/ai/sessions/detail/{session_id}", headers=auth_headers
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["messages"] == []
    finally:
        _delete_session(test_client, auth_headers, session_id)

    lst2 = test_client.get("/api/v1/ai/sessions/list", headers=auth_headers).json()["data"]
    assert all(s["id"] != session_id for s in lst2)


def test_stream_with_session_id_persists_two_messages(
    monkeypatch, test_client, auth_headers
):
    """传 session_id 跑一次流式：落 user + assistant 两条消息并累加数量。"""
    import openai

    session_id = _create_session(test_client, auth_headers, "pytest 流式会话")
    rounds = [[_FakeChunk(_FakeDelta(content="助手回复"))]]
    monkeypatch.setattr(openai, "AsyncOpenAI", _make_stream_client(rounds))
    _patch_runtime(monkeypatch)

    try:
        r = test_client.post(
            "/api/v1/ai/assistant/stream",
            json={
                "messages": [
                    {"role": "user", "parts": [{"type": "text", "text": "你好"}]}
                ],
                "session_id": session_id,
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert '"type": "text-delta"' in r.text
        assert "data: [DONE]" in r.text

        detail = test_client.get(
            f"/api/v1/ai/sessions/detail/{session_id}", headers=auth_headers
        ).json()["data"]
        msgs = detail["messages"]
        assert len(msgs) == 2, msgs
        assert msgs[0]["role"] == "user"
        assert msgs[0]["parts"][0]["text"] == "你好"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["parts"][0]["text"] == "助手回复"
        assert detail["message_count"] == 2
    finally:
        _delete_session(test_client, auth_headers, session_id)


def test_app_stream_with_session_id_persists(monkeypatch, test_client, auth_headers):
    """应用运行流式同样落会话：/ai/apps/{id}/run/stream 传 session_id 后多两条消息。"""
    import openai

    app_name = f"pytest-app-{uuid.uuid4().hex[:8]}"
    app_id = test_client.post(
        "/api/v1/ai/apps/create",
        json={
            "name": app_name,
            "icon": "",
            "description": None,
            "model_id": None,
            "prompt_id": None,
            "tools": [],
            "output_format": "text",
            "input_schema": None,
            "enabled": True,
            "order": 0,
        },
        headers=auth_headers,
    ).json()["data"]["id"]
    session_id = _create_session(test_client, auth_headers, "pytest 应用会话", app_id=app_id)
    rounds = [[_FakeChunk(_FakeDelta(content="应用回复"))]]
    monkeypatch.setattr(openai, "AsyncOpenAI", _make_stream_client(rounds))
    _patch_runtime(monkeypatch)

    try:
        r = test_client.post(
            f"/api/v1/ai/apps/{app_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "执行"}]}],
                "variables": {},
                "session_id": session_id,
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert "data: [DONE]" in r.text

        detail = test_client.get(
            f"/api/v1/ai/sessions/detail/{session_id}", headers=auth_headers
        ).json()["data"]
        msgs = detail["messages"]
        assert len(msgs) == 2, msgs
        assert msgs[0]["role"] == "user"
        assert msgs[0]["parts"][0]["text"] == "执行"
        assert msgs[1]["role"] == "assistant"
        assert msgs[1]["parts"][0]["text"] == "应用回复"
    finally:
        _delete_session(test_client, auth_headers, session_id)
        test_client.request(
            "DELETE", "/api/v1/ai/apps/delete", json=[app_id], headers=auth_headers
        )


def test_stream_without_session_id_does_not_persist(monkeypatch, test_client, auth_headers):
    """不传 session_id 时行为不变：不产生任何会话记录（回归保护）。"""
    import openai

    rounds = [[_FakeChunk(_FakeDelta(content="无会话回复"))]]
    monkeypatch.setattr(openai, "AsyncOpenAI", _make_stream_client(rounds))
    _patch_runtime(monkeypatch)

    before = test_client.get("/api/v1/ai/sessions/list", headers=auth_headers).json()["data"]
    r = test_client.post(
        "/api/v1/ai/assistant/stream",
        json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    after = test_client.get("/api/v1/ai/sessions/list", headers=auth_headers).json()["data"]
    assert len(after) == len(before)


def test_stream_error_still_persists_exchange(monkeypatch, test_client, auth_headers):
    """流中途异常（如工具/解析/连接失败）：已流出的 user/assistant 文本仍落库，不丢会话。"""
    import openai

    from app.plugin.module_ai.assistant.service import run_assistant_ui_stream
    from app.plugin.module_ai.sessions.service import AiSessionService

    session_id = _create_session(test_client, auth_headers, "pytest 异常兜底")
    monkeypatch.setattr(
        openai,
        "AsyncOpenAI",
        _make_raising_stream_client([_FakeChunk(_FakeDelta(content="部分回复"))]),
    )
    _patch_runtime(monkeypatch)

    try:

        async def _flow():
            agen = run_assistant_ui_stream(
                [{"role": "user", "parts": [{"type": "text", "text": "你好"}]}],
                SimpleNamespace(user=SimpleNamespace(id=1)),
                session_id=session_id,
            )
            try:
                async for _ in agen:
                    pass
            except RuntimeError:
                pass
            return await AiSessionService.get_messages(session_id)

        msgs = asyncio.run(_flow())
        assert [m["role"] for m in msgs] == ["user", "assistant"], msgs
        assert msgs[0]["parts"][0]["text"] == "你好"
        assert msgs[1]["parts"][0]["text"] == "部分回复"
    finally:
        _delete_session(test_client, auth_headers, session_id)


def test_session_ownership_enforced(test_client, auth_headers):
    """他人会话：detail/delete 均被拒（404），本人会话仍可访问。"""
    from app.plugin.module_ai.sessions.service import AiSessionService

    async def _create():
        return await AiSessionService.create("他人会话", app_id=None, user_id=888888)

    other_id = asyncio.run(_create())["id"]
    try:
        detail = test_client.get(
            f"/api/v1/ai/sessions/detail/{other_id}", headers=auth_headers
        )
        assert detail.status_code == 404, detail.text

        deleted = test_client.request(
            "DELETE",
            "/api/v1/ai/sessions/delete",
            json=[other_id],
            headers=auth_headers,
        )
        assert deleted.status_code == 404, deleted.text

        async def _still_there():
            return await AiSessionService.get_session(other_id)

        assert asyncio.run(_still_there()) is not None
    finally:
        asyncio.run(AiSessionService.delete([other_id]))


def test_append_message_increments_count():
    """service 层：append_message 落库并递增 message_count。"""
    from app.plugin.module_ai.sessions.service import AiSessionService

    async def _flow():
        s = await AiSessionService.create("pytest append", app_id=None, user_id=9001)
        await AiSessionService.append_message(
            s["id"], "user", [{"type": "text", "text": "第一句"}], app_id=None
        )
        msgs = await AiSessionService.get_messages(s["id"])
        return s["id"], msgs

    session_id, msgs = asyncio.run(_flow())
    try:
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"

        async def _get():
            return await AiSessionService.get_session(session_id)

        assert asyncio.run(_get())["message_count"] == 1
    finally:
        asyncio.run(AiSessionService.delete([session_id]))


def test_logs_list_pagination_and_filters(test_client, auth_headers):
    """日志分页 + usage/result/keyword 过滤。"""
    from app.plugin.module_ai.overview.service import AiOverviewService

    tag = _new_name()

    async def _seed():
        await AiOverviewService.add_log(tag, "chat", 11, "success", user_id=4242)
        await AiOverviewService.add_log(
            tag, "app", 22, "error", f"boom-{tag}", app_id=7, user_id=4242
        )

    asyncio.run(_seed())

    r = test_client.get(
        "/api/v1/ai/logs/list",
        params={"page_no": 1, "page_size": 10, "keyword": tag},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert {"page_no", "page_size", "total", "has_next", "items"} <= set(data.keys())
    assert data["total"] >= 2
    assert all(i["model_name"] == tag for i in data["items"])

    err = test_client.get(
        "/api/v1/ai/logs/list",
        params={"keyword": tag, "result": "error"},
        headers=auth_headers,
    ).json()["data"]["items"]
    assert err and all(i["result"] == "error" for i in err)
    assert any("boom" in (i["error"] or "") for i in err)

    app_only = test_client.get(
        "/api/v1/ai/logs/list",
        params={"keyword": tag, "usage": "app"},
        headers=auth_headers,
    ).json()["data"]["items"]
    assert app_only and all(i["usage"] == "app" for i in app_only)

    paged = test_client.get(
        "/api/v1/ai/logs/list",
        params={"keyword": tag, "page_no": 1, "page_size": 1},
        headers=auth_headers,
    ).json()["data"]
    assert paged["page_no"] == 1
    assert paged["page_size"] == 1
    assert len(paged["items"]) == 1
    assert paged["has_next"] is True
