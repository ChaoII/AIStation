"""迁移脚本

Revision ID: 183fb76b1184
Revises: d6d5f85952f5
Create Date: 2026-09-15 18:50:53.160283

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '183fb76b1184'
down_revision: str | None = 'd6d5f85952f5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_column(table: str, column: str) -> bool:
    """列存在探测：兼容「先重启兜底补列、后跑迁移」的顺序（避免 DuplicateColumn）。"""
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return column in {col["name"] for col in insp.get_columns(table)}


def upgrade() -> None:
    # 告警规则新增灰度配置列（缺省 {} 表示全量生效，既有规则行为不变）
    if not _has_column("video_alarm_rules", "rollout"):
        op.add_column(
            'video_alarm_rules',
            sa.Column(
                'rollout',
                postgresql.JSONB(astext_type=sa.Text()),
                server_default='{}',
                nullable=False,
                comment='灰度配置: {percent, whitelist, blacklist}',
            ),
        )


def downgrade() -> None:
    op.drop_column('video_alarm_rules', 'rollout')
