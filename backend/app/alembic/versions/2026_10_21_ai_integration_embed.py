"""AI 集成 P4'：嵌入令牌/会话两表 + 会话归属列 + 删除旧分享列

Revision ID: a9b8c7d6e5f4
Revises: c9d0e1f2a3b4
Create Date: 2026-10-22 00:00:00.000000

说明：手写迁移（`autogenerate` 会误判大量未被模型覆盖的历史/影子表，产生无关 DROP）。
- 新建两表（嵌入令牌、嵌入会话映射），`has_table` 幂等守卫，空库/重放安全；
- `ai_assistant_sessions.source_app_id`、`ai_workflows.share_token` 一律先 `has_column` 探测；
- 本迁移与「旧分享通道拆除」同批：`share_token` 列在此删除（代码侧已无引用）。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9b8c7d6e5f4"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TOKEN_TABLE = "ai_integration_access_tokens"
_EMBED_SESSION_TABLE = "ai_integration_embed_sessions"
_SESSION_TABLE = "ai_assistant_sessions"
_WORKFLOW_TABLE = "ai_workflows"


def _columns(insp, table: str) -> set[str]:
    """返回表的列名集合（表不存在返回空集）。"""
    if table not in insp.get_table_names():
        return set()
    return {c["name"] for c in insp.get_columns(table)}


def _index_names(insp, table: str) -> set[str]:
    """返回表的索引名集合（表不存在返回空集）。"""
    if table not in insp.get_table_names():
        return set()
    return {i["name"] for i in insp.get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    # 1. 嵌入令牌表
    if _TOKEN_TABLE not in tables:
        op.create_table(
            _TOKEN_TABLE,
            sa.Column("app_id", sa.Integer(), nullable=False, comment="所属应用ID"),
            sa.Column("appid", sa.String(length=64), nullable=False, comment="应用标识（冗余）"),
            sa.Column("kind", sa.String(length=16), nullable=False, comment="嵌入形态: agent/app/workflow"),
            sa.Column("target_id", sa.Integer(), nullable=False, comment="嵌入目标ID"),
            sa.Column("token_hash", sa.String(length=128), nullable=False, comment="令牌散列（sha256，不存明文）"),
            sa.Column("expires_at", sa.DateTime(), nullable=False, comment="过期时间"),
            sa.Column("revoked", sa.Boolean(), nullable=False, comment="是否已吊销"),
            sa.Column("issued_by", sa.String(length=16), nullable=False, comment="签发方式: exchange/admin"),
            sa.Column("use_count", sa.Integer(), nullable=False, comment="累计使用次数"),
            sa.Column("last_used_at", sa.DateTime(), nullable=True, comment="最后使用时间"),
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
            sa.Column("uuid", sa.String(length=64), nullable=False, comment="UUID全局唯一标识"),
            sa.Column("status", sa.String(length=10), nullable=False, comment="状态(0:正常 1:禁用)"),
            sa.Column("description", sa.Text(), nullable=True, comment="备注/描述"),
            sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="是否已删除(0:未删除 1:已删除)"),
            sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
            sa.ForeignKeyConstraint(["app_id"], ["ai_integration_apps.id"]),
            sa.PrimaryKeyConstraint("id"),
            comment="AI 集成嵌入令牌表",
        )
        op.create_index(op.f(f"ix_{_TOKEN_TABLE}_app_id"), _TOKEN_TABLE, ["app_id"], unique=False)
        op.create_index(op.f(f"ix_{_TOKEN_TABLE}_token_hash"), _TOKEN_TABLE, ["token_hash"], unique=True)
        op.create_index(op.f(f"ix_{_TOKEN_TABLE}_created_time"), _TOKEN_TABLE, ["created_time"], unique=False)
        op.create_index(op.f(f"ix_{_TOKEN_TABLE}_updated_time"), _TOKEN_TABLE, ["updated_time"], unique=False)
        op.create_index(op.f(f"ix_{_TOKEN_TABLE}_uuid"), _TOKEN_TABLE, ["uuid"], unique=True)
        op.create_index(op.f(f"ix_{_TOKEN_TABLE}_status"), _TOKEN_TABLE, ["status"], unique=False)
        op.create_index(op.f(f"ix_{_TOKEN_TABLE}_is_deleted"), _TOKEN_TABLE, ["is_deleted"], unique=False)
        op.create_index(op.f(f"ix_{_TOKEN_TABLE}_deleted_time"), _TOKEN_TABLE, ["deleted_time"], unique=False)

    # 2. 嵌入会话映射表
    if _EMBED_SESSION_TABLE not in tables:
        op.create_table(
            _EMBED_SESSION_TABLE,
            sa.Column("app_id", sa.Integer(), nullable=False, comment="所属应用ID"),
            sa.Column("sid", sa.String(length=64), nullable=False, comment="客户端会话标识"),
            sa.Column("kind", sa.String(length=16), nullable=False, comment="嵌入形态"),
            sa.Column("target_id", sa.Integer(), nullable=False, comment="嵌入目标ID"),
            sa.Column("session_id", sa.Integer(), nullable=False, comment="平台会话ID（ai_assistant_sessions.id）"),
            sa.Column("expires_at", sa.DateTime(), nullable=False, comment="映射过期时间"),
            sa.Column("last_active_at", sa.DateTime(), nullable=False, comment="最后活跃时间"),
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False, comment="主键ID"),
            sa.Column("uuid", sa.String(length=64), nullable=False, comment="UUID全局唯一标识"),
            sa.Column("status", sa.String(length=10), nullable=False, comment="状态(0:正常 1:禁用)"),
            sa.Column("description", sa.Text(), nullable=True, comment="备注/描述"),
            sa.Column("created_time", sa.DateTime(), nullable=False, comment="创建时间"),
            sa.Column("updated_time", sa.DateTime(), nullable=False, comment="更新时间"),
            sa.Column("is_deleted", sa.Boolean(), nullable=False, comment="是否已删除(0:未删除 1:已删除)"),
            sa.Column("deleted_time", sa.DateTime(), nullable=True, comment="删除时间"),
            sa.ForeignKeyConstraint(["app_id"], ["ai_integration_apps.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("app_id", "sid", name="uq_ai_integration_embed_sessions_app_sid"),
            comment="AI 集成嵌入会话映射表",
        )
        op.create_index(op.f(f"ix_{_EMBED_SESSION_TABLE}_app_id"), _EMBED_SESSION_TABLE, ["app_id"], unique=False)
        op.create_index(op.f(f"ix_{_EMBED_SESSION_TABLE}_sid"), _EMBED_SESSION_TABLE, ["sid"], unique=False)
        op.create_index(op.f(f"ix_{_EMBED_SESSION_TABLE}_created_time"), _EMBED_SESSION_TABLE, ["created_time"], unique=False)
        op.create_index(op.f(f"ix_{_EMBED_SESSION_TABLE}_updated_time"), _EMBED_SESSION_TABLE, ["updated_time"], unique=False)
        op.create_index(op.f(f"ix_{_EMBED_SESSION_TABLE}_uuid"), _EMBED_SESSION_TABLE, ["uuid"], unique=True)
        op.create_index(op.f(f"ix_{_EMBED_SESSION_TABLE}_status"), _EMBED_SESSION_TABLE, ["status"], unique=False)
        op.create_index(op.f(f"ix_{_EMBED_SESSION_TABLE}_is_deleted"), _EMBED_SESSION_TABLE, ["is_deleted"], unique=False)
        op.create_index(op.f(f"ix_{_EMBED_SESSION_TABLE}_deleted_time"), _EMBED_SESSION_TABLE, ["deleted_time"], unique=False)

    # 3. 会话归属列（P4' 起嵌入会话物化 source_app_id）
    if "source_app_id" not in _columns(insp, _SESSION_TABLE):
        op.add_column(
            _SESSION_TABLE,
            sa.Column(
                "source_app_id",
                sa.Integer(),
                nullable=True,
                comment="来源集成应用ID（空=内部用户创建）",
            ),
        )
        op.create_index(
            op.f(f"ix_{_SESSION_TABLE}_source_app_id"), _SESSION_TABLE, ["source_app_id"], unique=False
        )

    # 4. 删除旧分享列（旧 /share 通道已整体拆除）
    #    注意：SQLite 在有索引引用该列时拒绝 DROP COLUMN，必须先删索引。
    if "share_token" in _columns(insp, _WORKFLOW_TABLE):
        share_idx = op.f(f"ix_{_WORKFLOW_TABLE}_share_token")
        if share_idx in _index_names(insp, _WORKFLOW_TABLE):
            op.drop_index(share_idx, table_name=_WORKFLOW_TABLE)
        op.drop_column(_WORKFLOW_TABLE, "share_token")


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # 逆序撤销：恢复分享列 → 删会话归属列 → 删两表
    if _WORKFLOW_TABLE in insp.get_table_names():
        if "share_token" not in _columns(insp, _WORKFLOW_TABLE):
            op.add_column(
                _WORKFLOW_TABLE,
                sa.Column(
                    "share_token",
                    sa.String(length=64),
                    nullable=True,
                    comment="公开分享令牌（受限运行）",
                ),
            )
            op.create_index(
                op.f(f"ix_{_WORKFLOW_TABLE}_share_token"), _WORKFLOW_TABLE, ["share_token"], unique=False
            )

    if _SESSION_TABLE in insp.get_table_names() and "source_app_id" in _columns(insp, _SESSION_TABLE):
        idx = op.f(f"ix_{_SESSION_TABLE}_source_app_id")
        if idx in _index_names(insp, _SESSION_TABLE):
            op.drop_index(idx, table_name=_SESSION_TABLE)
        op.drop_column(_SESSION_TABLE, "source_app_id")

    tables = set(insp.get_table_names())
    if _EMBED_SESSION_TABLE in tables:
        op.drop_table(_EMBED_SESSION_TABLE)
    if _TOKEN_TABLE in tables:
        op.drop_table(_TOKEN_TABLE)
