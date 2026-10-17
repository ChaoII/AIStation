"""Agno OpenTelemetry 追踪接入。

把 Agno 的 agent / 模型调用 / 工具执行 / 工作流步骤写入运行态库
（``agno_traces`` / ``agno_spans``），用于定位慢调用、异常与调用链。

设计要点：
- 与工作流 HITL 共用同一 Agno 运行态库（SQLite 文件，与业务库分离）；
- **幂等**：进程内只初始化一次；Agno 侧若已有 TracerProvider 会自动跳过；
- **best-effort**：追踪不可用（缺依赖/库不可用）只告警，不影响主流程；
- 开关：``settings.AGNO_TRACING``（默认开）。
"""
from __future__ import annotations

from app.core.logger import log

_setup_done = False


def ensure_tracing() -> bool:
    """启用 Agno 追踪（幂等）。返回是否已启用。"""
    global _setup_done
    if _setup_done:
        return True
    _setup_done = True
    try:
        from app.config.setting import settings

        if not getattr(settings, "AGNO_TRACING", True):
            return False
        from agno.tracing import setup_tracing

        from .db import get_agno_db

        db = get_agno_db()
        if db is None:
            log.warning("[agno] 追踪未启用：Agno 运行态库不可用")
            return False
        setup_tracing(db=db)
        # 追踪落库走 SQLite（aiosqlite），其 DEBUG 日志会把每条 span 的完整
        # SQL 与参数打进日志（实测每个 LLM 调用 ~5KB），dev 下刷屏且拖慢；
        # 这里只静默该库自身的 DEBUG，不影响业务日志级别。
        import logging as _logging

        _logging.getLogger("aiosqlite").setLevel(_logging.WARNING)
        log.info("✅ Agno 追踪已启用（agno_traces / agno_spans）")
        return True
    except Exception as e:  # noqa: BLE001  追踪失败不阻断
        log.warning(f"[agno] 追踪启用失败（忽略）: {str(e)[:140]}")
        return False
