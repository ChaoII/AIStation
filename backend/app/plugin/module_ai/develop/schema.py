"""AI 集成开放平台 —— 应用 Pydantic Schema。

定义 :class:`DevelopCreateSchema` / :class:`DevelopUpdateSchema`，
字段与 ``AiIntegrationAppModel`` 对齐；``capabilities`` 由 service 层
经 ``capabilities.normalize_permissions`` 归一（去重 + 丢弃非法项）。
"""
from __future__ import annotations

from datetime import datetime

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


class DevelopUpdateSchema(BaseModel):
    """更新 AI 集成应用入参（所有字段均可空，仅更新显式传入的字段）。"""

    name: str | None = Field(default=None, description="应用名称（唯一）")
    description: str | None = Field(default=None, description="应用描述")
    capabilities: list[str] | None = Field(default=None, description="授权能力列表（非法项会被丢弃）")
    expire_at: datetime | None = Field(default=None, description="凭证过期时间（空为永久）")
    quota: dict | None = Field(default=None, description="配额配置（JSON 对象）")
    requires_approval: bool | None = Field(default=None, description="调用是否需要人工审批")
