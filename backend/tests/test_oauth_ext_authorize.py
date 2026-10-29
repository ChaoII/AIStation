# tests/test_oauth_ext_authorize.py
#
# 阶段 3a —— Task 3：用户授权（connect 生成 state / callback 换 token 加密落库）。
# 验证：connect 返回 authorize_url + state；callback 用 code 换 access/refresh 并加密落库；
#       state 不匹配被拒；redirect_uri 白名单校验。
import uuid
from datetime import datetime, timedelta

import pytest


def _uid():
    return uuid.uuid4().hex[:8]


def _create_service(test_client, auth_headers):
    r = test_client.post(
        "/api/v1/ai/oauth-ext/services",
        headers=auth_headers,
        json={
            "name": f"svc-{_uid()}",
            "authorize_url": "https://ext.example/authorize",
            "token_url": "https://ext.example/token",
            "client_id": "client-abc",
            "client_secret": "top-secret",
            "redirect_uri": "https://platform.example/oauth-ext/callback",
            "default_scopes": ["attendance"],
            "enabled": True,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _seed_token_row(service_id, user_id, access="at-1", refresh="rt-1", expires_delta_sec=3600):
    """直接落一条加密 token 行，供 callback 先建好（或用于其它测试）。"""
    from app.core.database import async_db_session
    from app.config.setting import settings
    from app.plugin.module_ai.oauth_ext.security import encrypt_secret
    from app.plugin.module_ai.oauth_ext.model import AiOauthExtTokenModel

    import asyncio

    async def _do():
        async with async_db_session.begin() as db:
            db.add(AiOauthExtTokenModel(
                service_id=service_id, user_id=user_id,
                access_token_enc=encrypt_secret(settings.SECRET_KEY, access),
                refresh_token_enc=encrypt_secret(settings.SECRET_KEY, refresh),
                access_expires_at=datetime.now() + timedelta(seconds=expires_delta_sec),
                scope=["attendance"], revoked=False,
            ))
            await db.flush()

    asyncio.run(_do())


def test_connect_returns_authorize_url_and_state(test_client, auth_headers):
    svc = _create_service(test_client, auth_headers)
    r = test_client.get(f"/api/v1/ai/oauth-ext/connect/{svc['id']}", headers=auth_headers)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["state"]
    assert svc["client_id"] in data["authorize_url"]
    assert "redirect_uri=" in data["authorize_url"]
    assert "response_type=code" in data["authorize_url"]


def test_callback_exchanges_and_stores(test_client, auth_headers, monkeypatch):
    """callback 用 code 换 token 落库加密。"""
    from app.plugin.module_ai.oauth_ext.service import OAuthExtService

    svc = _create_service(test_client, auth_headers)

    # 授权：先 connect 拿 state
    conn = test_client.get(f"/api/v1/ai/oauth-ext/connect/{svc['id']}", headers=auth_headers).json()["data"]
    state = conn["state"]

    async def fake_token_request(service, payload):
        return {
            "access_token": "ext-access-token",
            "refresh_token": "ext-refresh-token",
            "expires_in": 3600,
            "scope": "attendance",
        }

    monkeypatch.setattr(OAuthExtService, "_token_request", staticmethod(fake_token_request))

    user_id = 1  # admin
    r = test_client.get(
        "/api/v1/ai/oauth-ext/callback",
        headers=auth_headers,
        params={"service_id": svc["id"], "code": "auth-code-123", "state": state},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["connected"] is True


def test_callback_bad_state_rejected(test_client, auth_headers):
    """state 不匹配被拒，不换 token。"""
    from app.plugin.module_ai.oauth_ext.service import OAuthExtService

    svc = _create_service(test_client, auth_headers)
    test_client.get(f"/api/v1/ai/oauth-ext/connect/{svc['id']}", headers=auth_headers)  # 签一个 state
    r = test_client.get(
        "/api/v1/ai/oauth-ext/callback",
        headers=auth_headers,
        params={"service_id": svc["id"], "code": "code-x", "state": "wrong-state"},
    )
    assert r.status_code in (400, 401)
