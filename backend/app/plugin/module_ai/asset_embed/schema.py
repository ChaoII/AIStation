"""资产嵌入域 Schema（签发入参 / 嵌入对话入参）。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

#: 嵌入目标形态（工作台只服务 agent / workflow，不再支持 app）
AssetKind = Literal["agent", "workflow"]


class AssetTokenIssueSchema(BaseModel):
    """签发资产嵌入令牌入参（工作台侧）。"""

    kind: AssetKind = Field(..., description="嵌入形态: agent/workflow")
    target_id: int = Field(..., description="嵌入目标ID")
    ttl: int | None = Field(default=None, description="有效期秒数（缺省86400，下限60，上限2592000）")
    permanent: bool = Field(default=False, description="是否永久（true 时忽略 ttl）")
    allow_domains: str | None = Field(
        default=None, max_length=1024, description="允许来源域名（逗号分隔，空=不限）"
    )
    allow_ips: str | None = Field(
        default=None, max_length=1024, description="允许来源IP/网段（逗号分隔，空=不限）"
    )


class AssetTokenUpdateSchema(BaseModel):
    """更新资产嵌入令牌白名单入参（未传字段 = 不改）。"""

    allow_domains: str | None = Field(
        default=None, max_length=1024, description="允许来源域名（传空串=清空为不限）"
    )
    allow_ips: str | None = Field(
        default=None, max_length=1024, description="允许来源IP/网段（传空串=清空为不限）"
    )


class AssetRunSchema(BaseModel):
    """嵌入对话入参（客户端只传 ``sid`` + ``message``）。"""

    sid: str = Field(..., min_length=8, max_length=64, description="客户端会话标识")
    message: str = Field(..., min_length=1, max_length=4000, description="用户消息")
