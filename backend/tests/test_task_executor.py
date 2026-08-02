"""TaskExecutor 基类测试：并发信号量与注册表隔离。"""

from app.plugin.module_train.task_executor import TaskExecutor


class TrainExecutorStub(TaskExecutor):
    name = "train"

    @classmethod
    async def _execute(cls, task_id: int) -> None:
        pass


class EvalExecutorStub(TaskExecutor):
    name = "eval"

    @classmethod
    async def _execute(cls, task_id: int) -> None:
        pass


def test_semaphore_is_class_shared_and_initialized():
    t1, t2 = TrainExecutorStub(), TrainExecutorStub()
    assert t1._get_semaphore() is t2._get_semaphore()


def test_registry_is_per_executor_class():
    t = TrainExecutorStub()
    e = EvalExecutorStub()
    t._registry[1] = {"container_id": "abc"}
    assert 1 not in e._registry
    assert 1 in t._registry
