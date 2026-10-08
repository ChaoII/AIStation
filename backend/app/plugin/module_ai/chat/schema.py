from typing import Any

from pydantic import BaseModel, Field


class AiChatRequestSchema(BaseModel):
    """AI 对话请求模型（非流式）"""
    message: str = Field(..., description="用户消息内容")
    session_id: int | None = Field(None, description="会话ID（ai_sessions.id），不传则创建新会话")


class AiChatResponseSchema(BaseModel):
    """AI 对话响应模型（非流式）"""
    response: str = Field(..., description="AI 回复内容")
    session_id: int = Field(..., description="会话ID")
    function_calls: list[dict[str, Any]] | None = Field(None, description="函数调用信息")
    action: dict[str, Any] | None = Field(None, description="建议执行的操作")
