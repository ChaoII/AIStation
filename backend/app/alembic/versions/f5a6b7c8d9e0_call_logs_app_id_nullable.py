"""AI 集成开放平台：调用日志 app_id 改为可空（OAuth 委托调用无应用行）

Revision ID: f5a6b7c8d9e0
Revises: e3f4a5b6c7d8
Create Date: 2026-10-29 15:30:00.000000

背景：模式 C（OAuth 2.1 用户委托）调用数据面时没有对应的
``ai_integration_apps`` 应用行，审计只能记录 ``appid=client_id`` 而
``app_id`` 为 NULL。故把 ``ai_integration_call_logs.app_id`` 改为可空。

用 ``has_column`` 幂等守卫，避免空库全链重放（SQLite 回归）失败。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e3f4a5b6c7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("ai_integration_call_logs")}
    if "app_id" in cols:
        op.alter_column(
            "ai_integration_call_logs", "app_id",
            existing_type=sa.Integer(),
            nullable=True,
            existing_comment="所属应用ID",
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = {c["name"] for c in insp.get_columns("ai_integration_call_logs")}
    if "app_id" in cols:
        op.alter_column(
            "ai_integration_call_logs", "app_id",
            existing_type=sa.Integer(),
            nullable=False,
            existing_comment="所属应用ID",
        )
