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


def _set_tool_enabled(name: str, enabled: bool) -> None:
    """直接改 DB 启用态（绕开 API 门禁，仅供测试准备/还原）。"""
    from sqlalchemy import select

    from app.core.database import async_db_session
    from app.plugin.module_ai.tools_catalog.model import AiToolModel

    async def _run() -> None:
        async with async_db_session.begin() as db:
            t = await db.scalar(select(AiToolModel).where(AiToolModel.name == name))
            if t:
                t.enabled = enabled

    asyncio.run(_run())


def test_dispatch_executes_calculator_add():
    """通过分派路径执行 calculator.add 返回结果（工具需处于启用态）。"""
    from app.plugin.module_ai.tools_catalog.service import dispatch_tool

    spec = _specs()["calculator"]
    agno.build_openai_schemas(spec, used_names=set())
    _set_tool_enabled("calculator", True)
    try:
        result = asyncio.run(dispatch_tool("add", {"a": 1, "b": 2}, user_id=1))
    finally:
        _set_tool_enabled("calculator", False)
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
    _set_tool_enabled("calculator", True)
    try:
        result = asyncio.run(tools_service.dispatch_tool("add", {"a": 1, "b": 2}, 1))
    finally:
        _set_tool_enabled("calculator", False)
    assert result == {"ok": True}
    assert captured["config"] == {"api_key": "sk-cfg"}


def test_disabled_tool_dispatch_rejected():
    """停用的 Agno 工具即使名字仍在派发表中，也不可执行。"""
    from app.plugin.module_ai.tools_catalog.service import dispatch_tool

    spec = _specs()["calculator"]
    agno.build_openai_schemas(spec, used_names=set())  # 注册派发名
    _set_tool_enabled("calculator", False)
    result = asyncio.run(dispatch_tool("add", {"a": 1, "b": 2}, user_id=1))
    assert result == {"error": "工具未启用"}


def test_shell_args_param_is_array():
    """ShellTools.run_shell_command 的 args 应生成 array<string> 且必填（不能被按名跳过）。"""
    spec = agno.get_spec("shell")
    by_name = {
        s["function"]["name"]: s
        for s in agno.build_openai_schemas(spec, used_names=set())
    }
    shell = by_name["run_shell_command"]["function"]["parameters"]
    assert shell["properties"]["args"]["type"] == "array"
    assert shell["properties"]["args"]["items"]["type"] == "string"
    assert "args" in shell["required"]

    py = {
        s["function"]["name"]: s
        for s in agno.build_openai_schemas(agno.get_spec("python"), used_names=set())
    }
    code = py["run_python_code"]["function"]["parameters"]
    assert code["properties"]["code"]["type"] == "string"
    assert code["required"] == ["code"]


def test_high_risk_tool_gated_by_flag(monkeypatch):
    """高危工具默认未就绪；开启 AI_ENABLE_DANGEROUS_TOOLS 后才就绪。"""
    from app.config.setting import settings

    monkeypatch.setattr(settings, "AI_ENABLE_DANGEROUS_TOOLS", False)
    for key in ("shell", "python"):
        ready, reason = agno.readiness(agno.get_spec(key), None)
        assert ready is False
        assert "AI_ENABLE_DANGEROUS_TOOLS" in reason

    monkeypatch.setattr(settings, "AI_ENABLE_DANGEROUS_TOOLS", True)
    for key in ("shell", "python"):
        ready, reason = agno.readiness(agno.get_spec(key), None)
        assert ready is True
        assert reason == ""


def test_high_risk_tool_absent_from_schemas_when_flag_off(monkeypatch):
    """门禁关闭时，即使 DB 行被强制启用，shell 也不进入启用 schema 列表。"""
    from app.config.setting import settings
    from app.plugin.module_ai.tools_catalog.service import get_enabled_tool_schemas

    monkeypatch.setattr(settings, "AI_ENABLE_DANGEROUS_TOOLS", False)
    _set_tool_enabled("shell", True)
    try:
        names = {
            s["function"]["name"] for s in asyncio.run(get_enabled_tool_schemas())
        }
        assert "run_shell_command" not in names
    finally:
        _set_tool_enabled("shell", False)


def test_toggle_high_risk_rejected_when_flag_off(test_client, auth_headers):
    """高危工具未就绪时 toggle 启用应被拒绝。"""
    row = _tool_row(test_client, auth_headers, "python")
    assert row is not None
    r = test_client.put(
        f"/api/v1/ai/tools/toggle/{row['id']}",
        json={"enabled": True},
        headers=auth_headers,
    )
    assert r.status_code != 200, r.text


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
    # openweather 无 pip 依赖但缺必填 api_key，应判未就绪且 reason 提到字段
    assert specs["openweather"]["ready"] is False
    assert "api_key" in specs["openweather"]["reason"]


def test_list_tools_includes_agno_metadata(test_client, auth_headers):
    """工具列表对 agno 行合并 config_fields/group/risk/title；非 agno 行字段为空。"""
    row = _tool_row(test_client, auth_headers, "openweather")
    assert row is not None
    assert row["source"] == "agno"
    assert row["group"] == "网络"
    assert row["risk"] == "low"
    assert row["title"] == "城市天气"
    fields = row["config_fields"]
    assert fields and fields[0]["key"] == "api_key" and fields[0]["secret"] is True

    rows = test_client.get("/api/v1/ai/tools/list", headers=auth_headers).json()["data"]
    builtin = next(r for r in rows if r["kind"] == "builtin")
    assert builtin["config_fields"] == []
    assert builtin["group"] is None


def test_readiness_required_config_fields():
    """必填配置缺失 → 未就绪且 reason 提到字段；提供后 → 就绪。"""
    spec = agno.get_spec("openweather")
    ready, reason = agno.readiness(spec, None)
    assert ready is False
    assert "api_key" in reason

    ready2, reason2 = agno.readiness(spec, {"api_key": "k"})
    assert ready2 is True
    assert reason2 == ""


def test_get_tool_specs_consumes_config_map():
    """get_tool_specs 接受 ``{key: config}`` 映射，据此判定 ready/reason。"""
    no_cfg = {s["key"]: s for s in agno.get_tool_specs()}
    assert no_cfg["openweather"]["ready"] is False

    with_cfg = {
        s["key"]: s
        for s in agno.get_tool_specs({"openweather": {"api_key": "k"}})
    }
    assert with_cfg["openweather"]["ready"] is True


def test_registry_requires_are_import_module_names():
    """requires 必须是 import 模块名；pip 分发名放 pip_name 仅供展示。"""
    assert agno.get_spec("tavily")["requires"] == "tavily"
    assert agno.get_spec("serpapi")["requires"] == "serpapi"
    assert agno.get_spec("newspaper")["requires"] == "newspaper"
    assert agno.get_spec("tavily").get("pip_name") == "tavily-python"
    assert agno.get_spec("serpapi").get("pip_name") == "google-search-results"
    assert agno.get_spec("newspaper").get("pip_name") == "newspaper3k"


def test_probe_uses_import_name(monkeypatch):
    """_probe 用 import 模块名调用 find_spec，不能用 pip 分发名。"""
    import importlib.util as ilu

    seen: list[str] = []
    real = ilu.find_spec

    def _fake(name, *a, **k):
        seen.append(name)
        return real(name, *a, **k)

    monkeypatch.setattr(ilu, "find_spec", _fake)
    ready, reason = agno._probe(agno.get_spec("tavily"))
    assert ready is False
    assert "tavily" in seen
    assert "tavily-python" not in seen
    # 提示文案仍用 pip 分发名，便于用户安装
    assert "tavily-python" in reason


def test_enabled_schemas_respect_readiness(monkeypatch, test_client, auth_headers):
    """get_enabled_tool_schemas 显式按 readiness 过滤未就绪工具。"""
    from app.plugin.module_ai.tools_catalog.service import get_enabled_tool_schemas

    row = _tool_row(test_client, auth_headers, "calculator")
    assert row is not None
    original = row["enabled"]
    _toggle(test_client, auth_headers, row["id"], True)
    try:
        names = {
            s["function"]["name"] for s in asyncio.run(get_enabled_tool_schemas())
        }
        assert "add" in names

        def _forced(spec, config=None):
            return (False, "缺少配置：x") if spec["key"] == "calculator" else (True, "")

        monkeypatch.setattr(agno, "readiness", _forced)
        names2 = {
            s["function"]["name"] for s in asyncio.run(get_enabled_tool_schemas())
        }
        assert "add" not in names2
    finally:
        _toggle(test_client, auth_headers, row["id"], original)


def test_agno_endpoint_uses_stored_config(test_client, auth_headers):
    """精选规格接口会结合 ai_tools 已存 config 判定 ready。"""
    row = _tool_row(test_client, auth_headers, "openweather")
    assert row is not None
    original = _stored_tool(row["id"])["config"]
    try:
        upd = test_client.put(
            f"/api/v1/ai/tools/update/{row['id']}",
            json={"config": {"api_key": "k"}},
            headers=auth_headers,
        )
        assert upd.status_code == 200, upd.text
        specs = {
            s["key"]: s
            for s in test_client.get(
                "/api/v1/ai/tools/agno", headers=auth_headers
            ).json()["data"]
        }
        assert specs["openweather"]["ready"] is True
    finally:
        secret_keys = ("key", "secret", "token", "password")
        restore = {
            k: ("****" if any(h in k.lower() for h in secret_keys) else v)
            for k, v in (original or {}).items()
        }
        test_client.put(
            f"/api/v1/ai/tools/update/{row['id']}",
            json={"config": restore},
            headers=auth_headers,
        )


def test_load_tool_schemas_no_fallback_when_all_disabled(monkeypatch):
    """全禁用（查询成功返回 []）不得回退内置 TOOL_SCHEMAS。"""
    from app.plugin.module_ai.assistant import service as assistant
    from app.plugin.module_ai.assistant.tools import TOOL_SCHEMAS
    from app.plugin.module_ai.tools_catalog import service as catalog

    async def _empty():
        return []

    monkeypatch.setattr(catalog, "get_enabled_tool_schemas", _empty)
    assert asyncio.run(assistant._load_tool_schemas()) == []
    assert TOOL_SCHEMAS  # 内置静态列表存在，但不得被回落


def test_load_tool_schemas_returns_empty_on_exception(monkeypatch):
    """查询异常时返回 []，绝不回退内置 TOOL_SCHEMAS（DB 抖动不得重开禁用工具）。"""
    from app.plugin.module_ai.assistant import service as assistant
    from app.plugin.module_ai.assistant.tools import TOOL_SCHEMAS
    from app.plugin.module_ai.tools_catalog import service as catalog

    async def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(catalog, "get_enabled_tool_schemas", _boom)
    assert asyncio.run(assistant._load_tool_schemas()) == []
    assert TOOL_SCHEMAS  # 内置静态列表存在，但不得被回落


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
