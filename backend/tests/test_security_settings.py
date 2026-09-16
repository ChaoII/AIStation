"""安全配置校验测试（SECRET_KEY / ALGORITHM / 推理回调令牌 fail-closed）。

覆盖审计项：
- #2 BLOCKER：非 dev 环境禁止使用源码内置/弱 SECRET_KEY（应用应硬失败）
- #2 加固：拒绝 alg=none 之类的 JWT 算法
- #5 HIGH：推理回调共享密钥禁止沿用公开默认值
"""
import pytest
from pydantic import ValidationError

from app.config.setting import (
    DEFAULT_INSECURE_SECRET_KEY,
    INSECURE_SECRET_KEYS,
    Settings,
    is_placeholder_secret,
)

STRONG_SECRET = "k7Q2mZ9xV4pL1sD8fG3hJ6nB0cR5tY2uW9aE4zX7"
STRONG_INFER_TOKEN = "infer-callback-1f4a9c7e2b8d6035"


def _settings(**overrides) -> Settings:
    """构造 Settings：显式传入的字段优先级最高，避免受 .env / 环境变量干扰。"""
    params: dict = {
        "ENVIRONMENT": "dev",
        "SECRET_KEY": STRONG_SECRET,
        "INFERENCE_CALLBACK_TOKEN": STRONG_INFER_TOKEN,
    }
    params.update(overrides)
    return Settings(**params)


# ------------------------------------------------------------- SECRET_KEY
def test_insecure_secret_allowed_in_dev():
    """dev 环境允许沿用默认密钥（本地开发显式豁免），但不得抛错。"""
    s = _settings(ENVIRONMENT="dev", SECRET_KEY=DEFAULT_INSECURE_SECRET_KEY)
    assert s.SECRET_KEY == DEFAULT_INSECURE_SECRET_KEY


def test_insecure_secret_rejected_in_prod():
    """非 dev 环境使用源码内置默认密钥必须拒绝启动。"""
    with pytest.raises(ValidationError):
        _settings(ENVIRONMENT="prod", SECRET_KEY=DEFAULT_INSECURE_SECRET_KEY)


def test_empty_secret_rejected_in_prod():
    """非 dev 环境空密钥必须拒绝。"""
    with pytest.raises(ValidationError):
        _settings(ENVIRONMENT="prod", SECRET_KEY="")


def test_short_secret_rejected_in_prod():
    """非 dev 环境过短密钥必须拒绝。"""
    with pytest.raises(ValidationError):
        _settings(ENVIRONMENT="prod", SECRET_KEY="short-secret")


def test_strong_secret_accepted_in_prod():
    """非 dev 环境强密钥通过。"""
    s = _settings(ENVIRONMENT="prod", SECRET_KEY=STRONG_SECRET)
    assert s.SECRET_KEY == STRONG_SECRET


def test_known_example_secret_rejected_in_prod():
    """审计文档/示例里出现的已知弱密钥在非 dev 环境同样拒绝。"""
    for weak in ("change-me", "please-change-me", "your_secret_key"):
        assert weak in INSECURE_SECRET_KEYS
        with pytest.raises(ValidationError):
            _settings(ENVIRONMENT="prod", SECRET_KEY=weak)


def test_placeholder_secret_rejected_in_prod():
    """直接从 .env.prod.example 复制、未替换的占位符必须拒绝。"""
    placeholder = "CHANGE_ME_随机生成的强密钥_至少32字符"
    assert is_placeholder_secret(placeholder)
    with pytest.raises(ValidationError):
        _settings(ENVIRONMENT="prod", SECRET_KEY=placeholder)


# ------------------------------------------------------------- ALGORITHM
def test_algorithm_none_rejected():
    """alg=none 会让验签形同虚设，任何环境都拒绝。"""
    with pytest.raises(ValidationError):
        _settings(ALGORITHM="none")


def test_algorithm_unsupported_rejected():
    with pytest.raises(ValidationError):
        _settings(ALGORITHM="RS256")


def test_algorithm_hs256_accepted():
    assert _settings(ALGORITHM="HS256").ALGORITHM == "HS256"


# ------------------------------------------------------------- 推理回调令牌
def test_public_inference_token_rejected_in_prod():
    """公开默认值 infer_callback_shared_secret 不得用于非 dev 环境。"""
    with pytest.raises(ValidationError):
        _settings(ENVIRONMENT="prod", INFERENCE_CALLBACK_TOKEN="infer_callback_shared_secret")


def test_public_inference_token_allowed_in_dev():
    s = _settings(ENVIRONMENT="dev", INFERENCE_CALLBACK_TOKEN="infer_callback_shared_secret")
    assert s.INFERENCE_CALLBACK_TOKEN == "infer_callback_shared_secret"


def test_inference_token_fail_closed_default_is_empty():
    """默认值必须为空（fail-closed），不能是可被猜到/公开的共享密钥。"""
    assert Settings.model_fields["INFERENCE_CALLBACK_TOKEN"].default == ""
