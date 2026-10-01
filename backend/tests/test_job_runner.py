"""一次性容器作业骨架（``job_runner``）的行为测试。

为什么单独测这个模块
------------------
``eval_scheduler`` 与 ``predict_executor`` 原本各写一遍「起一次性容器跑命令」的完整
流程（申请 GPU → 起容器 → 跟日志 → 等退出 → 按退出码收尾 → 清理）。两份实现逐行
对应，只有「成功时要落什么字段」不同，而**这份重复已经付出过代价**：预测的结果收集
逻辑曾漂移成「找到文件后反而只去看 ``exp/``」，结果落在别处时静默返回空。

所以这里钉住三态收尾的判定顺序与副作用——那是最容易在改动中被破坏、又最难靠肉眼
发现的部分。
"""

import asyncio

import pytest

from app.plugin.module_train import job_runner as jr
from app.plugin.module_train.job_runner import (
    JobCancelled,
    JobOutcome,
    cancelled,
    cleanup_registry,
    mark_failed,
    needed_gpu_memory,
    settle,
)
from app.plugin.module_train.model import TrainStatus

# ---------------------------------------------------------------------------
# 假执行器：只实现 settle / run_and_follow / cleanup_registry 真正用到的那几个方法
# ---------------------------------------------------------------------------


class _FakeExecutor:
    """记录每次 ``_mark_status`` 的调用，并保存 registry。"""

    name = "fake"
    task_kind = "fake"
    _registry: dict = {}

    def __init__(self):
        self._registry = {}
        self.marks: list[tuple[int, TrainStatus, dict]] = []

    async def _mark_status(self, job_id, status, **fields):
        self.marks.append((job_id, status, fields))

    async def follow_logs(self, *_a, **_k):
        return []

    async def _get_exit_code(self, _container):
        return 0


# ---------------------------------------------------------------------------
# needed_gpu_memory
# ---------------------------------------------------------------------------


def test_needed_gpu_memory_from_hyperparams():
    assert needed_gpu_memory({"resources": {"gpu_memory_gb": 12}}) == 12.0
    assert needed_gpu_memory({"resources": {"gpu_memory_gb": "8"}}) == 8.0


def test_needed_gpu_memory_falls_back_to_global_min(monkeypatch):
    """没填就退回全局最小空闲阈值——不能返回 0（0 意味着什么卡都能占）。"""
    monkeypatch.setattr(jr.settings, "TORKILN_GPU_MIN_FREE_GB", 6.5)
    assert needed_gpu_memory({}) == 6.5
    assert needed_gpu_memory(None) == 6.5
    assert needed_gpu_memory({"resources": {}}) == 6.5


def test_needed_gpu_memory_zero_falls_back(monkeypatch):
    """``0`` 是falsy，必须回退；否则会向 gpu_pool 要一块「不需要显存」的卡。"""
    monkeypatch.setattr(jr.settings, "TORKILN_GPU_MIN_FREE_GB", 4.0)
    assert needed_gpu_memory({"resources": {"gpu_memory_gb": 0}}) == 4.0


# ---------------------------------------------------------------------------
# cancelled
# ---------------------------------------------------------------------------


def test_cancelled_reads_registry():
    ex = _FakeExecutor()
    assert cancelled(ex, 1) is False
    ex._registry[1] = {"cancel": True}
    assert cancelled(ex, 1) is True
    ex._registry[1] = {"container_id": "abc"}
    assert cancelled(ex, 1) is False


def test_cancelled_missing_job_is_false():
    """job 没进 registry 时不能当成已取消（否则首帧就被拦下）。"""
    assert cancelled(_FakeExecutor(), 999) is False


# ---------------------------------------------------------------------------
# settle：三态收尾
# ---------------------------------------------------------------------------


def test_settle_cancelled_only_marks_status():
    """取消：只改状态，不写任何成功/失败字段。"""
    ex = _FakeExecutor()
    asyncio.run(settle(ex, 7, was_cancelled=True, container_id="c1",
                       exit_code=0, success_fields={"metrics": {"a": 1}}))

    _job, status, fields = ex.marks[0]
    assert status == TrainStatus.CANCELLED
    assert fields["progress"] == 100
    assert "metrics" not in fields, "取消时不该把成功字段写进去"


def test_settle_cancelled_wins_over_success_exit_code():
    """退出码 0 但用户已取消 → 必须是 CANCELLED，不能记成功。"""
    ex = _FakeExecutor()
    asyncio.run(settle(ex, 7, was_cancelled=True, container_id=None, exit_code=0))
    assert ex.marks[0][1] == TrainStatus.CANCELLED


def test_settle_success_writes_success_fields():
    ex = _FakeExecutor()
    asyncio.run(settle(ex, 7, was_cancelled=False, container_id="c1", exit_code=0,
                       success_fields={"metrics": {"box_mAP50": 0.9}}))

    _job, status, fields = ex.marks[0]
    assert status == TrainStatus.SUCCESS
    assert fields["metrics"] == {"box_mAP50": 0.9}
    assert fields["progress"] == 100


def test_settle_success_without_success_fields():
    """没有成功字段也要能收尾（不能因为缺参数崩在收尾阶段）。"""
    ex = _FakeExecutor()
    asyncio.run(settle(ex, 7, was_cancelled=False, container_id=None, exit_code=0))
    assert ex.marks[0][1] == TrainStatus.SUCCESS


def test_settle_failure_uses_error_tail():
    """失败：容器尾日志写进 log 与 error_log（前端弹错误提示的依据）。"""
    ex = _FakeExecutor()
    asyncio.run(settle(ex, 7, was_cancelled=False, container_id="c1", exit_code=1,
                       error_tail="CUDA out of memory"))

    _job, status, fields = ex.marks[0]
    assert status == TrainStatus.FAILED
    assert fields["log"] == "CUDA out of memory"
    assert fields["error_log"] == "CUDA out of memory"
    assert fields["progress"] == 100


def test_settle_failure_falls_back_to_message():
    """取不到容器尾日志时退回给定文案，不能写空串。"""
    ex = _FakeExecutor()
    asyncio.run(settle(ex, 7, was_cancelled=False, container_id=None, exit_code=137,
                       error_tail="", failure_message="eval failed"))
    assert ex.marks[0][2]["error_log"] == "eval failed"


def test_settle_none_exit_code_is_failure():
    """``exit_code=None``（等待超时等）算失败，不能当成功。"""
    ex = _FakeExecutor()
    asyncio.run(settle(ex, 7, was_cancelled=False, container_id=None, exit_code=None))
    assert ex.marks[0][1] == TrainStatus.FAILED


# ---------------------------------------------------------------------------
# cleanup_registry
# ---------------------------------------------------------------------------


def test_cleanup_registry_pops_and_removes():
    """registry 必须清掉——残留会让 recover_orphans 永久跳过该行。"""
    ex = _FakeExecutor()
    ex._registry[3] = {"container_id": "c9"}
    asyncio.run(cleanup_registry(ex, 3, "c9"))
    assert 3 not in ex._registry


def test_cleanup_registry_tolerates_missing():
    """没有 container_id（容器从未起来）时也不能抛。"""
    ex = _FakeExecutor()
    asyncio.run(cleanup_registry(ex, 3, None))


# ---------------------------------------------------------------------------
# mark_failed
# ---------------------------------------------------------------------------


def test_mark_failed_records_exception_text():
    ex = _FakeExecutor()
    asyncio.run(mark_failed(ex, 5, RuntimeError("boom"), kind="eval"))

    _job, status, fields = ex.marks[0]
    assert status == TrainStatus.FAILED
    assert fields["log"] == "boom"


# ---------------------------------------------------------------------------
# JobOutcome / JobCancelled
# ---------------------------------------------------------------------------


def test_job_outcome_defaults():
    o = JobOutcome()
    assert (o.exit_code, o.container_id, o.error_tail) == (None, None, "")


def test_job_cancelled_is_exception_but_not_base_exception_only():
    """必须是 ``Exception`` 的子类（能被 except Exception 抓到），
    同时语义上区别于普通失败。"""
    assert issubclass(JobCancelled, Exception)
    assert not issubclass(JobCancelled, SystemExit)


def test_gpu_slot_raises_when_cancelled_before_start(monkeypatch):
    """等待GPU 期间被取消 → 抛 JobCancelled，调用方据此跳过收尾而不是记失败。"""
    import contextlib

    class _FakeLease:
        device_ids = ["GPU-x"]

    @contextlib.asynccontextmanager
    async def _fake_gpu_lease(_job_id, _mem):
        yield _FakeLease()

    @contextlib.asynccontextmanager
    async def _fake_semaphore():
        yield 1

    ex = _FakeExecutor()
    ex._registry[4] = {"cancel": True}

    monkeypatch.setattr(jr, "gpu_lease", _fake_gpu_lease)
    monkeypatch.setattr(jr, "get_train_semaphore", _fake_semaphore)

    async def _go():
        async with jr.gpu_slot(ex, 4, {}):
            raise AssertionError("不该进入 with 体")

    with pytest.raises(JobCancelled):
        asyncio.run(_go())


def test_gpu_slot_yields_lease_when_not_cancelled(monkeypatch):
    """没被取消：正常拿到租约。"""
    import contextlib

    class _FakeLease:
        device_ids = ["GPU-y"]

    @contextlib.asynccontextmanager
    async def _fake_gpu_lease(_job_id, _mem):
        yield _FakeLease()

    @contextlib.asynccontextmanager
    async def _fake_semaphore():
        yield 1

    ex = _FakeExecutor()
    monkeypatch.setattr(jr, "gpu_lease", _fake_gpu_lease)
    monkeypatch.setattr(jr, "get_train_semaphore", _fake_semaphore)

    async def _go():
        async with jr.gpu_slot(ex, 4, {}) as lease:
            return lease.device_ids

    assert asyncio.run(_go()) == ["GPU-y"]
