"""AI 集成开放平台 —— MCP Server（Streamable HTTP）。

设计要点
--------
- **工具即能力**：注册表里 ``mcp_tool`` 非空的能力各注册一个 MCP 工具，工具调用
  统一走 :func:`openapi.invoke_capability`（权限 → 限流/配额 → 执行 → 审计，
  ``method="MCP"``）；**不重写业务**。
- **鉴权在传输层**：``Bearer <appid>:<appkey>``（与开放 REST 同一套凭证）；
  未带/错误凭证直接 401，不进 MCP 协议层。
- **按授权过滤工具**：``list_tools`` 只返回当前应用已授权的能力
  （子类覆写，避免把未授权能力暴露给客户端）。
- **会话审计**：``initialize`` 落一行 ``ai_integration_mcp_sessions``；后续请求
  按 ``mcp-session-id`` 更新该行（工具调用数、结束时间、关闭原因）。

实现物说明（与 spec 的差异）：spec 写「FastMCP」，但 ``mcp`` 2.x 已把 ``FastMCP``
更名为 ``MCPServer``（``mcp/server/fastmcp.py`` 是导入即抛的占位模块），
因此本实现使用 :class:`mcp.server.mcpserver.MCPServer`，即 FastMCP 的继任者。

挂载方式：不能直接 ``app.mount()`` 子 Starlette（子应用 lifespan 不会运行），
改为在 FastAPI lifespan 里 ``async with mcp_session_manager():`` 启动会话管理器，
并把 ``StreamableHTTPASGIApp`` 挂在 ``/ai/develop-api/mcp``。
"""
from __future__ import annotations

import contextlib
import inspect
import json
import time
from collections.abc import AsyncIterator
from contextvars import ContextVar
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from .auth import AppContext, _parse_bearer
from .model import AiIntegrationAppModel, AiIntegrationMcpSessionModel
from .openapi import invoke_capability
from .registry import Capability, capabilities_for, mcp_capabilities
from .service import DevelopService, _app_to_dict

#: 当前请求的应用上下文（由 :class:`McpAuthMiddleware` 写入，工具执行时读取）。
CURRENT_APP_CTX: ContextVar[AppContext | None] = ContextVar("mcp_app_ctx", default=None)
#: 当前请求的 Redis 客户端（限流/配额用；由中间件注入）。
CURRENT_REDIS: ContextVar[Any] = ContextVar("mcp_redis", default=None)
#: 当前请求内的工具调用计数（**可变对象**：MCP 传输层可能在自己的任务里执行工具，
#: 整数型 ContextVar 的改动无法回传到中间件，故用 dict 承载计数）。
_TOOL_CALLS: ContextVar[dict | None] = ContextVar("mcp_tool_calls", default=None)

#: JSON-RPC 方法 → 会话行的中文「关闭原因」（管理端可读，别直接暴露方法名）。
_METHOD_LABELS: dict[str, str] = {
    "initialize": "握手完成",
    "tools/list": "查询工具清单",
    "tools/call": "工具调用",
    "resources/list": "查询资源清单",
    "prompts/list": "查询提示词清单",
    "ping": "心跳",
}


def _close_reason(method: str | None) -> str:
    """把 JSON-RPC 方法名转成中文会话原因（未知方法保留原名，便于排查）。"""
    if not method:
        return "请求完成"
    return _METHOD_LABELS.get(method, method)[:64]


#: JSON Schema 类型 → Python 类型（用于生成 MCP 工具的入参签名）。
_JSON_TYPES: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict,
    "array": list,
}

_SERVER_NAME = "aistation-ai-integration"
_SERVER_VERSION = "1.0.0"


def _jsonrpc_method(body: bytes) -> str | None:
    """从请求体里取 JSON-RPC 方法名（非 JSON / 批量请求返回 ``None``）。"""
    if not body:
        return None
    try:
        payload = json.loads(body.decode("utf-8", errors="ignore"))
    except (ValueError, UnicodeDecodeError):
        return None
    if isinstance(payload, list):
        return None
    if isinstance(payload, dict):
        method = payload.get("method")
        return method if isinstance(method, str) else None
    return None


def _client_info(headers: dict[str, str]) -> str | None:
    """客户端标识（User-Agent，截断 128）。"""
    ua = headers.get("user-agent")
    return ua[:128] if ua else None


async def _deny(send, status: int = 401, detail: str = "鉴权失败") -> None:
    """直接回一个最小 JSON 响应（不走 MCP 协议层）。"""
    body = json.dumps({"detail": detail}, ensure_ascii=False).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _record_session(
    app_row: AiIntegrationAppModel,
    *,
    method: str | None,
    session_key: str | None,
    tool_calls: int,
    duration_s: int,
    client_info: str | None,
) -> None:
    """写/更新 MCP 会话审计行。

    - ``initialize``：新建一行（一次连接一行）；
    - 其他请求：按 ``(app_id, session_id)`` 更新该行（工具调用数、结束时间、关闭原因），
      找不到行时补建（不丢审计）。
    """
    now = datetime.now()
    async with async_db_session.begin() as db:
        row = None
        if session_key:
            row = (
                await db.execute(
                    select(AiIntegrationMcpSessionModel).where(
                        AiIntegrationMcpSessionModel.app_id == app_row.id,
                        AiIntegrationMcpSessionModel.session_id == session_key,
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            db.add(
                AiIntegrationMcpSessionModel(
                    app_id=app_row.id,
                    appid=app_row.appid,
                    session_id=(session_key or f"mcp-{uuid4().hex[:16]}")[:64],
                    transport="streamable-http",
                    client_info=client_info,
                    started_at=now,
                    ended_at=now,
                    duration_s=duration_s,
                    tool_calls=tool_calls,
                    close_reason=_close_reason(method),
                )
            )
            return
        row.ended_at = now
        row.duration_s = (row.duration_s or 0) + duration_s
        row.tool_calls = (row.tool_calls or 0) + tool_calls
        row.close_reason = _close_reason(method)


def _tool_function(cap: Capability):
    """按能力的 ``input_schema`` 生成带正确入参签名的 MCP 工具函数。

    MCP SDK 从函数签名推导 ``inputSchema``；这里用 ``__signature__`` 注入
    schema 里的字段（类型/必填），避免手写 ``exec`` 生成函数体。
    """

    async def _tool(**kwargs: Any) -> str:
        ctx = CURRENT_APP_CTX.get()
        if ctx is None:  # 正常不会发生（中间件已鉴权）
            raise ValueError("鉴权失败")
        counter = _TOOL_CALLS.get()
        if counter is not None:
            counter["n"] = counter.get("n", 0) + 1
        payload = {k: v for k, v in kwargs.items() if v is not None}
        try:
            result = await invoke_capability(
                ctx,
                cap.code,
                payload,
                method="MCP",
                redis=_current_redis(),
                request_path=f"/mcp#{cap.mcp_tool}",
                transport="streamable-http",
            )
        except CustomException as e:
            # 转成 MCP 工具错误（SDK 会原样透出消息）：客户端看到明确的中文原因，
            # 而不是笼统的 "Error executing tool"。
            from mcp.server.mcpserver.exceptions import ToolError

            raise ToolError(f"[{e.code}] {e.msg}") from e
        return json.dumps(result, ensure_ascii=False, default=str)

    properties = (cap.input_schema or {}).get("properties") or {}
    required = set((cap.input_schema or {}).get("required") or [])
    params = []
    for name, spec in properties.items():
        annotation = _JSON_TYPES.get(str((spec or {}).get("type")), str)
        default = inspect.Parameter.empty if name in required else None
        params.append(
            inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, annotation=annotation, default=default)
        )
    _tool.__signature__ = inspect.Signature(params)  # type: ignore[attr-defined]
    _tool.__name__ = cap.mcp_tool or cap.code
    _tool.__doc__ = cap.description
    return _tool


def _current_redis():
    """取当前请求的 Redis 客户端（由中间件从 ``scope["app"].state`` 注入）。

    取不到时返回 ``None``：限流/配额整体跳过（降级），不阻断工具调用。
    """
    return CURRENT_REDIS.get()


def _scope_redis(scope) -> Any:
    """从 ASGI scope 里取应用级 Redis 客户端（``app.state.redis``，取不到为 None）。"""
    app = scope.get("app")
    state = getattr(app, "state", None)
    return getattr(state, "redis", None) if state is not None else None


def build_mcp_server():
    """构造 MCP Server 并注册全部 MCP 能力工具（惰性单例见 :func:`_get_server`）。"""
    from mcp.server.mcpserver import MCPServer

    class _PermFilteredServer(MCPServer):
        """按当前应用授权过滤 ``tools/list``（未授权能力不暴露给客户端）。"""

        async def list_tools(self):  # type: ignore[override]
            tools = await super().list_tools()
            ctx = CURRENT_APP_CTX.get()
            if ctx is None:
                return []
            allowed = {cap.mcp_tool for cap in capabilities_for(ctx.perms) if cap.mcp_tool}
            return [tool for tool in tools if tool.name in allowed]

    server = _PermFilteredServer(
        name=_SERVER_NAME,
        version=_SERVER_VERSION,
        instructions=(
            "AIStation 开放能力。所有工具调用均按应用的授权能力校验；"
            "未授权的工具不会出现在工具列表里。"
        ),
    )
    for cap in mcp_capabilities():
        server.add_tool(
            _tool_function(cap),
            name=cap.mcp_tool,
            description=f"{cap.name}：{cap.description}",
        )

    # 资源：当前应用**已授权**的能力清单（JSON，供客户端一次性了解可用工具面）
    @server.resource(
        uri="aistation://capabilities",
        name="开放能力清单",
        description="当前应用已授权的开放能力（能力码/权限点/MCP 工具名），按凭证过滤",
        mime_type="application/json",
    )
    def _capabilities_resource() -> str:
        from .registry import capabilities_for, to_public_dict

        ctx = CURRENT_APP_CTX.get()
        if ctx is None:  # 正常不会发生（传输层已鉴权）
            raise ValueError("鉴权失败")
        items = [to_public_dict(c) for c in capabilities_for(ctx.perms)]
        return json.dumps(
            {"appid": ctx.appid, "total": len(items), "capabilities": items},
            ensure_ascii=False,
            default=str,
        )

    # 提示词：接入引导（客户端可拉取，说明工具用法与约束）
    @server.prompt(
        name="platform_guide",
        title="平台能力接入引导",
        description="说明如何调用本平台开放能力（工具即能力、按授权过滤、敏感操作需审批）",
    )
    def _platform_guide_prompt() -> str:
        ctx = CURRENT_APP_CTX.get()
        appid = ctx.appid if ctx else "{appid}"
        return (
            f"你正在通过 MCP 访问 AIStation 平台（应用 {appid}）。\n"
            "1. 先用 resources/list 读取 aistation://capabilities，确认当前应用已授权的能力；\n"
            "2. 工具与能力一一对应（如 agent_list / chat_send），参数见工具的 inputSchema；\n"
            "3. 敏感能力（删除智能体、训练任务创建/启停）若应用开启「需人工审批」，"
            "调用会返回 pending_approval，需平台管理员批准后执行；\n"
            "4. 所有调用都写入平台审计，appid:appkey 只能放在服务端请求头。"
        )

    return server


_SERVER = None
_SESSION_MANAGER_READY = False


def _get_server():
    """惰性构造 MCP Server（并确保 session manager 已创建）。"""
    global _SERVER, _SESSION_MANAGER_READY
    if _SERVER is None:
        _SERVER = build_mcp_server()
        # streamable_http_app() 内部会创建 session manager；必须先调一次，
        # 否则 server.session_manager 抛 RuntimeError。
        #
        # 关闭 SDK 默认的 DNS-rebinding 保护：它只允许 Host 为 127.0.0.1/localhost，
        # 而本端点是**服务端到服务端**调用（浏览器拿不到 appkey，天然不具备 CSRF 面），
        # 且部署时 Host 是真实域名/IP。鉴权仍由 Bearer appid:appkey 强制。
        try:
            from mcp.server.transport_security import TransportSecuritySettings

            security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
        except Exception:  # noqa: BLE001 - 旧版本无该配置则用默认
            security = None
        from app.config.setting import settings

        _SERVER.streamable_http_app(
            streamable_http_path="/",
            json_response=True,
            transport_security=security,
            max_sessions=max(1, int(settings.MCP_MAX_SESSIONS)),
            session_idle_timeout=float(settings.MCP_SESSION_IDLE_TIMEOUT),
        )
        _SESSION_MANAGER_READY = True
    return _SERVER


class McpAuthMiddleware:
    """MCP 传输层鉴权 + 会话审计（ASGI 中间件）。

    校验 ``Authorization: Bearer <appid>:<appkey>``（与开放 REST 同一套凭证）；
    成功则把 :class:`AppContext` 写入 :data:`CURRENT_APP_CTX` 供工具读取，
    并在请求结束后写/更新 MCP 会话审计行。
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in (scope.get("headers") or [])
        }
        parsed = _parse_bearer(headers.get("authorization"))
        if parsed is None:
            await _deny(send)
            return
        appid, appkey = parsed
        app_row = await DevelopService.verify_appkey(appid, appkey)
        if app_row is None:
            await _deny(send)
            return

        ctx = AppContext(
            app_id=app_row.id,
            appid=app_row.appid,
            perms=set(app_row.capabilities or []),
            quota=app_row.quota,
            app=_app_to_dict(app_row),
        )
        ctx_token = CURRENT_APP_CTX.set(ctx)
        counter = {"n": 0}
        calls_token = _TOOL_CALLS.set(counter)
        redis_token = CURRENT_REDIS.set(_scope_redis(scope))

        body = bytearray()

        async def _receive():
            message = await receive()
            if message.get("type") == "http.request":
                body.extend(message.get("body") or b"")
            return message

        captured: dict[str, str] = {}

        async def _send(message):
            if message.get("type") == "http.response.start":
                for key, value in message.get("headers") or []:
                    if key.decode("latin-1").lower() == "mcp-session-id":
                        captured["sid"] = value.decode("latin-1")
            await send(message)

        started = time.perf_counter()
        try:
            await self.app(scope, _receive, _send)
        finally:
            method = _jsonrpc_method(bytes(body))
            session_key = captured.get("sid") or headers.get("mcp-session-id")
            tool_calls = counter.get("n", 0)
            duration_s = int(time.perf_counter() - started)
            with contextlib.suppress(Exception):  # 审计失败不影响协议响应
                await _record_session(
                    app_row,
                    method=method,
                    session_key=session_key,
                    tool_calls=tool_calls,
                    duration_s=duration_s,
                    client_info=_client_info(headers),
                )
            _TOOL_CALLS.reset(calls_token)
            CURRENT_REDIS.reset(redis_token)
            CURRENT_APP_CTX.reset(ctx_token)


def mcp_asgi_app() -> McpAuthMiddleware:
    """返回可直接 ``app.mount()`` 的 MCP ASGI 应用（鉴权包装 + Streamable HTTP）。"""
    from mcp.server.streamable_http_manager import StreamableHTTPASGIApp

    server = _get_server()
    return McpAuthMiddleware(StreamableHTTPASGIApp(server.session_manager))


@contextlib.asynccontextmanager
async def mcp_session_manager() -> AsyncIterator[None]:
    """启动 MCP 会话管理器（必须在 FastAPI lifespan 内 ``async with``）。"""
    server = _get_server()
    async with server.session_manager.run():
        yield


def mount_mcp(app) -> None:
    """把 MCP 端点注册到 FastAPI 应用（``/ai/develop-api/mcp``，对外带 ``/api/v1`` 前缀）。

    用 ``Route`` 而不是 ``app.mount()``：``Mount`` 要求以 ``/`` 结尾，否则对
    ``/ai/develop-api/mcp`` 回 307 重定向到 ``/ai/develop-api/mcp/``——很多 MCP
    客户端不跟随重定向（POST 307 还会丢自定义头），会直接连不上。
    """
    from starlette.routing import Route

    app.router.routes.append(
        Route("/ai/develop-api/mcp", mcp_asgi_app(), include_in_schema=False)
    )
