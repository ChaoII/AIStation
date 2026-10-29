# tests/test_develop_oauth_token_exchange.py
#
# 阶段 2（OAuth 2.1）—— Task 3：授权码 → token 换取（一次性）。
# 验证：换取返回 access/refresh 对；同 code 二次换取必须失败；PKCE verifier 校验。
import asyncio
from datetime import datetime, timedelta

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


async def _seed_client(service, max_scope=None, allow_pkce=True):
    from app.plugin.module_ai.develop.oauth_schema import OAuthClientCreateSchema

    data = OAuthClientCreateSchema(
        name=f"测试客户端-{_uniq()}",
        description="测试",
        redirect_uris=["https://assistant.example/callback"],
        allow_pkce=allow_pkce,
        max_scope=max_scope or ["agent.list", "knowledge.list"],
    )
    return await service.create_client(data, _auth())


async def _issue_code(service, client_dict, *, scope=None, challenge=None, method=None, user_id=1):
    row = await service.get_client(client_dict["client_id"])
    return await service.issue_authorization_code(
        row, user_id,
        scope=scope or ["agent.list"],
        redirect_uri="https://assistant.example/callback",
        code_challenge=challenge,
        code_challenge_method=method,
    )


def test_exchange_code_returns_token_pair(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService, OAuthTokenService

    created = _run(_seed_client(OAuthClientService))
    code = _run(_issue_code(OAuthClientService, created))["code"]

    result = _run(OAuthTokenService.exchange_code(
        client_id=created["client_id"],
        client_secret=created["client_secret"],
        code=code,
        redirect_uri="https://assistant.example/callback",
        code_verifier=None,
    ))
    assert result["access_token"]
    assert result["refresh_token"]
    assert result["token_type"] == "Bearer"
    assert result["expires_in"] > 0
    assert "agent.list" in result["scope"]


def test_exchange_code_code_used_once(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService, OAuthTokenService

    created = _run(_seed_client(OAuthClientService))
    code = _run(_issue_code(OAuthClientService, created))["code"]

    _run(OAuthTokenService.exchange_code(
        client_id=created["client_id"],
        client_secret=created["client_secret"],
        code=code,
        redirect_uri="https://assistant.example/callback",
        code_verifier=None,
    ))
    # 同 code 二次换取 → 必须失败
    with pytest.raises(CustomException) as exc_info:
        _run(OAuthTokenService.exchange_code(
            client_id=created["client_id"],
            client_secret=created["client_secret"],
            code=code,
            redirect_uri="https://assistant.example/callback",
            code_verifier=None,
        ))
    assert exc_info.value.status_code == 400


def test_exchange_code_pkce_verifier(test_client):
    import hashlib

    from app.plugin.module_ai.develop.oauth_server import OAuthClientService, OAuthTokenService

    created = _run(_seed_client(OAuthClientService))
    verifier = "some-random-verifier-value"
    challenge = hashlib.sha256(verifier.encode("utf-8")).hexdigest()
    code = _run(_issue_code(
        OAuthClientService, created,
        scope=["knowledge.list"],
        challenge=challenge, method="S256",
    ))["code"]

    # 错误 verifier → 拒绝
    with pytest.raises(CustomException) as exc_info:
        _run(OAuthTokenService.exchange_code(
            client_id=created["client_id"],
            client_secret=created["client_secret"],
            code=code,
            redirect_uri="https://assistant.example/callback",
            code_verifier="wrong-verifier",
        ))
    assert exc_info.value.status_code == 400

    # 正确 verifier → 通过
    result = _run(OAuthTokenService.exchange_code(
        client_id=created["client_id"],
        client_secret=created["client_secret"],
        code=code,
        redirect_uri="https://assistant.example/callback",
        code_verifier=verifier,
    ))
    assert result["access_token"]
    assert "knowledge.list" in result["scope"]


def test_exchange_code_client_secret_wrong(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService, OAuthTokenService

    created = _run(_seed_client(OAuthClientService))
    code = _run(_issue_code(OAuthClientService, created))["code"]
    with pytest.raises(CustomException) as exc_info:
        _run(OAuthTokenService.exchange_code(
            client_id=created["client_id"],
            client_secret="wrong-secret",
            code=code,
            redirect_uri="https://assistant.example/callback",
            code_verifier=None,
        ))
    assert exc_info.value.status_code == 401
