"""AI 工具中心：内置工具同步、HTTP 工具 CRUD/执行/启停。"""
import asyncio
import uuid

from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY


def _new_name(prefix: str = "pytest_http") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _create_tool(test_client, auth_headers, **overrides) -> int:
    payload = {
        "name": _new_name(),
        "kind": "http",
        "method": "GET",
        "url": "http://127.0.0.1:9/echo",
        "headers": {"X-Test": "1"},
        "params_schema": {"type": "object", "properties": {"q": {"type": "string"}}},
        "enabled": True,
    }
    payload.update(overrides)
    r = test_client.post("/api/v1/ai/tools/create", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _delete_tools(test_client, auth_headers, ids) -> None:
    if ids:
        test_client.request(
            "DELETE", "/api/v1/ai/tools/delete", json=ids, headers=auth_headers
        )


def test_builtin_tools_synced(test_client, auth_headers):
    """启动同步为 TOOL_REGISTRY 的每个内置工具写入 ai_tools（kind=builtin）。"""
    rows = test_client.get("/api/v1/ai/tools/list", headers=auth_headers).json()["data"]
    builtin = {r["name"] for r in rows if r["kind"] == "builtin"}
    missing = set(TOOL_REGISTRY) - builtin
    assert not missing, f"缺少内置工具同步行: {missing}"


def test_http_tool_crud_and_toggle(test_client, auth_headers):
    """创建 HTTP 工具 → 列表可见 → toggle 持久化 → 删除。"""
    tid = _create_tool(test_client, auth_headers, method="POST", url="http://x/{a}")
    try:
        rows = test_client.get("/api/v1/ai/tools/list", headers=auth_headers).json()["data"]
        row = next(r for r in rows if r["id"] == tid)
        assert row["kind"] == "http"
        assert row["method"] == "POST"
        assert row["url"] == "http://x/{a}"
        assert row["enabled"] is True

        off = test_client.put(
            f"/api/v1/ai/tools/toggle/{tid}", json={"enabled": False}, headers=auth_headers
        )
        assert off.status_code == 200, off.text
        assert off.json()["data"]["enabled"] is False

        rows2 = test_client.get("/api/v1/ai/tools/list", headers=auth_headers).json()["data"]
        assert next(r for r in rows2 if r["id"] == tid)["enabled"] is False

        upd = test_client.put(
            f"/api/v1/ai/tools/update/{tid}",
            json={"url": "http://x/{b}", "enabled": True},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        assert upd.json()["data"]["url"] == "http://x/{b}"
    finally:
        _delete_tools(test_client, auth_headers, [tid])


class _FakeResponse:
    status_code = 200
    text = "ok"

    def json(self):
        return {"ok": True, "echo": True}


class _FakeClient:
    """替身 httpx.AsyncClient：记录调用参数并返回固定响应。"""

    captured: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, params=None, headers=None):
        _FakeClient.captured = {
            "method": "GET",
            "url": url,
            "params": params,
            "headers": headers,
        }
        return _FakeResponse()

    async def post(self, url, json=None, headers=None):
        _FakeClient.captured = {
            "method": "POST",
            "url": url,
            "json": json,
            "headers": headers,
        }
        return _FakeResponse()


def test_execute_http_tool_substitutes_url_and_query(monkeypatch):
    """{key} 占位替换进 URL，剩余参数作为 query；headers 透传。"""
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    from app.plugin.module_ai.tools_catalog.model import AiToolModel
    from app.plugin.module_ai.tools_catalog.service import execute_http_tool

    tool = AiToolModel(
        name="pytest_exec",
        kind="http",
        method="GET",
        url="http://example.test/items/{item_id}",
        headers={"X-Test": "1"},
        enabled=True,
    )
    result = asyncio.run(execute_http_tool(tool, {"item_id": 7, "q": "hi"}))
    assert result == {"ok": True, "echo": True}
    assert _FakeClient.captured["method"] == "GET"
    assert _FakeClient.captured["url"] == "http://example.test/items/7"
    assert _FakeClient.captured["params"] == {"q": "hi"}
    assert _FakeClient.captured["headers"] == {"X-Test": "1"}


def test_http_tool_test_endpoint(monkeypatch, test_client, auth_headers):
    """/test/{id} 对 HTTP 工具发起真实请求并返回结果。"""
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    tid = _create_tool(test_client, auth_headers, url="http://example.test/ping")
    try:
        r = test_client.post(f"/api/v1/ai/tools/test/{tid}", headers=auth_headers)
        assert r.status_code == 200, r.text
        body = r.json()["data"]
        assert body["kind"] == "http"
        assert _FakeClient.captured["url"] == "http://example.test/ping"
    finally:
        _delete_tools(test_client, auth_headers, [tid])


def _stored_headers(tool_id: int):
    from app.core.database import async_db_session
    from app.plugin.module_ai.tools_catalog.model import AiToolModel

    async def _get():
        async with async_db_session() as db:
            t = await db.get(AiToolModel, tool_id)
            return dict(t.headers or {})

    return asyncio.run(_get())


def test_http_tool_headers_masked_and_kept_on_update(test_client, auth_headers):
    """请求头脱敏：列表只回显键+****；更新传 **** 保留原值，新值覆盖，缺失键移除。"""
    import json as _json

    secret = "Bearer super-secret-xyz"
    tid = _create_tool(
        test_client, auth_headers, headers={"Authorization": secret, "X-Test": "1"}
    )
    try:
        rows = test_client.get("/api/v1/ai/tools/list", headers=auth_headers).json()["data"]
        row = next(r for r in rows if r["id"] == tid)
        assert secret not in _json.dumps(row, ensure_ascii=False)
        assert row["headers"] == {"Authorization": "****", "X-Test": "****"}

        # 传 **** → 保留已存原值
        upd = test_client.put(
            f"/api/v1/ai/tools/update/{tid}",
            json={"headers": {"Authorization": "****", "X-Test": "****"}},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        stored = _stored_headers(tid)
        assert stored["Authorization"] == secret
        assert stored["X-Test"] == "1"

        # 传新值 → 覆盖；未出现的键 → 移除
        upd2 = test_client.put(
            f"/api/v1/ai/tools/update/{tid}",
            json={"headers": {"Authorization": "Bearer new-secret"}},
            headers=auth_headers,
        )
        assert upd2.status_code == 200, upd2.text
        assert _stored_headers(tid) == {"Authorization": "Bearer new-secret"}
    finally:
        _delete_tools(test_client, auth_headers, [tid])


def test_get_enabled_tool_schemas_excludes_disabled(test_client, auth_headers):
    """禁用的工具不出现在启用工具 schema 列表中。"""
    from app.plugin.module_ai.tools_catalog.service import get_enabled_tool_schemas

    enabled_name = _new_name("pytest_enabled")
    disabled_name = _new_name("pytest_disabled")
    ids = [
        _create_tool(test_client, auth_headers, name=enabled_name, enabled=True),
        _create_tool(test_client, auth_headers, name=disabled_name, enabled=False),
    ]
    try:
        names = {
            s["function"]["name"] for s in asyncio.run(get_enabled_tool_schemas())
        }
        assert enabled_name in names
        assert disabled_name not in names
    finally:
        _delete_tools(test_client, auth_headers, ids)
