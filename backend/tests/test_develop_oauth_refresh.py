# tests/test_develop_oauth_refresh.py
#
# 阶段 2（OAuth 2.1）—— Task 4：refresh token 续期（换新后旧 refresh 失效）。
import asyncio
import hashlib

import pytest

from app.core.exceptions import CustomException


def _run(coro):
    return asyncio.run(coro)


def _auth(user_id: int = 1):
    from types import SimpleNamespace

    return SimpleNamespace(user=SimpleNamespace(id=user_id, is_superuser=True))


def _uniq():
    import uuid

    return uuid.uuid4().hex[:8]


async def _seed_client(service):
    from app.plugin.module_ai.develop.oauth_schema import OAuthClientCreateSchema

    data = OAuthClientCreateSchema(
        name=f"测试客户端-{_uniq()}",
        description="测试",
        redirect_uris=["https://assistant.example/callback"],
        max_scope=["agent.list", "knowledge.list"],
    )
    return await service.create_client(data, _auth())


async def _exchange(service, client_dict):
    """刷出一个 refresh_token。"""
    from app.plugin.module_ai.develop.oauth_server import OAuthTokenService

    row = await service.get_client(client_dict["client_id"])
    code = await service.issue_authorization_code(
        row, 1, scope=["agent.list"],
        redirect_uri="https://assistant.example/callback",
        code_challenge=None, code_challenge_method=None,
    )
    return await OAuthTokenService.exchange_code(
        client_id=client_dict["client_id"],
        client_secret=client_dict["client_secret"],
        code=code["code"],
        redirect_uri="https://assistant.example/callback",
        code_verifier=None,
    )


def test_refresh_returns_new_pair(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService, OAuthTokenService

    created = _run(_seed_client(OAuthClientService))
    first = _run(_exchange(OAuthClientService, created))
    assert first["refresh_token"]

    new = _run(OAuthTokenService.refresh(
        client_id=created["client_id"],
        client_secret=created["client_secret"],
        refresh_token=first["refresh_token"],
    ))
    assert new["access_token"]
    assert new["refresh_token"]
    assert new["refresh_token"] != first["refresh_token"]  # 换新
    assert new["token_type"] == "Bearer"


def test_refresh_old_refresh_invalid(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService, OAuthTokenService

    created = _run(_seed_client(OAuthClientService))
    first = _run(_exchange(OAuthClientService, created))
    old_refresh = first["refresh_token"]

    _run(OAuthTokenService.refresh(
        client_id=created["client_id"],
        client_secret=created["client_secret"],
        refresh_token=old_refresh,
    ))
    # 旧 refresh 已被作废 → 再次使用必须失败
    with pytest.raises(CustomException) as exc_info:
        _run(OAuthTokenService.refresh(
            client_id=created["client_id"],
            client_secret=created["client_secret"],
            refresh_token=old_refresh,
        ))
    assert exc_info.value.status_code == 401


def test_refresh_wrong_secret(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService, OAuthTokenService

    created = _run(_seed_client(OAuthClientService))
    first = _run(_exchange(OAuthClientService, created))
    with pytest.raises(CustomException) as exc_info:
        _run(OAuthTokenService.refresh(
            client_id=created["client_id"],
            client_secret="wrong-secret",
            refresh_token=first["refresh_token"],
        ))
    assert exc_info.value.status_code == 401
