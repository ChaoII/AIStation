"""AI 表命名对齐（P2）：重命名 7 张命名不准确的物理表

Revision ID: e2f3a4b5c6d7
Revises: c8d9e0f1a2b3
Create Date: 2026-10-17 16:00:00.000000

说明（手写迁移，autogenerate 会因影子表产生无关 DROP）：
- 只做**表重命名**；PostgreSQL 的索引/序列名保留旧名（无功能影响，如需整洁可另行重命名）。
- 存在性判断：新库（create_all 已按新名建表）或已迁移库重复执行均安全。
- 对照（旧 → 新）：
    ai_action            → ai_query_writeback        （与本体 ai_ont_action 撞名）
    ai_action_log        → ai_query_writeback_log
    ai_sessions          → ai_assistant_sessions     （与问数会话区分）
    ai_messages          → ai_assistant_messages
    ai_query_reports     → ai_report_template        （与 ai_reports 区分）
    ai_domain            → ai_data_domain            （与 ai_ont_domain 区分）
    ai_fde_proposition   → ai_delivery_proposition   （去 FDE 借词）
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RENAMES: list[tuple[str, str]] = [
    ("ai_action", "ai_query_writeback"),
    ("ai_action_log", "ai_query_writeback_log"),
    ("ai_sessions", "ai_assistant_sessions"),
    ("ai_messages", "ai_assistant_messages"),
    ("ai_query_reports", "ai_report_template"),
    ("ai_domain", "ai_data_domain"),
    ("ai_fde_proposition", "ai_delivery_proposition"),
]


def _rename(pairs: list[tuple[str, str]]) -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    for old, new in pairs:
        if old in existing and new not in existing:
            op.rename_table(old, new)
            existing.discard(old)
            existing.add(new)


def upgrade() -> None:
    _rename(RENAMES)


def downgrade() -> None:
    _rename([(new, old) for old, new in RENAMES])
