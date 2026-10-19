"""RAG 任务处理器注册表（worker 按 ``kind`` 分派）。"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

#: ``kind -> handler``；handler 接收任务字典，内部负责进度上报与取消检查
JOB_HANDLERS: dict[str, Callable[[dict], Awaitable[None]]] = {}


def register(kind: str, handler: Callable[[dict], Awaitable[None]]) -> None:
    """注册任务处理器（重复注册以最后一次为准，便于测试覆盖）。"""
    JOB_HANDLERS[kind] = handler


def get_handler(kind: str) -> Callable[[dict], Awaitable[None]] | None:
    return JOB_HANDLERS.get(kind)
