"""个人空间智能体工具测试（纯逻辑 + mock，PYTEST_NO_APP 快速模式）。"""


def test_registry_contains_workspace_tools():
    from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY

    names = {k for k in TOOL_REGISTRY if k.startswith("workspace_")}
    assert {"workspace_save_file", "workspace_list_files", "workspace_read_file"} <= names


def test_build_workspace_tools_nonempty():
    from app.plugin.module_ai.agno_tools.business import build_workspace_tools

    tools = build_workspace_tools()
    assert len(tools) == 3
    assert all(t.name.startswith("workspace_") for t in tools)


def test_save_agent_file_sanitizes_name(monkeypatch):
    """文件名清洗：'../x.md' → 'x.md'，且 source='agent'。"""
    import asyncio

    from app.plugin.module_ai.space import service as svc

    captured = {}

    async def fake_upload(user_id, filename, data, folder_id=None, source="upload"):
        captured["filename"] = filename
        captured["source"] = source
        return {"id": 1, "name": filename}

    monkeypatch.setattr(svc.SpaceService, "upload_file", staticmethod(fake_upload))
    from app.plugin.module_ai.assistant.tools import workspace_save_file

    asyncio.run(workspace_save_file(name="../x.md", content="hi", user_id=7))
    assert captured["filename"] == "x.md" and captured["source"] == "agent"


def test_read_for_agent_truncates_long_text(monkeypatch):
    """读取 200KB 文本 → 返回 ≤100KB 且含截断标记。"""
    import asyncio

    from app.plugin.module_ai.space import service as svc

    async def fake_bytes(user_id, file_id):
        return {
            "data": b"x" * (200 * 1024),
            "mime_type": "text/plain",
            "name": "t.txt",
            "file_type": "txt",
        }

    monkeypatch.setattr(svc.SpaceService, "get_file_bytes", staticmethod(fake_bytes))
    from app.plugin.module_ai.assistant.tools import workspace_read_file

    out = asyncio.run(workspace_read_file(file_id=1, user_id=7))
    assert len(out) <= 100 * 1024 + 100 and "截断" in out
