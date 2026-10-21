# tests/test_embed_exchange.py
"""换票端点（/ai/develop-api/auth/token）：凭证/权限/目标三态 + 审计脱敏。

覆盖 Review Focus 第 4 条：明文 token 不得出现在审计（call_logs.request_body）中。
"""
import json
from uuid import uuid4

API = "/api/v1"


def _uid() -> str:
    return uuid4().hex[:8]


def _create_app(test_client, auth_headers, caps):
    r = test_client.post(
        f"{API}/ai/develop/create",
        json={"name": f"换票测试-{_uid()}", "capabilities": caps},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _create_workflow(test_client, auth_headers):
    r = test_client.post(
        f"{API}/ai/workflows/create",
        json={
            "name": f"换票目标-{_uid()}",
            "graph": {"nodes": [{"id": "start", "type": "start", "data": {}}], "edges": []},
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _app_auth(app):
    # X-Forwarded-For：OperationLogRoute 记操作日志需要合法 IP（TestClient 默认 host 为 testclient）
    return {
        "Authorization": f"Bearer {app['appid']}:{app['appkey']}",
        "X-Forwarded-For": "127.0.0.1",
    }


def _cleanup(test_client, auth_headers, app_id=None, workflow_id=None):
    if workflow_id:
        test_client.request(
            "DELETE", f"{API}/ai/workflows/delete", json=[workflow_id], headers=auth_headers
        )
    if app_id:
        test_client.request(
            "DELETE", f"{API}/ai/develop/delete", json=[app_id], headers=auth_headers
        )


def _embed_logs(test_client, auth_headers):
    return test_client.get(
        f"{API}/ai/develop/call-logs",
        params={"category": "embed", "page_size": 50},
        headers=auth_headers,
    ).json()["data"]["items"]


def test_exchange_ok_returns_token_once_and_audits_masked(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, ["integration:embed:use"])
    wf = None
    try:
        wf = _create_workflow(test_client, auth_headers)
        r = test_client.post(
            f"{API}/ai/develop-api/auth/token",
            json={"kind": "workflow", "target_id": wf},
            headers=_app_auth(app),
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["token"] and data["expires_in"] == 1800 and data["expires_at"]

        row = next(
            i
            for i in _embed_logs(test_client, auth_headers)
            if i["app_id"] == app["id"] and i["capability"] == "token.issue"
        )
        assert row["status"] == "success" and row["method"] == "REST"
        # 明文 token 绝不落审计
        assert data["token"] not in json.dumps(row, ensure_ascii=False)
    finally:
        _cleanup(test_client, auth_headers, app.get("id"), wf)


def test_exchange_denied_without_embed_perm(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, ["integration:chat:send"])
    wf = None
    try:
        wf = _create_workflow(test_client, auth_headers)
        r = test_client.post(
            f"{API}/ai/develop-api/auth/token",
            json={"kind": "workflow", "target_id": wf},
            headers=_app_auth(app),
        )
        assert r.status_code == 403, r.text
        assert any(
            i["app_id"] == app["id"] and i["status"] == "denied"
            for i in _embed_logs(test_client, auth_headers)
        )
    finally:
        _cleanup(test_client, auth_headers, app.get("id"), wf)


def test_exchange_target_not_found_404(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, ["integration:embed:use"])
    try:
        r = test_client.post(
            f"{API}/ai/develop-api/auth/token",
            json={"kind": "workflow", "target_id": 99999999},
            headers=_app_auth(app),
        )
        assert r.status_code == 404, r.text
    finally:
        _cleanup(test_client, auth_headers, app.get("id"))


def test_exchange_invalid_appkey_401(test_client, auth_headers):
    app = _create_app(test_client, auth_headers, ["integration:embed:use"])
    try:
        r = test_client.post(
            f"{API}/ai/develop-api/auth/token",
            json={"kind": "workflow", "target_id": 1},
            headers={"Authorization": f"Bearer {app['appid']}:wrong-key-xxx"},
        )
        assert r.status_code == 401, r.text
    finally:
        _cleanup(test_client, auth_headers, app.get("id"))
