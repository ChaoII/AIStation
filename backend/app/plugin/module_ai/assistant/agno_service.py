"""Agno 原生事件流助手服务：由 Agno Agent 驱动执行，直出 Agno 原生 SSE。

设计（对齐用户「都用 agno、全部换成 Agno 原生流式」）：
- 执行层完全由 ``agno_tools.agent_factory.build_agent`` 构建的 Agno ``Agent`` 驱动，
  Agno 负责全部 function-calling 循环（不再手写 OpenAI 循环）。
- 业务工具统一来自 ``agno_tools.business`` 注册中心。
- 输出为 Agno 原生事件流：``event: <RunEvent>\ndata: {event.to_dict()}\n\n``，
  事件类型见 ``agno.run.agent.RunEvent``（RunStarted / RunContent / ToolCallStarted /
  ToolCallCompleted / ReasoningContentDelta / RunCompleted / RunError ...）。

用法：``async for sse in run_agno_stream(...)`` 产出已格式化的 SSE 字符串。
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from app.core.exceptions import CustomException
from app.plugin.module_ai.provider.service import AiModelService


def _sse(event) -> str:
    """把 Agno RunOutputEvent 格式化为 Agno 原生 SSE 帧。"""
    from agno.os.utils import format_sse_event

    try:
        return format_sse_event(event)
    except Exception:  # noqa: BLE001 单事件序列化失败不中断整个流
        return ": event-serialize-error\n\n"


async def run_agno_stream(
    *,
    messages: list[dict],
    auth,
    user_id: int | None = None,
    session_id: int | None = None,
    knowledge_ids: list[int] | None = None,
    model_id: int | None = None,
) -> AsyncIterator[str]:
    """用 Agno Agent 驱动一轮助手对话，产出 Agno 原生 SSE 事件流。

    - ``messages``：AI SDK UIMessage 列表（兼容现有前端入参），取最后一条 user 文本作为输入。
    - 知识库 RAG 上下文会注入 system 提示。
    - 用户上下文（user_id）通过 ContextVar 注入业务工具。
    """
    from app.plugin.module_ai.agno_tools.agent_factory import build_agent
    from app.plugin.module_ai.agno_tools.business import reset_user_context, set_user_context
    from app.plugin.module_ai.assistant.service import last_user_text

    # 决定运行时模型：显式 model_id > chat 类 > 默认
    model_config = None
    if model_id:
        model_config = await AiModelService.get_runtime_model(model_id=model_id)
    if not model_config:
        model_config = await AiModelService.get_runtime_model("chat") or await AiModelService.get_runtime_model()
    if not model_config:
        raise CustomException(msg="未配置大模型，请在 AI 管理→模型配置 中添加并启用")

    user_text = last_user_text(messages)
    token = set_user_context(user_id)
    try:
        agent = build_agent(model_config=model_config, user_id=user_id, session_id=session_id)

        # 知识库 RAG：检索上下文拼接到 system 提示
        system_ctx = ""
        if knowledge_ids:
            try:
                from app.plugin.module_ai.assistant.service import retrieve_kb_rag

                kb_ctx, _ = await retrieve_kb_rag(knowledge_ids, user_text)
                if kb_ctx:
                    system_ctx = kb_ctx
            except Exception:  # noqa: BLE001 RAG 失败不阻断
                pass

        input_text = user_text
        if system_ctx:
            input_text = f"【参考知识】\n{system_ctx}\n\n问题：{user_text}"
        assistant_text = ""
        async for item in agent.arun(
            input_text,
            stream=True,
            stream_events=True,
            user_id=str(user_id) if user_id is not None else None,
            session_id=f"session_{session_id}" if session_id is not None else None,
            add_history_to_context=True,
        ):
            if isinstance(item, str):
                yield item
                continue
            # 累积正文（RunContent 事件），用于会话落库
            _d = item.to_dict() if hasattr(item, "to_dict") else {}
            if _d.get("event") == "RunContent" and isinstance(_d.get("content"), str):
                assistant_text += _d.get("content", "")
            yield _sse(item)
    finally:
        reset_user_context(token)
        # 会话落库（无论正常/异常/中断）：无 session_id 时内部直接返回
        try:
            from app.plugin.module_ai.sessions.service import persist_session_exchange

            await persist_session_exchange(
                session_id, user_text, assistant_text, user_id=user_id
            )
        except Exception:  # noqa: BLE001 落库失败不阻断（persist_session_exchange 内部已吞异常）
            pass


def agno_stream_response(body: AsyncIterator[str]):
    """Agno 原生事件流的 StreamingResponse（SSE 响应头）。"""
    from fastapi.responses import StreamingResponse

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
        "Content-Encoding": "identity",
    }
    return StreamingResponse(body, media_type="text/event-stream", headers=headers)


def agno_error_frame(message: str) -> str:
    """Agno 原生 error 帧（配合 SSE 终止）。"""
    import json

    return f"event: RunError\ndata: {json.dumps({'event': 'RunError', 'error': message}, ensure_ascii=False)}\n\n"
