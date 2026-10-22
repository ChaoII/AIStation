"""AI 集成开放平台 —— 应用 Pydantic Schema。

定义 :class:`DevelopCreateSchema` / :class:`DevelopUpdateSchema`，
字段与 ``AiIntegrationAppModel`` 对齐；``capabilities`` 由 service 层
经 ``capabilities.normalize_permissions`` 归一（去重 + 丢弃非法项）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DevelopCreateSchema(BaseModel):
    """创建 AI 集成应用入参。

    - ``name``：应用名称（唯一，必填）。
    - ``capabilities``：授权能力列表，service 层会归一为合法权限点。
    - ``requires_approval``：调用是否需要人工审批，默认 ``True``。
    """

    name: str = Field(..., description="应用名称（唯一）")
    description: str | None = Field(default=None, description="应用描述")
    capabilities: list[str] | None = Field(default=None, description="授权能力列表（非法项会被丢弃）")
    expire_at: datetime | None = Field(default=None, description="凭证过期时间（空为永久）")
    quota: dict | None = Field(default=None, description="配额配置（JSON 对象）")
    requires_approval: bool | None = Field(default=True, description="调用是否需要人工审批")
    enabled: bool | None = Field(default=None, description="是否启用（None 时默认 True）")


class DevelopUpdateSchema(BaseModel):
    """更新 AI 集成应用入参（所有字段均可空，仅更新显式传入的字段）。"""

    name: str | None = Field(default=None, description="应用名称（唯一）")
    description: str | None = Field(default=None, description="应用描述")
    capabilities: list[str] | None = Field(default=None, description="授权能力列表（非法项会被丢弃）")
    expire_at: datetime | None = Field(default=None, description="凭证过期时间（空为永久）")
    quota: dict | None = Field(default=None, description="配额配置（JSON 对象）")
    requires_approval: bool | None = Field(default=None, description="调用是否需要人工审批")
    enabled: bool | None = Field(default=None, description="是否启用（None 表示不更新）")


class EmbedTokenIssueSchema(BaseModel):
    """换票入参：形态 + 目标 + 可选有效期。

    - ``kind``：嵌入形态（与服务端 ``EmbedService.get_target`` 分派一致）。
    - ``target_id``：目标主键；令牌将绑定到该单目标。
    - ``ttl``：有效期秒数，缺省 1800、下限 60、上限 86400（service 层夹紧）。
    """

    kind: Literal["agent", "app", "workflow"] = Field(..., description="嵌入形态")
    target_id: int = Field(..., description="嵌入目标ID")
    ttl: int | None = Field(default=None, description="有效期秒数（缺省1800，上限86400）")


class EmbedRunSchema(BaseModel):
    """嵌入对话入参：仅会话标识 + 一条消息（上下文由服务端会话维护）。

    ``sid`` 由嵌入页生成并本地保存，服务端按 ``(app_id, sid)`` 映射平台会话。
    """

    sid: str = Field(..., min_length=8, max_length=64, description="客户端会话标识")
    message: str = Field(..., min_length=1, max_length=4000, description="用户消息")


class CapabilityInvokeSchema(BaseModel):
    """开放能力调用入参：一个 JSON 对象（能力各自的 ``input_schema`` 描述其字段）。"""

    payload: dict = Field(default_factory=dict, description="能力入参（JSON 对象）")


class ApprovalReviewSchema(BaseModel):
    """调用审批入参：批准（``approve=true`` 会立即执行原调用）或拒绝。"""

    approve: bool = Field(..., description="是否批准")
    note: str | None = Field(default=None, max_length=255, description="审批意见")


class CapabilityTrySchema(BaseModel):
    """能力试调入参（管理端）：能力码 + 完整 payload。"""

    capability: str = Field(..., description="能力码，如 agent.list")
    payload: dict = Field(default_factory=dict, description="能力入参")


class EmbedMintSchema(BaseModel):
    """管理端签发体验令牌入参（有效期固定 2 小时，便于当场试用）。"""

    app_id: int = Field(..., description="应用ID")
    kind: Literal["agent", "app", "workflow"] = Field(..., description="嵌入形态")
    target_id: int = Field(..., description="嵌入目标ID")


class NotifyConfigSchema(BaseModel):
    """审批通知配置入参：开关通道 + 各通道 JSON 配置。"""

    channels: list[str] = Field(default_factory=list, description="启用的通道（email/webhook/sms）")
    configs: dict = Field(default_factory=dict, description="{通道: JSON 对象}")


class ApprovalBatchReviewSchema(BaseModel):
    """批量批准入参（拒绝请逐条操作）。"""

    ids: list[int] = Field(..., min_length=1, max_length=50, description="审批记录 ID 列表（≤50）")
    note: str | None = Field(default=None, max_length=255, description="审批意见（可选）")
