"""AI 集成开放平台 —— 资源公开治理的品类解析回调。

为每个已接入公开治理的资产品类提供：
- ``get(resource_id)``：按 id 取该资源 dict（须含 ``created_id`` / ``is_public`` / ``name``），
  用于提交公开申请前的归属/公开状态校验。
- ``set_public(resource_id, is_public, public_perm)``：写回资源 ``is_public`` 并返回 dict。

延迟构造（函数内 import），避免模块级循环导入。未登记的品类不允许公开申请。
"""
from __future__ import annotations

from typing import Any


def build_resolvers() -> dict[str, dict[str, Any]]:
    """构建 {resource_type: {get, set_public}} 映射。"""
    resolvers: dict[str, dict[str, Any]] = {}
    # ---- knowledge ----
    from app.plugin.module_ai.knowledge.service import AiKnowledgeService

    async def _kb_get(resource_id: int) -> dict | None:
        return await AiKnowledgeService.get_base(resource_id, visible_where=None)

    async def _kb_set_public(resource_id: int, is_public: bool, public_perm: str, db=None) -> dict | None:
        return await AiKnowledgeService.set_public(resource_id, is_public, public_perm, db=db)

    resolvers["knowledge"] = {"get": _kb_get, "set_public": _kb_set_public}

    # ---- workflow ----
    from app.plugin.module_ai.workflow.service import AiWorkflowService

    async def _wf_get(resource_id: int) -> dict | None:
        return await AiWorkflowService.get_workflow(resource_id, visible_where=None)

    async def _wf_set_public(resource_id: int, is_public: bool, public_perm: str, db=None) -> dict | None:
        return await AiWorkflowService.set_public(resource_id, is_public, public_perm, db=db)

    resolvers["workflow"] = {"get": _wf_get, "set_public": _wf_set_public}

    # ---- app ----
    from app.plugin.module_ai.apps.service import AiAppService

    async def _app_get(resource_id: int) -> dict | None:
        return await AiAppService.get_app(resource_id, visible_where=None)

    async def _app_set_public(resource_id: int, is_public: bool, public_perm: str, db=None) -> dict | None:
        return await AiAppService.set_public(resource_id, is_public, public_perm, db=db)

    resolvers["app"] = {"get": _app_get, "set_public": _app_set_public}

    # ---- model ----
    from app.plugin.module_ai.models.service import AiModelService

    async def _model_get(resource_id: int) -> dict | None:
        return await AiModelService.get_model(resource_id, visible_where=None)

    async def _model_set_public(resource_id: int, is_public: bool, public_perm: str, db=None) -> dict | None:
        return await AiModelService.set_public(resource_id, is_public, public_perm, db=db)

    resolvers["model"] = {"get": _model_get, "set_public": _model_set_public}

    # ---- prompt ----
    from app.plugin.module_ai.prompts.service import AiPromptService

    async def _prompt_get(resource_id: int) -> dict | None:
        return await AiPromptService.get_prompt(resource_id, visible_where=None)

    async def _prompt_set_public(resource_id: int, is_public: bool, public_perm: str, db=None) -> dict | None:
        return await AiPromptService.set_public(resource_id, is_public, public_perm, db=db)

    resolvers["prompt"] = {"get": _prompt_get, "set_public": _prompt_set_public}

    # ---- provider ----
    from app.plugin.module_ai.providers.service import AiProviderService

    async def _provider_get(resource_id: int) -> dict | None:
        return await AiProviderService.get_provider(resource_id, visible_where=None)

    async def _provider_set_public(resource_id: int, is_public: bool, public_perm: str, db=None) -> dict | None:
        return await AiProviderService.set_public(resource_id, is_public, public_perm, db=db)

    resolvers["provider"] = {"get": _provider_get, "set_public": _provider_set_public}

    # ---- skill ----
    from app.plugin.module_ai.skill.service import AiSkillService

    async def _skill_get(resource_id: int) -> dict | None:
        return await AiSkillService.get_skill(resource_id, visible_where=None)

    async def _skill_set_public(resource_id: int, is_public: bool, public_perm: str, db=None) -> dict | None:
        return await AiSkillService.set_public(resource_id, is_public, public_perm, db=db)

    resolvers["skill"] = {"get": _skill_get, "set_public": _skill_set_public}

    # ---- tool ----
    from app.plugin.module_ai.tools_catalog.service import AiToolService

    async def _tool_get(resource_id: int) -> dict | None:
        return await AiToolService.get_tool(resource_id, visible_where=None)

    async def _tool_set_public(resource_id: int, is_public: bool, public_perm: str, db=None) -> dict | None:
        return await AiToolService.set_public(resource_id, is_public, public_perm, db=db)

    resolvers["tool"] = {"get": _tool_get, "set_public": _tool_set_public}

    # ---- plugin ----
    from app.plugin.module_ai.plugins.service import PluginService

    async def _plugin_get(resource_id: int) -> dict | None:
        return await PluginService.get_plugin(resource_id, visible_where=None)

    async def _plugin_set_public(resource_id: int, is_public: bool, public_perm: str, db=None) -> dict | None:
        return await PluginService.set_public(resource_id, is_public, public_perm, db=db)

    resolvers["plugin"] = {"get": _plugin_get, "set_public": _plugin_set_public}

    # ---- mcp ----
    from app.plugin.module_ai.mcp.model import AiMcpServerModel
    from app.plugin.module_ai.mcp.service import McpService

    async def _mcp_get(resource_id: int) -> dict | None:
        # mcp 的 get 在 visible_where=None 时回退按 created_id 过滤；传恒真条件表示按 id 无过滤取回。
        from sqlalchemy import true

        return await McpService.get(resource_id, 0, visible_where=true())

    async def _mcp_set_public(resource_id: int, is_public: bool, public_perm: str, db=None) -> dict | None:
        return await McpService.set_public(resource_id, is_public, public_perm, db=db)

    resolvers["mcp"] = {"get": _mcp_get, "set_public": _mcp_set_public}

    return resolvers
