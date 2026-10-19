"""merge heads：简单模式 bridge 与 RAG 检索 v2 迁移链

Revision ID: d2e3f4a5b6c7
Revises: f7a8b9c0d1e2, b1c2d3e4f5a6
Create Date: 2026-10-20 00:20:00.000000

说明：main 在简单模式分支验证期间又合入了 RAG 检索链路 v2（其迁移
``b1c2d3e4f5a6`` 同样以 ``f6b7c8d9e0a1`` 为父），与本分支已收敛的
``f7a8b9c0d1e2`` 形成两个 head。本迁移只做 DAG 合流（无 schema 变更），
使 ``alembic upgrade head`` 在最外层 main 上保持单 head。
"""
from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "d2e3f4a5b6c7"
down_revision: tuple[str, str] | None = ("f7a8b9c0d1e2", "b1c2d3e4f5a6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """纯 DAG 合并，无 schema 变更。"""


def downgrade() -> None:
    """回退到合并前（分支指针），无 schema 变更。"""
