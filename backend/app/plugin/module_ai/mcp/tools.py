"""MCP 运行时装配：把 MCP 服务器配置转成 agno ``MCPTools`` 并管理生命周期。

设计（对齐用户「都用 agno」）：MCP 客户端完全使用 agno 原生 ``MCPTools``，
不引入第二套 MCP 客户端实现。任何服务器不可用（缺命令/连不上）都只跳过该项，
不影响 Agent 其余能力（降级运行）。
"""
from __future__ import annotations

import asyncio

from app.core.logger import log


def _str_map(data) -> dict | None:
    """把配置字典规范化为 ``{str: str}``；空返回 None。"""
    if not data:
        return None
    return {str(k): str(v) for k, v in data.items()}


def build_mcp_tools(servers: list[dict] | None) -> list:
    """按服务器配置构建 ``MCPTools`` 列表（配置不合法者跳过）。"""
    if not servers:
        return []
    from agno.tools.mcp import MCPTools

    tools: list = []
    for s in servers:
        try:
            transport = (s.get("transport") or "streamable-http").lower()
            name = s.get("name") or "mcp"
            prefix = f"{name}_"
            if transport == "stdio":
                command = (s.get("command") or "").strip()
                if not command:
                    log.warning(f"MCP 服务器 {name} 缺少启动命令，已跳过")
                    continue
                from mcp import StdioServerParameters

                params = StdioServerParameters(
                    command=command,
                    args=[str(a) for a in (s.get("args") or [])],
                    env=_str_map(s.get("env")),
                )
                tools.append(
                    MCPTools(
                        server_params=params,
                        transport="stdio",
                        name=name,
                        tool_name_prefix=prefix,
                    )
                )
            else:
                url = (s.get("url") or "").strip()
                if not url:
                    log.warning(f"MCP 服务器 {name} 缺少服务地址，已跳过")
                    continue
                tools.append(
                    MCPTools(
                        url=url,
                        transport=transport,
                        headers=_str_map(s.get("headers")),
                        name=name,
                        tool_name_prefix=prefix,
                    )
                )
        except Exception as e:  # noqa: BLE001  单项失败不影响其它服务器
            log.warning(f"MCP 服务器 {s.get('name')} 装配失败：{e}")
            continue
    return tools


async def connect_mcp_tools(tools: list) -> list:
    """逐个连接 MCP 工具集，返回连接成功的列表（失败项跳过并记日志）。"""
    connected: list = []
    for t in tools or []:
        try:
            # A3: 连接加超时兜底，避免不可达 MCP 服务器挂起整个对话
            await asyncio.wait_for(t.connect(), timeout=10)
            connected.append(t)
        except Exception as e:  # noqa: BLE001  连不上就降级，不阻断对话
            log.warning(f"MCP 连接失败（{getattr(t, 'name', '')}）：{e}")
    return connected


async def close_mcp_tools(tools: list) -> None:
    """关闭所有已连接的 MCP 工具集（忽略关闭异常）。"""
    for t in tools or []:
        try:
            await t.close()
        except Exception:  # noqa: BLE001
            continue
