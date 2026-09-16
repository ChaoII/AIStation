"""新增告警规则场景参数列

Revision ID: 1164d4a7539d
Revises: 7a1b2c3d4e5f
Create Date: 2026-09-15 07:45:28.149617

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "1164d4a7539d"
down_revision: str | None = "7a1b2c3d4e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """仅新增 video_alarm_rules.params（JSONB，默认 '{}'）。"""
    op.add_column(
        "video_alarm_rules",
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
            comment="场景参数原值",
        ),
    )


def downgrade() -> None:
    op.drop_column("video_alarm_rules", "params")
