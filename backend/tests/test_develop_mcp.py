# tests/test_develop_mcp.py
"""MCP Server（Streamable HTTP）：鉴权、握手、工具按授权过滤、调用审计。

覆盖 Review Focus：
- 第 4 条 未鉴权握手必须 401（不是 500、不是正常 JSON-RPC 响应）；
- 第 5 条 工具调用写 call_logs(method=MCP) 且 mcp_sessions.tool_calls 累加。
"""
import json
from uuid import uuid4

API = "/api/v1"
MCP = f"{API}/ai/develop-api/mcp"
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
AGENT_CAPS = ["integration:agent:query", "integration:agent:create"]


def _uid() -> str:
    return uuid4().hex[:8]


def _create_app(test_client, auth_headers, caps):
    r = test_client.post(
        f"{API}/ai/develop/create",
        json={"name": f"MCP面-{_uid()}", "capabilities": caps, "requires_approval": False},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _app_auth(app):
    return {
        "Authorization": f"Bearer {app['appid']}:{app['appkey']}",
        "X-Forwarded-For": "127.0.0.1",
    }


def _cleanup(test_client, auth_headers, app_id):
    test_client.request(
        "DELETE", f"{API}/ai/develop/delete", json=[app_id], headers=auth_headers
    )


def _rpc(test_client, app, method, params=None, *, session_id=None, rid=1):
    headers = {**MCP_HEADERS, **_app_auth(app)}
    if session_id:
        headers["mcp-session-id"] = session_id
    return test_client.post(
        MCP,
        headers=headers,
        content=json.dumps(
            {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
        ),
    )


def _initialize(test_client, app):
    """完成 MCP 握手，返回服务端分配的 session id。"""
    r = _rpc(
        test_client,
        app,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "pytest-client", "version": "1.0"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["serverInfo"]["name"] == "aistation-ai-integration", body
    session_id = r.headers.get("mcp-session-id")
    assert session_id, "服务端应返回 mcp-session-id"
    # 通知（无 id）：客户端告知初始化完成
    test_client.post(
        MCP,
        headers={**MCP_HEADERS, **_app_auth(app), "mcp-session-id": session_id},
        content=json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
    )
    return session_id


def test_mcp_without_credentials_returns_401(test_client):
    """Review Focus 4：未带凭证的 MCP 请求必须被拦在协议层之外。"""
    r = test_client.post(
        MCP,
        headers=MCP_HEADERS,
        content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
    )
    assert r.status_code == 401, r.text
    assert r.json()["detail"] == "鉴权失败"


def test_mcp_bad_appkey_returns_401(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, AGENT_CAPS)
    try:
        r = test_client.post(
            MCP,
            headers={
                **MCP_HEADERS,
                "Authorization": f"Bearer {app['appid']}:wrong-key",
                "X-Forwarded-For": "127.0.0.1",
            },
            content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        )
        assert r.status_code == 401, r.text
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_mcp_lists_only_granted_tools(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, AGENT_CAPS)
    try:
        session_id = _initialize(test_client, app)
        r = _rpc(test_client, app, "tools/list", session_id=session_id)
        assert r.status_code == 200, r.text
        names = {tool["name"] for tool in r.json()["result"]["tools"]}
        assert {"agent_list", "agent_get", "agent_create"}.issubset(names)
        # 未授权的 train / bot 工具不得出现
        assert not {n for n in names if n.startswith("train_") or n == "bot_use"}, names
        # 工具带入参 schema
        agent_get = next(t for t in r.json()["result"]["tools"] if t["name"] == "agent_get")
        assert "agent_id" in agent_get["inputSchema"]["properties"]
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_mcp_tool_call_audits_and_counts_session(test_client, auth_headers):
    """Review Focus 5：工具调用 → call_logs(method=MCP) + mcp_sessions.tool_calls。"""
    app = _create_app(test_client, auth_headers, AGENT_CAPS)
    try:
        session_id = _initialize(test_client, app)
        created = _rpc(
            test_client,
            app,
            "tools/call",
            {"name": "agent_create", "arguments": {"agent_name": f"MCP-Agent-{_uid()}"}},
            session_id=session_id,
        )
        assert created.status_code == 200, created.text
        payload = json.loads(created.json()["result"]["content"][0]["text"])
        assert payload["source_app_id"] == app["id"]

        listed = _rpc(
            test_client, app, "tools/call", {"name": "agent_list", "arguments": {}}, session_id=session_id
        )
        assert listed.status_code == 200, listed.text
        items = json.loads(listed.json()["result"]["content"][0]["text"])["items"]
        assert any(item["id"] == payload["id"] for item in items)

        # 审计：call_logs(method=MCP)
        logs = test_client.get(
            f"{API}/ai/develop/call-logs",
            params={"app_id": app["id"], "method": "MCP", "page_size": 50},
            headers=auth_headers,
        ).json()["data"]["items"]
        caps = {log["capability"] for log in logs}
        assert {"agent.create", "agent.list"}.issubset(caps), caps
        assert all(log["status"] == "success" for log in logs)

        # 审计：mcp_sessions 行 + tool_calls 计数
        sessions = test_client.get(
            f"{API}/ai/develop/mcp-sessions",
            params={"app_id": app["id"], "page_size": 50},
            headers=auth_headers,
        ).json()["data"]["items"]
        assert sessions, "应写入 MCP 会话审计行"
        assert any((row["tool_calls"] or 0) >= 1 for row in sessions), sessions
        assert all(row["transport"] == "streamable-http" for row in sessions)

        test_client.request(
            "DELETE", f"{API}/ai/agents/delete", json=[payload["id"]], headers=auth_headers
        )
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_mcp_unauthorized_tool_call_is_rejected(test_client, auth_headers):
    """未授权工具：不在 tools/list 中；即便直接调用也被 403 语义拒绝。"""
    app = _create_app(test_client, auth_headers, ["integration:agent:query"])
    try:
        session_id = _initialize(test_client, app)
        r = _rpc(
            test_client,
            app,
            "tools/call",
            {"name": "train_create", "arguments": {"name": "x", "framework": "torchkiln", "dataset_id": 1}},
            session_id=session_id,
        )
        assert r.status_code == 200, r.text
        result = r.json()["result"]
        # 工具执行失败按 MCP 语义返回 isError 结果（不是 JSON-RPC error）
        assert result["isError"] is True, result
        text = result["content"][0]["text"]
        assert "10403" in text and "无权限操作" in text, text
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_mcp_resource_lists_authorized_capabilities(test_client, auth_headers):
    """resources/list 提供 aistation://capabilities；read 只回本应用已授权的能力。"""
    app = _create_app(test_client, auth_headers, AGENT_CAPS)
    try:
        session_id = _initialize(test_client, app)
        r = _rpc(test_client, app, "resources/list", session_id=session_id)
        assert r.status_code == 200, r.text
        uris = [res["uri"] for res in r.json()["result"]["resources"]]
        assert "aistation://capabilities" in uris, uris

        r = _rpc(
            test_client,
            app,
            "resources/read",
            {"uri": "aistation://capabilities"},
            session_id=session_id,
        )
        assert r.status_code == 200, r.text
        text_payload = r.json()["result"]["contents"][0]["text"]
        import json as _json

        data = _json.loads(text_payload)
        assert data["appid"] == app["appid"]
        codes = {c["code"] for c in data["capabilities"]}
        assert "agent.list" in codes
        assert not {c for c in codes if c.startswith("train.")}, codes
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_mcp_prompt_platform_guide(test_client, auth_headers):
    """prompts/list 暴露接入引导；get 返回含应用 appid 的说明。"""
    app = _create_app(test_client, auth_headers, AGENT_CAPS)
    try:
        session_id = _initialize(test_client, app)
        r = _rpc(test_client, app, "prompts/list", session_id=session_id)
        assert r.status_code == 200, r.text
        names = [p["name"] for p in r.json()["result"]["prompts"]]
        assert "platform_guide" in names, names

        r = _rpc(
            test_client,
            app,
            "prompts/get",
            {"name": "platform_guide"},
            session_id=session_id,
        )
        assert r.status_code == 200, r.text
        content = r.json()["result"]["messages"][0]["content"]["text"]
        assert app["appid"] in content
        assert "pending_approval" in content
    finally:
        _cleanup(test_client, auth_headers, app["id"])
