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


def test_script_extract_params_multi():
    """run 带类型注解的多参数：正确提取名/类型/默认/必填。"""
    from app.plugin.module_ai.tools_catalog.script_executor import _extract_run_params

    code = """
import re

def run(name: str = "world", age: int = 3, score: float = 0.5, tags: list = []) -> dict:
    return {"name": name, "age": age}
"""
    params = _extract_run_params(code)
    by_name = {p["name"]: p for p in params}
    assert set(by_name) == {"name", "age", "score", "tags"}
    assert by_name["name"]["type"] == "string"
    assert by_name["name"]["default"] == "world"
    assert by_name["name"]["required"] is False
    assert by_name["age"]["type"] == "integer"
    assert by_name["age"]["default"] == 3
    assert by_name["score"]["type"] == "number"
    assert by_name["tags"]["type"] == "array"


def test_script_extract_params_single_args_empty():
    """run(args) 单参形态：不可提取多参（返回空列表）。"""
    from app.plugin.module_ai.tools_catalog.script_executor import _extract_run_params

    code = 'def run(args: dict) -> dict:\n    return {"sum": args.get("a", 0)}\n'
    assert _extract_run_params(code) == []


def test_script_execute_multi_params():
    """run 多参形态：按参数名传值，缺省参数可省略。"""
    from app.plugin.module_ai.tools_catalog.model import AiToolModel
    from app.plugin.module_ai.tools_catalog.service import execute_script_tool

    code = (
        "def run(name: str = 'x', age: int = 3) -> dict:\n"
        '    return {"name": name, "age": age}\n'
    )
    tool = AiToolModel(name="pytest_multi", kind="script", code=code, timeout=10, enabled=True)
    result = asyncio.run(execute_script_tool(tool, {"name": "alice", "age": 20}))
    assert result == {"name": "alice", "age": 20}
    # 只传部分：缺省参数用默认值
    result2 = asyncio.run(execute_script_tool(tool, {"name": "bob"}))
    assert result2 == {"name": "bob", "age": 3}


def test_script_execute_legacy_args():
    """run(args) 单参形态：整个 dict 传入（向后兼容）。"""
    from app.plugin.module_ai.tools_catalog.model import AiToolModel
    from app.plugin.module_ai.tools_catalog.service import execute_script_tool

    code = 'def run(args):\n    return {"sum": args.get("a", 0) + args.get("b", 0)}\n'
    tool = AiToolModel(name="pytest_legacy", kind="script", code=code, timeout=10, enabled=True)
    result = asyncio.run(execute_script_tool(tool, {"a": 2, "b": 3}))
    assert result == {"sum": 5}


def test_inspect_script_endpoint(test_client, auth_headers):
    """/inspect-script 解析 run 签名并返回参数与校验状态。"""
    code = 'def run(name: str, count: int = 1) -> dict:\n    return {}\n'
    r = test_client.post(
        "/api/v1/ai/tools/inspect-script", json={"code": code}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["valid"] is True
    assert data["error"] == ""
    params = {p["name"]: p for p in data["params"]}
    assert params["name"]["type"] == "string"
    assert params["name"]["default"] is None
    assert params["name"]["required"] is True
    assert params["count"]["type"] == "integer"
    assert params["count"]["default"] == 1
    assert params["count"]["required"] is False


def test_inspect_script_invalid_endpoint(test_client, auth_headers):
    """/inspect-script 对非法脚本返回 valid=False 与错误信息。"""
    r = test_client.post(
        "/api/v1/ai/tools/inspect-script",
        json={"code": "def run(args:\n    pass"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["valid"] is False
    assert data["error"]


def test_format_script_endpoint(test_client, auth_headers):
    """/format-script 用 ruff 格式化（语法错误时原样返回）。"""
    messy = 'def run(x:int=1)->dict:\n  return{"x":x}\n'
    r = test_client.post(
        "/api/v1/ai/tools/format-script", json={"code": messy}, headers=auth_headers
    )
    assert r.status_code == 200, r.text
    out = r.json()["data"]["code"]
    assert "x: int = 1" in out or "x:int=1" in out  # 至少可通过 ast 解析
    import ast

    ast.parse(out)  # 不抛即通过
    # 语法错误：原样返回
    r2 = test_client.post(
        "/api/v1/ai/tools/format-script", json={"code": "def broken("}, headers=auth_headers
    )
    assert r2.json()["data"]["code"] == "def broken("


def test_script_execute_injects_tool_config():
    """脚本可读取工具私有配置：注入沙箱全局 TOOL_CONFIG，源码不含明文。"""
    from app.plugin.module_ai.tools_catalog.model import AiToolModel
    from app.plugin.module_ai.tools_catalog.service import execute_script_tool

    code = 'def run():\n    return {"key": TOOL_CONFIG.get("api_key", "missing")}\n'
    tool = AiToolModel(
        name="pytest_cfg",
        kind="script",
        code=code,
        config={"api_key": "sk-secret", "username": "alice"},
        timeout=10,
        enabled=True,
    )
    result = asyncio.run(execute_script_tool(tool, {}))
    assert result == {"key": "sk-secret"}
    # 未传入 config 时不报错，返回缺省
    tool2 = AiToolModel(name="pytest_cfg2", kind="script", code=code, timeout=10, enabled=True)
    assert asyncio.run(execute_script_tool(tool2, {})) == {"key": "missing"}


def test_script_tool_config_masked_in_list(test_client, auth_headers):
    """脚本工具 config（运行时私有参数）在列表回显时全量脱敏为 ****。"""
    import app.plugin.module_ai.tools_catalog.service as svc
    from app.plugin.module_ai.tools_catalog.model import AiToolModel
    from app.plugin.module_ai.tools_catalog.service import _to_dict

    tool = AiToolModel(
        name="pytest_masked",
        kind="script",
        code="def run(): return {}",
        config={"api_key": "sk-secret", "username": "alice"},
        timeout=10,
        enabled=True,
    )
    d = _to_dict(tool)
    assert d["config"] == {"api_key": svc.HEADER_MASK, "username": svc.HEADER_MASK}
    # 非脚本工具：仅密钥命名字段脱敏，普通值原样（用户名不脱敏）
    tool2 = AiToolModel(name="pytest_httpmask", kind="http", config={"username": "alice"}, enabled=True)
    d2 = _to_dict(tool2)
    assert d2["config"] == {"username": "alice"}
