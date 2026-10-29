"""AI 集成开放平台 —— OAuth 2.1 用户委托（模式 C）数据模型。

- :class:`AiIntegrationOauthClientModel`：OAuth 客户端（管理员创建，供外部第三方
  AI 助手作为 client 发起授权）。
- :class:`AiIntegrationOauthTokenModel`：委托 token（授权码 / access / refresh，
  **只存散列**，有状态落库以支持随时撤销）。

设计见 ``docs/superpowers/specs/2026-10-29-develop-oauth-server-design.md``。
两表复用 :class:`ModelMixin`（id/uuid/status/description/created_time/updated_time/
is_deleted/deleted_time）；client 额外用 ``UserMixin`` 记录创建人。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_model import ModelMixin, UserMixin


class AiIntegrationOauthClientModel(ModelMixin, UserMixin):
    """OAuth 客户端：外部第三方接入方的 client 凭证与授权约束。"""

    __tablename__ = "ai_integration_oauth_clients"
    __table_args__ = ({"comment": "AI 集成 OAuth 客户端表"},)

    client_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True,
        comment="OAuth client 标识（对外暴露，唯一，不含冒号）",
    )
    client_secret_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="client secret 散列（sha256，不存明文）",
    )
    name: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, comment="客户端名称（唯一）",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否启用",
    )
    redirect_uris: Mapped[list | None] = mapped_column(
        JSONB, default=list, nullable=False,
        comment="授权回调 URI 白名单（数组）",
    )
    allow_pkce: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="是否允许 PKCE（公共客户端）",
    )
    requires_approval: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="调敏感能力是否需审批",
    )
    max_scope: Mapped[list | None] = mapped_column(
        JSONB, default=None, nullable=True,
        comment="该 client 可授权的能力码上限（null=全部）",
    )
    expire_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True, comment="客户端凭证过期时间（空为永久）",
    )


class AiIntegrationOauthTokenModel(ModelMixin):
    """OAuth 委托 token：授权码 / access / refresh（只存散列，可撤销）。

    单表收敛三种凭证形态，用 ``token_type`` 区分：
    - ``auth``：一次性授权码（换 token 后 ``auth_code``/``auth_code_hash`` 置空）；
    - ``access``：委托访问 token（代表 ``user_id`` 用户）；
    - ``refresh``：刷新 token（换新后旧 refresh 置撤销）。
    """

    __tablename__ = "ai_integration_oauth_tokens"
    __table_args__ = ({"comment": "AI 集成 OAuth 委托 token 表"},)

    client_id: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="所属 OAuth client 标识",
    )
    oauth_client_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ai_integration_oauth_clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属 OAuth 客户端主键",
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sys_user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="被委托用户ID（OAuth sub）",
    )
    token_type: Mapped[str] = mapped_column(
        String(16), nullable=False, comment="凭证形态: auth/access/refresh",
    )
    token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True,
        comment="token 散列（sha256，不存明文）",
    )
    scope: Mapped[list | None] = mapped_column(
        JSONB, default=list, nullable=False, comment="授权能力码集合（用户被授予的 scope）",
    )
    redirect_uri: Mapped[str | None] = mapped_column(
        String(255), default=None, nullable=True, comment="签发时的回调（换 token/refresh 时校验）",
    )
    code_challenge: Mapped[str | None] = mapped_column(
        String(128), default=None, nullable=True, comment="PKCE challenge（关联授权码）",
    )
    code_challenge_method: Mapped[str | None] = mapped_column(
        String(16), default=None, nullable=True, comment="PKCE 方法: plain/S256",
    )
    auth_code: Mapped[str | None] = mapped_column(
        String(128), default=None, nullable=True, comment="授权码原始值（仅换 token 阶段用，换后清空）",
    )
    auth_code_hash: Mapped[str | None] = mapped_column(
        String(128), default=None, nullable=True, comment="授权码散列（校验用，换后置空）",
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="过期时间（access 短 / refresh 长）",
    )
    revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True, comment="是否已撤销",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True, comment="撤销时间",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, nullable=True, comment="最近使用时间",
    )
