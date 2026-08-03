"""trainframework 枚举补充 PYTORCH_OCR_DET / PYTORCH_OCR_REC

Revision ID: 1c2d3e4f5a6b
Revises: f1a2b3c4d5e6
Create Date: 2026-08-03

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1c2d3e4f5a6b"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PG 12+ 支持在事务内 ADD VALUE；IF NOT EXISTS 需 PG 12+ 才可用。
    # trainframework 枚举创建于 b744384adf6f，含 PADDLEX / ULTRALYTICS。
    op.execute("ALTER TYPE trainframework ADD VALUE IF NOT EXISTS 'PYTORCH_OCR_DET'")
    op.execute("ALTER TYPE trainframework ADD VALUE IF NOT EXISTS 'PYTORCH_OCR_REC'")


def downgrade() -> None:
    # PostgreSQL 不提供删除单个枚举值的语法；重建类型需 ALTER 依赖列，成本高且
    # 易出错。此迁移不提供 enum 回退（new values 是纯增量，不回退不影响旧数据）。
    pass
