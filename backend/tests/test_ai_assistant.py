"""AI 助手工具：导航、报告生成与落库、运行循环（假 LLM）。"""
import asyncio
import json
from types import SimpleNamespace

from app.plugin.module_ai.assistant import tools as T


def test_navigate_allowlist():
    ok = asyncio.run(T.navigate("/train/task", "查看训练"))
    assert ok["__action__"]["type"] == "navigate"
    assert ok["__action__"]["path"] == "/train/task"

    bad = asyncio.run(T.navigate("/etc/passwd"))
    assert "error" in bad


def test_generate_report_persists(test_client, auth_headers):
    result = asyncio.run(T.generate_report("Pytest 报告", scope="annotation", user_id=1))
    assert result["__report_id__"] > 0

    lst = test_client.get("/api/v1/ai/report/list", headers=auth_headers).json()["data"]
    row = next(x for x in lst if x["id"] == result["__report_id__"])
    assert row["title"] == "Pytest 报告"

    detail = test_client.get(
        f"/api/v1/ai/report/detail/{result['__report_id__']}", headers=auth_headers
    ).json()["data"]
    assert "# Pytest 报告" in detail["content"]

    test_client.request(
        "DELETE",
        "/api/v1/ai/report/delete",
        json=[result["__report_id__"]],
        headers=auth_headers,
    )


class _FakeFunction:
    def __init__(self, name, args):
        self.name = name
        self.arguments = json.dumps(args)


class _FakeToolCall:
    def __init__(self, name, args):
        self.id = "call_1"
        self.function = _FakeFunction(name, args)


class _FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _FakeResp:
    def __init__(self, message):
        self.choices = [SimpleNamespace(message=message)]


class _FakeCompletions:
    def __init__(self):
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return _FakeResp(_FakeMessage(tool_calls=[_FakeToolCall("navigate", {"path": "/ai/report", "reason": "t"})]))
        return _FakeResp(_FakeMessage(content="已为你打开报告页"))


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self, *a, **k):
        self.chat = _FakeChat()


def test_run_assistant_tool_loop(monkeypatch):
    """run_assistant 由 Agno Agent 驱动：替换 build_agent 产出带工具执行结果的假 agent。"""
    import app.plugin.module_ai.agno_tools.agent_factory as af
    from app.plugin.module_ai.models.service import AiModelService

    async def _runtime(usage=None):
        return {"base_url": "http://x", "api_key": "k", "model": "m", "temperature": 0.1, "max_tokens": 64}

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))

    class _RunOutput:
        content = "已为你打开报告页"

        tools = [
            type(
                "ToolExec",
                (),
                {
                    "tool_name": "navigate",
                    "tool_args": {"path": "/ai/report", "reason": "t"},
                    "result": json.dumps(
                        {"__action__": {"type": "navigate", "path": "/ai/report", "label": "AI 报告", "reason": "t"}}
                    ),
                },
            )()
        ]

        def get_content_as_string(self):
            return self.content

    class _FakeAgent:
        async def arun(self, *a, **k):
            return _RunOutput()

    monkeypatch.setattr(af, "build_agent", lambda **k: _FakeAgent())

    import app.plugin.module_ai.assistant.service as S

    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    out = asyncio.run(S.run_assistant("打开报告页", auth))
    assert out["reply"] == "已为你打开报告页"
    assert out["action"]["type"] == "navigate"
    assert out["tool_calls"][0]["name"] == "navigate"


def test_assistant_stream_rag(monkeypatch, test_client, auth_headers):
    """AI 助手流式接入知识库 RAG（Agno 原生流）：知识上下文注入 + 正文正常输出。"""
    from agno.run.agent import RunCompletedEvent, RunContentEvent, RunEvent, RunStartedEvent

    from app.plugin.module_ai.knowledge import service as kb_service
    from app.plugin.module_ai.models.service import AiModelService

    async def _fake_search(kb_ids, query, top_k=5):
        return [
            {
                "chunk_id": 1,
                "knowledge_base_id": 1,
                "file_name": "doc.txt",
                "content": "AIStation 是开源平台",
                "score": 0.92,
            }
        ]

    monkeypatch.setattr(kb_service.AiKnowledgeService, "search", staticmethod(_fake_search))

    async def _runtime(usage=None):
        return {"base_url": "http://x", "api_key": "k", "model": "m", "temperature": 0.1, "max_tokens": 64}

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))

    captured: dict = {}

    async def _agen():
        yield RunStartedEvent(event=RunEvent.run_started.value, model="m")
        yield RunContentEvent(event=RunEvent.run_content.value, content="好的，AIStation 是开源平台。")
        yield RunCompletedEvent(event=RunEvent.run_completed.value, content="好的，AIStation 是开源平台。")

    class _FakeAgent:
        @property
        def tools(self):
            return []

        def arun(self, *a, **k):
            captured["input"] = a[0] if a else None
            return _agen()

    import app.plugin.module_ai.agno_tools.agent_factory as af

    monkeypatch.setattr(af, "build_agent", lambda **k: _FakeAgent())

    r = test_client.post(
        "/api/v1/ai/assistant/stream",
        json={
            "messages": [{"role": "user", "parts": [{"type": "text", "text": "介绍一下"}]}],
            "knowledge_ids": [1],
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert "event: RunStarted" in body
    assert "event: RunContent" in body
    assert "event: RunCompleted" in body
    # 知识库上下文已注入输入文本（含来源）
    assert "参考知识" in captured["input"]
    assert "AIStation 是开源平台" in captured["input"]
