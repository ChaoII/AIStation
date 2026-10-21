# tests/test_embed_admin_tokens.py
"""管理面嵌入令牌：签发（一次性明文）→ 列表 → 吊销 → 令牌立即失效。"""
from uuid import uuid4

API = "/api/v1"


def _uid() -> str:
    return uuid4().hex[:8]


def _create_app(test_client, auth_headers):
    r = test_client.post(
        f"{API}/ai/develop/create",
        json={"name": f"令牌管理-{_uid()}", "capabilities": ["integration:embed:use"]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _create_workflow(test_client, auth_headers):
    r = test_client.post(
        f"{API}/ai/workflows/create",
        json={
            "name": f"令牌目标-{_uid()}",
            "graph": {"nodes": [{"id": "start", "type": "start", "data": {}}], "edges": []},
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _token_auth(token):
    return {"Authorization": f"Bearer {token}", "X-Forwarded-For": "127.0.0.1"}


def test_mint_list_revoke_and_token_dead(test_client, auth_headers):
    app = _create_app(test_client, auth_headers)
    wf = _create_workflow(test_client, auth_headers)
    try:
        m = test_client.post(
            f"{API}/ai/develop/tokens",
            json={"app_id": app["id"], "kind": "workflow", "target_id": wf},
            headers=auth_headers,
        )
        assert m.status_code == 200, m.text
        data = m.json()["data"]
        token = data["token"]
        assert token and data["expires_at"] and data["expires_in"] == 7200

        lst = test_client.get(
            f"{API}/ai/develop/tokens", params={"app_id": app["id"]}, headers=auth_headers
        )
        assert lst.status_code == 200, lst.text
        items = lst.json()["data"]["items"]
        row = next(i for i in items if i["kind"] == "workflow" and i["target_id"] == wf)
        assert row["target_name"] and row["revoked"] is False and row["issued_by"] == "admin"
        # 列表绝不泄露明文
        assert token not in lst.text

        ok = test_client.get(f"{API}/ai/embed/meta", headers=_token_auth(token))
        assert ok.status_code == 200, ok.text

        rv = test_client.put(
            f"{API}/ai/develop/tokens/{row['id']}/revoke", headers=auth_headers
        )
        assert rv.status_code == 200, rv.text

        dead = test_client.get(f"{API}/ai/embed/meta", headers=_token_auth(token))
        assert dead.status_code == 401
        lst2 = test_client.get(
            f"{API}/ai/develop/tokens", params={"app_id": app["id"]}, headers=auth_headers
        )
        row2 = next(i for i in lst2.json()["data"]["items"] if i["id"] == row["id"])
        assert row2["revoked"] is True
    finally:
        test_client.request("DELETE", f"{API}/ai/workflows/delete", json=[wf], headers=auth_headers)
        test_client.request(
            "DELETE", f"{API}/ai/develop/delete", json=[app["id"]], headers=auth_headers
        )


def test_mint_unknown_app_or_target(test_client, auth_headers):
    r = test_client.post(
        f"{API}/ai/develop/tokens",
        json={"app_id": 99999999, "kind": "workflow", "target_id": 1},
        headers=auth_headers,
    )
    assert r.status_code == 400 and "应用不存在" in r.text

    app = _create_app(test_client, auth_headers)
    try:
        r = test_client.post(
            f"{API}/ai/develop/tokens",
            json={"app_id": app["id"], "kind": "workflow", "target_id": 99999999},
            headers=auth_headers,
        )
        assert r.status_code == 404, r.text
    finally:
        test_client.request(
            "DELETE", f"{API}/ai/develop/delete", json=[app["id"]], headers=auth_headers
        )


def test_revoke_unknown_token(test_client, auth_headers):
    r = test_client.put(f"{API}/ai/develop/tokens/99999999/revoke", headers=auth_headers)
    assert r.status_code == 400 and "不存在" in r.text
