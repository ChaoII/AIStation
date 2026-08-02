"""创建模型部署表 train_deploys

Revision ID: d1e2f3a4b5c6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-16 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "train_deploys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("uuid", sa.String(64), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_time", sa.DateTime(), nullable=False),
        sa.Column("updated_time", sa.DateTime(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deleted_time", sa.DateTime(), nullable=True),
        sa.Column("created_id", sa.Integer(), nullable=True),
        sa.Column("updated_id", sa.Integer(), nullable=True),
        sa.Column("deleted_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(128), nullable=False, comment="部署名称"),
        sa.Column("model_id", sa.Integer(), nullable=False, comment="模型ID"),
        sa.Column("model_name", sa.String(128), nullable=False, comment="模型名称"),
        sa.Column("model_version", sa.String(32), nullable=False, comment="模型版本"),
        sa.Column("framework", sa.String(16), nullable=False, comment="框架"),
        sa.Column("device", sa.String(16), nullable=False, server_default="0", comment="GPU设备ID或cpu"),
        sa.Column("host_port", sa.Integer(), nullable=False, comment="宿主机端口"),
        sa.Column("container_id", sa.String(64), nullable=True, comment="Docker容器ID"),
        sa.Column("api_url", sa.String(256), nullable=True, comment="API地址"),
        sa.Column("api_key", sa.String(64), nullable=False, comment="API密钥"),
        sa.Column("docker_image", sa.String(256), nullable=False, server_default="ultralytics/ultralytics:latest", comment="Docker镜像"),
        sa.Column("hyperparams", sa.JSON(), nullable=True, comment="推理参数"),
        sa.Column("error_log", sa.Text(), nullable=True, comment="错误日志"),
        sa.Column("started_at", sa.DateTime(), nullable=True, comment="开始时间"),
        sa.Column("finished_at", sa.DateTime(), nullable=True, comment="完成时间"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_train_deploys_id"), "train_deploys", ["id"])


def downgrade() -> None:
    op.drop_table("train_deploys")
