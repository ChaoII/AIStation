# tests/test_develop_registry.py
"""能力注册表（纯逻辑）：登记 / 查表 / 按权限过滤 / 重复与非法守卫。

覆盖 Review Focus 第 2 条的前提：能力与权限点一一绑定，未授权能力不可见。

注意：真实应用启动时会由 ``develop.handlers`` 注册全部生产能力，因此本文件的
用例一律使用 ``tst.*`` 前缀的**测试专用能力码**，断言只针对自己注册的子集
（不对全局注册表做全量相等断言）。
"""
import pytest

from app.plugin.module_ai.develop.registry import (
    Capability,
    all_capabilities,
    capabilities_for,
    capabilities_for_codes,
    get_capability,
    is_granted,
    mcp_capabilities,
    normalize_channels,
    register,
    resolve_capability_grants,
    resolve_channels,
    to_public_dict,
)


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


pytestmark = pytest.mark.usefixtures("_clean_registry")


def _cap(code="tst.alpha", perm="integration:agent:query", mcp_tool="tst_alpha", **kw):
    base = dict(
        code=code,
        category="agent",
        perm=perm,
        name="测试能力",
        description="注册表单元测试用",
        input_schema={"type": "object", "properties": {}},
        returns="items: array",
        mcp_tool=mcp_tool,
    )
    base.update(kw)
    return Capability(**base)


def test_register_and_lookup():
    register(_cap())
    found = get_capability("tst.alpha")
    assert found is not None
    assert found.perm == "integration:agent:query"
    assert "tst.alpha" in [c.code for c in all_capabilities()]


def test_register_rejects_duplicate_code():
    register(_cap())
    with pytest.raises(ValueError, match="能力码重复"):
        register(_cap())


def test_register_rejects_duplicate_mcp_tool():
    register(_cap())
    with pytest.raises(ValueError, match="MCP 工具名重复"):
        register(_cap(code="tst.beta", mcp_tool="tst_alpha"))


def test_register_rejects_invalid_perm():
    with pytest.raises(ValueError, match="权限点非法"):
        register(_cap(perm="integration:agent:unknown"))


def test_capabilities_for_filters_by_perm():
    register(_cap())
    register(_cap(code="tst.gamma", perm="integration:train:create", mcp_tool="tst_gamma"))
    granted = {c.code for c in capabilities_for({"integration:agent:query"})}
    assert "tst.alpha" in granted
    assert "tst.gamma" not in granted
    assert capabilities_for(set()) == []


def test_mcp_capabilities_skips_rest_only():
    register(_cap(mcp_tool=None))
    register(_cap(code="tst.beta", mcp_tool="tst_beta"))
    tools = {c.mcp_tool for c in mcp_capabilities()}
    assert "tst_beta" in tools
    assert None not in tools


def test_to_public_dict_hides_handler():
    register(_cap(handler=lambda **kw: None))
    payload = to_public_dict(get_capability("tst.alpha"))
    assert "handler" not in payload
    assert payload["mcp_tool"] == "tst_alpha"
    assert payload["input_schema"] == {"type": "object", "properties": {}}


# --------------------------------------------------------------------------- #
# 按需授权：权限点 → 能力码展开 + REST/MCP 出口控制
# --------------------------------------------------------------------------- #


def test_resolve_grants_expands_perm_to_codes():
    register(_cap())  # perm=integration:agent:query
    register(_cap(code="tst.gamma", perm="integration:agent:query", mcp_tool="tst_gamma"))
    # 旧数据：integration:* 权限点 → 展开为其下全部能力码
    grants = resolve_capability_grants(["integration:agent:query"])
    assert grants == {"tst.alpha", "tst.gamma"}


def test_resolve_grants_keeps_codes_and_drops_invalid():
    register(_cap())
    grants = resolve_capability_grants(["tst.alpha", "tst.notexist", "integration:train:create"])
    assert "tst.alpha" in grants
    assert "tst.notexist" not in grants  # 非法能力码丢弃
    # integration:train:create 展开不成（无对应能力）也不会报错


def test_resolve_channels_default_all_supported():
    register(_cap(mcp_tool="tst_alpha"))  # rest=True + mcp_tool => rest+mcp
    register(_cap(code="tst.rest", mcp_tool=None))  # 仅 rest
    grants = {"tst.alpha", "tst.rest"}
    ch = resolve_channels(None, grants)
    assert ch["tst.alpha"] == {"rest", "mcp"}
    assert ch["tst.rest"] == {"rest"}


def test_resolve_channels_respects_explicit_and_limits():
    register(_cap(mcp_tool="tst_alpha"))
    ch = resolve_channels({"tst.alpha": ["mcp"]}, {"tst.alpha"})
    assert ch["tst.alpha"] == {"mcp"}  # 只开 mcp，rest 不开
    # 非法通道被丢弃；空列表回退默认
    ch2 = resolve_channels({"tst.alpha": ["rest", "bogus"]}, {"tst.alpha"})
    assert ch2["tst.alpha"] == {"rest"}
    ch3 = resolve_channels({"tst.alpha": []}, {"tst.alpha"})
    assert ch3["tst.alpha"] == {"rest", "mcp"}


def test_normalize_channels_storage_shape():
    register(_cap(mcp_tool="tst_alpha"))
    assert normalize_channels({"tst.alpha": ["mcp"]}, {"tst.alpha"}) == {"tst.alpha": ["mcp"]}


def test_is_granted_checks_code_and_channel():
    register(_cap(mcp_tool="tst_alpha"))
    # 未授权 → False
    assert is_granted(set(), None, "tst.alpha", "rest") is False
    # 授权 + 缺省通道（全支持）→ True
    assert is_granted({"tst.alpha"}, None, "tst.alpha", "mcp") is True
    # 授权但只开 rest → mcp 为 False
    assert is_granted({"tst.alpha"}, {"tst.alpha": {"rest"}}, "tst.alpha", "mcp") is False


def test_capabilities_for_codes_filters():
    register(_cap())
    register(_cap(code="tst.gamma", perm="integration:train:create", mcp_tool="tst_gamma"))
    codes = {c.code for c in capabilities_for_codes({"tst.alpha"})}
    assert codes == {"tst.alpha"}

