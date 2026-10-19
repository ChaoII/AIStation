"""simple mode 配置项测试（TORKILN_* 区块新增字段）。

覆盖：
- 默认值：TORKILN_MODE="container"、回调令牌为空（fail-closed）、
  环境轮询间隔 5.0 秒、最大并发 4
- 环境变量覆盖：TORKILN_MODE=simple 可覆盖默认值
- Literal 校验：非法值（如 bogus）触发 pydantic ValidationError

纯逻辑测试，可用 PYTEST_NO_APP=1 快速模式运行（不构造应用）。
"""
import pytest
from pydantic import ValidationError

from app.config.setting import Settings, settings


# ------------------------------------------------------------- 默认值
def test_default_mode_is_container():
    """默认必须是 container 模式（存量行为不变，simple 是显式开关）。"""
    assert settings.TORKILN_MODE == "container"


def test_default_simple_callback_token_is_empty():
    """simple 模式回调令牌默认为空（fail-closed，未配置应拒绝回调）。"""
    assert settings.TORKILN_SIMPLE_CALLBACK_TOKEN == ""


def test_default_simple_env_interval_is_5():
    """simple 模式训练环境（子进程）健康轮询间隔默认 5 秒。"""
    assert settings.TORKILN_SIMPLE_ENV_INTERVAL == 5.0


def test_default_simple_max_concurrent_is_4():
    """simple 模式最大并发默认 4（与 job 容器模式端口段容量建议一致）。"""
    assert settings.TORKILN_SIMPLE_MAX_CONCURRENT == 4


# ------------------------------------------------------------- 环境变量覆盖
def test_env_override_mode_simple(monkeypatch):
    """TORKILN_MODE=simple 环境变量可覆盖默认值（用新实例避免单例污染）。"""
    monkeypatch.setenv("TORKILN_MODE", "simple")
    assert Settings().TORKILN_MODE == "simple"


def test_env_override_mode_container(monkeypatch):
    """TORKILN_MODE=container 显式配置时保持 container。"""
    monkeypatch.setenv("TORKILN_MODE", "container")
    assert Settings().TORKILN_MODE == "container"


# ------------------------------------------------------------- Literal 校验
def test_invalid_mode_rejected(monkeypatch):
    """非法的 TORKILN_MODE 值必须触发 pydantic ValidationError（Literal 校验）。"""
    monkeypatch.setenv("TORKILN_MODE", "bogus")
    with pytest.raises(ValidationError):
        Settings()
