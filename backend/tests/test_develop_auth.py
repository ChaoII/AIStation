# tests/test_develop_auth.py （PYTEST_NO_APP=1 纯逻辑）
#
# 覆盖 AI 集成开放平台「开放数据面」的鉴权依赖纯逻辑：
# - ``AppContext``：鉴权后的应用上下文；
# - ``_parse_bearer``：解析 ``Authorization: Bearer <appid>:<appkey>``（appkey 可含冒号）；
# - ``require_app_perm``：权限点校验（未授权抛 10403）。
# 注：``get_app_api_auth`` 属于 FastAPI 依赖，需经 HTTP 触发，留给 Task 5 的集成用例验证。
import pytest

from app.core.exceptions import CustomException
from app.plugin.module_ai.develop.auth import AppContext, _parse_bearer, require_app_perm


def test_parse_bearer_valid():
    assert _parse_bearer("Bearer ai_x:abc:def") == ("ai_x", "abc:def")  # rsplit：appkey 可含冒号


def test_parse_bearer_missing_or_malformed():
    assert _parse_bearer(None) is None
    assert _parse_bearer("") is None
    assert _parse_bearer("Basic xxx") is None
    assert _parse_bearer("Bearer no-colon") is None


def test_require_app_perm_ok_and_denied():
    ctx = AppContext(app_id=1, appid="ai_x", perms={"integration:chat:send"}, quota=None, app={})
    require_app_perm(ctx, "integration:chat:send")  # 不抛
    with pytest.raises(CustomException) as ei:
        require_app_perm(ctx, "integration:train:create")
    assert ei.value.code == 10403


def test_empty_perms_denies_everything():
    ctx = AppContext(app_id=1, appid="ai_x", perms=set(), quota=None, app={})
    with pytest.raises(CustomException):
        require_app_perm(ctx, "integration:bot:use")
