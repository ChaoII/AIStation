# tests/test_develop_auth.py （PYTEST_NO_APP=1 纯逻辑）
#
# 覆盖 AI 集成开放平台「开放数据面」的鉴权依赖纯逻辑：
# - ``AppContext``：鉴权后的应用上下文（授权能力码 + 出口）；
# - ``_parse_bearer``：解析 ``Authorization: Bearer <appid>:<appkey>``（appkey 可含冒号）；
# - ``require_capability``：按「能力码 + 出口」校验（未授权/未开放出口抛 10403）。
# 注：``get_app_api_auth`` 属于 FastAPI 依赖，需经 HTTP 触发，留给集成用例验证。
import pytest

from app.core.exceptions import CustomException
from app.plugin.module_ai.develop.auth import AppContext, _parse_bearer, require_capability


def _ctx(grants=None, channels=None):
    return AppContext(
        app_id=1,
        appid="ai_x",
        grants=set(grants or []),
        channels=channels or {},
        quota=None,
        app={},
    )


def test_parse_bearer_valid():
    assert _parse_bearer("Bearer ai_x:abc:def") == ("ai_x", "abc:def")  # rsplit：appkey 可含冒号


def test_parse_bearer_missing_or_malformed():
    assert _parse_bearer(None) is None
    assert _parse_bearer("") is None
    assert _parse_bearer("Basic xxx") is None
    assert _parse_bearer("Bearer no-colon") is None


def test_require_capability_ok_and_denied():
    ctx = _ctx(grants={"agent.list"}, channels={"agent.list": {"rest", "mcp"}})
    require_capability(ctx, "agent.list", "rest")  # 不抛
    require_capability(ctx, "agent.list", "mcp")  # 不抛
    with pytest.raises(CustomException) as ei:
        require_capability(ctx, "agent.list", "rest") if False else require_capability(
            ctx, "agent.get", "rest"
        )
    assert ei.value.code == 10403


def test_require_capability_channel_not_open():
    # 已授权但未开放 mcp 出口 → 仍拒绝
    ctx = _ctx(grants={"agent.list"}, channels={"agent.list": {"rest"}})
    require_capability(ctx, "agent.list", "rest")  # rest 开放
    with pytest.raises(CustomException) as ei:
        require_capability(ctx, "agent.list", "mcp")
    assert ei.value.code == 10403


def test_empty_grants_denies_everything():
    ctx = _ctx()
    with pytest.raises(CustomException):
        require_capability(ctx, "agent.list", "rest")
