"""Agno Agent 工厂：从运行时模型配置构建 Agno Agent，并装配统一业务工具。

理念（对齐用户「都用 agno」）：所有执行（含工具调用循环）由 Agno ``Agent``
统一驱动，替代手写 OpenAI function-calling。工具来自
``agno_tools.business.build_business_tools()`` 的统一注册中心。
"""
from __future__ import annotations

from typing import Any

from agno.agent import Agent
from agno.models.openai.like import OpenAILike

from app.config.setting import settings
from app.plugin.module_ai.models.service import build_headers

#: 助手指令：约束工具使用与回答风格（中文、禁止编造、变更类提议确认）
AGENT_DESCRIPTION = "你是 AIStation 平台的智能助手，可调用工具查询系统数据、生成报告、导航页面。"
AGENT_INSTRUCTIONS: list[str] = [
    "涉及系统数据时必须调用工具获取，禁止编造",
    "需要跳转页面时使用工具返回导航动作",
    "变更类操作只能提议（propose_* / confirm 动作），由用户确认后执行",
    "用简洁中文回答，取数结果可用 Markdown 表格汇总",
]
AGENT_TEMPERATURE = 0.7

#: 会话上下文保留轮数（用于读取历史）
NUM_HISTORY_RUNS = 3


def build_model(model_config: dict | None = None) -> OpenAILike:
    """用运行时模型配置构建 Agno ``OpenAILike`` 模型；缺省回退 env。

    与 ``chat.utils.AgnoFactory._build_model`` 保持一致：支持自定义请求头。
    """
    mc = model_config or {}
    base_url = mc.get("base_url") or settings.OPENAI_BASE_URL
    kwargs: dict[str, Any] = {
        "id": mc.get("model") or settings.OPENAI_MODEL,
        "api_key": mc.get("api_key") or settings.OPENAI_API_KEY,
        "base_url": base_url,
        "temperature": AGENT_TEMPERATURE,
    }
    headers = build_headers(base_url, mc.get("extra_headers"))
    try:
        return OpenAILike(**kwargs, default_headers=headers or None)
    except TypeError:
        return OpenAILike(**kwargs)


def build_agent(
    *,
    model_config: dict | None = None,
    user_id: int | None = None,
    session_id: int | None = None,
    model: OpenAILike | None = None,
    instructions: list[str] | None = None,
    description: str | None = None,
    tools: list | None = None,
    extra_tools: list | None = None,
    name: str | None = None,
    db=None,
    skills=None,
) -> Agent:
    """构建装配好统一业务工具的 Agno ``Agent``。

    - ``model_config`` / ``model`` 至少提供一个用于覆盖默认模型。
    - 工具默认取自 ``agno_tools.business.build_business_tools()``；传入 ``tools``
      则覆盖（app/agent 运行台可注入自定义/HTTP 工具，见 ``agno_tools.dynamic``）。
    - ``extra_tools``：额外追加的工具集（如 MCP ``MCPTools``），与 ``tools`` 合并。
    - ``instructions`` / ``description`` / ``name`` 可覆盖默认（app/agent 可注入
      渲染后的系统提示词与自定义角色）。
    """
    from .business import build_business_tools

    tool_list = list(tools if tools is not None else build_business_tools())
    if extra_tools:
        tool_list.extend(extra_tools)
    model_obj = model or build_model(model_config)

    kwargs: dict[str, Any] = {
        "name": name or "aistation_assistant",
        "role": "AIStation 智能助手",
        "description": description or AGENT_DESCRIPTION,
        "instructions": instructions if instructions is not None else AGENT_INSTRUCTIONS,
        "model": model_obj,
        "tools": tool_list,
        "markdown": True,
        "add_datetime_to_context": True,
        # ---- agno 原生特性：长时记忆（跨会话记住用户偏好） ----
        "enable_agentic_memory": True,
        "update_memory_on_run": True,
        "add_memories_to_context": True,
        # agno 原生特性：让模型可读取历史 / 输出结构化结果
        "read_chat_history": True,
        "structured_outputs": True,
    }
    if user_id is not None:
        kwargs["user_id"] = str(user_id)
    if session_id is not None:
        kwargs["session_id"] = f"session_{session_id}"
    if db is not None:
        kwargs["db"] = db
    if skills is not None:
        kwargs["skills"] = skills
    return Agent(**kwargs)
