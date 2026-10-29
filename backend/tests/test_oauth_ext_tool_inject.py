# tests/test_oauth_ext_tool_inject.py
#
# 阶段 3a —— Task 5：http 工具绑定外部服务 + 调用注入 Bearer。
# 验证：绑定服务且用户已授权 -> 请求带 Authorization: Bearer <access>；
#       未绑定服务的工具 -> 请求不含 Authorization；未连接/已撤销 -> 返回错误 dict 不抛异常。
import uuid

import pytest


def _uid():
    return uuid.uuid4().hex[:8]


def _create_service(test_client, auth_headers):
    r = test_client.post(
        "/api/v1/ai/oauth-ext/services",
        headers=auth_headers,
        json={
            "name": f"svc-{_uid()}",
            "authorize_url": "https://ext.example/authorize",
            "token_url": "https://ext.example/token",
            "client_id": "client-abc",
            "client_secret": "top-secret",
            "redirect_uri": "https://platform.example/oauth-ext/callback",
            "default_scopes": ["attendance"],
            "enabled": True,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _create_http_tool(test_client, auth_headers, *, oauth_service_id=None, name=None):
    r = test_client.post(
        "/api/v1/ai/tools/create",
        headers=auth_headers,
        json={
            "name": name or f"tool-{_uid()}",
            "kind": "http",
            "source": "http",
            "url": "https://api.ext.example/v1/items",
            "method": "GET",
            "params_schema": {"type": "object", "properties": {}},
            "enabled": True,
            "oauth_ext_service_id": oauth_service_id,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


class _FakeResp:
    status_code = 200
    text = '{"ok": true}'

    def json(self):
        return {"ok": True}


class _FakeClient:
    def __init__(self, *a, **k):
        self.captured = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, params=None, headers=None):
        self.captured = {"url": url, "headers": headers}
        return _FakeResp()


async def _run_http(tool, user_id):
    from app.plugin.module_ai.tools_catalog.service import execute_http_tool

    client = _FakeClient()
    import app.plugin.module_ai.tools_catalog.service as svc

    import httpx

    orig = httpx.AsyncClient
    httpx.AsyncClient = lambda *a, **k: client  # noqa: E731
    try:
        from app.plugin.module_ai.tools_catalog.service import AiToolModel

        # 构造 ORM 行（无需落库）
        t = AiToolModel(
            id=1,
            name=getattr(tool, "name", "t"),
            kind="http",
            source="http",
            url=tool.get("url") or "https://api.ext.example/v1/items",
            method="GET",
            enabled=True,
            oauth_ext_service_id=tool.get("oauth_ext_service_id"),
        )
        return await execute_http_tool(t, {}, user_id), client.captured
    finally:
        httpx.AsyncClient = orig


def test_http_tool_injects_bearer(test_client, auth_headers, monkeypatch):
    """绑定服务且已授权 -> 请求头带 Bearer access。"""
    from app.plugin.module_ai.oauth_ext.service import OAuthExtService

    svc = _create_service(test_client, auth_headers)
    tool = _create_http_tool(test_client, auth_headers, oauth_service_id=svc["id"])

    async def _fake_resolve(service_id, user_id):
        return "ext-access-token"

    monkeypatch.setattr(OAuthExtService, "resolve_ext_access_token", staticmethod(_fake_resolve))

    import asyncio

    result, captured = asyncio.run(_run_http(tool, 1))
    assert result == {"ok": True}
    assert captured["headers"]["Authorization"] == "Bearer ext-access-token"


def test_http_tool_unbound_no_auth(test_client, auth_headers):
    """未绑定服务的工具 -> 请求不含 Authorization。"""
    tool = _create_http_tool(test_client, auth_headers, oauth_service_id=None)
    import asyncio

    result, captured = asyncio.run(_run_http(tool, 1))
    assert result == {"ok": True}
    assert "Authorization" not in (captured["headers"] or {})


def test_http_tool_not_connected_returns_error(test_client, auth_headers, monkeypatch):
    """绑定服务但用户未授权/已撤销 -> 返回错误 dict，不抛异常。"""
    from app.plugin.module_ai.oauth_ext.service import OAuthExtService
    from app.core.exceptions import CustomException

    svc = _create_service(test_client, auth_headers)
    tool = _create_http_tool(test_client, auth_headers, oauth_service_id=svc["id"])

    def _raise(service_id, user_id):
        raise CustomException(msg="你尚未连接该外部服务", code=10404, status_code=404)

    monkeypatch.setattr(OAuthExtService, "resolve_ext_access_token", staticmethod(_raise))

    import asyncio

    result, _ = asyncio.run(_run_http(tool, 1))
    assert isinstance(result, dict)
    assert "error" in result
