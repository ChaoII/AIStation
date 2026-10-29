# tests/test_oauth_ext_token_lifecycle.py
#
# 阶段 3a —— Task 4：token 刷新 / 撤销 / 连接状态。
# 验证：access 过期用 refresh 静默换新；用户可撤销外部授权；状态接口区分
#       未连接/已连接/已撤销。直接调用 service 层方法（走 SQLite + 加密）。
import asyncio
import uuid
from datetime import datetime, timedelta

import pytest


def _uid():
    return uuid.uuid4().hex[:8]


@pytest.fixture
def svc_row(test_client, auth_headers):
    """登记一个外部服务，返回 (service_id)。"""
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
    return r.json()["data"]["id"]


def _make_token_row(service_id, user_id, access="at", refresh="rt", expires_delta_sec=3600):
    from app.config.setting import settings
    from app.plugin.module_ai.oauth_ext.model import AiOauthExtTokenModel
    from app.plugin.module_ai.oauth_ext.security import encrypt_secret
    from app.core.database import async_db_session

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


def test_refresh_exchanges_new_access(svc_row, monkeypatch):
    """access 过期时用 refresh 换新 access 并回写。"""
    from app.plugin.module_ai.oauth_ext.service import OAuthExtService

    user_id = 1
    _make_token_row(svc_row, user_id, access="old-at", refresh="rt", expires_delta_sec=-10)  # 已过期

    async def fake_refresh(service, token_row):
        return {"access_token": "new-at", "refresh_token": "new-rt", "expires_in": 3600, "scope": "attendance"}

    monkeypatch.setattr(OAuthExtService, "_refresh_request", staticmethod(fake_refresh))

    access = asyncio.run(OAuthExtService.resolve_ext_access_token(svc_row, user_id))
    assert access == "new-at"


def test_revoke_marks_and_status(svc_row, test_client, auth_headers):
    """撤销后连接状态为已撤销，且不可用。"""
    from app.plugin.module_ai.oauth_ext.service import OAuthExtService

    user_id = 1
    _make_token_row(svc_row, user_id)
    st = asyncio.run(OAuthExtService.connection_status(svc_row, user_id))
    assert st["connected"] is True

    res = asyncio.run(OAuthExtService.revoke(svc_row, user_id))
    assert res is not None

    st2 = asyncio.run(OAuthExtService.connection_status(svc_row, user_id))
    assert st2["connected"] is False
    assert st2["revoked"] is True


def test_status_not_connected(svc_row):
    """未连接时 connected=False。"""
    from app.plugin.module_ai.oauth_ext.service import OAuthExtService

    user_id = 99
    st = asyncio.run(OAuthExtService.connection_status(svc_row, user_id))
    assert st["connected"] is False
