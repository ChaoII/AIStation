"""动态 Agno 工具构建器：把 OpenAI function schema + 派发器包装为 Agno Function。

用途：app/agent 运行台绑定的是 OpenAI function schema（来自 ``_build_app_tools``，
含内置/Agno/HTTP 工具），执行统一走 ``dispatch_tool``。Agno Agent 不接受原生
OpenAI schema，需要把每个 schema 包装成 Agno ``@tool``，执行体调用现有派发器。

设计：
- ``build_dynamic_tools(schemas, dispatch)`` 为每个 schema 生成一个 Agno ``Function``。
- 参数 schema 直接复用 OpenAI ``parameters``（properties/required），名称/描述取自 schema。
- ``dispatch(name, args, user_id)`` 由调用方注入（复用 ``tools_catalog.dispatch_tool`` 或
  app/agent 的自定义派发）。
"""
from __future__ import annotations

import contextvars
import functools

from agno.tools.decorator import tool

#: 当前请求用户 id，供动态工具在运行时注入
_USER_ID_CTX: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "dynamic_tool_user_id", default=None
)


def set_user_context(user_id: int | None):
    return _USER_ID_CTX.set(user_id)


def reset_user_context(token) -> None:
    if token is not None:
        _USER_ID_CTX.reset(token)


def _make_params(schema: dict) -> dict:
    """提取 OpenAI function schema 的 parameters（properties/required）。"""
    func = schema.get("function", {}) if isinstance(schema, dict) else {}
    params = func.get("parameters") or {}
    if not isinstance(params, dict):
        return {"type": "object", "properties": {}, "required": []}
    return params


def build_dynamic_tools(
    schemas: list[dict], dispatch, requires_confirmation: bool = False
) -> list:
    """把 OpenAI function schema 列表包装为 Agno Function 列表。

    - ``dispatch(name, args, user_id)``：异步函数，按工具名派发执行。
    - 每个生成的 Agno Function 执行体内会注入当前 ContextVar 里的 user_id。
    - ``requires_confirmation=True``：为工具打上 ``requires_confirmation``，
      由 Agno 在调用前暂停运行（HITL），经 requirements 确认后继续。
    """
    out: list = []
    for schema in schemas or []:
        try:
            func = schema.get("function", {})
            name = func.get("name")
            if not name:
                continue
            description = func.get("description", "")
            params = _make_params(schema)
            properties = params.get("properties", {})
            required = params.get("required", [])

            # 用 Agno @tool 包装一层：返回 Function，执行体调用 dispatch
            agno_fn = tool(
                name=name,
                description=description,
                requires_confirmation=requires_confirmation or None,
            )(_make_dispatch_wrapper(name, dispatch))
            # Agno 从函数签名推导参数；这里动态函数用 *args/**kwargs，需覆盖 parameters
            # 以匹配原 OpenAI schema（properties/required）。
            agno_fn.parameters = {"type": "object", "properties": properties, "required": required}
            if requires_confirmation:
                agno_fn.requires_confirmation = True
            out.append(agno_fn)
        except Exception:  # noqa: BLE001 单个工具失败不影响整体
            continue
    return out


def _make_dispatch_wrapper(func_name: str, dispatch):
    """构造调用派发器的包装函数（参数以 keyword 透传）。

    注意：不要在这里覆盖 ``__signature__``。Agno 会用 pydantic ``validate_call``
    按签名包装 entrypoint；保留 ``(**kwargs)`` 让 pydantic 接受任意关键字参数，
    这样 ``process_entrypoint`` 中用户显式 ``parameters`` 会被保留（params_set_by_user），
    而执行时能透传所有 schema 参数到 dispatch。
    """

    @functools.wraps(_async_dispatch_stub)
    async def _wrapper(**kwargs):
        user_id = _USER_ID_CTX.get()
        return await dispatch(func_name, kwargs, user_id)

    return _wrapper


async def _async_dispatch_stub(**kwargs):
    """占位函数：仅供 functools.wraps 保留签名（`(**kwargs)`）使用。"""
    return None
