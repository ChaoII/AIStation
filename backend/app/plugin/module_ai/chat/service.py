"""AI 对话（/chat，旧网关）：会话已统一并入规范 `ai_sessions` 仓库，执行复用共享 Agno Agent。"""
import json
from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.common.request import PaginationService
from app.core.logger import log

from .schema import (
    ChatSessionCreateSchema,
    ChatSessionQueryParam,
    ChatSessionUpdateSchema,
)


def _fmt_ai_session(
    sess: dict, auth: AuthSchema | None = None, include_messages: bool = False
) -> dict[str, Any]:
    """把 `ai_sessions` / `ai_messages` 的行格式化成 /chat 前端兼容的会话字典。"""
    out: dict[str, Any] = {
        "id": sess.get("id"),
        "session_id": str(sess.get("id")),
        "title": sess.get("title") or "",
        "message_count": sess.get("message_count") or 0,
        "created_time": sess.get("created_time"),
        "updated_time": sess.get("updated_time"),
        "team_name": None,
    }
    if include_messages:
        out["messages"] = [
            {
                "id": str(m.get("id")),
                "role": m.get("role"),
                "content": "".join(
                    p.get("text", "") for p in (m.get("parts") or []) if isinstance(p, dict)
                ),
                "created_at": None,
            }
            for m in (sess.get("messages") or [])
        ]
    return out


class ChatService:
    """聊天会话管理模块服务层（已统一到 `ai_sessions` + 共享 `build_agent`）。"""

    @classmethod
    async def chat_non_stream(
        cls, message: str, session_id: int | None, auth: AuthSchema
    ) -> dict[str, Any]:
        """非流式 AI 对话（/ai-chat）：用共享 Agno Agent 驱动，会话并入规范 `ai_sessions` 仓库。

        - 会话：优先复用调用方已归属的 `ai_sessions` 会话（整数 id），否则新建。
        - 执行：复用 ``agno_tools.agent_factory.build_agent``（业务工具统一注册）。
        - 落库：每轮经 ``AiSessionService.record_exchange`` 写入 `ai_sessions` / `ai_messages`。
        """
        from app.plugin.module_ai.agno_tools.agent_factory import build_agent
        from app.plugin.module_ai.agno_tools.business import (
            reset_user_context,
            set_user_context,
        )
        from app.plugin.module_ai.provider.service import AiModelService
        from app.plugin.module_ai.sessions.service import AiSessionService

        uid = getattr(getattr(auth, "user", None), "id", None)
        # 归属校验并复用会话；无归属/不符则新建（deny-by-default）
        sess = None
        if session_id:
            try:
                found = await AiSessionService.get_session(int(session_id))
                if found and (found.get("user_id") == uid or not found.get("user_id")):
                    sess = found
            except (TypeError, ValueError):
                sess = None
        if not sess:
            sess = await AiSessionService.create(title=(message or "")[:30], user_id=uid)
        session_id = int(sess["id"])

        try:
            model_config = (
                await AiModelService.get_runtime_model("chat")
                or await AiModelService.get_runtime_model()
            )
            if not model_config:
                return {
                    "response": "未配置大模型，请在 AI 管理→模型配置 中添加并启用",
                    "session_id": session_id,
                    "function_calls": None,
                    "action": None,
                }
            token = set_user_context(uid)
            try:
                agent = build_agent(model_config=model_config, user_id=uid)
                resp = await agent.arun(
                    message,
                    stream=False,
                    user_id=str(uid) if uid is not None else None,
                    add_history_to_context=True,
                )
            finally:
                reset_user_context(token)

            reply = (
                resp.get_content_as_string()
                if hasattr(resp, "get_content_as_string")
                else str(resp.content or "")
            )

            # 从工具执行结果提取 __action__ / function_calls
            action = None
            tool_log: list[dict[str, Any]] = []
            for tool in (resp.tools or []):
                name = getattr(tool, "tool_name", None)
                args = getattr(tool, "tool_args", None) or {}
                result = getattr(tool, "result", None)
                try:
                    if isinstance(result, str):
                        result = json.loads(result)
                except (ValueError, TypeError):
                    pass
                if isinstance(result, dict) and result.get("__action__"):
                    action = result["__action__"]
                tool_log.append({"name": name, "args": args, "result": result})

            await AiSessionService.record_exchange(
                session_id, message, reply, user_id=uid
            )
            return {
                "response": reply,
                "session_id": session_id,
                "function_calls": tool_log or None,
                "action": action,
            }
        except Exception as e:  # noqa: BLE001
            log.error(f"聊天查询失败: {e}")
            return {
                "response": f"抱歉，处理您的请求时出现错误：{str(e)}",
                "session_id": session_id,
                "function_calls": None,
                "action": None,
            }

    @classmethod
    async def create_service(
        cls, auth: AuthSchema, data: ChatSessionCreateSchema
    ) -> dict[str, Any] | None:
        """创建会话（并入规范 `ai_sessions` 仓库）。"""
        from app.plugin.module_ai.sessions.service import AiSessionService

        uid = getattr(getattr(auth, "user", None), "id", None)
        session = await AiSessionService.create(data.title or "新对话", None, uid)
        return _fmt_ai_session(session, auth)

    @classmethod
    async def get_session_service(
        cls, auth: AuthSchema, session_id: str
    ) -> dict[str, Any] | None:
        """获取单个会话详情（含消息，来自 `ai_sessions` / `ai_messages`）。"""
        from app.plugin.module_ai.sessions.service import AiSessionService

        uid = getattr(getattr(auth, "user", None), "id", None)
        try:
            session = await AiSessionService.get_session(int(session_id))
        except (TypeError, ValueError):
            return None
        if not session:
            return None
        if session.get("user_id") not in (None, uid):
            return None
        session["messages"] = await AiSessionService.get_messages(int(session_id))
        return _fmt_ai_session(session, auth, include_messages=True)

    @classmethod
    async def page_service(
        cls,
        auth: AuthSchema,
        page_no: int,
        page_size: int,
        search: ChatSessionQueryParam,
        order_by: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """分页获取会话列表（来自 `ai_sessions`）。"""
        from app.plugin.module_ai.sessions.service import AiSessionService

        uid = getattr(getattr(auth, "user", None), "id", None)
        sessions = await AiSessionService.list_sessions(uid)
        items = [_fmt_ai_session(s, auth) for s in sessions]
        result = await PaginationService.paginate(
            data_list=items, page_no=page_no, page_size=page_size
        )
        return result

    @classmethod
    async def update_service(
        cls, auth: AuthSchema, session_id: str, data: ChatSessionUpdateSchema
    ) -> bool:
        """重命名会话（`ai_sessions`）。"""
        from app.plugin.module_ai.sessions.service import AiSessionService

        try:
            result = await AiSessionService.rename(int(session_id), data.title, auth)
        except (TypeError, ValueError):
            return False
        return result is not None

    @classmethod
    async def delete_service(cls, auth: AuthSchema, session_ids: list[str]) -> None:
        """批量删除会话及消息（`ai_sessions`）。"""
        from app.plugin.module_ai.sessions.service import AiSessionService

        ids: list[int] = []
        for s in session_ids:
            try:
                ids.append(int(s))
            except (TypeError, ValueError):
                continue
        if ids:
            await AiSessionService.delete(ids)
