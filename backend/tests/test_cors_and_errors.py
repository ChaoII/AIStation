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


class _FakeRedis:
    pass


class _FakeState:
    redis = _FakeRedis()


class _FakeApp:
    state = _FakeState()


def _scope() -> dict:
    """最小可用 HTTP scope（``Request`` 需要 headers/method/path/client/server/app）。"""
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/boom",
        "raw_path": b"/boom",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "app": _FakeApp(),
    }


def _no_demo_config(monkeypatch) -> None:
    """让中间件拿到"未开演示模式"的配置，避免误拦。"""
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


def _run_middleware(app, receive_msg=None) -> list[dict]:
    """跑一遍中间件，返回它发给客户端的所有 ASGI 消息。"""
    sent: list[dict] = []

    async def _receive():
        return receive_msg or {"type": "http.request", "body": b"", "more_body": False}

    async def _send(message):
        sent.append(message)

    asyncio.run(RequestLogMiddleware(app=app)(_scope(), _receive, _send))
    return sent


def test_middleware_does_not_leak_exception_details(monkeypatch):
    """中间件兜底异常不得把异常内容回显给客户端。"""
    _no_demo_config(monkeypatch)

    async def _boom(_scope, _receive, _send):
        raise CustomException(msg="secret-internal-detail")

    sent = _run_middleware(_boom)
    body = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    assert sent, "兜底必须真的回一个响应，不能静默吞掉"
    assert b"secret-internal-detail" not in body


def test_middleware_propagates_disconnect_to_downstream(monkeypatch):
    """**核心契约**：``http.disconnect`` 必须透传到下游（纯 ASGI 的根因所在）。

    回归守卫：``BaseHTTPMiddleware`` 只在**中间件自己先看到断开**时才把断开转发给下游，
    流式端点因此永远收不到 → 客户端关掉页面后服务端白跑到底（实测：断开 12 秒后
    运行记录仍是 running）。改回 BaseHTTPMiddleware 这条断言就会挂。
    """
    _no_demo_config(monkeypatch)
    downstream: list[str] = []

    async def _app(_scope, receive, send):
        downstream.append((await receive())["type"])
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    _run_middleware(_app, receive_msg={"type": "http.disconnect"})
    assert downstream == ["http.disconnect"]


def test_middleware_adds_process_time_header(monkeypatch):
    """行为保持：仍要给响应补 ``X-Process-Time``（原实现改 Response，纯 ASGI 改消息头）。"""
    _no_demo_config(monkeypatch)

    async def _app(_scope, _receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok", "more_body": False})

    sent = _run_middleware(_app)
    start = next(m for m in sent if m["type"] == "http.response.start")
    names = {k.decode().lower() for k, _v in start["headers"]}
    assert "x-process-time" in names
