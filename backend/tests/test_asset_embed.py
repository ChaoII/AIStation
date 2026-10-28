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
    match_whitelist,
    parse_origin_host,
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


def test_asset_token_whitelist_columns():
    from app.plugin.module_ai.asset_embed.model import (
        AiAssetAccessTokenModel,
        AiAssetEmbedLogModel,
    )

    assert "allow_domains" in AiAssetAccessTokenModel.__table__.columns
    assert "allow_ips" in AiAssetAccessTokenModel.__table__.columns
    assert "token_id" in AiAssetEmbedLogModel.__table__.columns
    assert "client_ip" in AiAssetEmbedLogModel.__table__.columns


def test_parse_origin_host():
    assert parse_origin_host("https://a.com/x") == "a.com"
    assert parse_origin_host("http://a.com:8080/p") == "a.com"
    assert parse_origin_host("https://Sub.Example.COM/x") == "sub.example.com"
    assert parse_origin_host(None) is None
    assert parse_origin_host("") is None
    assert parse_origin_host("not-a-url") is None


def test_match_whitelist():
    # 两者都空 = 不限（兼容旧令牌）
    assert match_whitelist(None, None, None, "1.2.3.4") is True
    assert match_whitelist("", "", None, "1.2.3.4") is True
    # 域名命中（大小写/空白容忍）
    assert match_whitelist("a.com, b.com", None, "B.COM", "9.9.9.9") is True
    # 域名不命中且无 IP → False
    assert match_whitelist("a.com", None, "c.com", "9.9.9.9") is False
    # IP 命中
    assert match_whitelist(None, "1.2.3.4, 5.6.7.8", None, "5.6.7.8") is True
    # IP 不命中且无域名 → False
    assert match_whitelist(None, "1.2.3.4", None, "9.9.9.9") is False
    # 都配了也没有命中 → False
    assert match_whitelist("a.com", "1.2.3.4", "b.com", "9.9.9.9") is False


def test_asset_schema_kind_literal():
    from pydantic import ValidationError

    from app.plugin.module_ai.asset_embed.schema import AssetTokenIssueSchema

    assert AssetTokenIssueSchema(kind="agent", target_id=1).target_id == 1
    with pytest.raises(ValidationError):
        AssetTokenIssueSchema(kind="app", target_id=1)  # 资产不带 app 形态
