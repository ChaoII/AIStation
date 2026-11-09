"""护栏：问数包的**任一子模块**都必须能被单独导入（不能依赖 import 顺序）。

背景（2026-11-09 实测）：`service.py` 在模块顶层按名字从子模块取符号
（`from .metric_rules import AGG_INTENT`……），而子模块顶层又 `from . import service`。
如果调用方先导入**子模块**，两边互相等待 → `partially initialized module` ImportError。
启动路径永远先加载 service，所以这个问题只在「脚本/测试直接导入子模块」时暴露。

修法是包 `__init__.py` 先完整加载 service；这个测试把它钉住，防止以后有人
把那行 import 当成多余代码删掉。

⚠️ 每个用例都**另起进程**（子进程开销约 7s，因为要完整加载 service），
所以只保留两个最有代表性的场景，不要按模块逐个参数化（会慢到 50s+）。
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]

#: 曾经真实踩过的模块（覆盖三种写法：纯函数模块、缓存模块、执行层）
FRAGILE = ["metric_rules", "sqlguard", "sqlcache", "execution", "runtime_flags", "metrics_ops"]


def _import_in_fresh_process(modules: list[str]) -> subprocess.CompletedProcess:
    code = "import importlib\n" + "".join(
        f"importlib.import_module('app.plugin.module_ai.query.{m}')\n" for m in modules
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND)
    env.setdefault("ENVIRONMENT", "dev")
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )


def test_worst_case_single_module_import() -> None:
    """最坏情况：直接导入 `metric_rules`（service 从未被导入过）。"""
    r = _import_in_fresh_process(["metric_rules"])
    assert r.returncode == 0, f"单独导入 metric_rules 失败：\n{r.stderr[-800:]}"


def test_fragile_modules_import_in_sequence() -> None:
    """一次进程里依次导入全部「踩过坑」的模块（覆盖互相引用与缓存模块）。"""
    r = _import_in_fresh_process(FRAGILE)
    assert r.returncode == 0, f"多模块顺序导入失败：\n{r.stderr[-800:]}"
