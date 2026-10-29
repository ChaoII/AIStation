# tests/test_develop_oauth_revoke_auth.py
#
# 阶段 2（OAuth 2.1）—— Task 5：revoke 撤销 + AppContext.user_id + get_oauth_api_auth。
import asyncio

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


async def _exchange_oauth(service, client_dict, user_id=1):
    """走完整授权码流程，刷出 access_token。"""
    from app.plugin.module_ai.develop.oauth_server import OAuthTokenService

    row = await service.get_client(client_dict["client_id"])
    code = await service.issue_authorization_code(
        row, user_id, scope=["agent.list"],
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


def test_revoke_invalidates_token(test_client):
    from app.plugin.module_ai.develop.oauth_auth import get_oauth_api_auth
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService, OAuthTokenService

    created = _run(_seed_client(OAuthClientService))
    pair = _run(_exchange_oauth(OAuthClientService, created))
    access_token = pair["access_token"]

    # 撤销前：可鉴权
    ctx = _run(get_oauth_api_auth(f"Bearer {access_token}"))
    assert ctx.user_id == 1

    _run(OAuthTokenService.revoke(access_token))

    # 撤销后：必须 401
    with pytest.raises(CustomException) as exc_info:
        _run(get_oauth_api_auth(f"Bearer {access_token}"))
    assert exc_info.value.status_code == 401


def test_get_oauth_api_auth_builds_ctx(test_client):
    from app.plugin.module_ai.develop.oauth_auth import get_oauth_api_auth
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService

    created = _run(_seed_client(OAuthClientService))
    pair = _run(_exchange_oauth(OAuthClientService, created, user_id=42))
    access_token = pair["access_token"]

    ctx = _run(get_oauth_api_auth(f"Bearer {access_token}"))
    assert ctx.user_id == 42  # token.sub
    assert ctx.owner_user_id == 42
    assert ctx.source_type == "oauth"
    assert ctx.grants == {"agent.list"}
    assert "agent.list" in (ctx.oauth_scope or set())


def test_get_oauth_api_auth_bad_token_401(test_client):
    from app.plugin.module_ai.develop.oauth_auth import get_oauth_api_auth

    with pytest.raises(CustomException) as exc_info:
        _run(get_oauth_api_auth("Bearer not-a-real-token"))
    assert exc_info.value.status_code == 401
