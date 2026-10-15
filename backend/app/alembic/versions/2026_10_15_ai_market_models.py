"""AI 能力市场：五张新表 + ai_tools/ai_agents 增列

Revision ID: b6a11c0ffee2
Revises: 935f817cdee4
Create Date: 2026-10-15 17:20:00.000000

说明：手写迁移。autogenerate 会因本项目数据库存在大量未被模型覆盖的
历史/影子表（ont_* 等）产生无关 DROP，因此只保留本次特性所需变更。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b6a11c0ffee2"
down_revision: Union[str, None] = "935f817cdee4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 市场商品表
    op.create_table(
        "ai_market_items",
        sa.Column("asset_type", sa.String(length=16), nullable=False, comment="资产类型: tool/skill/mcp/plugin"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="商品名（同类型内唯一，业务层校验）"),
        sa.Column("description", sa.Text(), nullable=True, comment="商品描述"),
        sa.Column("icon", sa.String(length=256), nullable=True, comment="图标（emoji 或图片URL）"),
        sa.Column("category", sa.String(length=64), nullable=True, comment="市场分类"),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="标签数组"),
        sa.Column("version", sa.String(length=16), nullable=True, comment="版本（展示）"),
        sa.Column("owner_id", sa.Integer(), nullable=True, comment="提交人（官方内置为 NULL）"),
        sa.Column("is_official", sa.Boolean(), nullable=False, comment="平台内置"),
        sa.Column("featured", sa.Boolean(), nullable=False, comment="精选"),
        sa.Column("status", sa.String(length=16), nullable=False, comment="状态: draft/pending/approved/rejected/offline"),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="真实资产快照（按 asset_type 结构不同）"),
        sa.Column("source_id", sa.Integer(), nullable=True, comment="提交时来源真实记录 id（仅记录）"),
        sa.Column("install_count", sa.Integer(), nullable=False, comment="安装次数"),
        sa.Column("favorite_count", sa.Integer(), nullable=False, comment="收藏次数"),
        sa.Column("audit_remark", sa.String(length=255), nullable=True, comment="审核意见"),
        sa.Column("audit_user", sa.Integer(), nullable=True, comment="审核人"),
        sa.Column("audit_time", sa.DateTime(), nullable=True, comment="审核时间"),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
        sa.Column("uuid", sa.String(length=64), nullable=False, comment="UUID全局唯一标识"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="是否已删除(0:未删除 1:已删除)"),
        sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
        sa.PrimaryKeyConstraint("id"),
        comment="AI 能力市场商品表",
    )
    op.create_index(op.f("ix_ai_market_items_created_time"), "ai_market_items", ["created_time"], unique=False)
    op.create_index(op.f("ix_ai_market_items_deleted_time"), "ai_market_items", ["deleted_time"], unique=False)
    op.create_index(op.f("ix_ai_market_items_id"), "ai_market_items", ["id"], unique=False)
    op.create_index(op.f("ix_ai_market_items_is_deleted"), "ai_market_items", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_ai_market_items_updated_time"), "ai_market_items", ["updated_time"], unique=False)
    op.create_index(op.f("ix_ai_market_items_uuid"), "ai_market_items", ["uuid"], unique=True)

    # 2. 用户-商品关系表（安装/收藏）
    op.create_table(
        "ai_market_relations",
        sa.Column("user_id", sa.Integer(), nullable=False, comment="用户"),
        sa.Column("item_id", sa.Integer(), nullable=False, comment="商品"),
        sa.Column("kind", sa.String(length=16), nullable=False, comment="关系类型: installed/favorited"),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
        sa.Column("uuid", sa.String(length=64), nullable=False, comment="UUID全局唯一标识"),
        sa.Column("status", sa.String(length=10), nullable=False, comment="状态(0:正常 1:禁用)"),
        sa.Column("description", sa.Text(), nullable=True, comment="备注/描述"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="是否已删除(0:未删除 1:已删除)"),
        sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
        sa.ForeignKeyConstraint(["item_id"], ["ai_market_items.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        comment="AI 市场用户关系表（安装/收藏）",
    )
    op.create_index(op.f("ix_ai_market_relations_created_time"), "ai_market_relations", ["created_time"], unique=False)
    op.create_index(op.f("ix_ai_market_relations_deleted_time"), "ai_market_relations", ["deleted_time"], unique=False)
    op.create_index(op.f("ix_ai_market_relations_id"), "ai_market_relations", ["id"], unique=False)
    op.create_index(op.f("ix_ai_market_relations_is_deleted"), "ai_market_relations", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_ai_market_relations_status"), "ai_market_relations", ["status"], unique=False)
    op.create_index(op.f("ix_ai_market_relations_updated_time"), "ai_market_relations", ["updated_time"], unique=False)
    op.create_index(op.f("ix_ai_market_relations_uuid"), "ai_market_relations", ["uuid"], unique=True)

    # 3. 点对点分享表
    op.create_table(
        "ai_market_shares",
        sa.Column("item_id", sa.Integer(), nullable=False, comment="商品"),
        sa.Column("from_user_id", sa.Integer(), nullable=False, comment="分享人"),
        sa.Column("to_user_id", sa.Integer(), nullable=False, comment="接收人"),
        sa.Column("status", sa.String(length=16), nullable=False, comment="状态: pending/accepted/rejected"),
        sa.Column("message", sa.String(length=255), nullable=True, comment="留言"),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
        sa.Column("uuid", sa.String(length=64), nullable=False, comment="UUID全局唯一标识"),
        sa.Column("description", sa.Text(), nullable=True, comment="备注/描述"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="是否已删除(0:未删除 1:已删除)"),
        sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
        sa.ForeignKeyConstraint(["from_user_id"], ["sys_user.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["ai_market_items.id"]),
        sa.ForeignKeyConstraint(["to_user_id"], ["sys_user.id"]),
        sa.PrimaryKeyConstraint("id"),
        comment="AI 市场点对点分享表",
    )
    op.create_index(op.f("ix_ai_market_shares_created_time"), "ai_market_shares", ["created_time"], unique=False)
    op.create_index(op.f("ix_ai_market_shares_deleted_time"), "ai_market_shares", ["deleted_time"], unique=False)
    op.create_index(op.f("ix_ai_market_shares_id"), "ai_market_shares", ["id"], unique=False)
    op.create_index(op.f("ix_ai_market_shares_is_deleted"), "ai_market_shares", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_ai_market_shares_updated_time"), "ai_market_shares", ["updated_time"], unique=False)
    op.create_index(op.f("ix_ai_market_shares_uuid"), "ai_market_shares", ["uuid"], unique=True)

    # 4. MCP 服务器配置表
    op.create_table(
        "ai_mcp_servers",
        sa.Column("name", sa.String(length=128), nullable=False, comment="服务器名（唯一）"),
        sa.Column("transport", sa.String(length=32), nullable=False, comment="传输方式: stdio/sse/streamable-http"),
        sa.Column("command", sa.String(length=512), nullable=True, comment="stdio 启动命令"),
        sa.Column("args", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="stdio 命令参数数组"),
        sa.Column("env", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="stdio 环境变量"),
        sa.Column("url", sa.String(length=512), nullable=True, comment="sse/streamable-http 地址"),
        sa.Column("headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="自定义请求头"),
        sa.Column("auth_type", sa.String(length=16), nullable=False, comment="鉴权: none/bearer/custom"),
        sa.Column("enabled", sa.Boolean(), nullable=False, comment="是否启用"),
        sa.Column("description", sa.Text(), nullable=True, comment="描述"),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
        sa.Column("uuid", sa.String(length=64), nullable=False, comment="UUID全局唯一标识"),
        sa.Column("status", sa.String(length=10), nullable=False, comment="状态(0:正常 1:禁用)"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="是否已删除(0:未删除 1:已删除)"),
        sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
        sa.Column("created_id", sa.Integer(), nullable=True, comment="创建人ID"),
        sa.Column("updated_id", sa.Integer(), nullable=True, comment="更新人ID"),
        sa.Column("deleted_id", sa.Integer(), nullable=True, comment="删除人ID"),
        sa.ForeignKeyConstraint(["created_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        comment="AI MCP 服务器配置表",
    )
    op.create_index(op.f("ix_ai_mcp_servers_created_id"), "ai_mcp_servers", ["created_id"], unique=False)
    op.create_index(op.f("ix_ai_mcp_servers_created_time"), "ai_mcp_servers", ["created_time"], unique=False)
    op.create_index(op.f("ix_ai_mcp_servers_deleted_id"), "ai_mcp_servers", ["deleted_id"], unique=False)
    op.create_index(op.f("ix_ai_mcp_servers_deleted_time"), "ai_mcp_servers", ["deleted_time"], unique=False)
    op.create_index(op.f("ix_ai_mcp_servers_id"), "ai_mcp_servers", ["id"], unique=False)
    op.create_index(op.f("ix_ai_mcp_servers_is_deleted"), "ai_mcp_servers", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_ai_mcp_servers_status"), "ai_mcp_servers", ["status"], unique=False)
    op.create_index(op.f("ix_ai_mcp_servers_updated_id"), "ai_mcp_servers", ["updated_id"], unique=False)
    op.create_index(op.f("ix_ai_mcp_servers_updated_time"), "ai_mcp_servers", ["updated_time"], unique=False)
    op.create_index(op.f("ix_ai_mcp_servers_uuid"), "ai_mcp_servers", ["uuid"], unique=True)

    # 5. AI 能力插件表
    op.create_table(
        "ai_plugins",
        sa.Column("key", sa.String(length=64), nullable=False, comment="插件标识（执行器注册 key）"),
        sa.Column("label", sa.String(length=128), nullable=True, comment="显示名"),
        sa.Column("kind", sa.String(length=32), nullable=False, comment="插件类型: builtin/custom"),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="插件配置"),
        sa.Column("config_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="配置项 JSON schema"),
        sa.Column("executor_ready", sa.Boolean(), nullable=False, comment="执行器是否已实现"),
        sa.Column("enabled", sa.Boolean(), nullable=False, comment="是否启用"),
        sa.Column("description", sa.Text(), nullable=True, comment="描述"),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
        sa.Column("uuid", sa.String(length=64), nullable=False, comment="UUID全局唯一标识"),
        sa.Column("status", sa.String(length=10), nullable=False, comment="状态(0:正常 1:禁用)"),
        sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
        sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="是否已删除(0:未删除 1:已删除)"),
        sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
        sa.Column("created_id", sa.Integer(), nullable=True, comment="创建人ID"),
        sa.Column("updated_id", sa.Integer(), nullable=True, comment="更新人ID"),
        sa.Column("deleted_id", sa.Integer(), nullable=True, comment="删除人ID"),
        sa.ForeignKeyConstraint(["created_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deleted_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
        comment="AI 能力插件表",
    )
    op.create_index(op.f("ix_ai_plugins_created_id"), "ai_plugins", ["created_id"], unique=False)
    op.create_index(op.f("ix_ai_plugins_created_time"), "ai_plugins", ["created_time"], unique=False)
    op.create_index(op.f("ix_ai_plugins_deleted_id"), "ai_plugins", ["deleted_id"], unique=False)
    op.create_index(op.f("ix_ai_plugins_deleted_time"), "ai_plugins", ["deleted_time"], unique=False)
    op.create_index(op.f("ix_ai_plugins_id"), "ai_plugins", ["id"], unique=False)
    op.create_index(op.f("ix_ai_plugins_is_deleted"), "ai_plugins", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_ai_plugins_status"), "ai_plugins", ["status"], unique=False)
    op.create_index(op.f("ix_ai_plugins_updated_id"), "ai_plugins", ["updated_id"], unique=False)
    op.create_index(op.f("ix_ai_plugins_updated_time"), "ai_plugins", ["updated_time"], unique=False)
    op.create_index(op.f("ix_ai_plugins_uuid"), "ai_plugins", ["uuid"], unique=True)

    # 6. ai_agents 增加 MCP 服务器ID列表
    #    注意：ai_agents / ai_tools 属插件模块表，**不由迁移链创建**（由应用启动时补齐），
    #    因此空库重放（如 SQLite 全链回归）时表可能尚不存在——存在才增列，保证可重放。
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    def _has_column(table: str, column: str) -> bool:
        if not inspector.has_table(table):
            return False
        return column in {c["name"] for c in inspector.get_columns(table)}

    if inspector.has_table("ai_agents") and not _has_column("ai_agents", "mcp_ids"):
        op.add_column(
            "ai_agents",
            sa.Column("mcp_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="MCP 服务器ID列表"),
        )

    # 7. ai_tools 增加脚本工具字段
    if inspector.has_table("ai_tools"):
        if not _has_column("ai_tools", "code"):
            op.add_column("ai_tools", sa.Column("code", sa.Text(), nullable=True, comment="Python 脚本源码（kind=script）"))
        if not _has_column("ai_tools", "timeout"):
            # timeout 为 NOT NULL 且表内可能已有数据，需要 server_default 兜底
            op.add_column(
                "ai_tools",
                sa.Column("timeout", sa.Integer(), nullable=False, server_default="10", comment="脚本执行超时（秒）"),
            )


def downgrade() -> None:
    # 逆序撤销
    op.drop_column("ai_tools", "timeout")
    op.drop_column("ai_tools", "code")
    op.drop_column("ai_agents", "mcp_ids")

    op.drop_index(op.f("ix_ai_plugins_uuid"), table_name="ai_plugins")
    op.drop_index(op.f("ix_ai_plugins_updated_time"), table_name="ai_plugins")
    op.drop_index(op.f("ix_ai_plugins_updated_id"), table_name="ai_plugins")
    op.drop_index(op.f("ix_ai_plugins_status"), table_name="ai_plugins")
    op.drop_index(op.f("ix_ai_plugins_is_deleted"), table_name="ai_plugins")
    op.drop_index(op.f("ix_ai_plugins_id"), table_name="ai_plugins")
    op.drop_index(op.f("ix_ai_plugins_deleted_time"), table_name="ai_plugins")
    op.drop_index(op.f("ix_ai_plugins_deleted_id"), table_name="ai_plugins")
    op.drop_index(op.f("ix_ai_plugins_created_time"), table_name="ai_plugins")
    op.drop_index(op.f("ix_ai_plugins_created_id"), table_name="ai_plugins")
    op.drop_table("ai_plugins")

    op.drop_index(op.f("ix_ai_mcp_servers_uuid"), table_name="ai_mcp_servers")
    op.drop_index(op.f("ix_ai_mcp_servers_updated_time"), table_name="ai_mcp_servers")
    op.drop_index(op.f("ix_ai_mcp_servers_updated_id"), table_name="ai_mcp_servers")
    op.drop_index(op.f("ix_ai_mcp_servers_status"), table_name="ai_mcp_servers")
    op.drop_index(op.f("ix_ai_mcp_servers_is_deleted"), table_name="ai_mcp_servers")
    op.drop_index(op.f("ix_ai_mcp_servers_id"), table_name="ai_mcp_servers")
    op.drop_index(op.f("ix_ai_mcp_servers_deleted_time"), table_name="ai_mcp_servers")
    op.drop_index(op.f("ix_ai_mcp_servers_deleted_id"), table_name="ai_mcp_servers")
    op.drop_index(op.f("ix_ai_mcp_servers_created_time"), table_name="ai_mcp_servers")
    op.drop_index(op.f("ix_ai_mcp_servers_created_id"), table_name="ai_mcp_servers")
    op.drop_table("ai_mcp_servers")

    op.drop_index(op.f("ix_ai_market_shares_uuid"), table_name="ai_market_shares")
    op.drop_index(op.f("ix_ai_market_shares_updated_time"), table_name="ai_market_shares")
    op.drop_index(op.f("ix_ai_market_shares_is_deleted"), table_name="ai_market_shares")
    op.drop_index(op.f("ix_ai_market_shares_id"), table_name="ai_market_shares")
    op.drop_index(op.f("ix_ai_market_shares_deleted_time"), table_name="ai_market_shares")
    op.drop_index(op.f("ix_ai_market_shares_created_time"), table_name="ai_market_shares")
    op.drop_table("ai_market_shares")

    op.drop_index(op.f("ix_ai_market_relations_uuid"), table_name="ai_market_relations")
    op.drop_index(op.f("ix_ai_market_relations_updated_time"), table_name="ai_market_relations")
    op.drop_index(op.f("ix_ai_market_relations_status"), table_name="ai_market_relations")
    op.drop_index(op.f("ix_ai_market_relations_is_deleted"), table_name="ai_market_relations")
    op.drop_index(op.f("ix_ai_market_relations_id"), table_name="ai_market_relations")
    op.drop_index(op.f("ix_ai_market_relations_deleted_time"), table_name="ai_market_relations")
    op.drop_index(op.f("ix_ai_market_relations_created_time"), table_name="ai_market_relations")
    op.drop_table("ai_market_relations")

    op.drop_index(op.f("ix_ai_market_items_uuid"), table_name="ai_market_items")
    op.drop_index(op.f("ix_ai_market_items_updated_time"), table_name="ai_market_items")
    op.drop_index(op.f("ix_ai_market_items_is_deleted"), table_name="ai_market_items")
    op.drop_index(op.f("ix_ai_market_items_id"), table_name="ai_market_items")
    op.drop_index(op.f("ix_ai_market_items_deleted_time"), table_name="ai_market_items")
    op.drop_index(op.f("ix_ai_market_items_created_time"), table_name="ai_market_items")
    op.drop_table("ai_market_items")
