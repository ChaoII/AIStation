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
    return resolvers
