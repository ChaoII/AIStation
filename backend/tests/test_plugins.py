"""AI 能力插件测试：内置预置、CRUD、执行器。"""
import asyncio
import uuid

from app.plugin.module_ai.plugins.plugin_executor import (
    PLUGIN_EXECUTORS,
    execute_plugin,
)


def _new_key(prefix: str = "pytest_plugin") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def test_no_builtin_plugins_seeded(test_client, auth_headers):
    """内置插件预置已取消：web_fetch/table_export 改为内置工具，「插件」= 能力包（市场商品）。"""
    rows = test_client.get("/api/v1/ai/plugins/list", headers=auth_headers).json()["data"]
    assert all(r["kind"] != "builtin" for r in rows), "不应再预置内置插件"


def test_web_fetch_and_table_export_are_builtin_tools():
    """原先挂在插件下的两项能力已是内置工具（工具管理里可开关）。"""
    from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY

    assert "web_fetch" in TOOL_REGISTRY
    assert "table_export" in TOOL_REGISTRY


def test_plugin_specs_empty():
    """内置插件规格已清空（保留常量以备将来预置内置包）。"""
    from app.plugin.module_ai.plugins.plugin_executor import PLUGIN_SPECS

    assert PLUGIN_SPECS == []


def test_plugin_crud_and_toggle(test_client, auth_headers):
    """新增/编辑/启停/删除插件。"""
    key = _new_key()
    r = test_client.post(
        "/api/v1/ai/plugins/create",
        headers=auth_headers,
        json={"key": key, "label": "测试插件", "kind": "custom", "enabled": True},
    )
    assert r.status_code == 200, r.text
    pid = r.json()["data"]["id"]
    assert r.json()["data"]["executor_ready"] is False

    upd = test_client.put(
        f"/api/v1/ai/plugins/update/{pid}",
        json={"description": "改过了"},
        headers=auth_headers,
    )
    assert upd.json()["data"]["description"] == "改过了"

    off = test_client.put(
        f"/api/v1/ai/plugins/toggle/{pid}", json={"enabled": False}, headers=auth_headers
    )
    assert off.json()["data"]["enabled"] is False

    dele = test_client.request(
        "DELETE", "/api/v1/ai/plugins/delete", json=[pid], headers=auth_headers
    )
    assert dele.status_code == 200
    rows = test_client.get("/api/v1/ai/plugins/list", headers=auth_headers).json()["data"]
    assert not any(x["id"] == pid for x in rows)


def test_plugin_duplicate_key_rejected(test_client, auth_headers):
    """重复 key 被拒。"""
    key = _new_key()
    first = test_client.post(
        "/api/v1/ai/plugins/create",
        headers=auth_headers,
        json={"key": key, "label": "重复测试"},
    )
    assert first.status_code == 200, first.text
    r = test_client.post(
        "/api/v1/ai/plugins/create",
        headers=auth_headers,
        json={"key": key, "label": "重复"},
    )
    assert r.status_code != 200
    assert "已存在" in r.json()["msg"]


def test_executor_registry_shape():
    """执行器注册表含全部 5 个内置 key（web_fetch/table_export 及新补的三个）。"""
    assert set(PLUGIN_EXECUTORS) == {
        "web_fetch",
        "table_export",
        "email_send",
        "report_generate",
        "data_pipeline",
    }


def test_table_export_executor():
    """table_export 执行器输出 CSV 文本。"""
    out = asyncio.run(
        execute_plugin(
            "table_export",
            {"columns": ["a", "b"], "rows": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]},
        )
    )
    assert out["rows"] == 2
    assert out["csv"].splitlines()[0] == "a,b"
    assert out["csv"].splitlines()[1] == "1,2"


def test_unimplemented_plugin_returns_error():
    """未实现执行器的插件返回明确错误（用不存在的 key）。"""
    out = asyncio.run(execute_plugin("no_such_plugin_key", {}))
    assert "未实现执行器" in out["error"]


def test_plugin_executor_tools_registered():
    """新补的三个执行器暴露为内置工具，Agent 可调用。"""
    from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY

    assert "email_send" in TOOL_REGISTRY
    assert "report_generate" in TOOL_REGISTRY
    assert "data_pipeline" in TOOL_REGISTRY


def test_email_send_missing_recipients():
    """email_send 缺收件人返回明确错误（不依赖 SMTP/DB）。"""
    out = asyncio.run(execute_plugin("email_send", {"subject": "s", "body": "b"}))
    assert "收件人" in out["error"]


def test_email_send_missing_smtp(test_client):
    """SMTP 未配置时返回明确错误。"""
    out = asyncio.run(
        execute_plugin("email_send", {"to": "a@b.com", "subject": "s", "body": "b"})
    )
    assert "SMTP" in out["error"]


def test_report_generate_creates_report(test_client):
    """report_generate 保存报告并返回 report_id。"""
    out = asyncio.run(
        execute_plugin("report_generate", {"title": "测试报告", "content": "正文内容"})
    )
    assert out["report_id"]
    assert out["title"] == "测试报告"


def test_data_pipeline_missing_pipeline_id():
    """data_pipeline 缺 pipeline_id 返回错误（不依赖 DB）。"""
    out = asyncio.run(execute_plugin("data_pipeline", {}))
    assert "管道" in out["error"]


def test_data_pipeline_delegates_to_run_pipeline(monkeypatch):
    """data_pipeline 委派给 AiQueryService.run_pipeline，返回其结果。"""
    import asyncio

    from app.plugin.module_ai.plugins import plugin_executor as pe

    async def fake_run(pipeline_id: int) -> dict:
        return {"ok": True, "materialized": 5, "msg": "done"}

    monkeypatch.setattr(
        "app.plugin.module_ai.query.service.AiQueryService.run_pipeline", fake_run
    )
    out = asyncio.run(pe.execute_plugin("data_pipeline", {"pipeline_id": 3}))
    assert out["ok"] is True
    assert out["materialized"] == 5


def test_web_fetch_executor_unreachable():
    """web_fetch 抓取失败返回 error，不抛异常。"""
    out = asyncio.run(execute_plugin("web_fetch", {"url": "http://127.0.0.1:9/x"}))
    assert "error" in out


def test_web_fetch_missing_url():
    """缺 url 参数返回错误。"""
    out = asyncio.run(execute_plugin("web_fetch", {}))
    assert out["error"] == "缺少 url 参数"


def test_enabled_plugins_only_ready(test_client, auth_headers):
    """enabled_plugins 只返回执行器就绪的启用插件。"""
    from app.plugin.module_ai.plugins.service import PluginService

    rows = asyncio.run(PluginService.enabled_plugins())
    keys = {r["key"] for r in rows}
    assert keys <= set(PLUGIN_EXECUTORS)
    assert all(r["enabled"] for r in rows)
