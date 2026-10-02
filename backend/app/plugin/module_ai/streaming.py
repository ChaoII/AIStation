"""AI SDK UI Message Stream（v1）SSE 输出工具。"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

UI_STREAM_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
    "x-vercel-ai-ui-message-stream": "v1",
    # 让 GZipMiddleware 跳过压缩（否则 SSE 被缓冲，前端无法逐字）
    "Content-Encoding": "identity",
}


def _frame(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False, default=str)}\n\n"


class UiMessageStream:
    """按 AI SDK UI Message Stream v1 产出 SSE 帧；结束时发送 data: [DONE]。"""

    def __init__(self) -> None:
        self._text_id: str | None = None
        self._reason_id: str | None = None

    def start(self, message_id: str | None = None) -> str:
        return _frame({"type": "start", "messageId": message_id or uuid.uuid4().hex})

    def reasoning(self, text: str) -> str:
        if not text:
            return ""
        out = ""
        if self._reason_id is None:
            self._reason_id = uuid.uuid4().hex
            out += _frame({"type": "reasoning-start", "id": self._reason_id})
        out += _frame({"type": "reasoning-delta", "id": self._reason_id, "delta": text})
        return out

    def reasoning_end(self) -> str:
        if self._reason_id is None:
            return ""
        out = _frame({"type": "reasoning-end", "id": self._reason_id})
        self._reason_id = None
        return out

    def text(self, text: str) -> str:
        if not text:
            return ""
        out = ""
        if self._text_id is None:
            self._text_id = uuid.uuid4().hex
            out += _frame({"type": "text-start", "id": self._text_id})
        out += _frame({"type": "text-delta", "id": self._text_id, "delta": text})
        return out

    def text_end(self) -> str:
        if self._text_id is None:
            return ""
        out = _frame({"type": "text-end", "id": self._text_id})
        self._text_id = None
        return out

    def tool(
        self,
        tool_call_id: str,
        name: str,
        args: dict | None = None,
        output: object | None = None,
        error: str | None = None,
    ) -> str:
        out = ""
        if args is not None:
            out += _frame(
                {
                    "type": "tool-input-available",
                    "toolCallId": tool_call_id,
                    "toolName": name,
                    "input": args,
                    "dynamic": True,
                }
            )
        if error is not None:
            out += _frame(
                {
                    "type": "tool-output-error",
                    "toolCallId": tool_call_id,
                    "errorText": error,
                    "dynamic": True,
                }
            )
        else:
            out += _frame(
                {
                    "type": "tool-output-available",
                    "toolCallId": tool_call_id,
                    "output": output,
                    "dynamic": True,
                }
            )
        return out

    def tool_approval(self, tool_calls: list[dict]) -> str:
        """HITL 工具审批帧：透出待审批的工具调用（名/参数），前端需确认或拒绝。"""
        if not tool_calls:
            return ""
        return _frame({"type": "tool-approval", "toolCalls": tool_calls})

    def sources(self, sources: list[dict]) -> str:
        """知识检索引用来源帧：供前端展示引用的知识块（标题/片段/相似度）。"""
        if not sources:
            return ""
        return _frame({"type": "sources", "sources": sources})

    def error(self, text: str) -> str:
        return _frame({"type": "error", "errorText": text})

    def data(self, name: str, payload: object) -> str:
        return _frame({"type": f"data-{name}", "data": payload})

    def node_status(
        self,
        node_id: str,
        status: str,
        label: str = "",
        output: object | None = None,
        error: str | None = None,
    ) -> str:
        """节点执行状态帧：前端据此高亮进行中的节点并展示各节点输出。"""
        return _frame(
            {
                "type": "node-status",
                "nodeId": node_id,
                "status": status,  # running / success / error
                "label": label,
                "output": output,
                "error": error,
            }
        )

    def finish(self) -> str:
        return _frame({"type": "finish"})

    @staticmethod
    def done() -> str:
        return "data: [DONE]\n\n"


def ui_stream_response(body: AsyncIterator[str]):
    from fastapi.responses import StreamingResponse

    return StreamingResponse(body, media_type="text/event-stream", headers=UI_STREAM_HEADERS)
