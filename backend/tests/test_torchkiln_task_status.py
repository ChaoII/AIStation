"""训练任务的状态语义：PENDING=排队中，RUNNING=已分配资源开始执行。

为什么单独钉这一条：TorchKiln 执行器此前**从不**置 ``RUNNING``，任务从
创建到结束一直是 ``pending``。后果不是"少了个状态"，而是**显示与事实相反**——
列表页把正在训练的任务标成"排队中"，进度条与"运行中"分支
（``v-if="status === 'running'"``）永远不出现，用户完全无法区分
"正在训练" / "正在等 GPU" / "卡住了"。

判定跃迁点的原则：**拿到 GPU 与端口的那一刻**才算开始，此前是排队。
"""
from __future__ import annotations

import ast
import inspect
import pathlib

from app.plugin.module_train import torchkiln_executor as te

EXECUTOR = pathlib.Path(te.__file__)


def _execute_src() -> str:
    return inspect.getsource(te.TorchKilnExecutor._execute)


def _execute_ast() -> ast.FunctionDef:
    """从**整个模块文件**里取出 ``_execute`` 的语法树。

    不直接 parse 方法源码：类方法带一级缩进要 dedent，而 ``_execute`` 里含有
    多行字符串，其中某些行没有前导空白——``textwrap.dedent`` 的"最长公共前缀"
    因此为空、变成空操作，parse 直接 IndentationError。整文件 parse 没有这问题。
    """
    tree = ast.parse(EXECUTOR.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_execute":
            return node
    raise AssertionError("模块里找不到 _execute，可能被改名或移走")


def test_executor_marks_running_after_acquiring_resources():
    """必须在 acquire 之后置 RUNNING，且不在 acquire 之前。"""
    src = _execute_src()
    assert "TrainStatus.RUNNING" in src, "执行器必须把任务置为 RUNNING"

    # 用行号确认顺序：acquire 在前、置 RUNNING 在后
    lines = src.splitlines()
    acq = next(i for i, ln in enumerate(lines) if "gpu_pool.acquire(" in ln)
    running = next(i for i, ln in enumerate(lines) if "TrainStatus.RUNNING" in ln)
    assert acq < running, (
        f"RUNNING 的赋值（第 {running + 1} 行）必须晚于 acquire（第 {acq + 1} 行）："
        "先置 RUNNING 会让排队中的任务显示成运行中")


def test_running_is_not_set_when_acquire_fails():
    """拿不到资源时应判 FAILED 而不是 RUNNING——否则会显示成"运行中"然后失败。"""
    for node in ast.walk(_execute_ast()):
        if isinstance(node, ast.If) and ast.unparse(node.test) == "alloc is None":
            body = ast.unparse(node.body)
            assert "FAILED" in body, "拿不到 GPU 的分支必须置 FAILED"
            assert "RUNNING" not in body, "该分支不应置 RUNNING"
            return
    raise AssertionError("没找到 `if alloc is None` 分支，acquire 失败的处理被改了")


def test_queue_hint_threshold_is_defined():
    """排队超过阈值才提示，避免刚提交就刷一句没信息量的日志。"""
    assert te._QUEUE_HINT_AFTER > 0
    src = _execute_src()
    assert "_QUEUE_HINT_AFTER" in src, "等待时长必须参与判断，否则永远不提示"


def test_wait_hint_reports_busy_count():
    """提示语要说清"排了多久 + 前面有几个人占着卡"，否则用户无从判断该不该等。"""
    src = _execute_src()
    assert "busy_task_count" in src, "排队提示必须带上当前占卡的任务数"
    assert "已排队" in src


def test_executor_source_is_parseable():
    """占位：确保本文件读的是真实实现而不是被移动/删除后的残骸。"""
    assert "async def _execute" in EXECUTOR.read_text(encoding="utf-8")

