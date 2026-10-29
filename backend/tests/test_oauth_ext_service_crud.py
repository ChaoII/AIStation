# tests/test_oauth_ext_service_crud.py
#
# 阶段 3a —— Task 2：外部服务 CRUD（管理面）。
# 验证：管理员可登记外部 OAuth 服务；创建返回一次性明文 client_secret；
#       列表/详情不含 client_secret_hash；更新/启停。
import uuid


def _uid():
    return uuid.uuid4().hex[:8]


def _svc_payload(name=None):
    return {
        "name": name or f"svc-{_uid()}",
        "authorize_url": "https://ext.example/authorize",
        "token_url": "https://ext.example/token",
        "client_id": "client-abc",
        "client_secret": "top-secret",
        "redirect_uri": "https://platform.example/oauth-ext/callback",
        "default_scopes": ["attendance"],
        "enabled": True,
    }


def test_service_create_returns_secret_once(test_client, auth_headers):
    """创建返回含明文 client_secret（仅一次）；列表/详情不含 client_secret_hash。"""
    r = test_client.post("/api/v1/ai/oauth-ext/services", headers=auth_headers, json=_svc_payload())
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["client_secret"] == "top-secret"  # 一次明文
    assert "client_secret_hash" not in data
    assert "client_secret_enc" not in data  # 密文也不回显
    assert data["name"].startswith("svc-")


def test_service_list_hides_secret(test_client, auth_headers):
    test_client.post("/api/v1/ai/oauth-ext/services", headers=auth_headers, json=_svc_payload())
    listing = test_client.get("/api/v1/ai/oauth-ext/services", headers=auth_headers)
    assert listing.status_code == 200, listing.text
    items = listing.json()["data"]["items"]
    assert len(items) >= 1
    for it in items:
        assert "client_secret_hash" not in it
        assert "client_secret_enc" not in it


def test_service_update_and_toggle(test_client, auth_headers):
    created = test_client.post("/api/v1/ai/oauth-ext/services", headers=auth_headers, json=_svc_payload()).json()["data"]
    sid = created["id"]
    r = test_client.put(f"/api/v1/ai/oauth-ext/services/{sid}", headers=auth_headers, json={"name": f"svc-{_uid()}", "enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["enabled"] is False


def test_service_create_name_duplicate_rejected(test_client, auth_headers):
    """同名服务创建被拒（name 唯一）。"""
    payload = _svc_payload(name="dup-svc")
    r1 = test_client.post("/api/v1/ai/oauth-ext/services", headers=auth_headers, json=payload)
    assert r1.status_code == 200, r1.text
    r2 = test_client.post("/api/v1/ai/oauth-ext/services", headers=auth_headers, json=_svc_payload(name="dup-svc"))
    assert r2.status_code in (400, 409)
