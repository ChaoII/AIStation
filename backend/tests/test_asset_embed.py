# tests/test_asset_embed.py （PYTEST_NO_APP=1 纯逻辑）
#
# 覆盖「资产嵌入」令牌的纯逻辑（不碰 DB / HTTP）：
# - ``generate_asset_token`` / ``hash_asset_token``：生成与散列往返一致、不含冒号；
# - ``clamp_asset_ttl``：缺省 24h，下限 60s，上限 30 天；
# - ``AiAssetAccessTokenModel``/``ensure_asset_embed_schema`` 结构与 import 可用。
import pytest

from app.plugin.module_ai.asset_embed.service import (
    clamp_asset_ttl,
    generate_asset_token,
    hash_asset_token,
)


def test_generate_token_nocolon_and_hash_roundtrip():
    token = generate_asset_token()
    assert ":" not in token
    assert token
    assert hash_asset_token(token) == hash_asset_token(token)
    assert hash_asset_token("a") != hash_asset_token("b")


def test_clamp_ttl_bounds_and_default():
    assert clamp_asset_ttl(None) == 86400
    assert clamp_asset_ttl(10) == 60
    assert clamp_asset_ttl(999999999) == 2592000
    assert clamp_asset_ttl(3600) == 3600


def test_asset_token_model_table():
    from app.plugin.module_ai.asset_embed.model import AiAssetAccessTokenModel

    assert AiAssetAccessTokenModel.__tablename__ == "ai_asset_access_tokens"
    for col in ("kind", "target_id", "token_hash", "expires_at", "revoked", "use_count"):
        assert col in AiAssetAccessTokenModel.__table__.columns


def test_asset_schema_kind_literal():
    from app.plugin.module_ai.asset_embed.schema import AssetTokenIssueSchema

    assert AssetTokenIssueSchema(kind="agent", target_id=1).target_id == 1
    with pytest.raises(Exception):
        AssetTokenIssueSchema(kind="app", target_id=1)  # 资产不带 app 形态
