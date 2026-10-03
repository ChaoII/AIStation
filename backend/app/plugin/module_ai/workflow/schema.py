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
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)


class AiWorkflowDebugNodeSchema(BaseModel):
    """单节点调试：运行指定节点（带给定变量），返回其输入/输出/报错。"""

    node_id: str
    variables: dict | None = None
    messages: list[dict] = Field(default_factory=list)


class AiWorkflowStepSchema(BaseModel):
    """逐步执行：run_id 为空则新建；带 run_id 则从持久化 frontier 续跑一个节点。"""

    run_id: str | None = None
    variables: dict | None = None
    messages: list[dict] = Field(default_factory=list)


class AiWorkflowShareRunSchema(BaseModel):
    """公开分享运行：仅凭分享令牌 + 一条消息（匿名、受限白名单节点）。"""

    token: str
    message: str = Field(..., max_length=2000)


class AiWorkflowScheduleSchema(BaseModel):
    """定时调度配置：cron（5 段）+ 启用。"""

    cron: str | None = Field(default=None, max_length=128)
    enabled: bool = False


class AiWorkflowApproveSchema(BaseModel):
    """HITL 工具审批：基于 run_id 对挂起的工具调用做出 approve/reject。"""

    run_id: str
    decision: str = Field(pattern="^(approve|reject)$")
    tool_call_ids: list[str] | None = None


class AiWorkflowVersionCreateSchema(BaseModel):
    """保存工作流版本：可自带 graph，缺省用当前工作流 graph。"""

    remark: str | None = Field(default=None, max_length=255)
    graph: dict | None = None
