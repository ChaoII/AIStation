# tests/test_develop_oauth_mcp.py
#
# 阶段 2（OAuth 2.1）—— Task 8：MCP 数据面接入 OAuth 委托 token。
# 验证：MCP 传输层可用「纯委托 token（无冒号）」鉴权；tools/list 按 OAuth scope 过滤；
# 会话审计写 mcp_sessions（app_id 空、appid=client_id）。
import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

MCP = "/api/v1/ai/develop-api/mcp"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _run(coro):
    return asyncio.run(coro)


async def _seed_client(service, max_scope=None):
    from app.plugin.module_ai.develop.oauth_schema import OAuthClientCreateSchema

    data = OAuthClientCreateSchema(
        name=f"mcp-oauth-{uuid4().hex[:8]}",
        description="测试",
        redirect_uris=["https://assistant.example/callback"],
        max_scope=max_scope or ["agent.list"],
    )
    return await service.create_client(data, SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True)))


async def _issue_access(client_dict, user_id=100, scope=None):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService, OAuthTokenService

    row = await OAuthClientService.get_client(client_dict["client_id"])
    code = await OAuthClientService.issue_authorization_code(
        row, user_id, scope=scope or ["agent.list"],
        redirect_uri="https://assistant.example/callback",
        code_challenge=None, code_challenge_method=None,
    )
    pair = await OAuthTokenService.exchange_code(
        client_id=client_dict["client_id"],
        client_secret=client_dict["client_secret"],
        code=code["code"],
        redirect_uri="https://assistant.example/callback",
        code_verifier=None,
    )
    return pair["access_token"]


def _oauth_rpc(test_client, access_token, method, params=None, *, session_id=None, rid=1):
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {access_token}", "X-Forwarded-For": "127.0.0.1"}
    if session_id:
        headers["mcp-session-id"] = session_id
    return test_client.post(
        MCP,
        headers=headers,
        content=json.dumps(
            {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        ),
    )


async def _mcp_initialize(test_client, access_token):
    r = _oauth_rpc(
        test_client, access_token, "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "oauth-mcp", "version": "1.0"},
        },
    )
    assert r.status_code == 200, r.text
    sid = r.headers.get("mcp-session-id")
    assert sid
    test_client.post(
        MCP,
        headers={**MCP_HEADERS, "Authorization": f"Bearer {access_token}",
                 "X-Forwarded-For": "127.0.0.1", "mcp-session-id": sid},
        content=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
    )
    return sid


def test_mcp_oauth_token_authenticates(test_client):
    """MCP 传输层接受纯 OAuth 委托 token 并完成握手。"""
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService

    client = _run(_seed_client(OAuthClientService))
    access = _run(_issue_access(client, scope=["agent.list"]))
    sid = _run(_mcp_initialize(test_client, access))
    assert sid


def test_mcp_oauth_lists_only_granted_tools(test_client):
    """OAuth scope=['agent.list'] 时 tools/list 只含 agent 工具，不含未授权。"""
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService

    client = _run(_seed_client(OAuthClientService, max_scope=["agent.list"]))
    access = _run(_issue_access(client, scope=["agent.list"]))
    sid = _run(_mcp_initialize(test_client, access))

    r = _oauth_rpc(test_client, access, "tools/list", session_id=sid)
    assert r.status_code == 200, r.text
    names = {tool["name"] for tool in r.json()["result"]["tools"]}
    assert "agent_list" in names
    assert not {n for n in names if n.startswith("train_")}, names


def test_mcp_oauth_session_recorded(test_client):
    """OAuth MCP 会话审计写 mcp_sessions（app_id 空、appid=client_id）。"""
    from app.plugin.module_ai.develop.model import AiIntegrationMcpSessionModel
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService
    from sqlalchemy import select

    from app.core.database import async_db_session

    client = _run(_seed_client(OAuthClientService))
    access = _run(_issue_access(client, scope=["agent.list"]))
    sid = _run(_mcp_initialize(test_client, access))

    async def latest():
        async with async_db_session() as db:
            return (
                await db.execute(
                    select(AiIntegrationMcpSessionModel)
                    .order_by(AiIntegrationMcpSessionModel.id.desc())
                    .limit(1)
                )
            ).scalars().first()

    row = _run(latest())
    assert row is not None
    assert row.app_id is None
    assert row.appid == client["client_id"]
    assert row.transport == "streamable-http"


def test_mcp_oauth_bad_token_401(test_client):
    """无效 OAuth token 被 MCP 传输层 401。"""
    r = test_client.post(
        MCP,
        headers={**MCP_HEADERS, "Authorization": "Bearer not-a-real-oauth-token",
                 "X-Forwarded-For": "127.0.0.1"},
        content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
    )
    assert r.status_code == 401
