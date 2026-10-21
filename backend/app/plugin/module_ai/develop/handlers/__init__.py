"""开放面能力 handler 包。

导入本包即注册全部已实现能力（模块导入时调用各 ``register_*``）。
新增品类时：新建 ``handlers/<category>.py``，实现 ``register_<category>_capabilities()``，
并在此处 import + 调用一次。
"""
from __future__ import annotations

from .agents import register_agent_capabilities
from .chat import register_chat_capabilities
from .train import register_train_capabilities


def register_all() -> None:
    """注册全部开放能力（幂等：重复调用不重复注册）。"""
    from ..registry import all_capabilities

    existing = {cap.code for cap in all_capabilities()}
    if "agent.list" in existing:
        return
    register_agent_capabilities()
    register_chat_capabilities()
    register_train_capabilities()


# 导入本包即完成注册（开放端点与 MCP 工具都依赖注册表已填充）。
register_all()
