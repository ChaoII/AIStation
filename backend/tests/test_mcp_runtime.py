"""MCP 运行时装配测试：工具构建、连接生命周期、降级。"""
import asyncio

import pytest

from app.plugin.module_ai.assistant import agno_service
from app.plugin.module_ai.mcp.tools import build_mcp_tools, close_mcp_tools, connect_mcp_tools


def test_build_mcp_tools_empty():
    """空配置返回空列表。"""
    assert build_mcp_tools([]) == []
    assert build_mcp_tools(None) == []


def test_build_mcp_tools_skips_invalid_config():
    """缺命令的 stdio / 缺地址的 http 服务器被跳过，不影响其它项。"""
    servers = [
        {"name": "bad-stdio", "transport": "stdio", "command": ""},
        {"name": "bad-http", "transport": "streamable-http", "url": ""},
        {"name": "good-http", "transport": "streamable-http", "url": "http://127.0.0.1:9/mcp"},
    ]
    tools = build_mcp_tools(servers)
    assert len(tools) == 1
    assert tools[0].name == "good-http"


def test_build_mcp_tools_stdio_and_http():
    """stdio 与 streamable-http 均可构建（不建立连接）。"""
    tools = build_mcp_tools(
        [
            {"name": "py-mcp", "transport": "stdio", "command": "python", "args": ["-c", "print(1)"]},
            {"name": "web-mcp", "transport": "streamable-http", "url": "http://127.0.0.1:9/mcp", "headers": {"X-A": "1"}},
        ]
    )
    assert {t.name for t in tools} == {"py-mcp", "web-mcp"}


def test_connect_skips_failures():
    """连接失败的服务器被跳过，返回成功列表。"""

    class FakeTool:
        def __init__(self, name, ok):
            self.name = name
            self._ok = ok

        async def connect(self):
            if not self._ok:
                raise RuntimeError("boom")

    async def _go():
        return await connect_mcp_tools([FakeTool("a", True), FakeTool("b", False)])

    ok = asyncio.run(_go())
    assert [t.name for t in ok] == ["a"]


def test_close_ignores_errors():
    """关闭异常被忽略。"""

    class FakeTool:
        name = "x"

        async def close(self):
            raise RuntimeError("boom")

    asyncio.run(close_mcp_tools([FakeTool()]))


def test_run_agno_tool_stream_connects_and_closes_mcp(monkeypatch):
    """运行流会连接 MCP 工具、把工具集注入 Agent、并在结束时关闭。"""
    calls: dict = {}

    class FakeMCP:
        name = "fake-mcp"

        async def connect(self):
            calls["connected"] = True

        async def close(self):
            calls["closed"] = True

    async def fake_core(**kwargs):
        calls["extra_tools"] = kwargs.get("extra_tools")
        yield "event: RunContent\ndata: {}\n\n"

    monkeypatch.setattr(agno_service, "run_agno_core", fake_core)

    async def _dispatch(name, args, user_id):
        return {}

    async def _go():
        frames = []
        async for sse in agno_service.run_agno_tool_stream(
            model_config={},
            system_prompt="sys",
            tool_schemas=[],
            dispatch=_dispatch,
            user_text="你好",
            user_id=1,
            session_id=None,
            mcp_tools=[FakeMCP()],
        ):
            frames.append(sse)
        return frames

    frames = asyncio.run(_go())
    assert calls.get("connected") is True
    assert calls.get("closed") is True
    assert calls.get("extra_tools") and calls["extra_tools"][0].name == "fake-mcp"
    assert frames


# ---------- 需要应用的用例 ----------

def _seed_server(enabled: bool = True, owner_id: int | None = None) -> int:
    from app.core.database import async_db_session
    from app.plugin.module_ai.mcp.model import AiMcpServerModel

    async def _go():
        async with async_db_session.begin() as db:
            s = AiMcpServerModel(
                name=f"pytest_rt_{enabled}",
                transport="streamable-http",
                url="http://127.0.0.1:9/mcp",
                enabled=enabled,
                created_id=owner_id,
                updated_id=owner_id,
            )
            db.add(s)
            await db.flush()
            return s.id

    return asyncio.run(_go())


def test_enabled_servers_filters_disabled(test_client, auth_headers):
    """仅返回启用中的服务器；禁用项被过滤（Agent 运行时降级）。"""
    from sqlalchemy import select

    from app.api.v1.module_system.user.model import UserModel
    from app.core.database import async_db_session
    from app.plugin.module_ai.mcp.service import McpService

    async def _admin():
        async with async_db_session() as db:
            return (await db.execute(select(UserModel.id).where(UserModel.username == "admin"))).scalar()

    uid = asyncio.run(_admin())
    on_id = _seed_server(True, uid)
    off_id = _seed_server(False, uid)

    servers = asyncio.run(McpService.enabled_servers([on_id, off_id], uid))
    ids = {s["id"] for s in servers}
    assert on_id in ids
    assert off_id not in ids


def test_enabled_servers_empty_ids(test_client, auth_headers):
    """mcp_ids 为空时返回空列表（不影响原有运行）。"""
    from app.plugin.module_ai.mcp.service import McpService

    assert asyncio.run(McpService.enabled_servers([], 1)) == []


def test_agent_schema_and_dict_include_mcp_ids(test_client, auth_headers):
    """Agent 创建/详情包含 mcp_ids 字段。"""
    r = test_client.post(
        "/api/v1/ai/agents/create",
        headers=auth_headers,
        json={"agent_name": "pytest_mcp_agent", "mcp_ids": [], "enabled": True},
    )
    assert r.status_code == 200, r.text
    assert "mcp_ids" in r.json()["data"]
    aid = r.json()["data"]["id"]
    detail = test_client.get(f"/api/v1/ai/agents/detail/{aid}", headers=auth_headers)
    if detail.status_code == 200:
        assert "mcp_ids" in detail.json()["data"]
