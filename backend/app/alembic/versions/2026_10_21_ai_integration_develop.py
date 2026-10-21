"""AI 集成开放平台：应用、调用日志与 MCP 会话三张表

Revision ID: c9d0e1f2a3b4
Revises: a2b3c4d5e6f7
Create Date: 2026-10-21 00:00:00.000000

说明：手写迁移。autogenerate 会因本项目存在大量未被模型覆盖的历史/影子表
（ont_* 等）产生无关 DROP，因此只保留本特性所需变更。
插件模块表（ai_*）可由应用启动 create_all 兜底，此处 ``has_table`` 幂等守卫，
避免空库全链重放（SQLite 回归）失败。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 1. AI 集成应用表
    if "ai_integration_apps" not in insp.get_table_names():
        op.create_table(
            "ai_integration_apps",
            sa.Column("appid", sa.String(length=64), nullable=False, comment="应用标识（对外暴露，唯一）"),
            sa.Column("appkey_hash", sa.String(length=128), nullable=False, comment="AppKey 散列（不存明文）"),
            sa.Column("name", sa.String(length=128), nullable=False, comment="应用名称（唯一）"),
            sa.Column("enabled", sa.Boolean(), nullable=False, comment="是否启用（启停开关）"),
            sa.Column("expire_at", sa.DateTime(), nullable=True, comment="凭证过期时间（空为永久）"),
            sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False, comment="授权能力列表"),
            sa.Column("quota", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="配额配置（JSON 对象）"),
            sa.Column("requires_approval", sa.Boolean(), nullable=False, comment="调用是否需要人工审批"),
            sa.Column("source_type", sa.String(length=16), nullable=False, comment="来源类型: admin/self"),
            sa.Column("last_call_at", sa.DateTime(), nullable=True, comment="最近一次调用时间"),
            sa.Column("call_count", sa.Integer(), nullable=False, comment="累计调用次数"),
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
            sa.ForeignKeyConstraint(["created_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["deleted_id"], ["sys_user.id"], onupdate="CASCADE", ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
            comment="AI 集成应用表",
        )
        op.create_index(op.f("ix_ai_integration_apps_appid"), "ai_integration_apps", ["appid"], unique=True)
        op.create_index(op.f("ix_ai_integration_apps_created_id"), "ai_integration_apps", ["created_id"], unique=False)
        op.create_index(op.f("ix_ai_integration_apps_created_time"), "ai_integration_apps", ["created_time"], unique=False)
        op.create_index(op.f("ix_ai_integration_apps_deleted_id"), "ai_integration_apps", ["deleted_id"], unique=False)
        op.create_index(op.f("ix_ai_integration_apps_deleted_time"), "ai_integration_apps", ["deleted_time"], unique=False)
        op.create_index(op.f("ix_ai_integration_apps_id"), "ai_integration_apps", ["id"], unique=False)
        op.create_index(op.f("ix_ai_integration_apps_is_deleted"), "ai_integration_apps", ["is_deleted"], unique=False)
        op.create_index(op.f("ix_ai_integration_apps_status"), "ai_integration_apps", ["status"], unique=False)
        op.create_index(op.f("ix_ai_integration_apps_updated_id"), "ai_integration_apps", ["updated_id"], unique=False)
        op.create_index(op.f("ix_ai_integration_apps_updated_time"), "ai_integration_apps", ["updated_time"], unique=False)
        op.create_index(op.f("ix_ai_integration_apps_uuid"), "ai_integration_apps", ["uuid"], unique=True)

    # 2. AI 集成调用日志表
    if "ai_integration_call_logs" not in insp.get_table_names():
        op.create_table(
            "ai_integration_call_logs",
            sa.Column("app_id", sa.Integer(), nullable=False, comment="所属应用ID"),
            sa.Column("appid", sa.String(length=64), nullable=False, comment="应用标识（冗余，便于只读查询）"),
            sa.Column("category", sa.String(length=16), nullable=False, comment="能力品类: train/agent/chat/bot/embed"),
            sa.Column("capability", sa.String(length=64), nullable=False, comment="具体能力码"),
            sa.Column("log_type", sa.String(length=16), nullable=False, comment="日志类型: request/response/error"),
            sa.Column("method", sa.String(length=16), nullable=False, comment="HTTP 方法"),
            sa.Column("transport", sa.String(length=16), nullable=False, comment="传输方式: http/sse/ws"),
            sa.Column("session_id", sa.String(length=64), nullable=True, comment="关联会话ID"),
            sa.Column("client_info", sa.String(length=128), nullable=True, comment="客户端信息"),
            sa.Column("request_path", sa.String(length=255), nullable=False, comment="请求路径"),
            sa.Column("request_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment="请求体（JSON）"),
            sa.Column("status", sa.String(length=16), nullable=False, comment="调用状态: success/failed/denied"),
            sa.Column("error", sa.String(length=255), nullable=True, comment="错误信息"),
            sa.Column("latency_ms", sa.Integer(), nullable=False, comment="耗时（毫秒）"),
            sa.Column("cost_tokens", sa.Integer(), nullable=False, comment="消耗 token 数"),
            sa.Column("result_summary", sa.String(length=512), nullable=True, comment="结果摘要"),
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
            sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.ForeignKeyConstraint(["app_id"], ["ai_integration_apps.id"], onupdate="CASCADE", ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            comment="AI 集成调用日志表",
        )
        op.create_index(op.f("ix_ai_integration_call_logs_app_id"), "ai_integration_call_logs", ["app_id"], unique=False)
        op.create_index(op.f("ix_ai_integration_call_logs_created_time"), "ai_integration_call_logs", ["created_time"], unique=False)

    # 3. AI 集成 MCP 会话表
    if "ai_integration_mcp_sessions" not in insp.get_table_names():
        op.create_table(
            "ai_integration_mcp_sessions",
            sa.Column("app_id", sa.Integer(), nullable=False, comment="所属应用ID"),
            sa.Column("appid", sa.String(length=64), nullable=False, comment="应用标识（冗余）"),
            sa.Column("session_id", sa.String(length=64), nullable=False, comment="会话ID"),
            sa.Column("transport", sa.String(length=16), nullable=False, comment="传输方式: stdio/sse/streamable-http"),
            sa.Column("client_info", sa.String(length=128), nullable=True, comment="客户端信息"),
            sa.Column("started_at", sa.DateTime(), nullable=False, comment="会话开始时间"),
            sa.Column("ended_at", sa.DateTime(), nullable=True, comment="会话结束时间"),
            sa.Column("duration_s", sa.Integer(), nullable=False, comment="会话时长（秒）"),
            sa.Column("tool_calls", sa.Integer(), nullable=False, comment="会话内工具调用次数"),
            sa.Column("close_reason", sa.String(length=64), nullable=True, comment="关闭原因"),
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
            sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.ForeignKeyConstraint(["app_id"], ["ai_integration_apps.id"], onupdate="CASCADE", ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            comment="AI 集成 MCP 会话表",
        )
        op.create_index(op.f("ix_ai_integration_mcp_sessions_app_id"), "ai_integration_mcp_sessions", ["app_id"], unique=False)
        op.create_index(op.f("ix_ai_integration_mcp_sessions_created_time"), "ai_integration_mcp_sessions", ["created_time"], unique=False)


def downgrade() -> None:
    # 逆序撤销（drop_table 会自动连带删除索引）
    op.drop_table("ai_integration_mcp_sessions")
    op.drop_table("ai_integration_call_logs")
    op.drop_table("ai_integration_apps")
