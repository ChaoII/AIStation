"""``TorchKilnExecutor`` 简单模式分派 / 子进程执行 / 孤儿恢复测试（Task 5）。

覆盖（真实走 ``_execute`` 分派与 ``_execute_simple``；仅 patch 子进程、调度器、
导出、权重入库与运行时探测）：

1. ``TORKILN_MODE=simple`` 时 ``_execute`` 走 ``_execute_simple``；
2. ``_execute_simple`` 子进程 argv 正确（含 ``-m torchkiln.simple_run`` / spec
   路径 / ``--task-id`` / ``--repo-root``=submodule 路径 / 回调 URL）；
3. 收敛：returncode=0 + end(finished) → SUCCESS + 调 ``export_model``；
   returncode≠0 或 无 end → FAILED；``release`` 被调用；
4. 孤儿恢复：simple 行 + pid 死 → FAILED；pid 活 + 最近事件 <180s → reattach
   （registry 登记 + 后台任务存在）。

需要应用（``test_client`` 建表/seed），**不要** ``PYTEST_NO_APP=1``。
task_id 用 2000+ 区间，不与 Task 3/4 的 (1)/(900+) 冲突。
"""
import asyncio
import time
from datetime import datetime, timezone

import pytest

from app.config.setting import settings
from app.core.database import async_db_session
from app.plugin.module_train import torchkiln_executor as te
from app.plugin.module_train.gpu_pool.alloc import Allocation
from app.plugin.module_train.model import (
    TrainFramework,
    TrainStatus,
    TrainTask,
    insert_event,
)

_TASK = 2000
_TOKEN = "simple-test-token"


def _run(coro):
    return asyncio.run(coro)


async def _async_none():
    return None


def _async(value):
    async def _inner(*_a, **_k):
        return value

    return _inner


def _alloc(task_id: int, gpu_id: int = 0) -> Allocation:
    return Allocation(task_id=task_id, port=0, gpu_indices=[gpu_id])


@pytest.fixture
def simple_task(test_client, monkeypatch):
    """建一条真实训练任务（framework=TORKILN），并把执行器切到 simple 模式。"""
    monkeypatch.setattr(settings, "TORKILN_MODE", "simple")
    monkeypatch.setattr(settings, "TORKILN_ENABLED", True)
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_CALLBACK_TOKEN", _TOKEN)

    async def _create():
        async with async_db_session() as db:
            task = TrainTask(
                name="simple-exec-test-task",
                framework=TrainFramework.TORKILN,
                dataset_id=1,
                docker_image="torchkiln:0.1.0",
                hyperparams={"model": "yolov8n-det", "params": {"Global.epoch_num": 1}},
            )
            db.add(task)
            await db.commit()
            return task.id

    return _run(_create())


class _FakeProc:
    """可控 returncode 的假子进程。"""

    def __init__(self, returncode=0, pid=4242):
        self.pid = pid
        self.returncode = returncode

    async def wait(self):
        return self.returncode


def _install_spy(monkeypatch, returncode=0, pid=4242):
    """把 ``asyncio.create_subprocess_exec`` 换成记录 argv 的假生成器。"""
    records = {}

    async def _fake_spawn(*args, **kwargs):
        records["args"] = list(args)
        records["kwargs"] = kwargs
        return _FakeProc(returncode=returncode, pid=pid)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_spawn)
    return records


def _patch_simple_runtime(monkeypatch, task_id, *, gpu_id=0):
    """让 simple 执行不依赖真实 torch / 子进程 / 数据导出 / 权重入库。"""
    monkeypatch.setattr(te, "_ensure_torchkiln_runtime", lambda: None)
    monkeypatch.setattr(te, "broadcast_line", _async(None))
    monkeypatch.setattr(te.simple_scheduler, "acquire", _async(_alloc(task_id, gpu_id)))
    monkeypatch.setattr(te.simple_scheduler, "release", _async(None))
    monkeypatch.setattr(te.simple_scheduler, "record_pid", _async(None))
    monkeypatch.setattr(
        te.TorchKilnExecutor, "_export_training_data",
        _async(None))
    monkeypatch.setattr(
        "app.plugin.module_train.exporter.export_model", _async(None))


def _task_status(task_id):
    async def _get():
        async with async_db_session() as db:
            task = await db.get(TrainTask, task_id)
            return task.status
    return _run(_get())


# ---------------------------------------------------------------- 分派
def test_execute_dispatches_to_simple_when_mode_simple(monkeypatch, simple_task):
    """``TORKILN_MODE=simple`` 时 ``_execute`` 必须走 ``_execute_simple``。"""
    called = []
    monkeypatch.setattr(
        te.TorchKilnExecutor, "_execute_simple",
        classmethod(lambda cls, tid: called.append(tid) or _async(None)()))
    _run(te.TorchKilnExecutor._execute(simple_task))
    assert called == [simple_task], "simple 模式应调用 _execute_simple"


def test_execute_container_when_mode_container(monkeypatch, simple_task):
    """``TORKILN_MODE=container`` 时不得调用 ``_execute_simple``。"""
    monkeypatch.setattr(settings, "TORKILN_MODE", "container")
    called = []
    monkeypatch.setattr(
        te.TorchKilnExecutor, "_execute_simple",
        classmethod(lambda cls, tid: called.append(tid)))
    # 容器路径依赖 gpu_pool/容器，这里只验证不进入 simple 分支即算通过：
    # 用 monkeypatch 让数据导出与 gpu_pool.acquire 快速返回
    monkeypatch.setattr(
        te.TorchKilnExecutor, "_export_training_data", _async(None))
    monkeypatch.setattr(te.gpu_pool, "acquire", _async(None))
    monkeypatch.setattr(te, "broadcast_line", _async(None))
    _run(te.TorchKilnExecutor._execute(simple_task))
    assert called == [], "container 模式不应调用 _execute_simple"


# ---------------------------------------------------------------- 子进程 + 收敛
def test_execute_simple_success(monkeypatch, simple_task):
    """returncode=0 + DB 有 end(finished) → SUCCESS + 调 export_model。"""
    records = _install_spy(monkeypatch, returncode=0)
    _patch_simple_runtime(monkeypatch, simple_task)
    monkeypatch.setattr(
        "app.plugin.module_train.exporter.export_model",
        _async({"repo_id": 7, "storage_path": "x"}))

    async def _seed_end():
        async with async_db_session() as db:
            await insert_event(db, simple_task, seq=100, ts=1_700_000_100.0,
                               type_="end", payload={"exit_reason": "finished",
                                                     "epoch": 1, "main_value": 0.5})
    _run(_seed_end())

    _run(te.TorchKilnExecutor._execute_simple(simple_task))

    args = records["args"]
    assert "-m" in args, "argv 应含 -m"
    assert args[args.index("-m") + 1] == "torchkiln.simple_run", "应调用 simple_run 模块"
    idx = args.index("torchkiln.simple_run")
    spec_path = args[idx + 1]
    assert spec_path.lower().endswith("spec.json"), f"simple_run 后应为 spec.json，实际 {spec_path!r}"
    assert args[args.index("--task-id") + 1] == str(simple_task), "argv 应含 --task-id <id>"
    assert "--repo-root" in args, "argv 应含 --repo-root"
    repo = args[args.index("--repo-root") + 1]
    assert repo.endswith("submodules\\torchkiln") or repo.endswith("submodules/torchkiln"), (
        f"--repo-root 应为 submodule 路径，实际 {repo!r}")
    assert "--callback-url" in args and "--token" in args, "argv 应含回调 URL 与 token"

    assert _task_status(simple_task) == TrainStatus.SUCCESS, "应标记 SUCCESS"
    assert records["kwargs"].get("cwd", "").endswith("torchkiln"), "cwd 应为 submodule 目录"


def test_execute_simple_failed_no_end_event(monkeypatch, simple_task):
    """returncode=0 但无 end 事件 → 保守 FAILED（M6 兜底语义）。"""
    _install_spy(monkeypatch, returncode=0)
    _patch_simple_runtime(monkeypatch, simple_task)
    released = []
    monkeypatch.setattr(te.simple_scheduler, "release", _report(released))

    _run(te.TorchKilnExecutor._execute_simple(simple_task))
    assert _task_status(simple_task) == TrainStatus.FAILED, "无终态事件应 FAILED"
    assert simple_task in released, "finally 应调用 release"


def test_execute_simple_failed_bad_returncode(monkeypatch, simple_task):
    """returncode≠0 → FAILED，即使有 end(finished) 也不判成功。"""
    _install_spy(monkeypatch, returncode=1)
    _patch_simple_runtime(monkeypatch, simple_task)

    async def _seed_end():
        async with async_db_session() as db:
            await insert_event(db, simple_task, seq=101, ts=1_700_000_101.0,
                               type_="end", payload={"exit_reason": "finished"})
    _run(_seed_end())

    _run(te.TorchKilnExecutor._execute_simple(simple_task))
    assert _task_status(simple_task) == TrainStatus.FAILED, "returncode≠0 应 FAILED"


# ---------------------------------------------------------------- 孤儿恢复
def _set_running(task_id, hyperparams=None):
    async def _upd():
        async with async_db_session.begin() as db:
            row = await db.get(TrainTask, task_id)
            row.status = TrainStatus.RUNNING
            row.started_at = datetime.now(timezone.utc)
            if hyperparams is not None:
                row.hyperparams = hyperparams
    _run(_upd())


def test_recover_simple_orphan_dead_pid(monkeypatch, simple_task):
    """simple 行 + Redis pid 已死 → 置 FAILED、release。"""
    _set_running(simple_task, hyperparams={"__tk_mode": "simple"})
    monkeypatch.setattr(te.simple_scheduler, "get_entry",
                        _async({"gpu_id": 0, "pid": 99999, "ts": 1.0}))
    monkeypatch.setattr(te, "_pid_alive", lambda pid: False)
    released = []
    monkeypatch.setattr(te.simple_scheduler, "release", _report(released))
    te.TorchKilnExecutor._registry = {}

    _run(te.TorchKilnExecutor.recover_orphans())
    assert _task_status(simple_task) == TrainStatus.FAILED, "pid 已死应置 FAILED"
    assert simple_task in released, "恢复失败应 release"


def test_recover_simple_orphan_alive_reattach(monkeypatch, simple_task):
    """pid 存活 + 最近事件 <180s → registry 登记 + 后台 reattach。"""
    _set_running(simple_task, hyperparams={"__tk_mode": "simple"})
    monkeypatch.setattr(te.simple_scheduler, "get_entry",
                        _async({"gpu_id": 0, "pid": 8888, "ts": 1.0}))
    monkeypatch.setattr(te, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(te.TorchKilnExecutor, "_reattach_simple", _async(None))
    te.TorchKilnExecutor._registry = {}

    async def _seed_env():
        async with async_db_session() as db:
            await insert_event(db, simple_task, seq=1, ts=time.time(),
                               type_="env", payload={"gpu": [{"id": 0}]})
    _run(_seed_env())

    _run(te.TorchKilnExecutor.recover_orphans())
    entry = te.TorchKilnExecutor._registry.get(simple_task)
    assert entry is not None, "存活 simple 任务应登记 registry 让基类跳过"
    assert entry.get("pid") == 8888
    assert "reattach_task" in entry, "应登记后台 reattach 任务"


def _report(lst):
    async def _inner(value, *_a, **_k):
        lst.append(value)
    return _inner
