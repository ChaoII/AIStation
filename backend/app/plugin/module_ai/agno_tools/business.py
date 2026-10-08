"""统一 Agno 业务工具注册中心：把 AIStation 内置业务工具注册为 Agno 原生 Function。

设计目标（对齐用户「都用 agno，工具统一注册管理」）：
- 复用 ``assistant.tools`` 的 ``TOOL_REGISTRY``（业务工具的单一事实来源），
  将其中的每个工具包装为 Agno ``Function``（通过 ``@tool`` 装饰器生成），
  供 Agno ``Agent`` / ``Team`` 统一调度，替代手写 OpenAI function-calling。

- ``user_id`` 注入：业务工具（如 ``ai_query``/``resolve_object``/``generate_report``）
  需要当前请求用户。Agno 的工具参数对模型可见，为避免把 ``user_id`` 暴露给模型，
  这里用 ``contextvars`` 在每次运行前注入，模型侧不可见、也无需传参。

- 包装时不改变业务工具的执行逻辑，仅剔除 ``user_id`` 形参并补上上下文注入。
"""
from __future__ import annotations

import contextvars
import functools
import inspect

from agno.tools.decorator import tool

#: 当前运行请求的用户 id，供业务工具在运行时读取（模型不可见）
USER_ID_CONTEXT: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "business_user_id", default=None
)


def set_user_context(user_id: int | None):
    """在启动一轮 Agno 运行前注入用户上下文（ContextVar 仅线程/任务内生效）。"""
    token = USER_ID_CONTEXT.set(user_id)
    return token


def reset_user_context(token) -> None:
    """恢复注入前的用户上下文，避免跨请求泄漏。"""
    if token is not None:
        USER_ID_CONTEXT.reset(token)


def _inject_user_id(fn):
    """为业务工具生成包装函数：剔除 ``user_id`` 形参，运行时从 ContextVar 注入。

    返回的 wrapper 保留原签名（除 user_id）与文档，Agno ``@tool`` 据此
    生成正确的参数 schema 与描述；模型不会看到 user_id 参数。
    """
    sig = inspect.signature(fn)
    params = [p for p in sig.parameters.values() if p.name != "user_id"]
    new_sig = sig.replace(parameters=params)

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        kwargs["user_id"] = USER_ID_CONTEXT.get()
        return await fn(*args, **kwargs)

    wrapper.__signature__ = new_sig
    return wrapper


def _build_agno_tool(entry: dict) -> object | None:
    """把一条业务工具注册表条目包装为 Agno ``Function``。

    依赖初始化失败或包装异常时返回 None（调用方跳过该工具，保证其它工具可用）。
    """
    try:
        fn = entry["fn"]
        name = entry["schema"]["function"]["name"]
        description = entry["schema"]["function"].get("description", "")
        wrapper = _inject_user_id(fn)
        # ``tool`` 装饰器返回 Function 对象；name/description 显式给定，
        # 避免与内置 docstring 推导不一致。
        return tool(name=name, description=description)(wrapper)
    except Exception:  # noqa: BLE001 单个工具失败不影响整体注册
        return None


def build_business_tools() -> list:
    """返回全部可用业务工具对应的 Agno Function 列表。

    供 Agno ``Agent(tools=[...])`` 使用。仅收录能成功包装的工具。
    """
    try:
        from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY
    except Exception:  # noqa: BLE001
        return []

    out: list = []
    for entry in TOOL_REGISTRY.values():
        agno_fn = _build_agno_tool(entry)
        if agno_fn is not None:
            out.append(agno_fn)
    return out
