"""CORS 凭据泄露与中间件错误信息脱敏测试（审计 #7、verbose errors）。"""
import asyncio

from app.config.setting import settings
from app.core.exceptions import CustomException
from app.core.middlewares import RequestLogMiddleware


def test_wildcard_origin_does_not_allow_credentials(test_client):
    """ALLOW_ORIGINS 为通配时不得携带凭据，避免任意站点跨域带凭据。"""
    assert "*" in settings.ALLOW_ORIGINS
    resp = test_client.options(
        "/api/v1/system/auth/login",
        headers={
            "Origin": "http://evil.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.headers.get("access-control-allow-credentials") is None
    # 不得把任意 Origin 回显为可信来源（通配时应返回 * 或不返回）
    assert resp.headers.get("access-control-allow-origin") in (None, "*")


class _FakeClient:
    host = "127.0.0.1"


class _FakeURL:
    path = "/boom"


class _FakeRedis:
    pass


class _FakeState:
    redis = _FakeRedis()


class _FakeApp:
    state = _FakeState()


class _FakeRequest:
    method = "GET"
    client = _FakeClient()
    url = _FakeURL()
    app = _FakeApp()
    headers: dict = {}

    def __init__(self) -> None:
        self.scope = {"type": "http"}


def test_middleware_does_not_leak_exception_details(monkeypatch):
    """中间件兜底异常不得把异常内容回显给客户端。"""
    from app.api.v1.module_system.params import service as params_service

    async def _no_config(_redis):
        return {
            "demo_enable": False,
            "ip_white_list": [],
            "white_api_list_path": [],
            "ip_black_list": [],
        }

    monkeypatch.setattr(
        params_service.ParamsService, "get_system_config_for_middleware", _no_config
    )

    async def _boom(_request):
        raise CustomException(msg="secret-internal-detail")

    mw = RequestLogMiddleware(app=None)
    resp = asyncio.run(mw.dispatch(_FakeRequest(), _boom))
    body = resp.body.decode()
    assert "secret-internal-detail" not in body
