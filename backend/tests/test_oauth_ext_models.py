# tests/test_oauth_ext_models.py
#
# 阶段 3a（通用 OAuth client）—— Task 1：外部服务 + 用户 token 两表模型 + Fernet 加密。
# 验证：模型可实例化（字段齐全）、client_secret_hash 列存在、加密解密往返（明文不入库、密文可还原）。
def test_models_instantiate(test_client):
    from app.plugin.module_ai.oauth_ext.model import (
        AiOauthExtServiceModel,
        AiOauthExtTokenModel,
    )

    svc = AiOauthExtServiceModel(
        name="考勤",
        authorize_url="https://x/authorize",
        token_url="https://x/token",
        client_id="c1",
        client_secret_enc="enc-secret",
        client_secret_hash="hash-secret",
        redirect_uri="https://x/cb",
        default_scopes=["attendance"],
        enabled=True,
    )
    assert svc.client_id == "c1"
    assert svc.default_scopes == ["attendance"]
    assert svc.enabled is True

    tok = AiOauthExtTokenModel(
        service_id=1,
        user_id=2,
        access_token_enc="enc-access",
        refresh_token_enc="enc-refresh",
        scope=["attendance"],
        revoked=False,
    )
    assert tok.revoked is False
    assert tok.user_id == 2


def test_encrypt_decrypt_roundtrip(test_client):
    """加密后不是明文，解密可还原（外部 token 必须可还原用于注入）。"""
    from app.plugin.module_ai.oauth_ext.security import (
        decrypt_secret,
        derive_fernet_key,
        encrypt_secret,
    )

    key = derive_fernet_key("some-secret-key-value-32chars-min!!")
    assert len(key) > 0

    plaintext = "my-secret-access-token"
    enc = encrypt_secret("some-secret-key-value-32chars-min!!", plaintext)
    assert enc != plaintext  # 不是明文
    assert decrypt_secret("some-secret-key-value-32chars-min!!", enc) == plaintext


def test_decrypt_with_wrong_key_fails(test_client):
    """用错误 key 解密应失败（不会静默还原错误内容）。"""
    from app.plugin.module_ai.oauth_ext.security import (
        InvalidToken,
        decrypt_secret,
        encrypt_secret,
    )

    enc = encrypt_secret("key-one-0123456789abcdef-0123456789", "token-123")
    try:
        decrypt_secret("key-two-9876543210fedcba-9876543210", enc)
        # 不应走到这里
        assert False, "错误 key 不应解密成功"
    except InvalidToken:
        pass
