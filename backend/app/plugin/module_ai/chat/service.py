"""AI 对话（/chat，旧网关）：执行复用共享 Agno Agent；会话管理统一由 `/sessions` 提供（单一口子）。"""
import json
from typing import Any

from app.api.v1.module_system.auth.schema import AuthSchema
from app.core.logger import log


class ChatService:
    """聊天执行服务（非流式 /ai-chat）。会话的列举/详情/新建/重命名/删除统一走 `/sessions`。"""

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
