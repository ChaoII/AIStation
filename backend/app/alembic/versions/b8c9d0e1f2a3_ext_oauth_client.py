"""AI 集成开放平台：外部服务连接 + 用户级 token 表（平台代用户访问外部 OAuth）

Revision ID: b8c9d0e1f2a3
Revises: f5a6b7c8d9e0
Create Date: 2026-10-29 16:00:00.000000

说明：手写迁移。autogenerate 会因本项目存在大量未被模型覆盖的历史/影子表
（ont_* 等）产生无关 DROP，因此只保留本特性所需变更。
- 新建 ``ai_oauth_ext_services``（外部 OAuth 服务连接，管理员登记）。
- 新建 ``ai_oauth_ext_tokens``（平台用户×外部服务的加密 token）。
- ``ai_tools`` 增列 ``oauth_ext_service_id``（http 工具绑定外部服务）。
均用 ``has_table``/``has_column`` 幂等守卫，避免空库全链重放（SQLite 回归）失败。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _mixin_cols(with_user: bool) -> list[sa.Column]:
    """ModelMixin 公共列（``with_user`` 时附加 UserMixin 的 created/updated/deleted_id）。"""
    cols = [
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
        sa.Column("uuid", sa.String(length=64), nullable=False, comment="UUID全局唯一标识"),
        sa.Column("status", sa.String(length=10), nullable=False, comment="状态(0:正常 1:禁用)"),
        sa.Column("description", sa.Text(), nullable=True, comment="备注/描述"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="是否已删除(0:未删除 1:已删除)"),
        sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
    ]
    if with_user:
        cols += [
            sa.Column("created_id", sa.Integer(), nullable=True, comment="创建人ID"),
            sa.Column("updated_id", sa.Integer(), nullable=True, comment="更新人ID"),
            sa.Column("deleted_id", sa.Integer(), nullable=True, comment="删除人ID"),
        ]
    return cols


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. 外部服务连接表
    if "ai_oauth_ext_services" not in insp.get_table_names():
        op.create_table(
            "ai_oauth_ext_services",
            *_mixin_cols(with_user=True),
            sa.Column("name", sa.String(length=128), nullable=False, comment="服务名称（唯一）"),
            sa.Column("authorize_url", sa.String(length=512), nullable=False, comment="外部 OAuth authorize 端点"),
            sa.Column("token_url", sa.String(length=512), nullable=False, comment="外部 OAuth token 端点"),
            sa.Column("client_id", sa.String(length=256), nullable=False, comment="平台作为该服务 client 的 id"),
            sa.Column("client_secret_enc", sa.Text(), nullable=True, comment="client secret 密文（Fernet，仅换取用，不回读）"),
            sa.Column("client_secret_hash", sa.String(length=128), nullable=True, comment="client secret 散列（sha256，不存明文）"),
            sa.Column("redirect_uri", sa.String(length=512), nullable=False, comment="平台回跳地址"),
            sa.Column("default_scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment="授权时默认请求的 scope 列表"),
            sa.Column("userinfo_url", sa.String(length=512), nullable=True, comment="可选：校验用户身份的 userinfo 端点"),
            sa.Column("enabled", sa.Boolean(), nullable=False, comment="是否启用"),
            sa.ForeignKeyConstraint(["created_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["deleted_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
            sa.UniqueConstraint("uuid"),
            comment="AI 平台外部 OAuth 服务连接表",
        )
        op.create_index(op.f("ix_ai_oauth_ext_services_created_time"), "ai_oauth_ext_services", ["created_time"], unique=False)
        op.create_index(op.f("ix_ai_oauth_ext_services_id"), "ai_oauth_ext_services", ["id"], unique=False)
        op.create_index(op.f("ix_ai_oauth_ext_services_name"), "ai_oauth_ext_services", ["name"], unique=True)
        op.create_index(op.f("ix_ai_oauth_ext_services_status"), "ai_oauth_ext_services", ["status"], unique=False)
        op.create_index(op.f("ix_ai_oauth_ext_services_uuid"), "ai_oauth_ext_services", ["uuid"], unique=True)

    # 2. 用户级 token 表（无 UserMixin 列，用 user_id）
    if "ai_oauth_ext_tokens" not in insp.get_table_names():
        op.create_table(
            "ai_oauth_ext_tokens",
            *_mixin_cols(with_user=False),
            sa.Column("service_id", sa.Integer(), nullable=False, comment="所属外部服务主键"),
            sa.Column("user_id", sa.Integer(), nullable=False, comment="平台用户 ID"),
            sa.Column("provider_user_id", sa.String(length=256), nullable=True, comment="外部服务返回的用户标识（若 userinfo 解析）"),
            sa.Column("access_token_enc", sa.Text(), nullable=False, comment="access token 密文（Fernet，可还原注入）"),
            sa.Column("refresh_token_enc", sa.Text(), nullable=True, comment="refresh token 密文（Fernet）"),
            sa.Column("access_expires_at", sa.DateTime(), nullable=True, comment="access 过期时间"),
            sa.Column("scope", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment="实际授权 scope"),
            sa.Column("revoked", sa.Boolean(), nullable=False, comment="用户是否已撤销该外部授权"),
            sa.Column("revoked_at", sa.DateTime(), nullable=True, comment="撤销时间"),
            sa.Column("last_used_at", sa.DateTime(), nullable=True, comment="最近使用时间"),
            sa.ForeignKeyConstraint(["service_id"], ["ai_oauth_ext_services.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["sys_user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("uuid"),
            sa.UniqueConstraint("service_id", "user_id", name="uq_oauth_ext_tok_svc_user"),
            comment="AI 平台用户外部服务授权 token 表",
        )
        op.create_index(op.f("ix_ai_oauth_ext_tokens_created_time"), "ai_oauth_ext_tokens", ["created_time"], unique=False)
        op.create_index(op.f("ix_ai_oauth_ext_tokens_id"), "ai_oauth_ext_tokens", ["id"], unique=False)
        op.create_index(op.f("ix_ai_oauth_ext_tokens_revoked"), "ai_oauth_ext_tokens", ["revoked"], unique=False)
        op.create_index(op.f("ix_ai_oauth_ext_tokens_service_id"), "ai_oauth_ext_tokens", ["service_id"], unique=False)
        op.create_index(op.f("ix_ai_oauth_ext_tokens_status"), "ai_oauth_ext_tokens", ["status"], unique=False)
        op.create_index(op.f("ix_ai_oauth_ext_tokens_user_id"), "ai_oauth_ext_tokens", ["user_id"], unique=False)
        op.create_index(op.f("ix_ai_oauth_ext_tokens_uuid"), "ai_oauth_ext_tokens", ["uuid"], unique=True)

    # 3. ai_tools 增列（http 工具绑定外部服务）
    if "ai_tools" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("ai_tools")}
        if "oauth_ext_service_id" not in cols:
            op.add_column(
                "ai_tools",
                sa.Column("oauth_ext_service_id", sa.Integer(), nullable=True, comment="绑定的外部服务ID（OAuth注入）"),
            )
            op.create_index(op.f("ix_ai_tools_oauth_ext_service_id"), "ai_tools", ["oauth_ext_service_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if "ai_oauth_ext_tokens" in insp.get_table_names():
        op.drop_table("ai_oauth_ext_tokens")
    if "ai_oauth_ext_services" in insp.get_table_names():
        op.drop_table("ai_oauth_ext_services")

    if "ai_tools" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("ai_tools")}
        if "oauth_ext_service_id" in cols:
            op.drop_index(op.f("ix_ai_tools_oauth_ext_service_id"), table_name="ai_tools")
            op.drop_column("ai_tools", "oauth_ext_service_id")
