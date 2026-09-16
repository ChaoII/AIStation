"""补齐训练模块缺失列

Revision ID: 7a1b2c3d4e5f
Revises: 1c2d3e4f5a6b
Create Date: 2026-09-11
"""
from collections.abc import Sequence

from alembic import op

revision: str = "7a1b2c3d4e5f"
down_revision: str | None = "1c2d3e4f5a6b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADDITIONS: dict[str, list[tuple[str, str]]] = {
    "train_tasks": [
        ("annotation_task_id", "INTEGER"),
        ("cleanup_delay_minutes", "INTEGER"),
        ("metrics_log", "JSONB"),
        ("best_metrics", "JSONB"),
        ("last_metrics", "JSONB"),
        ("error_log", "TEXT"),
    ],
    "train_models": [
        ("repo_id", "INTEGER"),
        ("export_format", "VARCHAR(32)"),
    ],
    "train_evals": [
        ("model_id", "INTEGER"),
        ("framework", "VARCHAR(16)"),
        ("hyperparams", "JSONB"),
        ("progress", "INTEGER"),
        ("started_at", "TIMESTAMP"),
        ("finished_at", "TIMESTAMP"),
        ("error_log", "TEXT"),
        ("metrics_log", "JSONB"),
        ("best_metrics", "JSONB"),
        ("last_metrics", "JSONB"),
    ],
}


def upgrade() -> None:
    for table, columns in _ADDITIONS.items():
        for name, col_type in columns:
            op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {col_type}")


def downgrade() -> None:
    pass
