"""工作台：统一分类树 + 多类型条目聚合（DB 集成，test_client 起临时库）。"""
import asyncio
from types import SimpleNamespace as SN

from app.core.database import async_db_session
from app.plugin.module_ai.agent.service import AiAgentService
from app.plugin.module_ai.workspace.model import AiWorkspaceCategoryModel
from app.plugin.module_ai.workspace.service import WorkspaceService


async def _insert_cat(name: str, parent_id: int | None = None) -> int:
    async with async_db_session.begin() as db:
        row = AiWorkspaceCategoryModel(
            name=name, parent_id=parent_id, created_id=1, updated_id=1
        )
        db.add(row)
        await db.flush()
        return row.id


async def _create_agent(name: str, category_id: int | None = None):
    data = SN(
        agent_name=name, category_id=category_id, agent_role="测试", description="",
        model_id=None, prompt_id=None, temperature=None, workflow_id=None,
        tool_ids=[], skill_ids=[], knowledge_ids=[], mcp_ids=[], capabilities=[],
        query_enabled=False, query_datasource="system", input_schema=None,
        avatar="", color="", markdown=True, enabled=True, order=0,
    )
    return await AiAgentService.create(data, auth=SN(user=SN(id=1)))


def test_category_tree_nested():
    """分类树构建：父子多级正确。"""
    root = asyncio.run(_insert_cat("办公"))
    child = asyncio.run(_insert_cat("文档", parent_id=root))
    tree = asyncio.run(WorkspaceService.list_tree())
    root_node = next(n for n in tree if n["id"] == root)
    assert root_node["name"] == "办公"
    assert any(c["id"] == child for c in root_node.get("children", []))


def test_items_aggregate_agent_by_category():
    """按分类聚合：agent 归入其 category_id 的分类下。"""
    cat = asyncio.run(_insert_cat("研发"))
    agent = asyncio.run(_create_agent("工作台测试助手", category_id=cat))
    data = asyncio.run(WorkspaceService.items(category_id=cat))
    assert data["total"] >= 1
    assert any(
        it["type"] == "agent" and it["id"] == agent["id"] for it in data["items"]
    )


def test_items_all_includes_uncategorized():
    """全部（category_id=None）应包含未分类条目。"""
    agent = asyncio.run(_create_agent("未分类助手"))
    data = asyncio.run(WorkspaceService.items(category_id=None))
    assert data["total"] >= 1
    assert any(it["id"] == agent["id"] for it in data["items"])
