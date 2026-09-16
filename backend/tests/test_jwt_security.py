"""JWT 签发/校验加固测试：签发者、过期时间、算法白名单（含 alg=none）。"""
import base64
import json
from datetime import datetime, timedelta

import jwt
import pytest

from app.api.v1.module_system.auth.schema import JWTPayloadSchema
from app.config.setting import settings
from app.core.exceptions import CustomException
from app.core.security import create_access_token, decode_access_token


def _b64(obj: dict) -> str:
    raw = json.dumps(obj, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _payload(sub: str = '{"user_id":1,"user_name":"admin"}', exp_minutes: int = 5) -> JWTPayloadSchema:
    return JWTPayloadSchema(
        sub=sub,
        is_refresh=False,
        exp=datetime.now() + timedelta(minutes=exp_minutes),
    )


def test_created_token_carries_issuer():
    """签发 token 时必须带上 iss，供 WS/HTTP 校验签发者。"""
    token = create_access_token(_payload())
    decoded = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"verify_iss": False},
    )
    assert decoded["iss"] == settings.JWT_ISSUER


def test_decode_accepts_valid_token():
    decoded = decode_access_token(create_access_token(_payload()))
    assert decoded.sub


def test_decode_rejects_alg_none():
    """alg=none 的无签名 token 必须拒绝。"""
    token = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64({'sub': '{}', 'exp': 9999999999})}."
    with pytest.raises(CustomException) as ei:
        decode_access_token(token)
    assert ei.value.status_code == 401


def test_decode_rejects_wrong_issuer():
    """使用相同密钥但签发者不同（iss 不匹配）必须拒绝。"""
    token = jwt.encode(
        {"sub": '{"user_id":1,"user_name":"admin"}', "is_refresh": False, "exp": datetime.now() + timedelta(minutes=5), "iss": "evil-issuer"},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(CustomException) as ei:
        decode_access_token(token)
    assert ei.value.status_code == 401


def test_decode_rejects_expired_token():
    token = create_access_token(_payload(exp_minutes=-5))
    with pytest.raises(CustomException) as ei:
        decode_access_token(token)
    assert ei.value.status_code == 401


def test_decode_rejects_missing_exp():
    """缺少 exp 的 token 必须拒绝（不得依赖默认不过期）。"""
    token = jwt.encode(
        {"sub": '{"user_id":1,"user_name":"admin"}', "is_refresh": False, "iss": settings.JWT_ISSUER},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(CustomException) as ei:
        decode_access_token(token)
    assert ei.value.status_code == 401


def test_decode_rejects_empty():
    for bad in ("", None):
        with pytest.raises(CustomException) as ei:
            decode_access_token(bad)  # type: ignore[arg-type]
        assert ei.value.status_code == 401
