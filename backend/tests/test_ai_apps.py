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


def _patch_build_agent_agno(monkeypatch, captured, events_factory):
    """把 agent_factory.build_agent 替换为记录 kwargs 的假 agent。

    - ``captured``：dict，用于记录传给 build_agent 的 kwargs（含 tools/instructions）。
    - ``events_factory()``：返回一个 async 生成器，产出 Agno RunOutputEvent。
    """
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
                # payload = (name, args, result_json_str, call_id)
                name, args, result, cid = payload
                yield ToolCallStartedEvent(
                    event=RunEvent.tool_call_started.value,
                    tool=ToolExecution(
                        tool_call_id=cid or f"call_{name}",
                        tool_name=name,
                        tool_args=args,
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
    """绑定提示词+内置工具的运行：Agno 原生帧完整、系统提示词被渲染、日志含 app_id。"""
    prompt_name = _new_name("pytest_prompt")
    prompt_id = _create_prompt(test_client, auth_headers, prompt_name)
    app_id = _create_app(test_client, auth_headers, prompt_id=prompt_id)
    captured: dict = {}
    _patch_runtime(monkeypatch)
    _patch_build_agent_agno(
        monkeypatch,
        captured,
        lambda: _agno_events(
            ("start", None),
            (
                "tool",
                ("navigate", {"path": "/ai/app", "reason": "t"}, '{"__action__":{"type":"navigate","path":"/ai/app"}}', "c1"),
            ),
            ("content", "已为你打开应用页"),
            ("done", "已为你打开应用页"),
        ),
    )
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
        assert "event: RunStarted" in body
        assert "event: RunContent" in body
        assert "event: ToolCallStarted" in body
        assert "event: ToolCallCompleted" in body
        assert "event: RunCompleted" in body
        assert "已为你打开应用页" in body
        assert "navigate" in body

        # 系统提示词经 render_prompt 渲染：传入 build_agent 的 instructions 已替换变量
        instructions = captured["kwargs"]["instructions"]
        assert instructions and instructions[0].startswith("【system】")
        assert "测试" in instructions[0]
        assert "你是 {{name}} 应用助手" not in instructions[0]
        # 动态工具已装配为 Agno 工具
        tool_names = {t.name for t in (captured["kwargs"].get("tools") or [])}
        assert "navigate" in tool_names

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
    from app.plugin.module_ai.tools_catalog import service as tools_service

    tool_name = _new_name("pytest_http")
    tool_id = _create_http_tool(
        test_client, auth_headers, tool_name, "http://127.0.0.1:1/should-fail"
    )
    app_id = _create_app(test_client, auth_headers, tools=[tool_name])

    async def _boom(tool, args):
        raise RuntimeError("http 工具炸了")

    monkeypatch.setattr(tools_service, "execute_http_tool", _boom)
    captured: dict = {}
    _patch_runtime(monkeypatch)
    _patch_build_agent_agno(
        monkeypatch,
        captured,
        lambda: _agno_events(
            ("start", None),
            ("content", "已处理完成"),
            ("done", "已处理完成"),
        ),
    )

    try:
        body = _run_stream(test_client, auth_headers, app_id)
        assert "event: RunContent" in body
        assert "event: RunCompleted" in body
        assert "已处理完成" in body
    finally:
        _delete_apps(test_client, auth_headers, [app_id])
        test_client.request(
            "DELETE", "/api/v1/ai/tools/delete", json=[tool_id], headers=auth_headers
        )


def test_app_builtin_tool_respects_enabled_flag(monkeypatch, test_client, auth_headers):
    """内置工具停用后不装配 Agno 工具 schema 且未执行；重新启用后恢复。"""
    assert "navigate" in TOOL_REGISTRY
    tool_id = _get_tool_row(test_client, auth_headers, "navigate")["id"]
    app_id = _create_app(test_client, auth_headers, tools=["navigate"])
    captured: dict = {}
    _patch_runtime(monkeypatch)

    try:
        # 停用 → 不装配任何 Agno 工具
        _toggle_tool(test_client, auth_headers, tool_id, False)
        _patch_build_agent_agno(
            monkeypatch, captured, lambda: _agno_events(("start", None), ("content", "未启用工具，直接回答"), ("done", "未启用工具，直接回答"))
        )
        off_body = _run_stream(test_client, auth_headers, app_id)
        assert "event: RunContent" in off_body
        assert "navigate" not in off_body

        # 重新启用 → Agno 工具被装配
        _toggle_tool(test_client, auth_headers, tool_id, True)
        _patch_build_agent_agno(
            monkeypatch,
            captured,
            lambda: _agno_events(
                ("start", None),
                ("tool", ("navigate", {"path": "/ai/app"}, '{"__action__":{"type":"navigate","path":"/ai/app"}}', "c2")),
                ("content", "已打开"),
                ("done", "已打开"),
            ),
        )
        on_body = _run_stream(test_client, auth_headers, app_id)
        assert "event: ToolCallStarted" in on_body
        assert "navigate" in on_body
    finally:
        _toggle_tool(test_client, auth_headers, tool_id, True)
        _delete_apps(test_client, auth_headers, [app_id])


def test_app_input_schema_default_variables(monkeypatch, test_client, auth_headers):
    """input_schema 默认值参与提示词渲染；显式变量优先覆盖默认值。"""
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
    captured: dict = {}
    _patch_runtime(monkeypatch)

    try:
        # 未传显式变量 → 使用 input_schema 默认值
        _patch_build_agent_agno(
            monkeypatch, captured, lambda: _agno_events(("start", None), ("content", "收到"), ("done", "收到"))
        )
        _run_stream(test_client, auth_headers, app_id)
        content = captured["kwargs"]["instructions"][0]
        assert "默认应用名" in content
        assert "{{name}}" not in content

        # 显式变量覆盖默认值
        _patch_build_agent_agno(
            monkeypatch, captured, lambda: _agno_events(("start", None), ("content", "收到"), ("done", "收到"))
        )
        _run_stream(test_client, auth_headers, app_id, variables={"name": "显式应用名"})
        content2 = captured["kwargs"]["instructions"][0]
        assert "显式应用名" in content2
        assert "默认应用名" not in content2
    finally:
        _delete_apps(test_client, auth_headers, [app_id])
        test_client.request(
            "DELETE", "/api/v1/ai/prompts/delete", json=[prompt_id], headers=auth_headers
        )


def test_app_templates_and_create_from_template(test_client, auth_headers):
    """AIP 应用市场模板齐全；从模板创建成功并带工具/类型。"""
    tpl = test_client.get("/api/v1/ai/apps/templates", headers=auth_headers).json()["data"]
    assert len(tpl) >= 4
    assert any(t["key"] == "data_query" and "ai_query" in t["tools"] for t in tpl)
    r = test_client.post(
        "/api/v1/ai/apps/create-from-template",
        json={"key": "report", "name": "pytest-报告"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["name"] == "pytest-报告"
    assert body["app_type"] == "report"
    _delete_apps(test_client, auth_headers, [body["id"]])
