"""执行器操作测试（不真实跑容器）。

覆盖：
- 容器 label 过滤（find_task_containers）
- 按 label 停容器（stop_task_containers）
- start_training 对 RUNNING 任务的状态守卫（不重复启动）
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.plugin.module_train import docker_utils as du
from app.plugin.module_train import scheduler as sch
from app.plugin.module_train.model import TrainFramework, TrainStatus


class _FakeBegin:
    """模拟 async_sessionmaker.begin() 返回的异步上下文管理器。"""

    def __init__(self, task):
        self._task = task

    async def __aenter__(self):
        task = self._task

        class _Session:
            async def get(self, _model, _tid):
                return task

            async def execute(self, *_a, **_k):
                raise AssertionError("状态守卫应在此之前抛出，不应执行 UPDATE")

        return _Session()

    async def __aexit__(self, *_exc):
        return False


class _FakeSessionMaker:
    def __init__(self, task):
        self._task = task

    def __call__(self):
        # 兼容 start_training 现在的 `async with async_db_session() as db` 用法
        return self.begin()

    def begin(self):
        return _FakeBegin(self._task)


def test_start_training_refuses_running_task(monkeypatch):
    """RUNNING 任务再次 start 应抛出异常且不创建后台任务/不启动容器。"""
    task = SimpleNamespace(
        id=7,
        status=TrainStatus.RUNNING,
        annotation_task_id=None,
        framework=TrainFramework.ULTRALYTICS,
    )
    monkeypatch.setattr(sch, "async_db_session", _FakeSessionMaker(task))

    started = {"container": False}

    async def _fake_run_container(*_a, **_k):
        started["container"] = True
        raise AssertionError("RUNNING 任务不应启动容器")

    monkeypatch.setattr(sch, "run_container", _fake_run_container)
    monkeypatch.setattr(sch.asyncio, "create_task", lambda _coro: started.__setitem__("container", True))

    with pytest.raises(Exception, match="任务正在运行"):
        asyncio.run(sch.start_training(7))
    assert started["container"] is False


class _C:
    def __init__(self, i, labels):
        self.id = i
        self.labels = labels


class _Containers:
    """模拟 Docker daemon：按 label 过滤条件返回匹配容器。"""

    def __init__(self):
        self.all_containers = [
            _C("a", {"aistation.task_kind": "train", "aistation.task_id": "7"}),
            _C("b", {"aistation.task_kind": "eval", "aistation.task_id": "7"}),
            _C("c", {"aistation.task_kind": "train", "aistation.task_id": "8"}),
        ]

    def list(self, all=True, filters=None):
        wanted = (filters or {}).get("label", [])
        if not wanted:
            return list(self.all_containers)

        def _match(c):
            for kv in wanted:
                key, _, val = kv.partition("=")
                if c.labels.get(key) != val:
                    return False
            return True

        return [c for c in self.all_containers if _match(c)]


def test_find_task_containers_filters_by_label(monkeypatch):
    monkeypatch.setattr(du, "client", type("L", (), {"containers": _Containers()})())
    assert du.find_task_containers("train", 7) == ["a"]


def test_stop_task_containers_stops_each_found(monkeypatch):
    monkeypatch.setattr(du, "find_task_containers", lambda _kind, _tid: ["a", "b"])
    stopped: list[str] = []

    async def _fake_stop(cid):
        stopped.append(cid)

    monkeypatch.setattr(du, "stop_container", _fake_stop)
    asyncio.run(du.stop_task_containers("train", 7))
    assert stopped == ["a", "b"]
