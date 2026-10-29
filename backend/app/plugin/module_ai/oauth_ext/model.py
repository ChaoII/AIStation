"""AI 集成开放平台 —— 阶段 3a：外部服务连接与用户级 token 数据模型。

- :class:`AiOauthExtServiceModel`：外部 OAuth server 的连接登记（管理员配置
  authorize/token 端点、client 凭证、回调、scope）。client secret 只存散列 +
  加密一次（换取用，不回读）。
- :class:`AiOauthExtTokenModel`：平台某个用户对某个外部服务的授权 token
  （access/refresh **加密存储**，可还原用于调用注入）。一个用户对每个外部服务
  只有一条（``UniqueConstraint(service_id, user_id)``）。

设计见 ``docs/superpowers/specs/2026-10-29-ext-oauth-client-design.md``。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiOauthExtServiceModel(ModelMixin, UserMixin):
    """外部 OAuth 服务连接：管理员登记的标准 OAuth 2.x server。"""

    __tablename__ = "ai_oauth_ext_services"
    __table_args__ = ({"comment": "AI 平台外部 OAuth 服务连接表"},)

    name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="服务名称（唯一）",
    )
    authorize_url: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="外部 OAuth authorize 端点",
    )
    token_url: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="外部 OAuth token 端点",
    )
    client_id: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="平台作为该服务 client 的 id",
    )
    client_secret_enc: Mapped[str | None] = mapped_column(
        Text, default=None, nullable=True, comment="client secret 密文（Fernet，仅换取用，不回读）",
    )
    client_secret_hash: Mapped[str | None] = mapped_column(
        String(128), default=None, nullable=True, comment="client secret 散列（sha256，不存明文）",
    )
    redirect_uri: Mapped[str] = mapped_column(
        String(512), nullable=False, comment="平台回跳地址",
    )
    default_scopes: Mapped[list | None] = mapped_column(
        JSONB, default=list, nullable=False, comment="授权时默认请求的 scope 列表",
    )
    userinfo_url: Mapped[str | None] = mapped_column(
        String(512), default=None, nullable=True, comment="可选：校验用户身份的 userinfo 端点",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否启用",
    )


class AiOauthExtTokenModel(ModelMixin):
    """平台用户对某个外部服务的授权 token（access/refresh 加密存储）。

    一个用户对每个外部服务只有一条记录；``revoked`` 置位表示用户已撤销该外部授权。
    """

    __tablename__ = "ai_oauth_ext_tokens"
    __table_args__ = (
        UniqueConstraint("service_id", "user_id", name="uq_oauth_ext_tok_svc_user"),
        {"comment": "AI 平台用户外部服务授权 token 表"},
    )

    service_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ai_oauth_ext_services.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属外部服务主键",
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="平台用户 ID",
    )
    provider_user_id: Mapped[str | None] = mapped_column(
        String(256), default=None, nullable=True,
        comment="外部服务返回的用户标识（若 userinfo 解析）",
    )
    access_token_enc: Mapped[str] = mapped_column(
        Text, nullable=False, comment="access token 密文（Fernet，可还原注入）",
    )
    refresh_token_enc: Mapped[str | None] = mapped_column(
        Text, default=None, nullable=True, comment="refresh token 密文（Fernet）",
    )
    access_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True, comment="access 过期时间",
    )
    scope: Mapped[list | None] = mapped_column(
        JSONB, default=list, nullable=False, comment="实际授权 scope",
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True, comment="用户是否已撤销该外部授权",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True, comment="撤销时间",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True, comment="最近使用时间",
    )
