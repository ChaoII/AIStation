"""智能体绑定资产校验：防跨用户绑定与绑定不存在资产（DB 集成，test_client 起临时库）。"""
import asyncio
from types import SimpleNamespace as SN

import pytest

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.plugin.module_ai.agent.service import AiAgentService
from app.plugin.module_ai.mcp.model import AiMcpServerModel


async def _insert_mcp(name: str, owner_id: int) -> int:
    async with async_db_session.begin() as db:
        row = AiMcpServerModel(
            name=name,
            transport="streamable-http",
            enabled=True,
            created_id=owner_id,
            updated_id=owner_id,
        )
        db.add(row)
        await db.flush()
        return row.id


async def _create_agent(mcp_ids=None, skill_ids=None, tool_ids=None, knowledge_ids=None, uid=1):
    data = SN(
        agent_name="测试智能体",
        category_id=None,
        agent_role="",
        description="",
        model_id=None,
        prompt_id=None,
        temperature=None,
        workflow_id=None,
        tool_ids=tool_ids or [],
        skill_ids=skill_ids or [],
        mcp_ids=mcp_ids or [],
        knowledge_ids=knowledge_ids or [],
        capabilities=[],
        query_enabled=False,
        query_datasource="system",
        input_schema=None,
        avatar="",
        color="",
        markdown=True,
        enabled=True,
        order=0,
    )
    return await AiAgentService.create(data, auth=SN(user=SN(id=uid)))


def test_create_rejects_foreign_mcp():
    """绑定不属于当前用户的 MCP（owner=1 而以 uid=2 视角绑定）应抛异常。"""
    mid = asyncio.run(_insert_mcp("admin_mcp", owner_id=1))
    with pytest.raises(CustomException):
        asyncio.run(_create_agent(mcp_ids=[mid], uid=2))


def test_create_accepts_own_mcp():
    """绑定自己创建的 MCP 应通过。"""
    mid = asyncio.run(_insert_mcp("own_mcp", owner_id=1))
    a = asyncio.run(_create_agent(mcp_ids=[mid], uid=1))
    assert a["mcp_ids"] == [mid]


def test_create_rejects_missing_skill():
    """绑定不存在技能应抛异常。"""
    with pytest.raises(CustomException):
        asyncio.run(_create_agent(skill_ids=[999999], uid=1))


def test_create_rejects_missing_tool():
    """绑定不存在工具应抛异常。"""
    with pytest.raises(CustomException):
        asyncio.run(_create_agent(tool_ids=["no_such_tool"], uid=1))
