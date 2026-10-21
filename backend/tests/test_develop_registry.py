# tests/test_develop_registry.py
"""能力注册表（纯逻辑）：登记 / 查表 / 按权限过滤 / 重复与非法守卫。

覆盖 Review Focus 第 2 条的前提：能力与权限点一一绑定，未授权能力不可见。
"""
import pytest

from app.plugin.module_ai.develop.registry import (
    Capability,
    all_capabilities,
    capabilities_for,
    get_capability,
    mcp_capabilities,
    register,
    to_public_dict,
)

pytestmark = pytest.mark.usefixtures("_clean_registry")


@pytest.fixture()
def _clean_registry():
    """隔离测试：备份/恢复全局注册表，避免用例之间互相污染。"""
    from app.plugin.module_ai.develop import registry as reg

    codes = dict(reg._REGISTRY)
    tools = dict(reg._MCP_TOOLS)
    yield
    reg._REGISTRY.clear()
    reg._REGISTRY.update(codes)
    reg._MCP_TOOLS.clear()
    reg._MCP_TOOLS.update(tools)


def _cap(code="agent.list", perm="integration:agent:query", mcp_tool="agent_list", **kw):
    base = dict(
        code=code,
        category="agent",
        perm=perm,
        name="查询智能体列表",
        description="列出本应用创建的智能体",
        input_schema={"type": "object", "properties": {}},
        returns="items: array",
        mcp_tool=mcp_tool,
    )
    base.update(kw)
    return Capability(**base)


def test_register_and_lookup():
    register(_cap())
    found = get_capability("agent.list")
    assert found is not None
    assert found.perm == "integration:agent:query"
    assert [c.code for c in all_capabilities()] == ["agent.list"]


def test_register_rejects_duplicate_code():
    register(_cap())
    with pytest.raises(ValueError, match="能力码重复"):
        register(_cap())


def test_register_rejects_duplicate_mcp_tool():
    register(_cap())
    with pytest.raises(ValueError, match="MCP 工具名重复"):
        register(_cap(code="agent.get", mcp_tool="agent_list"))


def test_register_rejects_invalid_perm():
    with pytest.raises(ValueError, match="权限点非法"):
        register(_cap(perm="integration:agent:unknown"))


def test_capabilities_for_filters_by_perm():
    register(_cap())
    register(_cap(code="train.create", perm="integration:train:create", mcp_tool="train_create", category="train"))
    assert [c.code for c in capabilities_for({"integration:agent:query"})] == ["agent.list"]
    assert capabilities_for(set()) == []


def test_mcp_capabilities_skips_rest_only():
    register(_cap(mcp_tool=None))
    register(_cap(code="agent.get", mcp_tool="agent_get"))
    assert [c.mcp_tool for c in mcp_capabilities()] == ["agent_get"]


def test_to_public_dict_hides_handler():
    register(_cap(handler=lambda **kw: None))
    payload = to_public_dict(get_capability("agent.list"))
    assert "handler" not in payload
    assert payload["mcp_tool"] == "agent_list"
    assert payload["input_schema"] == {"type": "object", "properties": {}}
