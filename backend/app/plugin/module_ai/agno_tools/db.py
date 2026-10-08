"""Agno 运行态数据库：为工作流 HITL（跨请求审批续跑）持久化 Agno 运行状态。

Agno 的 HITL 续跑（``acontinue_run``）依赖 agent 的 session/run 状态；工作流的
「暂停 → 人工审批 → 续跑」跨请求，故用轻量 SQLite 文件承载 Agno 运行态（与业务库
分离，避免占用业务连接池与 schema）。非 HITL 的普通 LLM 节点不需要此库。
"""
from __future__ import annotations

import os
from pathlib import Path

#: 运行态库文件（backend/data/agno_workflow_runs.db；测试环境用临时文件）
_DB_FILE = str(Path(__file__).resolve().parents[4] / "data" / "agno_workflow_runs.db")

_db = None
_initialized = False


def get_agno_db():
    """返回工作流 HITL 用的 Agno 运行态库（懒加载、进程内缓存）；不可用时返回 None。"""
    global _db, _initialized
    if _initialized:
        return _db
    _initialized = True
    try:
        import tempfile

        from agno.db.sqlite import AsyncSqliteDb

        from app.config.setting import settings

        if settings.TESTING:
            db_file = str(Path(tempfile.gettempdir()) / "agno_workflow_runs_test.db")
        else:
            db_file = _DB_FILE
            os.makedirs(os.path.dirname(db_file), exist_ok=True)
        _db = AsyncSqliteDb(db_file=db_file)
    except Exception:  # noqa: BLE001 运行态库不可用时降级（HITL 不可用，不阻断进程）
        _db = None
    return _db
