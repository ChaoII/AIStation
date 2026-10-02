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


class AiWorkflowDebugNodeSchema(BaseModel):
    """单节点调试：运行指定节点（带给定变量），返回其输入/输出/报错。"""

    node_id: str
    variables: dict | None = None
    messages: list[dict] = Field(default_factory=list)


class AiWorkflowApproveSchema(BaseModel):
    """HITL 工具审批：基于 run_id 对挂起的工具调用做出 approve/reject。"""

    run_id: str
    decision: str = Field(pattern="^(approve|reject)$")
    tool_call_ids: list[str] | None = None


class AiWorkflowVersionCreateSchema(BaseModel):
    """保存工作流版本：可自带 graph，缺省用当前工作流 graph。"""

    remark: str | None = Field(default=None, max_length=255)
    graph: dict | None = None
