"""AI 集成开放平台 —— 阶段 3a：外部 OAuth 服务连接 schema。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OAuthExtServiceCreateSchema(BaseModel):
    """登记外部 OAuth 服务（管理员）。"""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., max_length=128)
    authorize_url: str = Field(..., max_length=512)
    token_url: str = Field(..., max_length=512)
    client_id: str = Field(..., max_length=256)
    client_secret: str = Field(..., max_length=512)
    redirect_uri: str = Field(..., max_length=512)
    default_scopes: list[str] = Field(default_factory=list)
    userinfo_url: str | None = Field(default=None, max_length=512)
    enabled: bool = True


class OAuthExtServiceUpdateSchema(BaseModel):
    """编辑外部 OAuth 服务（仅更新显式传入字段）。"""

    model_config = ConfigDict(from_attributes=True)

    name: str | None = Field(default=None, max_length=128)
    authorize_url: str | None = Field(default=None, max_length=512)
    token_url: str | None = Field(default=None, max_length=512)
    client_id: str | None = Field(default=None, max_length=256)
    client_secret: str | None = Field(default=None, max_length=512)
    redirect_uri: str | None = Field(default=None, max_length=512)
    default_scopes: list[str] | None = None
    userinfo_url: str | None = Field(default=None, max_length=512)
    enabled: bool | None = None
