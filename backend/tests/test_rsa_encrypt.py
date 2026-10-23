"""登录密码 RSA 加密工具测试（纯逻辑，无需应用/数据库）。"""

import base64

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.core import rsa_util


def _encrypt_with_public_key(password: str) -> str:
    """模拟前端 WebCrypto 用 RSA-OAEP/SHA-256 加密密码，返回 base64 密文。"""
    pub = serialization.load_der_public_key(
        base64.b64decode(rsa_util.get_public_key_b64())
    )
    cipher = pub.encrypt(
        password.encode("utf-8"),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(cipher).decode()


def test_rsa_password_roundtrip():
    """RSA 公钥加密后能用私钥解回明文。"""
    cipher_b64 = _encrypt_with_public_key("P@ssw0rd!中文密码")
    assert rsa_util.decrypt_password(cipher_b64) == "P@ssw0rd!中文密码"


def test_resolve_password_from_cipher():
    """resolve_password 能把手持 RSA 密文解析回明文。"""
    cipher_b64 = _encrypt_with_public_key("123456")
    assert rsa_util.resolve_password(cipher_b64) == "123456"


def test_resolve_password_plaintext_passthrough():
    """向后兼容：非密文（明文）原样返回，不影响现有明文直连/API 测试。"""
    assert rsa_util.resolve_password("123456") == "123456"
    assert rsa_util.resolve_password("abc-def_ghi") == "abc-def_ghi"
    assert rsa_util.resolve_password("") == ""


def test_public_key_is_stable_within_process():
    """同一进程内公钥重复获取一致（密钥对已持久化）。"""
    assert rsa_util.get_public_key_b64() == rsa_util.get_public_key_b64()
