"""删除资产后的智能体绑定清理。

资产被删除（软删除）后，若智能体仍保留 ``tool_ids``（按名）/``skill_ids``/``mcp_ids``，
运行时会静默丢掉该能力，用户却看不到原因。这里在删除路径上把对应绑定一并摘除。

说明：智能体数量为百级，按行读取再在 Python 侧过滤即可，避免依赖 PG 专属的 JSONB
包含运算符（测试环境为 SQLite）。
"""
from collections.abc import Iterable

from sqlalchemy import select

from app.plugin.module_ai.agent.model import AiAgentModel


async def detach_from_agents(
    db,
    *,
    tool_names: Iterable[str] = (),
    skill_ids: Iterable[int] = (),
    mcp_ids: Iterable[int] = (),
) -> int:
    """把已删除资产从所有智能体绑定中摘除，返回受影响的智能体数量。"""
    names = {str(n) for n in tool_names if n}
    sids = {int(i) for i in skill_ids if i}
    mids = {int(i) for i in mcp_ids if i}
    if not (names or sids or mids):
        return 0

    agents = (await db.execute(select(AiAgentModel))).scalars().all()
    changed = 0
    for agent in agents:
        touched = False
        if names and agent.tool_ids:
            kept = [n for n in agent.tool_ids if n not in names]
            if len(kept) != len(agent.tool_ids):
                agent.tool_ids = kept
                touched = True
        if sids and agent.skill_ids:
            kept = [i for i in agent.skill_ids if i not in sids]
            if len(kept) != len(agent.skill_ids):
                agent.skill_ids = kept
                touched = True
        if mids and agent.mcp_ids:
            kept = [i for i in agent.mcp_ids if i not in mids]
            if len(kept) != len(agent.mcp_ids):
                agent.mcp_ids = kept
                touched = True
        if touched:
            changed += 1
    return changed
