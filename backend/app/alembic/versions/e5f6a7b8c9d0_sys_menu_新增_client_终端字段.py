"""sys_menu 新增 client 终端字段（FastapiAdmin v3 升级）

Revision ID: e5f6a7b8c9d0
Revises: d1e2f3a4b5c6
Create Date: 2026-07-20 12:00:00.000000
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d1e2f3a4b5c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sys_menu",
        sa.Column(
            "client",
            sa.String(length=20),
            nullable=False,
            server_default="pc",
            comment="终端(pc:管理端桌面 app:移动端)",
        ),
    )


def downgrade() -> None:
    op.drop_column("sys_menu", "client")
