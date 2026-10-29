"""AI 集成开放平台：OAuth 2.1 用户委托（客户端表 + 委托 token 表）

Revision ID: e3f4a5b6c7d8
Revises: a0b1c2d3e4f5
Create Date: 2026-10-29 15:00:00.000000

说明：手写迁移。autogenerate 会因本项目存在大量未被模型覆盖的历史/影子表
（ont_* 等）产生无关 DROP，因此只保留本特性所需变更。
- 新建 ``ai_integration_oauth_clients``（OAuth 客户端，管理员创建）。
- 新建 ``ai_integration_oauth_tokens``（委托 token：授权码/access/refresh，只存散列）。
均用 ``has_table`` 幂等守卫，避免空库全链重放（SQLite 回归）失败。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e3f4a5b6c7d8"
down_revision: str | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _model_mixin_cols() -> list[sa.Column]:
    """ModelMixin + UserMixin 的公共列（与 base_model 一致）。"""
    return [
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
        sa.Column("uuid", sa.String(length=64), nullable=False, comment="UUID全局唯一标识"),
        sa.Column("status", sa.String(length=10), nullable=False, comment="状态(0:正常 1:禁用)"),
        sa.Column("description", sa.Text(), nullable=True, comment="备注/描述"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="是否已删除(0:未删除 1:已删除)"),
        sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
        sa.Column("created_id", sa.Integer(), nullable=True, comment="创建人ID"),
        sa.Column("updated_id", sa.Integer(), nullable=True, comment="更新人ID"),
        sa.Column("deleted_id", sa.Integer(), nullable=True, comment="删除人ID"),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. OAuth 客户端表
    if "ai_integration_oauth_clients" not in insp.get_table_names():
        op.create_table(
            "ai_integration_oauth_clients",
            *_model_mixin_cols(),
            sa.Column("client_id", sa.String(length=64), nullable=False, comment="OAuth client 标识（对外暴露，唯一，不含冒号）"),
            sa.Column("client_secret_hash", sa.String(length=128), nullable=False, comment="client secret 散列（sha256，不存明文）"),
            sa.Column("name", sa.String(length=128), nullable=False, comment="客户端名称（唯一）"),
            sa.Column("enabled", sa.Boolean(), nullable=False, comment="是否启用"),
            sa.Column("redirect_uris", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment="授权回调 URI 白名单（数组）"),
            sa.Column("allow_pkce", sa.Boolean(), nullable=False, comment="是否允许 PKCE（公共客户端）"),
            sa.Column("requires_approval", sa.Boolean(), nullable=False, comment="调敏感能力是否需审批"),
            sa.Column("max_scope", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="该 client 可授权的能力码上限（null=全部）"),
            sa.Column("expire_at", sa.DateTime(), nullable=True, comment="客户端凭证过期时间（空为永久）"),
            sa.ForeignKeyConstraint(["created_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["deleted_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("client_id"),
            sa.UniqueConstraint("name"),
            sa.UniqueConstraint("uuid"),
            comment="AI 集成 OAuth 客户端表",
        )
        op.create_index(op.f("ix_ai_integration_oauth_clients_client_id"), "ai_integration_oauth_clients", ["client_id"], unique=True)
        op.create_index(op.f("ix_ai_integration_oauth_clients_created_time"), "ai_integration_oauth_clients", ["created_time"], unique=False)
        op.create_index(op.f("ix_ai_integration_oauth_clients_id"), "ai_integration_oauth_clients", ["id"], unique=False)
        op.create_index(op.f("ix_ai_integration_oauth_clients_name"), "ai_integration_oauth_clients", ["name"], unique=True)
        op.create_index(op.f("ix_ai_integration_oauth_clients_status"), "ai_integration_oauth_clients", ["status"], unique=False)
        op.create_index(op.f("ix_ai_integration_oauth_clients_uuid"), "ai_integration_oauth_clients", ["uuid"], unique=True)

    # 2. OAuth 委托 token 表
    if "ai_integration_oauth_tokens" not in insp.get_table_names():
        op.create_table(
            "ai_integration_oauth_tokens",
            *_model_mixin_cols(),
            sa.Column("client_id", sa.String(length=64), nullable=False, comment="所属 OAuth client 标识"),
            sa.Column("oauth_client_id", sa.Integer(), nullable=False, comment="所属 OAuth 客户端主键"),
            sa.Column("user_id", sa.Integer(), nullable=False, comment="被委托用户ID（OAuth sub）"),
            sa.Column("token_type", sa.String(length=16), nullable=False, comment="凭证形态: auth/access/refresh"),
            sa.Column("token_hash", sa.String(length=128), nullable=False, comment="token 散列（sha256，不存明文）"),
            sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment="授权能力码集合（用户被授予的 scope）"),
            sa.Column("redirect_uri", sa.String(length=255), nullable=True, comment="签发时的回调（换 token/refresh 时校验）"),
            sa.Column("code_challenge", sa.String(length=128), nullable=True, comment="PKCE challenge（关联授权码）"),
            sa.Column("code_challenge_method", sa.String(length=16), nullable=True, comment="PKCE 方法: plain/S256"),
            sa.Column("auth_code", sa.String(length=128), nullable=True, comment="授权码原始值（仅换 token 阶段用，换后清空）"),
            sa.Column("auth_code_hash", sa.String(length=128), nullable=True, comment="授权码散列（校验用，换后置空）"),
            sa.Column("expires_at", sa.DateTime(), nullable=False, comment="过期时间（access 短 / refresh 长）"),
            sa.Column("revoked", sa.Boolean(), nullable=False, comment="是否已撤销"),
            sa.Column("revoked_at", sa.DateTime(), nullable=True, comment="撤销时间"),
            sa.Column("last_used_at", sa.DateTime(), nullable=True, comment="最近使用时间"),
            sa.ForeignKeyConstraint(["oauth_client_id"], ["ai_integration_oauth_clients.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["sys_user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["deleted_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
            sa.UniqueConstraint("uuid"),
            comment="AI 集成 OAuth 委托 token 表",
        )
        op.create_index(op.f("ix_ai_integration_oauth_tokens_client_id"), "ai_integration_oauth_tokens", ["client_id"], unique=False)
        op.create_index(op.f("ix_ai_integration_oauth_tokens_created_time"), "ai_integration_oauth_tokens", ["created_time"], unique=False)
        op.create_index(op.f("ix_ai_integration_oauth_tokens_id"), "ai_integration_oauth_tokens", ["id"], unique=False)
        op.create_index(op.f("ix_ai_integration_oauth_tokens_oauth_client_id"), "ai_integration_oauth_tokens", ["oauth_client_id"], unique=False)
        op.create_index(op.f("ix_ai_integration_oauth_tokens_revoked"), "ai_integration_oauth_tokens", ["revoked"], unique=False)
        op.create_index(op.f("ix_ai_integration_oauth_tokens_status"), "ai_integration_oauth_tokens", ["status"], unique=False)
        op.create_index(op.f("ix_ai_integration_oauth_tokens_token_hash"), "ai_integration_oauth_tokens", ["token_hash"], unique=True)
        op.create_index(op.f("ix_ai_integration_oauth_tokens_user_id"), "ai_integration_oauth_tokens", ["user_id"], unique=False)
        op.create_index(op.f("ix_ai_integration_oauth_tokens_uuid"), "ai_integration_oauth_tokens", ["uuid"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "ai_integration_oauth_tokens" in insp.get_table_names():
        op.drop_table("ai_integration_oauth_tokens")
    if "ai_integration_oauth_clients" in insp.get_table_names():
        op.drop_table("ai_integration_oauth_clients")
