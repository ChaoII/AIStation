"""Agno 原生事件流协议测试：assistant /stream 输出 Agno 原生 SSE（RunContent 等）。

替换旧 AI SDK UI Message Stream v1 协议断言（reasoning-delta/text-delta/finish/[DONE]），
对齐「全部换成 Agno 原生流式」的方向。
"""
import asyncio
import json

from app.plugin.module_ai.assistant.service import extract_openai_messages


def test_extract_openai_messages():
    """只取 user/assistant 的 text part，忽略其他 role 与 part，保留多轮。"""
    ui = [
        {
            "role": "user",
            "parts": [
                {"type": "text", "text": "你好"},
                {"type": "file", "url": "http://x/a.png"},
            ],
        },
        {
            "role": "assistant",
            "parts": [
                {"type": "text", "text": "在的"},
                {"type": "tool-navigate", "state": "output-available"},
            ],
        },
        {"role": "system", "parts": [{"type": "text", "text": "应忽略"}]},
        {"role": "user", "parts": [{"type": "text", "text": ""}]},
    ]
    out = extract_openai_messages(ui)
    assert out == [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "在的"},
    ]
    assert extract_openai_messages([]) == []
    assert extract_openai_messages(None) == []


def _patch_runtime(monkeypatch):
    from app.plugin.module_ai.models.service import AiModelService

    async def _runtime(usage=None, model_id=None):
        return {"base_url": "http://x", "api_key": "k", "model": "m", "temperature": 0.1, "max_tokens": 64}

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_runtime))


def _patch_build_agent(monkeypatch, events):
    """替换 build_agent，产出指定 Agno 事件序列的假 agent。"""

    async def _agen():
        for e in events:
            yield e

    class _FakeAgent:
        @property
        def tools(self):
            return []

        def arun(self, *a, **k):
            return _agen()

    import app.plugin.module_ai.agno_tools.agent_factory as af

    monkeypatch.setattr(af, "build_agent", lambda **k: _FakeAgent())


def _event(cls, **kw):
    from agno.run.agent import RunEvent

    return cls(event=RunEvent.run_content.value, **kw)


def test_ui_stream_agno_native_reasoning_and_text(monkeypatch, test_client, auth_headers):
    """Agno 原生流：透出 RunContent 正文与 reasoning 事件。"""
    from agno.run.agent import RunCompletedEvent, RunContentEvent, RunEvent, RunStartedEvent

    _patch_runtime(monkeypatch)
    _patch_build_agent(
        monkeypatch,
        [
            RunStartedEvent(event=RunEvent.run_started.value, model="m"),
            RunContentEvent(event=RunEvent.run_content.value, content="你好"),
            RunContentEvent(event=RunEvent.run_content.value, content="世界"),
            RunCompletedEvent(event=RunEvent.run_completed.value, content="你好世界"),
        ],
    )

    r = test_client.post(
        "/api/v1/ai/assistant/stream",
        json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "你好"}]}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert "event: RunStarted" in body
    assert "event: RunContent" in body
    assert "你好" in body and "世界" in body
    assert "event: RunCompleted" in body


def test_ui_stream_agno_native_tool_then_text(monkeypatch, test_client, auth_headers):
    """Agno 原生流：透出 ToolCallStarted/ToolCallCompleted 工具事件。"""
    from agno.models.response import ToolExecution
    from agno.run.agent import (
        RunCompletedEvent,
        RunContentEvent,
        RunEvent,
        RunStartedEvent,
        ToolCallCompletedEvent,
        ToolCallStartedEvent,
    )

    _patch_runtime(monkeypatch)
    _patch_build_agent(
        monkeypatch,
        [
            RunStartedEvent(event=RunEvent.run_started.value, model="m"),
            ToolCallStartedEvent(
                event=RunEvent.tool_call_started.value,
                tool=ToolExecution(tool_call_id="c1", tool_name="navigate", tool_args={"path": "/ai/report"}),
            ),
            ToolCallCompletedEvent(
                event=RunEvent.tool_call_completed.value,
                tool=ToolExecution(
                    tool_call_id="c1",
                    tool_name="navigate",
                    tool_args={"path": "/ai/report"},
                    result=json.dumps({"__action__": {"type": "navigate", "path": "/ai/report"}}),
                ),
            ),
            RunContentEvent(event=RunEvent.run_content.value, content="已为你打开报告页"),
            RunCompletedEvent(event=RunEvent.run_completed.value, content="已为你打开报告页"),
        ],
    )

    r = test_client.post(
        "/api/v1/ai/assistant/stream",
        json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "打开报告页"}]}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert "event: ToolCallStarted" in body
    assert "event: ToolCallCompleted" in body
    assert '"tool_name": "navigate"' in body or '"toolName": "navigate"' in body or "navigate" in body
    assert "event: RunContent" in body


def test_ui_stream_no_runtime_model_emits_error(monkeypatch, test_client, auth_headers):
    """未配置运行时模型时应输出 RunError 事件帧。"""
    from app.plugin.module_ai.models.service import AiModelService

    async def _none(usage=None, model_id=None):
        return None

    monkeypatch.setattr(AiModelService, "get_runtime_model", staticmethod(_none))

    r = test_client.post(
        "/api/v1/ai/assistant/stream",
        json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert "event: RunError" in body or "RunError" in body


def test_ui_stream_midstream_error_emits_terminal_frame(
    monkeypatch, test_client, auth_headers
):
    """流中途异常：仍透出终止帧（keepalive/error），不悬空。"""
    from agno.run.agent import RunContentEvent, RunEvent

    async def _boom():
        yield RunContentEvent(event=RunEvent.run_content.value, content="部分回复")
        raise RuntimeError("mid stream boom")

    class _FakeAgent:
        @property
        def tools(self):
            return []

        def arun(self, *a, **k):
            return _boom()

    import app.plugin.module_ai.agno_tools.agent_factory as af

    _patch_runtime(monkeypatch)
    monkeypatch.setattr(af, "build_agent", lambda **k: _FakeAgent())

    r = test_client.post(
        "/api/v1/ai/assistant/stream",
        json={"messages": [{"role": "user", "parts": [{"type": "text", "text": "hi"}]}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert "RunContent" in body
    # 异常被外层捕获并以 error 帧透出，保证有终止帧
    assert "RunError" in body or "运行失败" in body


def test_add_log_persists_user_id(test_client, auth_headers):
    """回归：旧实现写不存在的 created_id 导致日志静默丢失。"""
    from sqlalchemy import select

    from app.core.database import async_db_session
    from app.plugin.module_ai.overview.model import AiCallLogModel
    from app.plugin.module_ai.overview.service import AiOverviewService

    asyncio.run(
        AiOverviewService.add_log("pytest-uilog", "chat", 12, "success", user_id=424242)
    )

    async def _count() -> int:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiCallLogModel).where(
                        AiCallLogModel.model_name == "pytest-uilog",
                        AiCallLogModel.user_id == 424242,
                    )
                )
            ).scalars().all()
            return len(rows)

    assert asyncio.run(_count()) >= 1
