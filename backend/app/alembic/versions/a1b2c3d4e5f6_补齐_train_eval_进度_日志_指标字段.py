"""补齐 TrainEval 进度/日志/指标字段

Revision ID: a1b2c3d4e5f6
Revises: c9f2a1b4d8e3
Create Date: 2026-07-16 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "c9f2a1b4d8e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("train_evals", sa.Column("progress", sa.Integer(), nullable=True, server_default="0", comment="进度0-100"))
    op.add_column("train_evals", sa.Column("error_log", sa.Text(), nullable=True, comment="错误日志"))
    op.add_column("train_evals", sa.Column("metrics_log", sa.JSON(), nullable=True, comment="每轮评估指标"))
    op.add_column("train_evals", sa.Column("best_metrics", sa.JSON(), nullable=True, comment="最优指标"))
    op.add_column("train_evals", sa.Column("last_metrics", sa.JSON(), nullable=True, comment="最终指标"))


def downgrade() -> None:
    op.drop_column("train_evals", "progress")
    op.drop_column("train_evals", "error_log")
    op.drop_column("train_evals", "metrics_log")
    op.drop_column("train_evals", "best_metrics")
    op.drop_column("train_evals", "last_metrics")
