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


def all_capability_codes() -> list[str]:
    """全部能力码（按品类 + 能力码排序，与 :func:`all_capabilities` 同序）。"""
    return [cap.code for cap in all_capabilities()]


def is_valid_capability_code(code: str) -> bool:
    """判断给定字符串是否为合法能力码（注册表中存在）。"""
    if not isinstance(code, str):
        return False
    return code in _REGISTRY


def capabilities_for_codes(codes: set[str] | list[str]) -> list[Capability]:
    """按授权能力码集合过滤出能力（顺序同 :func:`all_capabilities`）。"""
    codeset = set(codes or [])
    return [cap for cap in all_capabilities() if cap.code in codeset]


# --------------------------------------------------------------------------- #
# 授权归一与出口控制（按需授权：能力码 + REST/MCP 出口分离）
# --------------------------------------------------------------------------- #

#: 合法出口标识。
GRANT_CHANNELS = ("rest", "mcp")


def _perm_to_codes() -> dict[str, set[str]]:
    """``权限点 → 该权限点下全部能力码`` 反查（用于兼容旧 integration:* 授权）。"""
    out: dict[str, set[str]] = {}
    for cap in all_capabilities():
        out.setdefault(cap.perm, set()).add(cap.code)
    return out


def _default_channels(cap: Capability) -> set[str]:
    """某能力默认开放的出口（rest 若 ``cap.rest``；mcp 若 ``cap.mcp_tool``）。"""
    out: set[str] = set()
    if cap.rest:
        out.add("rest")
    if cap.mcp_tool:
        out.add("mcp")
    return out


def resolve_capability_grants(raw: list | None) -> set[str]:
    """把应用的 ``capabilities`` 字段归一为**授权能力码集合**。

    兼容存量数据：``integration:*`` 权限点 → 展开为该权限点下全部能力码；
    能力码原样保留；非法项丢弃；返回空集表示未授权任何能力。
    """
    if not raw:
        return set()
    perm_codes = _perm_to_codes()
    grants: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        if item.startswith("integration:"):
            grants |= perm_codes.get(item, set())
        elif is_valid_capability_code(item):
            grants.add(item)
    return grants


def resolve_channels(raw_channels: dict | None, grants: set[str]) -> dict[str, set[str]]:
    """把应用的 ``channels`` 字段归一为 ``{能力码: {rest,mcp}}``。

    - 仅保留已授权（在 ``grants`` 内）的能力；
    - 某能力在 ``raw_channels`` 缺失 → 用该能力默认出口（全支持）；
    - 非法通道丢弃、不超出口支持范围。
    """
    out: dict[str, set[str]] = {}
    for code in grants:
        cap = get_capability(code)
        if cap is None:
            continue
        default = _default_channels(cap)
        raw = (raw_channels or {}).get(code) if isinstance(raw_channels, dict) else None
        if isinstance(raw, list):
            sel = {ch for ch in raw if ch in GRANT_CHANNELS}
            out[code] = (sel & default) if sel else default
        else:
            out[code] = default
    return out


def normalize_channels(raw_channels: dict | None, grants: set[str]) -> dict[str, list[str]]:
    """写入侧：把 ``channels`` 归一为可存储的 ``{能力码: [出口,...]}``（仅授权能力）。"""
    resolved = resolve_channels(raw_channels, grants)
    return {code: sorted(chans) for code, chans in resolved.items()}


def is_granted(
    grants: set[str], channels: dict | None, code: str, channel: str
) -> bool:
    """判断某能力是否已授权且开放指定出口（``rest`` / ``mcp``）。"""
    if code not in grants:
        return False
    chans = (channels or {}).get(code)
    if chans is None:
        cap = get_capability(code)
        chans = _default_channels(cap) if cap is not None else set()
    return channel in chans


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
