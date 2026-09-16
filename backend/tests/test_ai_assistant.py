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
    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _FakeClient)
    # 让运行时模型可用
    import app.plugin.module_ai.assistant.service as S
    from app.plugin.module_ai.provider.service import AiModelService

    async def _runtime(usage=None):
        return {"base_url": "http://x", "api_key": "k", "model": "m", "temperature": 0.1, "max_tokens": 64}

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))

    auth = SimpleNamespace(user=SimpleNamespace(id=1))
    out = asyncio.run(S.run_assistant("打开报告页", auth))
    assert out["reply"] == "已为你打开报告页"
    assert out["action"]["type"] == "navigate"
    assert out["tool_calls"][0]["name"] == "navigate"
