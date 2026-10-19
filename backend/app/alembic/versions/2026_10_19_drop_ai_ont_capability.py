"""删除已下线的本体能力登记表 ai_ont_capability

Revision ID: c7d8e9f0a1b2
Revises: f6b7c8d9e0a1
Create Date: 2026-10-19

说明（**手写迁移**，本项目禁用 autogenerate）：

本体能力登记（Capability）于 2026-10-19 整体下线，理由：
- Palantir Ontology 没有 "Capability" 这个本体对象类型（自造概念贴官方标签）；
- 代码侧唯一读它的是 ``agent/service.py`` 的 ``_cap_names`` / ``_cap_types``，
  二者**定义了但零调用**（死代码），且自带 except 兜底 —— 属"有关联但是死关联"；
- 本体的 CRUD 端点、服务层、前端封装、「维护 → 能力登记」UI、相关测试均已删除。

本迁移负责把表从各环境清掉：
- ``upgrade()`` 幂等：表不存在（空库全链重放 / 已手工删过）即跳过；
- ``downgrade()`` 重建一张**空表**（纯登记数据，无可恢复价值，重建只为可回滚）。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "f6b7c8d9e0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table("ai_ont_capability"):
        return  # 空库全链重放 / 已删过：幂等跳过
    op.drop_table("ai_ont_capability")


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("ai_ont_capability"):
        return  # 已存在（重复回滚）：幂等跳过
    op.create_table(
        "ai_ont_capability",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("name", sa.String(160)),
        sa.Column("type", sa.String(32)),
        sa.Column("description", sa.Text),
        sa.Column("enabled", sa.Boolean, server_default=sa.text("1")),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("0")),
        sa.Column("created_time", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
