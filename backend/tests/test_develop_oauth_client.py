# tests/test_develop_oauth_client.py
#
# 阶段 2（OAuth 2.1）—— Task 2：OAuth 客户端 CRUD + 授权码签发。
# 验证：创建返回一次性 secret（库中仅散列）、redirect_uri 白名单、scope 上限、PKCE。
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


async def _seed_client(service, name=None, redirect_uris=None, max_scope=None, allow_pkce=True):
    from app.plugin.module_ai.develop.oauth_schema import OAuthClientCreateSchema

    data = OAuthClientCreateSchema(
        name=name or f"测试客户端-{_uniq()}",
        description="测试客户端",
        redirect_uris=redirect_uris or ["https://assistant.example/callback"],
        allow_pkce=allow_pkce,
        max_scope=max_scope or ["agent.list", "knowledge.list"],
    )
    return await service.create_client(data, _auth())


async def _get_row_client_id(client_id: str):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService

    return await OAuthClientService.get_client(client_id)


def test_create_client_returns_secret_once(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService

    created = _run(_seed_client(OAuthClientService))
    assert created["client_id"]
    assert created["client_secret"]  # 一次性明文
    assert "client_secret_hash" not in created  # 不泄出散列

    # 库中只存散列，明文 ≠ 散列
    row = _run(_get_row_client_id(created["client_id"]))
    assert row is not None
    assert row.client_secret_hash != created["client_secret"]
    assert len(row.client_secret_hash) == 64  # sha256 hex


def test_create_client_name_unique(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService

    _run(_seed_client(OAuthClientService, name="重名客户端"))
    with pytest.raises(CustomException) as exc_info:
        _run(_seed_client(OAuthClientService, name="重名客户端"))
    assert exc_info.value.status_code == 400


def test_verify_client_credentials(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService

    created = _run(_seed_client(OAuthClientService))
    ok = _run(OAuthClientService.verify_client_credentials(created["client_id"], created["client_secret"]))
    assert ok is not None and ok.client_id == created["client_id"]
    bad = _run(OAuthClientService.verify_client_credentials(created["client_id"], "wrong"))
    assert bad is None


def test_issue_code_redirect_uri_whitelist(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService

    created = _run(_seed_client(OAuthClientService))
    row = _run(_get_row_client_id(created["client_id"]))
    with pytest.raises(CustomException) as exc_info:
        _run(OAuthClientService.issue_authorization_code(
            row, 100, scope=["agent.list"], redirect_uri="https://evil.example/cb",
            code_challenge=None, code_challenge_method=None,
        ))
    assert exc_info.value.status_code == 400


def test_issue_code_scope_exceeds_max(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService

    created = _run(_seed_client(OAuthClientService, max_scope=["agent.list"]))
    row = _run(_get_row_client_id(created["client_id"]))
    with pytest.raises(CustomException) as exc_info:
        _run(OAuthClientService.issue_authorization_code(
            row, 100, scope=["agent.list", "model.list"], redirect_uri="https://assistant.example/callback",
            code_challenge=None, code_challenge_method=None,
        ))
    assert exc_info.value.status_code == 400
    assert "超出客户端可授权范围" in exc_info.value.msg


def test_issue_code_pkce_challenge(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService

    created = _run(_seed_client(OAuthClientService, allow_pkce=True))
    row = _run(_get_row_client_id(created["client_id"]))
    result = _run(OAuthClientService.issue_authorization_code(
        row, 100, scope=["agent.list"], redirect_uri="https://assistant.example/callback",
        code_challenge="abcchallenge", code_challenge_method="S256",
    ))
    assert result["code"]

    # 授权码行已落库（token_type='auth'）
    from app.plugin.module_ai.develop.oauth_model import AiIntegrationOauthTokenModel
    from app.core.database import async_db_session

    async def find_auth():
        from sqlalchemy import select
        async with async_db_session() as db:
            return (
                await db.execute(
                    select(AiIntegrationOauthTokenModel).where(
                        AiIntegrationOauthTokenModel.token_type == "auth",
                        AiIntegrationOauthTokenModel.client_id == created["client_id"],
                    ).order_by(AiIntegrationOauthTokenModel.id.desc())
                )
            ).scalars().first()

    token_row = _run(find_auth())
    assert token_row is not None
    assert token_row.code_challenge == "abcchallenge"
    assert token_row.code_challenge_method == "S256"
    assert token_row.auth_code_hash != "abcchallenge"  # 不存明文


def test_issue_code_rejects_pkce_when_disallowed(test_client):
    from app.plugin.module_ai.develop.oauth_server import OAuthClientService

    created = _run(_seed_client(OAuthClientService, allow_pkce=False))
    row = _run(_get_row_client_id(created["client_id"]))
    with pytest.raises(CustomException) as exc_info:
        _run(OAuthClientService.issue_authorization_code(
            row, 100, scope=["agent.list"], redirect_uri="https://assistant.example/callback",
            code_challenge="abc", code_challenge_method="S256",
        ))
    assert exc_info.value.status_code == 400
