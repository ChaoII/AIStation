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
    "app/plugin/module_ai/query/assets_ops.py",
]

_ROOT = pathlib.Path(__file__).resolve().parents[1]


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
