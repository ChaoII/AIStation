"""开放面能力 handler —— 对话与机器人（chat / bot 品类）。

- ``chat.send``：把消息发给 Agent / AI 应用 / 工作流，**聚合成非流式回复**返回
  （开放 REST 与 MCP 都是请求-响应语义，不做 SSE）；会话续接复用嵌入通道同一套
  ``(app_id, sid)`` 映射（``ai_integration_embed_sessions``），跨应用互不可见。
- ``chat.sessions`` / ``chat.messages``：只返回本应用（``source_app_id``）的会话。
- ``bot.use``：对指定 AI 应用发一条消息并取回复（权限点独立为
  ``integration:bot:use``，便于按「机器人」单独授权）。
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, AsyncIterator
from uuid import uuid4

from sqlalchemy import select

from app.core.database import async_db_session
from app.core.exceptions import CustomException

from ..auth import AppContext
from ..embed import EmbedService
from ..model import AiIntegrationEmbedSessionModel
from ..registry import Capability, register

#: 开放面调用既有 run 服务时的「无平台用户」身份。
_OPEN_AUTH = SimpleNamespace(user=None)
_KINDS = ("agent", "app", "workflow")


def _need_str(payload: dict, key: str, *, max_len: int = 4000) -> str:
    """取必填字符串字段（去空白、限长），非法抛 400。"""
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CustomException(msg=f"参数不合法：{key} 必须为非空字符串", code=10400, status_code=400)
    return value.strip()[:max_len]


async def _run_frames(kind: str, target_id: int, ui_messages: list[dict], session_id: int):
    """按形态取既有 run 服务的帧流（与嵌入通道同一套 service）。"""
    if kind == "agent":
        from app.plugin.module_ai.agent.service import AiAgentService

        return AiAgentService.run_ui_stream(target_id, ui_messages, _OPEN_AUTH, None, session_id)
    if kind == "app":
        from app.plugin.module_ai.apps.service import run_app_ui_stream

        return run_app_ui_stream(target_id, ui_messages, _OPEN_AUTH, None, session_id)
    from app.plugin.module_ai.workflow.service import AiWorkflowService

    return AiWorkflowService.run_ui_stream(target_id, ui_messages, _OPEN_AUTH, None, session_id)


async def _collect_reply(frames: AsyncIterator[str]) -> tuple[str, str | None]:
    """把 SSE 帧流聚合成一段回复文本。

    兼容两种帧协议（既有实现不统一）：
    - UI Message Stream：``data: {"type":"text-delta","delta":...}``，收尾
      ``data-finish.reply`` 作为兜底（工作流形态的权威回复）；
    - Agno 事件：``event: RunContent`` + ``data: {"content": ...}``。

    Returns:
        ``(reply, error)``：``error`` 非空表示流内出现 ``error`` 帧。
    """
    parts: list[str] = []
    finish_reply: str | None = None
    error_text: str | None = None
    async for chunk in frames:
        if not chunk:
            continue
        for raw in chunk.split("\n\n"):
            if not raw.strip():
                continue
            event = ""
            data_line = ""
            for line in raw.splitlines():
                if line.startswith("event: "):
                    event = line[7:].strip()
                elif line.startswith("data: "):
                    data_line = line[6:].strip()
            if not data_line or data_line == "[DONE]":
                continue
            try:
                data = json.loads(data_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            if event:  # Agno 帧
                text = data.get("content") or data.get("delta") or data.get("text")
                if isinstance(text, str) and text:
                    parts.append(text)
                continue
            ftype = data.get("type")
            if ftype == "text-delta" and isinstance(data.get("delta"), str):
                parts.append(data["delta"])
            elif ftype == "data-finish":
                payload = data.get("data") or {}
                reply = payload.get("reply") if isinstance(payload, dict) else None
                if isinstance(reply, str) and reply:
                    finish_reply = reply
            elif ftype == "error":
                error_text = str(data.get("errorText") or "对话执行失败")
    text = "".join(parts).strip() or (finish_reply or "")
    return text, error_text


async def _send(
    app_ctx: AppContext, *, kind: str, target_id: int, message: str, sid: str | None
) -> dict:
    """公共发送逻辑：目标校验 → 会话绑定 → 跑流 → 聚合回复。"""
    if kind not in _KINDS:
        raise CustomException(msg="参数不合法：kind 仅支持 agent/app/workflow", code=10400, status_code=400)
    target = await EmbedService.get_target(kind, target_id)
    if target is None:
        raise CustomException(msg="目标不存在", code=10404, status_code=404)
    if not target.get("enabled", True):
        raise CustomException(msg="目标未启用", code=10400, status_code=400)

    session_sid = (sid or f"open-{uuid4().hex[:12]}")[:64]
    # 复用嵌入会话映射：只用到 app_id/kind/target_id 三个属性（鸭子类型即可）
    session_id, session_reset = await EmbedService.prepare_session(
        SimpleNamespace(app_id=app_ctx.app_id, kind=kind, target_id=target_id), session_sid
    )

    from app.plugin.module_ai.sessions.service import AiSessionService

    history = await AiSessionService.get_messages(session_id)
    ui_messages = [{"role": m["role"], "parts": m["parts"]} for m in history]
    ui_messages.append({"role": "user", "parts": [{"type": "text", "text": message}]})

    reply, error_text = await _collect_reply(
        await _run_frames(kind, target_id, ui_messages, session_id)
    )
    if error_text:
        raise CustomException(msg=error_text[:200], code=10400, status_code=400)
    return {
        "reply": reply,
        "sid": session_sid,
        "session_id": session_id,
        "session_reset": session_reset,
        "kind": kind,
        "target_id": target_id,
    }


async def _chat_send(*, app_ctx: AppContext, payload: dict) -> dict:
    kind = payload.get("kind")
    if not isinstance(kind, str):
        raise CustomException(msg="参数不合法：kind 必须为字符串", code=10400, status_code=400)
    target_id = payload.get("target_id")
    if isinstance(target_id, bool) or not isinstance(target_id, int):
        raise CustomException(msg="参数不合法：target_id 必须为整数", code=10400, status_code=400)
    sid = payload.get("sid")
    if sid is not None and not isinstance(sid, str):
        raise CustomException(msg="参数不合法：sid 必须为字符串", code=10400, status_code=400)
    return await _send(
        app_ctx,
        kind=kind,
        target_id=target_id,
        message=_need_str(payload, "message"),
        sid=sid,
    )


async def _bot_use(*, app_ctx: AppContext, payload: dict) -> dict:
    target_id = payload.get("app_id")
    if isinstance(target_id, bool) or not isinstance(target_id, int):
        raise CustomException(msg="参数不合法：app_id 必须为整数", code=10400, status_code=400)
    result = await _send(
        app_ctx, kind="app", target_id=target_id, message=_need_str(payload, "message"), sid=payload.get("sid")
    )
    result.pop("kind", None)
    result["app_id"] = target_id
    return result


async def _own_session_ids(app_id: int) -> list[int]:
    """本应用在嵌入/开放通道下产生的平台会话 id 列表。"""
    async with async_db_session() as db:
        rows = (
            await db.execute(
                select(AiIntegrationEmbedSessionModel.session_id).where(
                    AiIntegrationEmbedSessionModel.app_id == app_id,
                    AiIntegrationEmbedSessionModel.is_deleted.is_(False),
                )
            )
        ).scalars().all()
    return list(rows)


async def _chat_sessions(*, app_ctx: AppContext, payload: dict) -> dict:
    from app.plugin.module_ai.sessions.service import AiSessionService

    items: list[dict] = []
    for session_id in await _own_session_ids(app_ctx.app_id):
        session = await AiSessionService.get_session(session_id)
        if session:
            items.append(session)
    return {"items": items, "total": len(items)}


async def _chat_messages(*, app_ctx: AppContext, payload: dict) -> dict:
    from app.plugin.module_ai.sessions.service import AiSessionService

    session_id = payload.get("session_id")
    if isinstance(session_id, bool) or not isinstance(session_id, int):
        raise CustomException(msg="参数不合法：session_id 必须为整数", code=10400, status_code=400)
    if session_id not in await _own_session_ids(app_ctx.app_id):
        raise CustomException(msg="会话不存在", code=10404, status_code=404)
    return {"session_id": session_id, "items": await AiSessionService.get_messages(session_id)}


def register_chat_capabilities() -> None:
    """注册 chat / bot 品类能力。"""
    defs: list[tuple[str, str, str, str, str, dict, str, Any, str]] = [
        (
            "chat.send",
            "chat",
            "integration:chat:send",
            "发送消息（聚合回复）",
            "把消息发给 Agent / AI 应用 / 工作流并返回最终回复（非流式）",
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["agent", "app", "workflow"]},
                    "target_id": {"type": "integer"},
                    "message": {"type": "string"},
                    "sid": {"type": "string", "description": "会话标识（缺省自动生成，用于续接）"},
                },
                "required": ["kind", "target_id", "message"],
            },
            "reply / session_id / sid / kind / target_id",
            _chat_send,
            "chat_send",
        ),
        (
            "chat.sessions",
            "chat",
            "integration:chat:query",
            "查询本应用会话",
            "列出本应用通过开放通道产生的会话",
            {"type": "object", "properties": {}},
            "items: array, total: int",
            _chat_sessions,
            "chat_sessions",
        ),
        (
            "chat.messages",
            "chat",
            "integration:chat:query",
            "查询会话消息",
            "查询本应用某个会话的历史消息（跨应用 404）",
            {
                "type": "object",
                "properties": {"session_id": {"type": "integer"}},
                "required": ["session_id"],
            },
            "session_id: int, items: array",
            _chat_messages,
            "chat_messages",
        ),
        (
            "bot.use",
            "bot",
            "integration:bot:use",
            "机器人对话",
            "对指定 AI 应用发一条消息并取回复",
            {
                "type": "object",
                "properties": {
                    "app_id": {"type": "integer"},
                    "message": {"type": "string"},
                    "sid": {"type": "string"},
                },
                "required": ["app_id", "message"],
            },
            "reply / session_id / app_id",
            _bot_use,
            "bot_use",
        ),
    ]
    for code, category, perm, name, desc, schema, returns, handler, tool in defs:
        register(
            Capability(
                code=code,
                category=category,
                perm=perm,
                name=name,
                description=desc,
                input_schema=schema,
                returns=returns,
                handler=handler,
                mcp_tool=tool,
            )
        )
