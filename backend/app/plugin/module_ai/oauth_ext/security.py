"""AI 集成开放平台 —— 阶段 3a：外部 token 加密封装。

外部 access/refresh token 必须**可还原**（平台要用它调外部 API 注入 Bearer），
故与阶段 2（委托 token 只存散列）不同，这里用 ``cryptography.Fernet`` 加密存储。

密钥由平台 ``SECRET_KEY`` 派生：``base64.urlsafe_b64encode(sha256(secret_key))``，
满足 Fernet 的 32 字节 urlsafe base64 要求。明文仅在注入时内存中出现，不落库、不落日志。
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken  # noqa: F401  # 供外界引用


def derive_fernet_key(secret_key: str) -> bytes:
    """从平台 ``SECRET_KEY`` 派生 Fernet 密钥（32 字节 urlsafe base64）。"""
    digest = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(secret_key: str, plaintext: str) -> str:
    """加密明文，返回 Fernet 密文字符串。"""
    return Fernet(derive_fernet_key(secret_key)).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(secret_key: str, ciphertext: str) -> str:
    """解密 Fernet 密文，返回明文；密钥/密文非法时抛 ``InvalidToken``。"""
    return Fernet(derive_fernet_key(secret_key)).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
