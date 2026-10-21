# tests/test_develop_openapi.py
"""开放 REST 能力入口：凭证 / 权限 / 能力不存在 / 审计脱敏 / 归属隔离。

覆盖 Review Focus：
- 第 1 条 跨应用资源不可见（agent.get 他人资源 → 404）；
- 第 2 条 缺权限点调用 → 403 + denied 审计；
- 第 3 条 appkey 不得出现在审计请求体里。
"""
from uuid import uuid4

API = "/api/v1"
AGENT_CAPS = ["integration:agent:query", "integration:agent:create"]
# 跨应用隔离用例需要 delete 权限点，否则先撞 403（权限先于归属校验，属预期顺序）
AGENT_CAPS_FULL = [*AGENT_CAPS, "integration:agent:delete"]
TRAIN_CAPS = ["integration:train:query"]


def _uid() -> str:
    return uuid4().hex[:8]


def _create_app(test_client, auth_headers, caps):
    r = test_client.post(
        f"{API}/ai/develop/create",
        json={"name": f"开放面-{_uid()}", "capabilities": caps},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _app_auth(app):
    return {
        "Authorization": f"Bearer {app['appid']}:{app['appkey']}",
        "X-Forwarded-For": "127.0.0.1",
    }


def _invoke(test_client, app, code, payload):
    return test_client.post(
        f"{API}/ai/develop-api/capabilities/{code}",
        json={"payload": payload},
        headers=_app_auth(app),
    )


def _logs(test_client, auth_headers, app_id, **params):
    query = {"app_id": app_id, "page_size": 50, **params}
    return test_client.get(
        f"{API}/ai/develop/call-logs", params=query, headers=auth_headers
    ).json()["data"]["items"]


def _cleanup(test_client, auth_headers, app_id):
    test_client.request(
        "DELETE", f"{API}/ai/develop/delete", json=[app_id], headers=auth_headers
    )


def test_agent_delete_requires_explicit_confirm(test_client, auth_headers):
    """物理删除不可恢复：开放面必须显式 confirm=true，否则 400 且资源不动。"""
    app = _create_app(test_client, auth_headers, AGENT_CAPS_FULL)
    try:
        created = _invoke(test_client, app, "agent.create", {"agent_name": f"待删-{_uid()}"})
        assert created.status_code == 200, created.text
        agent_id = created.json()["data"]["id"]

        refused = _invoke(test_client, app, "agent.delete", {"agent_id": agent_id})
        assert refused.status_code == 400, refused.text
        assert "confirm" in refused.json()["msg"]
        assert _invoke(test_client, app, "agent.get", {"agent_id": agent_id}).status_code == 200

        ok = _invoke(test_client, app, "agent.delete", {"agent_id": agent_id, "confirm": True})
        assert ok.status_code == 200, ok.text
        assert _invoke(test_client, app, "agent.get", {"agent_id": agent_id}).status_code == 404
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_admin_capability_catalog_lists_all(test_client, auth_headers):
    """管理面能力清单：接入文档展示「有哪些能力可授权」。"""
    r = test_client.get(f"{API}/ai/develop/capabilities", headers=auth_headers)
    assert r.status_code == 200, r.text
    codes = {item["code"] for item in r.json()["data"]["items"]}
    assert {"agent.list", "agent.create", "chat.send", "bot.use", "train.create"}.issubset(codes)
    # 每个能力都带权限点与 MCP 工具名，便于文档展示
    sample = next(i for i in r.json()["data"]["items"] if i["code"] == "agent.list")
    assert sample["perm"] == "integration:agent:query"
    assert sample["mcp_tool"] == "agent_list"


def test_missing_credentials_returns_401(test_client):
    r = test_client.post(
        f"{API}/ai/develop-api/capabilities/agent.list",
        json={"payload": {}},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    assert r.status_code == 401, r.text


def test_capability_list_filtered_by_granted_perms(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, AGENT_CAPS)
    try:
        r = test_client.get(f"{API}/ai/develop-api/capabilities", headers=_app_auth(app))
        assert r.status_code == 200, r.text
        codes = {item["code"] for item in r.json()["data"]["items"]}
        assert {"agent.list", "agent.get", "agent.create"}.issubset(codes)
        # 未授权的 train 能力不得出现
        assert not {c for c in codes if c.startswith("train.")}
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_unauthorized_capability_returns_403_and_denied_audit(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, AGENT_CAPS)
    try:
        r = _invoke(test_client, app, "train.list", {})
        assert r.status_code == 403, r.text
        denied = _logs(test_client, auth_headers, app["id"], status="denied")
        assert any(
            log["capability"] == "train.list" and log["status"] == "denied" for log in denied
        ), denied
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_unknown_capability_returns_404(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, AGENT_CAPS)
    try:
        r = _invoke(test_client, app, "agent.not_exist", {})
        assert r.status_code == 404, r.text
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_success_call_audits_rest_without_appkey(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, AGENT_CAPS)
    try:
        r = _invoke(test_client, app, "agent.create", {"agent_name": f"开放Agent-{_uid()}"})
        assert r.status_code == 200, r.text
        created = r.json()["data"]
        assert created["source_app_id"] == app["id"]

        logs = _logs(test_client, auth_headers, app["id"], method="REST")
        assert logs, "应写入 REST 调用审计"
        assert all(log["status"] == "success" for log in logs)
        # Review Focus 3：审计请求体绝不含 appkey 明文
        body_text = str([log["request_body"] for log in logs])
        assert app["appkey"] not in body_text

        # 清理开放面创建的 Agent
        test_client.request(
            "DELETE", f"{API}/ai/agents/delete", json=[created["id"]], headers=auth_headers
        )
    finally:
        _cleanup(test_client, auth_headers, app["id"])


def test_agent_isolation_between_apps(test_client, auth_headers):
    """Review Focus 1：A 应用看不到 / 改不了 B 应用创建的 Agent。"""
    app_a = _create_app(test_client, auth_headers, AGENT_CAPS)
    app_b = _create_app(test_client, auth_headers, AGENT_CAPS_FULL)
    try:
        created = _invoke(test_client, app_a, "agent.create", {"agent_name": f"A-{_uid()}"})
        assert created.status_code == 200, created.text
        agent_id = created.json()["data"]["id"]

        # B 应用：读 → 404；列表不含 A 的 Agent
        got = _invoke(test_client, app_b, "agent.get", {"agent_id": agent_id})
        assert got.status_code == 404, got.text
        listed = _invoke(test_client, app_b, "agent.list", {})
        assert all(item["id"] != agent_id for item in listed.json()["data"]["items"])

        # B 应用：删 → 404，且资源仍在（注意删除需 confirm=true，否则先撞 400）
        deleted = _invoke(test_client, app_b, "agent.delete", {"agent_id": agent_id, "confirm": True})
        assert deleted.status_code == 404, deleted.text
        still = _invoke(test_client, app_a, "agent.get", {"agent_id": agent_id})
        assert still.status_code == 200, still.text

        test_client.request(
            "DELETE", f"{API}/ai/agents/delete", json=[agent_id], headers=auth_headers
        )
    finally:
        _cleanup(test_client, auth_headers, app_a["id"])
        _cleanup(test_client, auth_headers, app_b["id"])
