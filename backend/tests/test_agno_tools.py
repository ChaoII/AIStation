"""Agno 精选工具：就绪探测、schema 生成、执行分派与 ai_tools 持久化。"""
import asyncio
import json
import uuid

from app.plugin.module_ai.agno_tools import service as agno


def _specs() -> dict[str, dict]:
    return {s["key"]: s for s in agno.get_tool_specs()}


def _tool_row(test_client, auth_headers, name: str) -> dict | None:
    rows = test_client.get("/api/v1/ai/tools/list", headers=auth_headers).json()["data"]
    return next((r for r in rows if r["name"] == name), None)


def _toggle(test_client, auth_headers, tool_id: int, enabled: bool) -> None:
    r = test_client.put(
        f"/api/v1/ai/tools/toggle/{tool_id}",
        json={"enabled": enabled},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text


def test_tool_specs_readiness():
    """calculator 无依赖应就绪；缺依赖项应未就绪且给出原因。"""
    specs = _specs()
    assert specs["calculator"]["ready"] is True
    assert specs["calculator"]["source"] == "agno"

    missing = specs["csv_toolkit"]  # requires duckdb（本机未安装）
    assert missing["ready"] is False
    assert missing["reason"]


def test_build_openai_schemas_expands_all_functions():
    """一个 toolkit 展开为多个函数 schema，参数类型/必填由签名推导。"""
    spec = _specs()["calculator"]
    schemas = agno.build_openai_schemas(spec, used_names=set())
    by_name = {s["function"]["name"]: s for s in schemas}
    assert {"add", "subtract", "multiply"} <= set(by_name)

    add = by_name["add"]["function"]
    assert add["parameters"]["type"] == "object"
    assert add["parameters"]["required"] == ["a", "b"]
    assert add["parameters"]["properties"]["a"]["type"] == "number"
    assert add["description"]


def test_build_openai_schemas_unique_name_fallback():
    """生成名与已占用名冲突时，退化为 ``key_fn`` 前缀形式。"""
    spec = _specs()["calculator"]
    schemas = agno.build_openai_schemas(spec, used_names={"add"})
    names = {s["function"]["name"] for s in schemas}
    assert "add" not in names
    assert "calculator_add" in names
    assert agno.resolve_function("calculator_add")[1] == "add"


def test_dispatch_executes_calculator_add():
    """通过分派路径执行 calculator.add 返回结果。"""
    from app.plugin.module_ai.tools_catalog.service import dispatch_tool

    spec = _specs()["calculator"]
    agno.build_openai_schemas(spec, used_names=set())
    result = asyncio.run(dispatch_tool("add", {"a": 1, "b": 2}, user_id=1))
    if isinstance(result, str):
        result = json.loads(result)
    assert result["result"] == 3


def test_dispatch_passes_toolkit_config(monkeypatch):
    """分派执行时把 toolkit 配置（如 api_key）透传给 execute。"""
    from app.plugin.module_ai.tools_catalog import service as tools_service

    spec = _specs()["calculator"]
    agno.build_openai_schemas(spec, {"api_key": "sk-cfg"}, used_names=set())
    assert agno.resolve_config("add") == {"api_key": "sk-cfg"}

    captured: dict = {}

    async def _fake_execute(spec, fn_name, args, config=None):
        captured["config"] = config
        return {"ok": True}

    monkeypatch.setattr(agno, "execute", _fake_execute)
    result = asyncio.run(tools_service.dispatch_tool("add", {"a": 1, "b": 2}, 1))
    assert result == {"ok": True}
    assert captured["config"] == {"api_key": "sk-cfg"}


def test_execute_unknown_function_returns_error():
    """执行不存在的函数名返回 error，不抛异常。"""
    spec = _specs()["calculator"]
    result = asyncio.run(agno.execute(spec, "not_a_function", {}))
    assert "error" in result


def test_disabled_toolkit_contributes_no_schemas(test_client, auth_headers):
    """停用 calculator 后 get_enabled_tool_schemas 不含其函数；启用后恢复。"""
    from app.plugin.module_ai.tools_catalog.service import get_enabled_tool_schemas

    row = _tool_row(test_client, auth_headers, "calculator")
    assert row is not None and row["source"] == "agno"
    original = row["enabled"]
    try:
        _toggle(test_client, auth_headers, row["id"], False)
        names_off = {
            s["function"]["name"] for s in asyncio.run(get_enabled_tool_schemas())
        }
        assert "add" not in names_off
        assert "subtract" not in names_off

        _toggle(test_client, auth_headers, row["id"], True)
        names_on = {
            s["function"]["name"] for s in asyncio.run(get_enabled_tool_schemas())
        }
        assert "add" in names_on
    finally:
        _toggle(test_client, auth_headers, row["id"], original)


def test_agno_catalog_endpoint(test_client, auth_headers):
    """精选工具规格接口返回 ready/config_fields 元数据。"""
    r = test_client.get("/api/v1/ai/tools/agno", headers=auth_headers)
    assert r.status_code == 200, r.text
    specs = {s["key"]: s for s in r.json()["data"]}
    assert specs["calculator"]["ready"] is True
    assert specs["tavily"]["config_fields"][0]["key"] == "api_key"


def _stored_tool(tool_id: int):
    from app.core.database import async_db_session
    from app.plugin.module_ai.tools_catalog.model import AiToolModel

    async def _get():
        async with async_db_session() as db:
            t = await db.get(AiToolModel, tool_id)
            return {"source": t.source, "config": dict(t.config or {})}

    return asyncio.run(_get())


def test_source_and_config_persistence_and_mask(test_client, auth_headers):
    """source/config 持久化；密钥字段列表脱敏，更新传掩码保留原值。"""
    name = f"pytest_cfg_{uuid.uuid4().hex[:8]}"
    r = test_client.post(
        "/api/v1/ai/tools/create",
        json={
            "name": name,
            "kind": "http",
            "source": "http",
            "method": "GET",
            "url": "http://x/{q}",
            "config": {"api_key": "sk-super-secret", "base_url": "http://x"},
            "params_schema": {"type": "object", "properties": {}},
            "enabled": True,
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    tid = r.json()["data"]["id"]
    try:
        row = _tool_row(test_client, auth_headers, name)
        assert row["source"] == "http"
        assert row["config"]["api_key"] == "****"
        assert row["config"]["base_url"] == "http://x"
        assert "sk-super-secret" not in json.dumps(row, ensure_ascii=False)

        # 传入掩码 → 保留原密钥；同时新增自定义参数
        upd = test_client.put(
            f"/api/v1/ai/tools/update/{tid}",
            json={"config": {"api_key": "****", "base_url": "http://y", "custom": "v"}},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        stored = _stored_tool(tid)
        assert stored["source"] == "http"
        assert stored["config"]["api_key"] == "sk-super-secret"
        assert stored["config"]["base_url"] == "http://y"
        assert stored["config"]["custom"] == "v"
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/tools/delete", json=[tid], headers=auth_headers
        )
