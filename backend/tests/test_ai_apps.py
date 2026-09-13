"""AI 应用：CRUD、绑定提示词/工具的运行流式与调用日志。"""
import json
import uuid
from types import SimpleNamespace

from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY


def _new_name(prefix: str = "pytest_app") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


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
    def __init__(self, name, args, index=0, call_id="call_app_1"):
        self.index = index
        self.id = call_id
        self.function = _FakeFunctionDelta(name, json.dumps(args))


def _make_stream_client(rounds, sink):
    """假 AsyncOpenAI：每轮返回一个异步生成器，并记录每次 create 的入参。"""

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
    from app.plugin.module_ai.provider.service import AiModelService

    async def _runtime(usage=None, model_id=None):
        return {
            "base_url": "http://x",
            "api_key": "k",
            "model": "pytest-app-model",
            "temperature": 0.1,
            "max_tokens": 64,
        }

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))


def _create_prompt(test_client, auth_headers, name: str) -> int:
    r = test_client.post(
        "/api/v1/ai/prompts/create",
        json={
            "name": name,
            "category": "app",
            "blocks": [
                {"type": "system", "content": "你是 {{name}} 应用助手"},
                {"type": "instruction", "content": "回答用户：{{question}}"},
            ],
            "variables": ["name", "question"],
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _create_app(test_client, auth_headers, **overrides) -> int:
    payload = {
        "name": _new_name(),
        "icon": "MagicStick",
        "description": "pytest 应用",
        "model_id": None,
        "prompt_id": None,
        "tools": ["navigate"],
        "output_format": "text",
        "input_schema": {"type": "object", "properties": {}},
        "enabled": True,
        "order": 0,
    }
    payload.update(overrides)
    r = test_client.post("/api/v1/ai/apps/create", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _delete_apps(test_client, auth_headers, ids) -> None:
    if ids:
        test_client.request(
            "DELETE", "/api/v1/ai/apps/delete", json=ids, headers=auth_headers
        )


def test_app_crud(test_client, auth_headers):
    """创建 → 列表 → 详情 → 更新（含清空可空字段）→ 删除。"""
    app_id = _create_app(
        test_client, auth_headers, output_format="report", model_id=999
    )
    try:
        lst = test_client.get("/api/v1/ai/apps/list", headers=auth_headers).json()["data"]
        row = next(x for x in lst if x["id"] == app_id)
        assert row["tools"] == ["navigate"]
        assert row["output_format"] == "report"
        assert row["enabled"] is True

        detail = test_client.get(f"/api/v1/ai/apps/detail/{app_id}", headers=auth_headers)
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["icon"] == "MagicStick"

        upd = test_client.put(
            f"/api/v1/ai/apps/update/{app_id}",
            json={"name": "pytest-app-updated", "enabled": False, "tools": [], "model_id": None},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        body = upd.json()["data"]
        assert body["name"] == "pytest-app-updated"
        assert body["enabled"] is False
        assert body["tools"] == []
        assert body["model_id"] is None
    finally:
        _delete_apps(test_client, auth_headers, [app_id])

    lst2 = test_client.get("/api/v1/ai/apps/list", headers=auth_headers).json()["data"]
    assert all(x["id"] != app_id for x in lst2)


def test_app_run_stream_uses_prompt_tool_and_logs(
    monkeypatch, test_client, auth_headers
):
    """绑定提示词+内置工具的运行：SSE 帧完整、系统提示词被渲染、日志含 app_id。"""
    import openai

    prompt_name = _new_name("pytest_prompt")
    prompt_id = _create_prompt(test_client, auth_headers, prompt_name)
    app_id = _create_app(test_client, auth_headers, prompt_id=prompt_id)
    sent: list[dict] = []
    rounds = [
        [
            _FakeChunk(
                _FakeDelta(
                    tool_calls=[
                        _FakeToolCallDelta("navigate", {"path": "/ai/app", "reason": "t"})
                    ]
                )
            )
        ],
        [_FakeChunk(_FakeDelta(content="已为你打开应用页"))],
    ]
    monkeypatch.setattr(openai, "AsyncOpenAI", _make_stream_client(rounds, sent))
    _patch_runtime(monkeypatch)
    assert "navigate" in TOOL_REGISTRY

    try:
        r = test_client.post(
            f"/api/v1/ai/apps/{app_id}/run/stream",
            json={
                "messages": [
                    {"role": "user", "parts": [{"type": "text", "text": "打开应用"}]}
                ],
                "variables": {"name": "测试", "question": "你好"},
            },
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.text
        assert '"type": "text-delta"' in body
        assert '"type": "tool-input-available"' in body
        assert '"type": "tool-output-available"' in body
        assert '"type": "data-finish"' in body
        assert '"action"' in body
        assert "navigate" in body
        assert "data: [DONE]" in body

        # 系统提示词经 render_prompt 渲染：含【system】前缀且变量被替换
        system_content = sent[0]["messages"][0]["content"]
        assert system_content.startswith("【system】")
        assert "测试" in system_content
        assert "你是 {{name}} 应用助手" not in system_content
        # 工具 schema 随请求发送
        assert any(t["function"]["name"] == "navigate" for t in sent[0]["tools"])

        # 调用日志落库，且带 app_id
        import asyncio

        from sqlalchemy import select

        from app.core.database import async_db_session
        from app.plugin.module_ai.overview.model import AiCallLogModel

        async def _count() -> int:
            async with async_db_session() as db:
                rows = (
                    await db.execute(
                        select(AiCallLogModel).where(
                            AiCallLogModel.app_id == app_id,
                            AiCallLogModel.usage == "app",
                        )
                    )
                ).scalars().all()
                return len(rows)

        assert asyncio.run(_count()) >= 1
    finally:
        _delete_apps(test_client, auth_headers, [app_id])
        test_client.request(
            "DELETE", "/api/v1/ai/prompts/delete", json=[prompt_id], headers=auth_headers
        )
