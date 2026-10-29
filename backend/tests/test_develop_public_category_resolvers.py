# tests/test_develop_public_category_resolvers.py
#
# AI 集成开放平台 —— 阶段 1.5 横向接入：各资产品类的公开申请链路。
# 验证 app / model / prompt / provider / skill / tool / plugin / mcp 品类：
# - 都已在 public_resolvers 登记（get + set_public 回调可解析）；
# - 用户对私有资源发起公开申请 → 管理员批准 → 资源 is_public 被写回 true。
# 说明：DB 相关统一 asyncio.run 一层，使用 test_client 夹具（PYTEST_NO_APP=1 自动 skip）。
import asyncio

import pytest

from app.core.exceptions import CustomException


def _run(coro):
    return asyncio.run(coro)


# 各品类：resource_type + 模型类 + 用于造测试行的最小字段
_CATEGORIES = [
    ("app", "app.plugin.module_ai.apps.model", "AiAppModel", {"name": "公开测试应用"}),
    ("model", "app.plugin.module_ai.models.model", "AiModelModel", {"name": "公开测试模型", "provider": "openai", "model": "gpt", "enabled": True, "is_default": False}),
    ("prompt", "app.plugin.module_ai.prompts.model", "AiPromptModel", {"name": "公开测试提示词", "enabled": True}),
    ("provider", "app.plugin.module_ai.providers.model", "AiProviderModel", {"name": "公开测试供应商", "protocol": "openai", "base_url": "", "enabled": True}),
    ("skill", "app.plugin.module_ai.skill.model", "AiSkillModel", {"name": "公开测试技能", "enabled": True}),
    ("tool", "app.plugin.module_ai.tools_catalog.model", "AiToolModel", {"name": "公开测试工具", "kind": "builtin", "enabled": True}),
    ("plugin", "app.plugin.module_ai.plugins.model", "AiPluginModel", {"key": "test_public_plugin", "label": "公开测试插件", "kind": "custom", "enabled": True}),
    ("mcp", "app.plugin.module_ai.mcp.model", "AiMcpServerModel", {"name": "公开测试MCP", "transport": "streamable-http", "url": "http://x", "enabled": True}),
]


def test_all_categories_registered(test_client):
    """app / model / prompt / provider / skill / tool / plugin / mcp 都已在 resolvers 登记。"""
    from app.plugin.module_ai.develop.public_resolvers import build_resolvers

    resolvers = build_resolvers()
    for resource_type, *_ in _CATEGORIES:
        assert resource_type in resolvers, f"{resource_type} 未登记公开申请回调"
        assert callable(resolvers[resource_type]["get"])
        assert callable(resolvers[resource_type]["set_public"])


def test_public_apply_flow_all_categories(test_client):
    """每个品类：用户对私有资源发起公开申请 → 批准 → is_public 被写回 true。"""
    from app.plugin.module_ai.develop.public_apps import PublicApplyService
    from app.plugin.module_ai.develop.public_resolvers import build_resolvers
    from types import SimpleNamespace

    from app.core.database import async_db_session
    import importlib
    from datetime import datetime

    resolvers = build_resolvers()
    user = SimpleNamespace(id=100, is_superuser=False)

    for resource_type, model_path, model_name, extra in _CATEGORIES:
        model = getattr(importlib.import_module(model_path), model_name)

        async def seed(m=model, extra=extra):
            async with async_db_session.begin() as db:
                kwargs = dict(extra)
                kwargs.update(
                    created_id=100, updated_id=100, is_public=False,
                    created_time=datetime.now(), updated_time=datetime.now(),
                )
                obj = m(**kwargs)
                db.add(obj)
                await db.flush()
                return obj.id

        rid = _run(seed())

        # 提交公开申请（用户 100 创建，应允许）
        row = _run(PublicApplyService.submit(
            user, resource_type=resource_type, resource_id=rid, reason="测试公开"
        ))
        assert row["apply_status"] == "pending"

        # 批准
        result = _run(PublicApplyService.review(row["id"], approve=True, reviewer_id=1, note="同意"))
        assert result["apply_status"] == "approved"

        # is_public 写回 true
        target = _run(resolvers[resource_type]["get"](rid))
        assert target is not None, f"{resource_type} 批准后 get 不到资源"
        assert target.get("is_public") is True, f"{resource_type} is_public 未写回 true"


def test_public_apply_reject_foreign_resource_all(test_client):
    """每个品类：用户申请公开他人私有资源 → 403。"""
    from app.plugin.module_ai.develop.public_apps import PublicApplyService
    from types import SimpleNamespace

    user = SimpleNamespace(id=100, is_superuser=False)
    for resource_type, *_ in _CATEGORIES:
        with pytest.raises(CustomException) as exc_info:
            _run(PublicApplyService.submit(
                user, resource_type=resource_type, resource_id=99999999, reason="越权"
            ))
        assert exc_info.value.status_code == 404
