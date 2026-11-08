"""测试辅助：把「问数服务」的**全部源码**拼成一份，供结构断言使用。

背景（2026-11-08）：`service.py` 已按职责拆成 `*_ops.py` 的 mixin。原本
`inspect.getsource(service)` 只覆盖 service.py，代码搬走后结构断言会**假失败**
（找不到子串），或更糟——**假通过**（新模块里违规了但没扫到）。

约定：凡是「扫描源码找某段代码/某个默认值」的测试，一律走这里，而不是直接
`inspect.getsource(service)`。
"""
from __future__ import annotations

import inspect

MODULE_NAMES = (
    "settings_ops",
    "sqlguard",
    "sqlcache",
    "question_rules",
    "metric_rules",
    "degraded",
    "datasource_ops",
    "session_ops",
    "service",
    "ask_ops",
    "actions_ops",
    "assets_ops",
    "context_ops",
    "execute_ops",
    "metrics_ops",
    "nl2sql_ops",
    "ontology_ops",
    "propositions_ops",
    "slowpath_ops",
)


def query_module_sources() -> str:
    """service + 全部 mixin 的源码（顺序固定，便于断言与排查）。"""
    from app.plugin.module_ai.query import __dict__ as pkg  # noqa: F401  (确保包已导入)

    import importlib

    parts = []
    for name in MODULE_NAMES:
        mod = importlib.import_module(f"app.plugin.module_ai.query.{name}")
        parts.append(inspect.getsource(mod))
    return "\n".join(parts)


def read_query_file(filename: str) -> str:
    """按文件名读源码（`test_query_eval.py` 那种按路径读的场景用）。"""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    return (
        root / "app" / "plugin" / "module_ai" / "query" / filename
    ).read_text(encoding="utf-8")
