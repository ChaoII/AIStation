"""开放面能力 handler —— 能力资产标准 CRUD（skill / tool / plugin / mcp 品类）。

统一用 ``register_standard_crud`` 注册标准 CRUD；写操作身份由 :func:`create_auth`
按应用上下文决定（B 应用以 owner 身份、默认不公开；平台级以服务账号、默认公开），
并叠加可见性过滤与公开资源只读守卫。对按 ``user_id`` 个人隔离的 mcp 在
list/get/delete 时传服务账号 id（开放面以服务账号为统一归属）。
"""
from __future__ import annotations

from ._common import register_standard_crud


def register_assets_capabilities() -> None:
    """注册 skill / tool / plugin / mcp 品类能力。"""
    # ---- 技能（skill）----
    register_standard_crud(
        category="skill",
        domain="skill",
        cls_name="AiSkillService",
        service_path="app.plugin.module_ai.skill.service",
        schema_path="app.plugin.module_ai.skill.schema",
        create_schema="AiSkillCreateSchema",
        update_schema="AiSkillUpdateSchema",
        list_name="list_skills",
        get_name="get_skill",
        label="技能",
        id_key="skill_id",
        model_path="app.plugin.module_ai.skill.model",
        model_name="AiSkillModel",
        delete_needs_user=True,
        approval=True,
    )
    # ---- 工具（tool）----
    register_standard_crud(
        category="tool",
        domain="tool",
        cls_name="AiToolService",
        service_path="app.plugin.module_ai.tools_catalog.service",
        schema_path="app.plugin.module_ai.tools_catalog.schema",
        create_schema="AiToolCreateSchema",
        update_schema="AiToolUpdateSchema",
        list_name="list_tools",
        get_name="get_tool",
        label="工具",
        id_key="tool_id",
        model_path="app.plugin.module_ai.tools_catalog.model",
        model_name="AiToolModel",
        delete_needs_user=True,
        approval=True,
    )
    # ---- 插件（plugin）----
    register_standard_crud(
        category="plugin",
        domain="plugin",
        cls_name="PluginService",
        service_path="app.plugin.module_ai.plugins.service",
        schema_path="app.plugin.module_ai.plugins.schema",
        create_schema="PluginCreateSchema",
        update_schema="PluginUpdateSchema",
        list_name="list_plugins",
        get_name="get_plugin",
        label="插件",
        id_key="plugin_id",
        model_path="app.plugin.module_ai.plugins.model",
        model_name="AiPluginModel",
        delete_needs_user=True,
        approval=True,
    )
    # ---- MCP 服务器（mcp；原按 created_id 个人隔离，开放面以服务账号为统一归属）----
    register_standard_crud(
        category="mcp",
        domain="mcp",
        cls_name="McpService",
        service_path="app.plugin.module_ai.mcp.service",
        schema_path="app.plugin.module_ai.mcp.schema",
        create_schema="McpCreateSchema",
        update_schema="McpUpdateSchema",
        list_name="list_servers",
        get_name="get",
        label="MCP 服务器",
        id_key="server_id",
        model_path="app.plugin.module_ai.mcp.model",
        model_name="AiMcpServerModel",
        delete_needs_user=True,
        list_needs_user=True,
        get_needs_user=True,
        approval=True,
    )
