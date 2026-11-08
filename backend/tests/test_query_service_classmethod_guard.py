"""护栏：问数 service / mixin 里的类方法必须带装饰器。

背景（2026-11 实测两次）：脚本批量插入/搬移代码时把 ``@classmethod`` 挤掉，
``py_compile`` 通过、单测也可能全绿，但 ``AiQueryService.ask()`` 一调就变成
「缺少 1 个位置参数」的 500。这个测试直接把契约钉死，不用等到运行时。

判定：模块顶层类里，4 空格缩进的 ``def``/``async def`` 上方（跳过空行）必须是
装饰器（``@...``）；嵌套函数不受影响（缩进更深）。
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest

#: 参与检查的文件（新增 mixin 记得加进来）
TARGETS = [
    "app/plugin/module_ai/query/service.py",
    "app/plugin/module_ai/query/actions_ops.py",
    "app/plugin/module_ai/query/ask_ops.py",
    "app/plugin/module_ai/query/assets_ops.py",
    "app/plugin/module_ai/query/slowpath_ops.py",
    "app/plugin/module_ai/query/nl2sql_ops.py",
    "app/plugin/module_ai/query/context_ops.py",
    "app/plugin/module_ai/query/execute_ops.py",
    "app/plugin/module_ai/query/metrics_ops.py",
    "app/plugin/module_ai/query/ontology_ops.py",
    "app/plugin/module_ai/query/propositions_ops.py",
]

_ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("rel", TARGETS)
def test_no_cross_module_global_state(rel: str) -> None:
    """mixin 里不得用 ``global`` 改 service 的进程级缓存。

    搬进 mixin 后 ``global _SCHEMA_CACHE`` 只会创建**本模块**的新变量：
    service 的缓存永远不失效，表现为「改完资产/生成完指标，前端还是旧数据」。
    正确写法是 ``from . import service as _svc; _svc._SCHEMA_CACHE = None``。
    """
    src = io.open(_ROOT / rel, encoding="utf-8").read()
    # service.py 是这些缓存的**主人**，它用 global 是正确的；只有搬出去的模块不行
    if not rel.endswith("/service.py"):
        for cache in ("_SCHEMA_CACHE", "_SEMANTIC_INDEX", "_ASSET_TMETA", "_SETTINGS_CACHE"):
            assert f"global {cache}" not in src, f"{rel} 用 global 改 {cache}（跨模块无效）"
            assert f"global _SCHEMA_CACHE, {cache}" not in src, rel


@pytest.mark.parametrize("rel", TARGETS)
def test_class_methods_keep_decorator(rel: str) -> None:
    lines = io.open(_ROOT / rel, encoding="utf-8").read().split("\n")
    missing: list[str] = []
    in_class = False
    for i, line in enumerate(lines):
        # 只在类体里检查：顶层函数内部嵌套的 def（如 _render_template.repl）不算类方法
        if re.match(r"^class ", line):
            in_class = True
            continue
        if re.match(r"^\S", line):
            in_class = False
        if not in_class or not re.match(r"^    (async def |def )", line):
            continue
        j = i - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        prev = lines[j].strip() if j >= 0 else ""
        if not prev.startswith("@"):
            missing.append(f"{rel}:{i + 1} {line.strip()[:70]}")
    assert not missing, "类方法丢了装饰器（会变成需要额外位置参数的实例方法）：\n" + "\n".join(missing)
