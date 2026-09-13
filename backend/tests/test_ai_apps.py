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


def _create_http_tool(test_client, auth_headers, name: str, url: str) -> int:
    r = test_client.post(
        "/api/v1/ai/tools/create",
        json={
            "name": name,
            "kind": "http",
            "method": "GET",
            "url": url,
            "params_schema": {"type": "object", "properties": {}},
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _get_tool_row(test_client, auth_headers, name: str) -> dict:
    lst = test_client.get("/api/v1/ai/tools/list", headers=auth_headers).json()["data"]
    return next(t for t in lst if t["name"] == name)


def _toggle_tool(test_client, auth_headers, tool_id: int, enabled: bool) -> None:
    r = test_client.put(
        f"/api/v1/ai/tools/toggle/{tool_id}",
        json={"enabled": enabled},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text


def _run_stream(test_client, auth_headers, app_id: int, variables=None) -> str:
    payload: dict = {
        "messages": [{"role": "user", "parts": [{"type": "text", "text": "执行"}]}]
    }
    if variables is not None:
        payload["variables"] = variables
    r = test_client.post(
        f"/api/v1/ai/apps/{app_id}/run/stream", json=payload, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    return r.text


def test_app_http_tool_error_does_not_abort_stream(monkeypatch, test_client, auth_headers):
    """HTTP 工具抛异常时兜底：流正常收尾，工具帧携带 error 输出。"""
    import openai

    from app.plugin.module_ai.tools_catalog import service as tools_service

    tool_name = _new_name("pytest_http")
    tool_id = _create_http_tool(
        test_client, auth_headers, tool_name, "http://127.0.0.1:1/should-fail"
    )
    app_id = _create_app(test_client, auth_headers, tools=[tool_name])

    async def _boom(tool, args):
        raise RuntimeError("http 工具炸了")

    monkeypatch.setattr(tools_service, "execute_http_tool", _boom)
    sent: list[dict] = []
    rounds = [
        [
            _FakeChunk(
                _FakeDelta(tool_calls=[_FakeToolCallDelta(tool_name, {"q": 1})])
            )
        ],
        [_FakeChunk(_FakeDelta(content="已处理完成"))],
    ]
    monkeypatch.setattr(openai, "AsyncOpenAI", _make_stream_client(rounds, sent))
    _patch_runtime(monkeypatch)

    try:
        body = _run_stream(test_client, auth_headers, app_id)
        assert '"type": "tool-output-available"' in body
        assert "http 工具炸了" in body
        assert '"type": "data-finish"' in body
        assert "data: [DONE]" in body
    finally:
        _delete_apps(test_client, auth_headers, [app_id])
        test_client.request(
            "DELETE", "/api/v1/ai/tools/delete", json=[tool_id], headers=auth_headers
        )


def test_app_builtin_tool_respects_enabled_flag(monkeypatch, test_client, auth_headers):
    """内置工具停用后不发送 schema 且不执行；重新启用后恢复。"""
    import openai

    assert "navigate" in TOOL_REGISTRY
    tool_id = _get_tool_row(test_client, auth_headers, "navigate")["id"]
    app_id = _create_app(test_client, auth_headers, tools=["navigate"])
    sent: list[dict] = []
    rounds = [
        [
            _FakeChunk(
                _FakeDelta(tool_calls=[_FakeToolCallDelta("navigate", {"path": "/ai/app"})])
            )
        ],
        [_FakeChunk(_FakeDelta(content="已打开"))],
    ]
    _patch_runtime(monkeypatch)

    try:
        # 停用 → 不发送 tools，也不会出现工具帧
        _toggle_tool(test_client, auth_headers, tool_id, False)
        sent.clear()
        off_rounds = [[_FakeChunk(_FakeDelta(content="未启用工具，直接回答"))]]
        monkeypatch.setattr(openai, "AsyncOpenAI", _make_stream_client(off_rounds, sent))
        off_body = _run_stream(test_client, auth_headers, app_id)
        assert "tools" not in sent[0]
        assert '"type": "tool-input-available"' not in off_body
        assert "data: [DONE]" in off_body

        # 重新启用 → schema 发送且工具被调用
        _toggle_tool(test_client, auth_headers, tool_id, True)
        sent.clear()
        monkeypatch.setattr(openai, "AsyncOpenAI", _make_stream_client(rounds, sent))
        on_body = _run_stream(test_client, auth_headers, app_id)
        assert any(t["function"]["name"] == "navigate" for t in sent[0]["tools"])
        assert '"type": "tool-input-available"' in on_body
        assert '"type": "tool-output-available"' in on_body
    finally:
        _toggle_tool(test_client, auth_headers, tool_id, True)
        _delete_apps(test_client, auth_headers, [app_id])


def test_app_input_schema_default_variables(monkeypatch, test_client, auth_headers):
    """input_schema 默认值参与提示词渲染；显式变量优先覆盖默认值。"""
    import openai

    prompt_name = _new_name("pytest_prompt")
    prompt_id = _create_prompt(test_client, auth_headers, prompt_name)
    app_id = _create_app(
        test_client,
        auth_headers,
        prompt_id=prompt_id,
        tools=[],
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string", "default": "默认应用名"}},
        },
    )
    sent: list[dict] = []
    _patch_runtime(monkeypatch)

    try:
        # 未传显式变量 → 使用 input_schema 默认值
        monkeypatch.setattr(
            openai,
            "AsyncOpenAI",
            _make_stream_client([[_FakeChunk(_FakeDelta(content="收到"))]], sent),
        )
        _run_stream(test_client, auth_headers, app_id)
        content = sent[0]["messages"][0]["content"]
        assert "默认应用名" in content
        assert "{{name}}" not in content

        # 显式变量覆盖默认值
        sent.clear()
        monkeypatch.setattr(
            openai,
            "AsyncOpenAI",
            _make_stream_client([[_FakeChunk(_FakeDelta(content="收到"))]], sent),
        )
        _run_stream(test_client, auth_headers, app_id, variables={"name": "显式应用名"})
        content2 = sent[0]["messages"][0]["content"]
        assert "显式应用名" in content2
        assert "默认应用名" not in content2
    finally:
        _delete_apps(test_client, auth_headers, [app_id])
        test_client.request(
            "DELETE", "/api/v1/ai/prompts/delete", json=[prompt_id], headers=auth_headers
        )
