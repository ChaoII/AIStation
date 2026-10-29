"""AI 集成开放平台 —— OAuth 2.1（模式 C）Pydantic Schema。

- :class:`OAuthClientCreateSchema`：管理员创建 OAuth 客户端入参。
- :class:`OAuthClientUpdateSchema`：更新 OAuth 客户端入参（所有字段可空）。
- :class:`OAuthAuthorizeSchema`：授权码请求入参（前端授权页）。
- :class:`OAuthTokenSchema`：token 换取入参（grant_type=authorization_code / refresh_token）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OAuthClientCreateSchema(BaseModel):
    """创建 OAuth 客户端入参（管理员）。"""

    name: str = Field(..., description="客户端名称（唯一）")
    description: str | None = Field(default=None, description="描述")
    redirect_uris: list[str] = Field(..., description="授权回调 URI 白名单（数组）")
    allow_pkce: bool | None = Field(default=True, description="是否允许 PKCE（公共客户端）")
    requires_approval: bool | None = Field(default=True, description="调敏感能力是否需审批")
    max_scope: list[str] | None = Field(default=None, description="可授权的能力码上限（null=全部）")
    expire_at: datetime | None = Field(default=None, description="凭证过期时间（空为永久）")


class OAuthClientUpdateSchema(BaseModel):
    """更新 OAuth 客户端入参（所有字段可空，仅更新显式传入的字段）。"""

    name: str | None = Field(default=None, description="客户端名称")
    description: str | None = Field(default=None, description="描述")
    redirect_uris: list[str] | None = Field(default=None, description="授权回调 URI 白名单")
    allow_pkce: bool | None = Field(default=None, description="是否允许 PKCE")
    requires_approval: bool | None = Field(default=None, description="调敏感能力是否需审批")
    max_scope: list[str] | None = Field(default=None, description="可授权的能力码上限（null=全部）")
    expire_at: datetime | None = Field(default=None, description="凭证过期时间（空为永久）")
    enabled: bool | None = Field(default=None, description="是否启用")


class OAuthAuthorizeSchema(BaseModel):
    """授权码请求入参（用户授权页）。"""

    client_id: str = Field(..., description="OAuth 客户端标识")
    scope: list[str] = Field(default_factory=list, description="请求的能力码集合")
    redirect_uri: str | None = Field(default=None, description="授权回调 URI（须在白名单）")
    state: str | None = Field(default=None, description="CSRF state（原样回传）")
    code_challenge: str | None = Field(default=None, description="PKCE challenge")
    code_challenge_method: Literal["plain", "S256"] | None = Field(default=None, description="PKCE 方法")


class OAuthTokenSchema(BaseModel):
    """token 换取入参（form 亦可）。"""

    grant_type: Literal["authorization_code", "refresh_token"] = Field(..., description="授权类型")
    code: str | None = Field(default=None, description="授权码（grant_type=authorization_code 时必填）")
    redirect_uri: str | None = Field(default=None, description="授权回调 URI（授权码换取时校验）")
    client_id: str | None = Field(default=None, description="客户端标识（PKCE/机密客户端）")
    client_secret: str | None = Field(default=None, description="客户端密钥（机密客户端）")
    refresh_token: str | None = Field(default=None, description="刷新 token（grant_type=refresh_token 时必填）")
    code_verifier: str | None = Field(default=None, description="PKCE verifier（公共客户端）")
