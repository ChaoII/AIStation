"""登录密码 RSA 加密工具。

前端用服务端下发的 RSA 公钥（RSA-OAEP/SHA-256）对密码加密后再发送，
请求体不再出现明文密码；后端用私钥解密后用现有 bcrypt 校验（向后兼容，
存量密码哈希不变，现有用户登录方式不受影响）。

密钥对在首次启动时生成并持久化到 backend/keys/login_rsa_private.pem
（该目录已 gitignore），重启复用同一私钥，保证前端获取的公钥与后端解密一致。
"""

import base64
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

# backend 根目录（app/core/rsa_util.py 上溯两级得到 .../backend）
_BACKEND_ROOT: Path = Path(__file__).resolve().parents[2]
_PRIVATE_KEY_FILE: Path = _BACKEND_ROOT / "keys" / "login_rsa_private.pem"


@lru_cache(maxsize=1)
def _get_private_key() -> rsa.RSAPrivateKey:
    """加载或首次生成并持久化 RSA 私钥（2048 位）。"""
    if _PRIVATE_KEY_FILE.exists():
        return serialization.load_pem_private_key(
            _PRIVATE_KEY_FILE.read_bytes(), password=None
        )
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _PRIVATE_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PRIVATE_KEY_FILE.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return key


def get_public_key_b64() -> str:
    """返回 RSA 公钥（SPKI/DER，base64），供前端 WebCrypto importKey。"""
    pub_bytes = _get_private_key().public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return base64.b64encode(pub_bytes).decode("ascii")


def decrypt_password(cipher_b64: str) -> str | None:
    """用私钥解密前端 RSA-OAEP 加密的密码；解密失败（如非密文）返回 None。"""
    try:
        cipher = base64.b64decode(cipher_b64)
        plain = _get_private_key().decrypt(
            cipher,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )
        return plain.decode("utf-8")
    except Exception:
        return None


def resolve_password(candidate: str) -> str:
    """把登录/注册/改密等接口收到的 password 字段解析为明文。

    若是 RSA 密文则用私钥解密；否则原样返回（向后兼容明文直连 / API 测试）。
    """
    if not candidate:
        return candidate
    plain = decrypt_password(candidate)
    return plain if plain is not None else candidate
