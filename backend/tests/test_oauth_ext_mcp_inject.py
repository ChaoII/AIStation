"""阶段 3b：build_mcp_tools 建连前注入外部 OAuth Bearer。"""

import asyncio

import agno.tools.mcp as agno_mcp

from app.core.exceptions import CustomException
from app.plugin.module_ai.mcp import tools as mcp_tools


def test_build_mcp_tools_injects_bearer(monkeypatch):
    """绑定外部 OAuth 服务时，headers 注入 Authorization: Bearer <access>，且不覆盖用户自定义头。"""
    captured = {}

    def fake_mcp_tools(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(agno_mcp, "MCPTools", fake_mcp_tools)

    async def fake_resolve(service_id, user_id):
        return "ext-access-token"

    from app.plugin.module_ai.oauth_ext.service import OAuthExtService

    monkeypatch.setattr(OAuthExtService, "resolve_ext_access_token", staticmethod(fake_resolve))

    result = asyncio.run(
        mcp_tools.build_mcp_tools(
            [{"name": "m", "transport": "streamable-http", "url": "https://x/mcp", "headers": {"X-A": "1"}, "oauth_ext_service_id": 5}],
            user_id=1,
        )
    )
    assert len(result) == 1
    assert captured["headers"]["Authorization"] == "Bearer ext-access-token"
    assert captured["headers"]["X-A"] == "1"  # 不覆盖用户自定义头


def test_build_mcp_tools_unbound_no_auth(monkeypatch):
    """未绑定外部服务 -> 不注入 Authorization（行为与现状一致）。"""
    captured = {}

    def fake_mcp_tools(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(agno_mcp, "MCPTools", fake_mcp_tools)
    asyncio.run(
        mcp_tools.build_mcp_tools(
            [{"name": "m", "transport": "streamable-http", "url": "https://x/mcp", "headers": {"X-A": "1"}}],
            user_id=1,
        )
    )
    assert "Authorization" not in (captured.get("headers") or {})


def test_build_mcp_tools_not_connected_skips(monkeypatch):
    """绑定服务但用户未连接/已撤销 -> 该服务器被跳过，不抛异常。"""
    from app.plugin.module_ai.oauth_ext.service import OAuthExtService

    calls = []

    def fake_mcp_tools(**kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.setattr(agno_mcp, "MCPTools", fake_mcp_tools)

    async def fake_resolve(service_id, user_id):
        raise CustomException(msg="你尚未连接该外部服务", code=10404, status_code=404)

    monkeypatch.setattr(OAuthExtService, "resolve_ext_access_token", staticmethod(fake_resolve))

    result = asyncio.run(
        mcp_tools.build_mcp_tools(
            [{"name": "m", "transport": "streamable-http", "url": "https://x/mcp", "oauth_ext_service_id": 5}],
            user_id=1,
        )
    )
    assert len(result) == 0  # 服务器被跳过
    assert len(calls) == 0  # 未构造任何 MCPTools
