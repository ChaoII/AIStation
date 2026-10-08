"""统一 Agno 工具注册中心与 Agent 工厂测试。"""
import asyncio


def test_build_business_tools_returns_agno_functions():
    """统一注册中心应把业务工具包成 Agno Function，且不含 user_id 参数。"""
    from app.plugin.module_ai.agno_tools.business import build_business_tools

    tools = build_business_tools()
    assert len(tools) > 0
    names = [t.name for t in tools]
    # 核心业务工具应在列
    assert "navigate" in names
    assert "ai_query" in names
    assert "generate_report" in names
    assert "get_annotation_overview" in names


def test_business_tool_user_id_injected():
    """业务工具运行时应注入 user_id；模型侧 schema 不应出现 user_id 参数。"""
    from app.plugin.module_ai.agno_tools.business import (
        USER_ID_CONTEXT,
        build_business_tools,
        reset_user_context,
        set_user_context,
    )

    tools = {t.name: t for t in build_business_tools()}
    navigate = tools["navigate"]
    # navigate 无 user_id 形参，schema 不含 user_id
    assert "user_id" not in (navigate.parameters or {}).get("properties", {})

    # 手动调用带 user_id 的工具，验证 contextvar 注入
    fn = tools["generate_report"].entrypoint
    # 直接调用 entrypoint，注入 user_id
    token = set_user_context(7)
    try:
        res = asyncio.run(fn(topic="Pytest 工具注入", scope="annotation"))
    finally:
        reset_user_context(token)
    assert res.get("__report_id__") > 0


def test_agent_factory_builds_agent_with_tools():
    """工厂应能构建 Agno Agent 并装配业务工具。"""
    from app.plugin.module_ai.agno_tools.agent_factory import build_agent

    agent = build_agent()
    assert agent is not None
    # 工具已装配
    assert len(agent.tools) > 0
