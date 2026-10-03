"""后端启动时初始化 AI 扩展（pgvector / Apache AGE / pg_jieba）。

仅对 PostgreSQL 数据库执行；非 PostgreSQL 或未安装扩展（如旧 postgres:17 或 SQLite 测试）
时静默跳过，不阻塞启动。
"""
from __future__ import annotations

import os

_STMTS = [
    "CREATE EXTENSION IF NOT EXISTS vector",
    "CREATE EXTENSION IF NOT EXISTS age",
    "CREATE EXTENSION IF NOT EXISTS pg_jieba",
]


async def ensure_extensions() -> None:
    """初始化扩展：创建扩展、LOAD age、确保 jieba 全文配置。"""
    if (os.getenv("DATABASE_TYPE") or "postgresql").lower() != "postgresql":
        return
    try:
        from sqlalchemy import text

        from app.core.database import async_db_session

        async with async_db_session() as db:
            for stmt in _STMTS:
                try:
                    await db.execute(text(stmt))
                except Exception:  # noqa: BLE001 单个扩展失败不影响其它
                    await db.rollback()
            # ARGE 会话内加载（若已 preload 则冗余无害）
            try:
                await db.execute(text("LOAD 'age'"))
            except Exception:  # noqa: BLE001
                pass
            # 确保中文全文检索配置存在（pg_jieba 提供 jiebacfg 字典，缺则按 simple 补建）
            try:
                await db.execute(
                    text(
                        "CREATE TEXT SEARCH CONFIGURATION IF NOT EXISTS jiebacfg (COPY = simple)"
                    )
                )
            except Exception:  # noqa: BLE001
                await db.rollback()
            await db.commit()
    except Exception:  # noqa: BLE001  初始化失败不阻塞服务启动
        pass
