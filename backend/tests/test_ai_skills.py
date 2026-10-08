"""AI 技能广场：CRUD、分类、精选、列表过滤，以及技能注入智能体运行。"""
import uuid
from types import SimpleNamespace


def _new_name(prefix: str = "pytest_skill") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _create_skill(test_client, auth_headers, **overrides) -> int:
    payload = {
        "name": _new_name(),
        "description": "pytest 技能",
        "content": "遇到用户提问，请按此技能说明执行步骤。",
        "skill_type": "instruction",
        "category": "pytest-技能",
        "version": "1.0",
        "featured": False,
        "enabled": True,
    }
    payload.update(overrides)
    r = test_client.post("/api/v1/ai/skills/create", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _delete_skill(test_client, auth_headers, ids) -> None:
    if ids:
        test_client.request(
            "DELETE", "/api/v1/ai/skills/delete", json=ids, headers=auth_headers
        )


def test_skill_crud(test_client, auth_headers):
    skill_id = _create_skill(test_client, auth_headers)
    try:
        lst = test_client.get("/api/v1/ai/skills/list", headers=auth_headers).json()["data"]
        row = next(x for x in lst if x["id"] == skill_id)
        assert row["skill_type"] == "instruction"
        assert row["category"] == "pytest-技能"

        detail = test_client.get(
            f"/api/v1/ai/skills/detail/{skill_id}", headers=auth_headers
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["name"] == row["name"]

        upd = test_client.put(
            f"/api/v1/ai/skills/update/{skill_id}",
            json={"version": "2.0", "featured": True},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["data"]["version"] == "2.0"
        assert upd.json()["data"]["featured"] is True
    finally:
        _delete_skill(test_client, auth_headers, [skill_id])

    lst2 = test_client.get("/api/v1/ai/skills/list", headers=auth_headers).json()["data"]
    assert all(x["id"] != skill_id for x in lst2)


def test_skill_categories_and_toggle(test_client, auth_headers):
    skill_id = _create_skill(test_client, auth_headers, category="pytest-分类A")
    try:
        cats = test_client.get("/api/v1/ai/skills/categories", headers=auth_headers).json()["data"]
        assert any(c["name"] == "pytest-分类A" and c["count"] >= 1 for c in cats)

        tog = test_client.put(
            f"/api/v1/ai/skills/toggle/{skill_id}",
            params={"featured": True},
            headers=auth_headers,
        )
        assert tog.status_code == 200, tog.text
        assert tog.json()["data"]["featured"] is True
    finally:
        _delete_skill(test_client, auth_headers, [skill_id])


def test_skill_list_filter(test_client, auth_headers):
    sid1 = _create_skill(test_client, auth_headers, skill_type="tool", category="pytest-工具")
    sid2 = _create_skill(test_client, auth_headers, skill_type="instruction", category="pytest-指引")
    try:
        tools = test_client.get(
            "/api/v1/ai/skills/list", params={"skill_type": "tool"}, headers=auth_headers
        ).json()["data"]
        assert all(x["skill_type"] == "tool" for x in tools)
        assert any(x["id"] == sid1 for x in tools)
        assert not any(x["id"] == sid2 for x in tools)

        cat = test_client.get(
            "/api/v1/ai/skills/list", params={"category": "pytest-指引"}, headers=auth_headers
        ).json()["data"]
        assert any(x["id"] == sid2 for x in cat)
        assert not any(x["id"] == sid1 for x in cat)
    finally:
        _delete_skill(test_client, auth_headers, [sid1, sid2])


class _FakeDelta:
    def __init__(self, content=None, reasoning_content=None, tool_calls=None):
        self.content = content
        self.reasoning_content = reasoning_content
        self.tool_calls = tool_calls


class _FakeChunk:
    def __init__(self, delta):
        self.choices = [SimpleNamespace(delta=delta)]


def _make_stream_client(chunks, sink):
    """假 AsyncOpenAI：返回异步生成器，记录每次 create 入参。"""

    class _Completions:
        def __init__(self):
            self.calls = 0

        async def create(self, **kwargs):
            sink.append(kwargs)
            batch = chunks[self.calls]
            self.calls += 1

            async def _gen():
                for c in batch:
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
    from app.plugin.module_ai.models.service import AiModelService

    async def _runtime(usage=None, model_id=None):
        return {
            "base_url": "http://x",
            "api_key": "k",
            "model": "pytest-skill-model",
            "temperature": 0.1,
            "max_tokens": 64,
        }

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))


def _patch_build_agent_agno(monkeypatch, captured):
    """替换 build_agent，记录 instructions（系统提示词）并产出 Agno 原生事件流。"""
    from agno.run.agent import RunCompletedEvent, RunContentEvent, RunEvent, RunStartedEvent

    async def _agen():
        yield RunStartedEvent(event=RunEvent.run_started.value, model="m")
        yield RunContentEvent(event=RunEvent.run_content.value, content="好的")
        yield RunCompletedEvent(event=RunEvent.run_completed.value, content="好的")

    class _FakeAgent:
        def __init__(self, **kw):
            captured["kwargs"] = kw

        @property
        def tools(self):
            return (captured.get("kwargs") or {}).get("tools") or []

        def arun(self, *a, **k):
            return _agen()

    import app.plugin.module_ai.agno_tools.agent_factory as af

    monkeypatch.setattr(af, "build_agent", lambda **kw: _FakeAgent(**kw))


def _delete_agent(test_client, auth_headers, ids) -> None:
    if ids:
        test_client.request(
            "DELETE", "/api/v1/ai/agents/delete", json=ids, headers=auth_headers
        )


def test_skill_injected_into_agent_run(monkeypatch, test_client, auth_headers):
    """绑定技能的智能体，运行回退路径把技能内容并入系统提示词。"""
    skill_id = _create_skill(test_client, auth_headers, content="我是技能内容XYZ")
    captured: dict = {}
    _patch_runtime(monkeypatch)
    _patch_build_agent_agno(monkeypatch, captured)

    r = test_client.post(
        "/api/v1/ai/agents/create",
        json={
            "agent_name": _new_name("pytest_agent"),
            "skill_ids": [skill_id],
            "model_id": 1,
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    agent_id = r.json()["data"]["id"]
    try:
        run = test_client.post(
            f"/api/v1/ai/agents/{agent_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "你好"}]}],
                "variables": {},
            },
            headers=auth_headers,
        )
        assert run.status_code == 200, run.text
        assert "好的" in run.text
        assert "event: RunContent" in run.text
        # 系统提示词（传入 build_agent 的 instructions）应包含技能内容
        instructions = captured["kwargs"]["instructions"]
        assert instructions
        sys_prompt = instructions[0]
        assert "我是技能内容XYZ" in sys_prompt
        assert "可调用技能" in sys_prompt
    finally:
        _delete_agent(test_client, auth_headers, [agent_id])
        _delete_skill(test_client, auth_headers, [skill_id])
