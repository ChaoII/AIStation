"""工作流定义与运行的 Pydantic 模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class AiWorkflowCreateSchema(BaseModel):
    name: str = Field(..., max_length=128)
    description: str | None = Field(default=None, max_length=512)
    graph: dict | None = None
    enabled: bool = True


class AiWorkflowUpdateSchema(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    graph: dict | None = None
    enabled: bool | None = None


class AiWorkflowRunSchema(BaseModel):
    """运行工作流：messages（AI SDK UIMessage）+ 变量 + 会话。"""

    messages: list[dict] = Field(default_factory=list)
    variables: dict | None = None
    session_id: int | None = None
