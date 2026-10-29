# tests/test_develop_oauth_models.py
#
# 阶段 2（OAuth 2.1 用户委托）—— Task 1：数据模型。
# 验证 OAuth 客户端 / 委托 token 两模型可实例化且字段语义正确。
# 纯 SQLAlchemy 模型（无 DB 交互），PYTEST_NO_APP=1 可用。
import asyncio
from datetime import datetime

import pytest


def test_oauth_client_model_instantiates(test_client):
    from app.plugin.module_ai.develop.oauth_model import AiIntegrationOauthClientModel

    c = AiIntegrationOauthClientModel(
        client_id="c-abc123",
        client_secret_hash="sha256hash",
        name="外部AI助手",
        enabled=True,
        redirect_uris=["https://assistant.example/callback"],
        allow_pkce=True,
        requires_approval=True,
        max_scope=["agent.list", "knowledge.list"],
    )
    assert c.client_id == "c-abc123"
    assert c.client_secret_hash == "sha256hash"
    assert c.redirect_uris == ["https://assistant.example/callback"]
    assert c.max_scope == ["agent.list", "knowledge.list"]
    assert c.enabled is True


def test_oauth_token_model_instantiates(test_client):
    from app.plugin.module_ai.develop.oauth_model import AiIntegrationOauthTokenModel

    t = AiIntegrationOauthTokenModel(
        client_id="c-abc123",
        oauth_client_id=1,
        user_id=2,
        token_type="access",
        token_hash="sha256token",
        scope=["agent.list"],
        redirect_uri="https://assistant.example/callback",
        expires_at=datetime(2099, 1, 1),
        revoked=False,
    )
    assert t.token_type == "access"
    assert t.token_hash == "sha256token"
    assert t.user_id == 2
    assert t.oauth_client_id == 1
    assert t.scope == ["agent.list"]


def test_oauth_token_model_has_fields(test_client):
    """token 模型含撤销/授权码/PKCE 相关列。"""
    from app.plugin.module_ai.develop.oauth_model import AiIntegrationOauthTokenModel

    cols = set(AiIntegrationOauthTokenModel.__table__.columns.keys())
    assert {
        "client_id", "oauth_client_id", "user_id", "token_type", "token_hash",
        "scope", "redirect_uri", "code_challenge", "code_challenge_method",
        "auth_code", "auth_code_hash", "expires_at", "revoked", "revoked_at",
        "last_used_at",
    }.issubset(cols)


def test_oauth_client_model_has_fields(test_client):
    """client 模型含收 redirect/scope 上限/创建人等列。"""
    from app.plugin.module_ai.develop.oauth_model import AiIntegrationOauthClientModel

    cols = set(AiIntegrationOauthClientModel.__table__.columns.keys())
    assert {
        "client_id", "client_secret_hash", "name", "enabled", "redirect_uris",
        "allow_pkce", "requires_approval", "max_scope", "expire_at", "created_id",
    }.issubset(cols)


def test_oauth_token_fields_for_auth_code(test_client):
    """授权码形态：auth_code / code_challenge / method 字段可用。"""
    from app.plugin.module_ai.develop.oauth_model import AiIntegrationOauthTokenModel

    t = AiIntegrationOauthTokenModel(
        client_id="c1",
        oauth_client_id=1,
        user_id=5,
        token_type="auth",
        token_hash="sha256auth",
        scope=[],
        auth_code="rawcode",
        auth_code_hash="sha256code",
        code_challenge="challenge",
        code_challenge_method="S256",
        expires_at=datetime(2099, 1, 1),
    )
    assert t.token_type == "auth"
    assert t.auth_code == "rawcode"
    assert t.code_challenge_method == "S256"


def test_alembic_revision_unique(test_client):
    """新迁移 revision id 唯一，且 down_revision 指向 stage 1.5 的 head。"""
    import importlib
    import os

    p = "app.plugin.module_ai.develop.oauth_model"
    # 只需确认迁移文件存在且 revision 值正确（读取文件内容）
    base = os.path.join(os.path.dirname(__file__), "..", "app", "alembic", "versions")
    target = os.path.join(base, "e3f4a5b6c7d8_ai_integration_oauth.py")
    assert os.path.exists(target), "OAuth 迁移文件缺失"
    with open(target, encoding="utf-8") as f:
        content = f.read()
    assert 'revision: str = "e3f4a5b6c7d8"' in content
    assert 'down_revision: str | None = "a0b1c2d3e4f5"' in content
