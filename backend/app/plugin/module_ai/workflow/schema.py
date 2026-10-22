"""工作流定义与运行的 Pydantic 模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AiWorkflowCreateSchema(BaseModel):
    name: str = Field(..., max_length=128)
    description: str | None = Field(default=None, max_length=512)
    graph: dict | None = None
    enabled: bool = True
    # 工作台分类（模型列早已存在，此前 schema 未暴露 → 工作流永远挂不上分类）
    category_id: int | None = None


class AiWorkflowUpdateSchema(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=512)
    graph: dict | None = None
    enabled: bool | None = None
    category_id: int | None = None


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
    """定时调度配置：四种触发类型（`trigger` + `trigger_args`）+ 启用。

    **字段优先规则**：`trigger` 显式提供（非空串）时以它为准；`cron` 是兼容字段，
    **仅在 `trigger` 缺省时**才被解读 —— 非 cron 类型的前端仍会带上 `cron: ""`，
    若先看旧字段会把它误判成「空表达式 + 启用」而误报 400（C4 审查钉死的缺口）。
    """

    trigger: str | None = Field(
        default=None, max_length=32, description="触发类型：cron / interval / date / now"
    )
    trigger_args: Any | None = Field(
        default=None,
        description="触发参数：cron 5 段串 / interval 对象或 JSON 串 / date 时间串 / now 为 null",
    )
    cron: str | None = Field(default=None, max_length=128, description="兼容字段（仅 cron 类型）")
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
