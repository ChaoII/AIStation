# tests/test_embed_token.py （PYTEST_NO_APP=1）
"""嵌入短期令牌（P4'）纯逻辑与模型列测试。"""
import hashlib

from app.plugin.module_ai.develop.model import (
    AiIntegrationAccessTokenModel,
    AiIntegrationEmbedSessionModel,
)
from app.plugin.module_ai.develop.service import (
    _generate_embed_token,
    _hash_embed_token,
    clamp_embed_ttl,
)


def test_embed_token_generate_and_hash():
    t = _generate_embed_token()
    assert len(t) >= 32 and ":" not in t
    assert _hash_embed_token(t) == hashlib.sha256(t.encode()).hexdigest()
    assert _generate_embed_token() != _generate_embed_token()


def test_clamp_embed_ttl():
    assert clamp_embed_ttl(None) == 1800
    assert clamp_embed_ttl(30) == 60
    assert clamp_embed_ttl(999999) == 86400
    assert clamp_embed_ttl(3600) == 3600


def test_access_token_model_columns():
    cols = set(AiIntegrationAccessTokenModel.__table__.columns.keys())
    assert {
        "id",
        "app_id",
        "appid",
        "kind",
        "target_id",
        "token_hash",
        "expires_at",
        "revoked",
        "issued_by",
        "use_count",
        "last_used_at",
    }.issubset(cols)
    # 只存散列：token_hash 必须唯一
    assert AiIntegrationAccessTokenModel.__table__.c.token_hash.unique is True
    # 复用 ModelMixin 审计列（软删 + 时间戳）
    assert "is_deleted" in cols and "created_time" in cols


def test_embed_session_model_columns_and_unique():
    t = AiIntegrationEmbedSessionModel.__table__
    assert {
        "id",
        "app_id",
        "sid",
        "kind",
        "target_id",
        "session_id",
        "expires_at",
        "last_active_at",
    }.issubset(set(t.columns.keys()))
    # (app_id, sid) 复合唯一：防跨应用 sid 撞号
    unis = [c for c in t.constraints if c.__class__.__name__ == "UniqueConstraint"]
    assert any({col.name for col in u.columns} == {"app_id", "sid"} for u in unis)
