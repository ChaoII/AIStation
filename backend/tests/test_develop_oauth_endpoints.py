# tests/test_develop_oauth_endpoints.py
#
# 阶段 2（OAuth 2.1）—— Task 6：OAuth server 端点（authorize/token/revoke/userinfo）
# + REST 数据面（委托 token 调用能力）集成测试。
import hashlib


def _ip_headers(extra=None):
    """OperationLogRoute 需合法 request_ip；TestClient 缺省 host='testclient' 会 400。"""
    headers = {"X-Forwarded-For": "127.0.0.1"}
    if extra:
        headers.update(extra)
    return headers


def _create_client(test_client, auth_headers):
    """经管理面创建 OAuth 客户端，返回 dict（含一次性 client_secret）。"""
    import uuid

    r = test_client.post(
        "/api/v1/ai/develop/oauth/clients",
        headers=auth_headers,
        json={
            "name": f"e2e-oauth-client-{uuid.uuid4().hex[:8]}",
            "redirect_uris": ["https://assistant.example/callback"],
            "max_scope": ["agent.list", "knowledge.list"],
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _authorize(test_client, auth_headers, client_id, scope, redirect, **extra):
    return test_client.post(
        "/api/v1/ai/develop/oauth/authorize",
        headers=auth_headers,
        json={
            "client_id": client_id,
            "scope": scope,
            "redirect_uri": redirect,
            **extra,
        },
    )


def _token(test_client, client_id, client_secret, code, verifier=None, redirect=None):
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect or "https://assistant.example/callback",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    if verifier is not None:
        data["code_verifier"] = verifier
    return test_client.post("/api/v1/ai/develop/oauth/token", data=data, headers=_ip_headers())


def test_oauth_client_crud_and_endpoint_flow(test_client, auth_headers):
    """完整链路：创建 client -> authorize 签发 code -> token 换对 -> userinfo -> revoke。"""
    # 1. 创建 client（带一次性 secret）
    created = _create_client(test_client, auth_headers)
    assert created["client_id"]
    assert created["client_secret"]
    assert "client_secret_hash" not in created

    # 2. 列表校验
    listing = test_client.get("/api/v1/ai/develop/oauth/clients", headers=auth_headers)
    assert listing.status_code == 200
    assert any(c["client_id"] == created["client_id"] for c in listing.json()["data"]["items"])

    # 3. authorize 签发授权码（带登录态）
    authz = _authorize(
        test_client, auth_headers, created["client_id"], ["agent.list"],
        "https://assistant.example/callback", state="xyz-state",
    )
    assert authz.status_code == 200, authz.text
    code = authz.json()["data"]["code"]
    assert code
    assert authz.json()["data"]["state"] == "xyz-state"

    # 4. token 换取
    tok = _token(test_client, created["client_id"], created["client_secret"], code)
    assert tok.status_code == 200, tok.text
    token_data = tok.json()
    assert token_data["access_token"]
    assert token_data["refresh_token"]
    assert token_data["token_type"] == "Bearer"

    # 5. userinfo（委托 token）
    ui = test_client.get(
        "/api/v1/ai/develop/oauth/userinfo",
        headers=_ip_headers({"Authorization": f"Bearer {token_data['access_token']}"}),
    )
    assert ui.status_code == 200, ui.text
    assert ui.json()["data"]["scope"] == ["agent.list"]

    # 6. revoke 后 userinfo 必须 401
    rv = test_client.post(
        "/api/v1/ai/develop/oauth/revoke",
        data={"token": token_data["access_token"]},
        headers=_ip_headers(),
    )
    assert rv.status_code == 200, rv.text
    ui2 = test_client.get(
        "/api/v1/ai/develop/oauth/userinfo",
        headers=_ip_headers({"Authorization": f"Bearer {token_data['access_token']}"}),
    )
    assert ui2.status_code == 401, ui2.text


def test_oauth_pkce_flow(test_client, auth_headers):
    """PKCE 公共客户端：S256 verifier 校验通过才换 token。"""
    created = _create_client(test_client, auth_headers)
    verifier = "e2e-pkce-verifier-value"
    challenge = hashlib.sha256(verifier.encode("utf-8")).hexdigest()

    authz = _authorize(
        test_client, auth_headers, created["client_id"], ["knowledge.list"],
        "https://assistant.example/callback",
        code_challenge=challenge, code_challenge_method="S256",
    )
    assert authz.status_code == 200, authz.text
    code = authz.json()["data"]["code"]

    # 错误 verifier -> 400
    bad = _token(test_client, created["client_id"], created["client_secret"], code, verifier="wrong-verifier")
    assert bad.status_code in (400, 401)

    # 正确 verifier -> 200
    ok = _token(test_client, created["client_id"], created["client_secret"], code, verifier=verifier)
    assert ok.status_code == 200, ok.text
    assert ok.json()["access_token"]


def test_oauth_authorize_rejects_bad_redirect(test_client, auth_headers):
    """非白名单 redirect_uri 被拒。"""
    created = _create_client(test_client, auth_headers)
    authz = _authorize(
        test_client, auth_headers, created["client_id"], ["agent.list"],
        "https://evil.example/cb",
    )
    assert authz.status_code == 400, authz.text


def test_oauth_data_invoke_denied_without_scope(test_client, auth_headers):
    """委托 token 未授权某能力时，调数据面 403。"""
    created = _create_client(test_client, auth_headers)
    authz = _authorize(
        test_client, auth_headers, created["client_id"], ["agent.list"],
        "https://assistant.example/callback",
    )
    assert authz.status_code == 200, authz.text
    code = authz.json()["data"]["code"]
    tok = _token(test_client, created["client_id"], created["client_secret"], code)
    assert tok.status_code == 200, tok.text
    access = tok.json()["access_token"]

    # 未授权能力 -> 403
    inv = test_client.post(
        "/api/v1/ai/develop-api/oauth/capabilities/model.list",
        headers=_ip_headers({"Authorization": f"Bearer {access}"}),
        json={"payload": {}},
    )
    assert inv.status_code == 403, inv.text
