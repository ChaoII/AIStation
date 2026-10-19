"""merge heads：train_metric_events（简单模式）与 AI 空间迁移链

Revision ID: f7a8b9c0d1e2
Revises: 3f9c2a71d5e8, c0ffee111111
Create Date: 2026-10-19 23:40:00.000000

说明：2026-10-19 把 main 合入 feat/simple-mode-bridge 后出现两个 head——
本分支的 ``3f9c2a71d5e8``（train_metric_events）与 main 的 ``c0ffee111111``
（AI 空间表）同源于 ``f6b7c8d9e0a1``。本迁移只做 DAG 合并（无 schema 变更），
保证 ``alembic upgrade head`` 不再报「The script directory has multiple heads」。
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: tuple[str, str] | None = ("3f9c2a71d5e8", "c0ffee111111")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """纯 DAG 合并，无 schema 变更。"""


def downgrade() -> None:
    """回退到合并前（分支指针），无 schema 变更。"""
