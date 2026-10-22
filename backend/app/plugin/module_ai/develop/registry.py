"""AI 集成开放平台 —— 能力注册表（元数据 + 分发，纯逻辑，无 DB / HTTP）。

P2/P3 的统一入口：REST 与 MCP 两态出口都从这里取能力元数据并分发到
handler。注册表**只做元数据与查表**，不重写业务逻辑——handler 复用既有
service。

约定：
- ``code``：能力码，形如 ``"agent.list"``，全局唯一（重复注册抛错）。
- ``perm``：调用该能力所需的权限点，必须来自 ``capabilities.PERMISSION_CODES``。
- ``mcp_tool``：MCP 工具名（``None`` = 不对 MCP 暴露），MCP 工具名不允许重复。
- ``handler``：``async def handler(*, app_ctx, payload) -> Any``。
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .capabilities import is_valid_perm

#: handler 统一签名：关键字参数 ``app_ctx``（AppContext）与 ``payload``（dict）。
Handler = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class Capability:
    """一个对外开放能力：元数据 + 分发入口。

    Attributes:
        code: 能力码（``"train.create"``），全局唯一。
        category: 所属品类码（train/agent/chat/bot），须存在于 ``CATEGORIES``。
        perm: 调用所需权限点（``integration:train:create``）。
        name: 中文名（管理端展示）。
        description: 一句话说明（接入文档与 MCP 工具描述共用）。
        input_schema: 入参 JSON Schema（MCP 工具 schema 与文档共用）。
        returns: 返回值说明（文档展示）。
        handler: 异步处理函数；注册时可为 ``None``（仅登记元数据）。
        mcp_tool: MCP 工具名；``None`` = 不暴露为 MCP 工具。
        rest: 是否暴露为 REST 能力（默认 ``True``）。
        requires_approval: 是否为「敏感能力」——应用开启 ``requires_approval`` 时，
            调用该能力先进入待审批队列（管理员批准后才执行）。
    """

    code: str
    category: str
    perm: str
    name: str
    description: str
    input_schema: dict
    returns: str
    handler: Handler | None = None
    mcp_tool: str | None = None
    rest: bool = True
    requires_approval: bool = False


_REGISTRY: dict[str, Capability] = {}
_MCP_TOOLS: dict[str, str] = {}


def register(cap: Capability) -> None:
    """登记一个能力。

    Args:
        cap: 能力定义。

    Raises:
        ValueError: 能力码重复、权限点非法，或 MCP 工具名重复。
    """
    if cap.code in _REGISTRY:
        raise ValueError(f"能力码重复注册: {cap.code}")
    if not is_valid_perm(cap.perm):
        raise ValueError(f"能力权限点非法: {cap.perm}")
    if cap.mcp_tool:
        if cap.mcp_tool in _MCP_TOOLS:
            raise ValueError(f"MCP 工具名重复: {cap.mcp_tool}")
        _MCP_TOOLS[cap.mcp_tool] = cap.code
    _REGISTRY[cap.code] = cap


def get_capability(code: str) -> Capability | None:
    """按能力码取能力定义，不存在返回 ``None``。"""
    return _REGISTRY.get(code)


def all_capabilities() -> list[Capability]:
    """全部能力（按品类 + 能力码排序，顺序稳定）。"""
    return sorted(_REGISTRY.values(), key=lambda c: (c.category, c.code))


def capabilities_for(perms: set[str]) -> list[Capability]:
    """按授权权限集合过滤出可用能力（顺序同 :func:`all_capabilities`）。"""
    return [cap for cap in all_capabilities() if cap.perm in perms]


def to_public_dict(cap: Capability) -> dict:
    """转成对外可暴露的元数据 dict（**不含 handler**）。"""
    return {
        "code": cap.code,
        "category": cap.category,
        "perm": cap.perm,
        "name": cap.name,
        "description": cap.description,
        "input_schema": cap.input_schema,
        "returns": cap.returns,
        "mcp_tool": cap.mcp_tool,
        "rest": cap.rest,
        "requires_approval": cap.requires_approval,
    }


def mcp_capabilities() -> list[Capability]:
    """暴露为 MCP 工具的能力（``mcp_tool`` 非空）。"""
    return [cap for cap in all_capabilities() if cap.mcp_tool]
