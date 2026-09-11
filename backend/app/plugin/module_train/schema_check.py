"""训练模块缺失列清单与启动补列。

用于旧库升级：Alembic 迁移之外，启动时幂等补齐 ORM 已声明但库里缺失的列。
"""

MISSING_TRAIN_COLUMNS: dict[str, list[tuple[str, str]]] = {
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


async def ensure_train_columns(engine) -> None:
    """幂等补齐训练相关表的缺失列（ALTER TABLE ... ADD COLUMN IF NOT EXISTS）。

    每条 DDL 使用独立事务：PostgreSQL 中一条语句失败会中止当前事务，
    若共用事务将导致后续语句全部报 InFailedSqlTransaction 并回滚，
    静默丢弃全部补列。独立事务可隔离单列失败，且失败会被记录而非吞掉。
    """
    from sqlalchemy import text

    from app.core.logger import log

    for table, columns in MISSING_TRAIN_COLUMNS.items():
        for name, col_type in columns:
            try:
                async with engine.begin() as conn:
                    await conn.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {col_type}")
                    )
            except Exception as e:
                log.warning(f"train backfill skipped {table}.{name}: {e}")
