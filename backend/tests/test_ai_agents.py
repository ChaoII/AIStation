"""AI 智能体：分类、实体 CRUD、运行（回退模型+提示词+工具 / 委托工作流）。"""
import uuid
from types import SimpleNamespace

from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY


def _new_name(prefix: str = "pytest_agent") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class _FakeDelta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.reasoning_content = None
        self.tool_calls = tool_calls


class _FakeChunk:
    def __init__(self, delta):
        self.choices = [SimpleNamespace(delta=delta)]


class _FakeFunctionDelta:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _FakeToolCallDelta:
    def __init__(self, name, args, index=0, call_id="call_agent_1"):
        self.index = index
        self.id = call_id
        self.function = _FakeFunctionDelta(name, __import__("json").dumps(args))


def _make_stream_client(rounds, sink):
    class _Completions:
        def __init__(self):
            self.calls = 0

        async def create(self, **kwargs):
            sink.append(kwargs)
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
    from app.plugin.module_ai.models.service import AiModelService

    async def _runtime(usage=None, model_id=None):
        return {
            "base_url": "http://x",
            "api_key": "k",
            "model": "pytest-agent-model",
            "temperature": 0.1,
            "max_tokens": 64,
        }

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))


def _patch_build_agent_agno(monkeypatch, captured, events_factory):
    """把 agent_factory.build_agent 替换为记录 kwargs 的假 agent（Agno 原生事件流）。"""
    import app.plugin.module_ai.agno_tools.agent_factory as af

    class _FakeAgent:
        def __init__(self, **kw):
            captured["kwargs"] = kw

        @property
        def tools(self):
            return (captured.get("kwargs") or {}).get("tools") or []

        def arun(self, *a, **k):
            return events_factory()

    monkeypatch.setattr(af, "build_agent", lambda **kw: _FakeAgent(**kw))


def _agno_events(*specs):
    """根据 (event_type, payload) 列表构造 Agno 事件 async 生成器。"""
    from agno.models.response import ToolExecution
    from agno.run.agent import (
        RunCompletedEvent,
        RunContentEvent,
        RunEvent,
        RunStartedEvent,
        ToolCallCompletedEvent,
        ToolCallStartedEvent,
    )

    async def _gen():
        for kind, payload in specs:
            if kind == "start":
                yield RunStartedEvent(event=RunEvent.run_started.value, model="m")
            elif kind == "content":
                yield RunContentEvent(event=RunEvent.run_content.value, content=payload)
            elif kind == "tool":
                name, args, result, cid = payload
                yield ToolCallStartedEvent(
                    event=RunEvent.tool_call_started.value,
                    tool=ToolExecution(
                        tool_call_id=cid or f"call_{name}", tool_name=name, tool_args=args
                    ),
                )
                yield ToolCallCompletedEvent(
                    event=RunEvent.tool_call_completed.value,
                    tool=ToolExecution(
                        tool_call_id=cid or f"call_{name}",
                        tool_name=name,
                        tool_args=args,
                        result=result,
                    ),
                )
            elif kind == "done":
                yield RunCompletedEvent(event=RunEvent.run_completed.value, content=payload or "")

    return _gen()


def _create_agent(test_client, auth_headers, **overrides) -> int:
    payload = {
        "agent_name": _new_name(),
        "agent_role": "测试角色",
        "description": "pytest 智能体",
        "tool_ids": [],
        "knowledge_ids": [],
        "markdown": True,
        "enabled": True,
        "order": 0,
    }
    payload.update(overrides)
    r = test_client.post("/api/v1/ai/agents/create", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _delete_agents(test_client, auth_headers, ids) -> None:
    if ids:
        test_client.request(
            "DELETE", "/api/v1/ai/agents/delete", json=ids, headers=auth_headers
        )


def test_agent_category_crud(test_client, auth_headers):
    r = test_client.post(
        "/api/v1/ai/agents/categories/create",
        json={"name": "客服", "parent_id": None, "sort": 1},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    cat_id = r.json()["data"]["id"]

    lst = test_client.get("/api/v1/ai/agents/categories/list", headers=auth_headers)
    assert lst.status_code == 200, lst.text
    assert any(c["id"] == cat_id for c in lst.json()["data"])

    cat_id2 = test_client.post(
        "/api/v1/ai/agents/categories/create",
        json={"name": "子分类", "parent_id": cat_id, "sort": 0},
        headers=auth_headers,
    ).json()["data"]["id"]

    upd = test_client.put(
        f"/api/v1/ai/agents/categories/update/{cat_id}",
        json={"name": "智能客服"},
        headers=auth_headers,
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["data"]["name"] == "智能客服"

    test_client.request(
        "DELETE", "/api/v1/ai/agents/categories/delete", json=cat_id, headers=auth_headers
    )
    test_client.request(
        "DELETE", "/api/v1/ai/agents/categories/delete", json=cat_id2, headers=auth_headers
    )


def test_agent_crud(test_client, auth_headers):
    agent_id = _create_agent(
        test_client, auth_headers, model_id=999, workflow_id=None, tool_ids=["navigate"]
    )
    try:
        lst = test_client.get("/api/v1/ai/agents/list", headers=auth_headers).json()["data"]
        row = next(x for x in lst if x["id"] == agent_id)
        assert row["agent_name"].startswith("pytest_agent")
        assert row["tool_ids"] == ["navigate"]
        assert row["markdown"] is True

        detail = test_client.get(f"/api/v1/ai/agents/detail/{agent_id}", headers=auth_headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["agent_role"] == "测试角色"

        upd = test_client.put(
            f"/api/v1/ai/agents/update/{agent_id}",
            json={"agent_name": "pytest-agent-updated", "enabled": False, "tool_ids": []},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        body = upd.json()["data"]
        assert body["agent_name"] == "pytest-agent-updated"
        assert body["enabled"] is False
        assert body["tool_ids"] == []
    finally:
        _delete_agents(test_client, auth_headers, [agent_id])

    lst2 = test_client.get("/api/v1/ai/agents/list", headers=auth_headers).json()["data"]
    assert all(x["id"] != agent_id for x in lst2)


def test_agent_run_fallback_stream(monkeypatch, test_client, auth_headers):
    """无 workflow 时回退模型+提示词+工具：Agno 原生工具帧与文本帧完整。"""
    assert "navigate" in TOOL_REGISTRY

    agent_id = _create_agent(test_client, auth_headers, tool_ids=["navigate"])
    captured: dict = {}
    _patch_runtime(monkeypatch)
    _patch_build_agent_agno(
        monkeypatch,
        captured,
        lambda: _agno_events(
            ("start", None),
            ("tool", ("navigate", {"path": "/ai"}, '{"__action__":{"type":"navigate","path":"/ai"}}', "c1")),
            ("content", "已跳转"),
            ("done", "已跳转"),
        ),
    )

    try:
        r = test_client.post(
            f"/api/v1/ai/agents/{agent_id}/run/stream",
            json={
                "messages": [{"role": "user", "parts": [{"type": "text", "text": "打开"}]}]
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.text
        assert "event: RunStarted" in body
        assert "event: ToolCallStarted" in body
        assert "event: ToolCallCompleted" in body
        assert "event: RunContent" in body
        assert "event: RunCompleted" in body
        assert "已跳转" in body
        tool_names = {t.name for t in (captured["kwargs"].get("tools") or [])}
        assert "navigate" in tool_names
    finally:
        _delete_agents(test_client, auth_headers, [agent_id])


def test_agent_run_delegates_to_workflow(monkeypatch, test_client, auth_headers):
    """绑定 workflow_id 时委托工作流运行。"""

    wf_r = test_client.post(
        "/api/v1/ai/workflows/create",
        json={
            "name": _new_name("pytest_wf"),
            "graph": {
                "nodes": [
                    {"id": "start", "type": "start", "data": {"variables": []}},
                    {"id": "end", "type": "end", "data": {"output_template": "工作流回复"}},
                ],
                "edges": [{"id": "e1", "source": "start", "target": "end"}],
            },
            "enabled": True,
        },
        headers=auth_headers,
    )
    wf_id = wf_r.json()["data"]["id"]
    agent_id = _create_agent(test_client, auth_headers, workflow_id=wf_id)

    def _nop_runtime(usage=None, model_id=None):
        raise AssertionError("委托工作流时不应再解析模型")

    from app.plugin.module_ai.models.service import AiModelService

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_nop_runtime))

    try:
        r = test_client.post(
            f"/api/v1/ai/agents/{agent_id}/run/stream",
            json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.text
        assert '"type": "data-finish"' in body
        assert '"reply": "工作流回复"' in body
        assert "data: [DONE]" in body
    finally:
        _delete_agents(test_client, auth_headers, [agent_id])
        test_client.request(
            "DELETE", "/api/v1/ai/workflows/delete", json=[wf_id], headers=auth_headers
        )


def test_agent_install_uninstall_skill(test_client, auth_headers):
    """技能安装到智能体：同步 skill_ids 并累加安装次数；卸载移除。"""
    sk = test_client.post(
        "/api/v1/ai/skills/create",
        json={"name": _new_name("pytest_skill"), "skill_type": "instruction"},
        headers=auth_headers,
    ).json()["data"]
    ag = test_client.post(
        "/api/v1/ai/agents/create",
        json={"agent_name": _new_name("pytest_agent"), "skill_ids": []},
        headers=auth_headers,
    ).json()["data"]
    try:
        r = test_client.post(
            f"/api/v1/ai/agents/{ag['id']}/install-skill",
            json={"skill_id": sk["id"]},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        detail = test_client.get(
            f"/api/v1/ai/agents/detail/{ag['id']}", headers=auth_headers
        ).json()["data"]
        assert sk["id"] in (detail.get("skill_ids") or [])
        sdetail = test_client.get(
            f"/api/v1/ai/skills/detail/{sk['id']}", headers=auth_headers
        ).json()["data"]
        assert sdetail["install_count"] >= 1

        r2 = test_client.post(
            f"/api/v1/ai/agents/{ag['id']}/uninstall-skill",
            json={"skill_id": sk["id"]},
            headers=auth_headers,
        )
        assert r2.status_code == 200, r2.text
        detail2 = test_client.get(
            f"/api/v1/ai/agents/detail/{ag['id']}", headers=auth_headers
        ).json()["data"]
        assert sk["id"] not in (detail2.get("skill_ids") or [])
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/agents/delete", json=[ag["id"]], headers=auth_headers
        )
        test_client.request(
            "DELETE", "/api/v1/ai/skills/delete", json=[sk["id"]], headers=auth_headers
        )
