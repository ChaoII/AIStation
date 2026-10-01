"""预测的启动守卫测试。

⚠️ 这里曾有一个 ``test_predict_cmd.py`` 名字对、实际零覆盖的教训：该文件 import
``build_predict_cmd`` 却从没测它，于是命令拼错（照 ``tkiln val`` 的样式拼
``-o Global.pretrained_model=``）在容器里被 argparse 直接拒绝，长期无人察觉。
命令构造的测试现在在 TorchKiln 侧 ``tests/test_service_predict_jobs.py``
（那里才是拼命令的地方）；平台侧只保留**接缝**的测试。
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.plugin.module_train import predict_executor as pe
from app.plugin.module_train.model import TrainStatus


class _FakeResult:
    """模拟 UPDATE 结果：只暴露 rowcount。"""

    def __init__(self, rowcount):
        self.rowcount = rowcount


class _FakeSession:
    """模拟 ORM 会话：execute 返回固定 rowcount，get 返回固定行。"""

    def __init__(self, rowcount, row):
        self._rowcount = rowcount
        self._row = row
        self.executed = 0
        self.get_calls = 0

    async def execute(self, _stmt):
        self.executed += 1
        return _FakeResult(self._rowcount)

    async def get(self, _model, _row_id):
        self.get_calls += 1
        return self._row


class _FakeCtx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_exc):
        return False


class _FakeSessionMaker:
    def __init__(self, rowcount, row):
        self.session = _FakeSession(rowcount, row)

    def begin(self):
        return _FakeCtx(self.session)


def _patch_enqueue(monkeypatch, calls):
    """拦截 asyncio.create_task，记录并关闭协程（避免未 await 警告）。"""

    def _create_task(coro):
        calls.append(coro)
        close = getattr(coro, "close", None)
        if close:
            close()
        return None

    monkeypatch.setattr(pe.asyncio, "create_task", _create_task)


def test_start_prediction_refuses_running(monkeypatch):
    """已在运行：抛异常且不入队第二次运行。"""
    row = SimpleNamespace(id=5, status=TrainStatus.RUNNING)
    monkeypatch.setattr(pe, "async_db_session", _FakeSessionMaker(rowcount=0, row=row))
    enqueued: list = []
    _patch_enqueue(monkeypatch, enqueued)

    with pytest.raises(Exception, match="预测任务正在运行"):
        asyncio.run(pe.start_prediction(5))
    assert enqueued == []


def test_start_prediction_atomic_guard_loses_race(monkeypatch):
    """TOCTOU：读到的状态已过期（非 RUNNING），但条件 UPDATE 影响 0 行 → 必须拒绝。"""
    stale = SimpleNamespace(id=5, status=TrainStatus.PENDING)
    monkeypatch.setattr(pe, "async_db_session", _FakeSessionMaker(rowcount=0, row=stale))
    enqueued: list = []
    _patch_enqueue(monkeypatch, enqueued)

    with pytest.raises(Exception, match="预测任务正在运行"):
        asyncio.run(pe.start_prediction(5))
    assert enqueued == []


def test_start_prediction_not_found(monkeypatch):
    """行不存在：抛异常且不入队。"""
    monkeypatch.setattr(pe, "async_db_session", _FakeSessionMaker(rowcount=0, row=None))
    enqueued: list = []
    _patch_enqueue(monkeypatch, enqueued)

    with pytest.raises(Exception, match="预测任务 5 不存在"):
        asyncio.run(pe.start_prediction(5))
    assert enqueued == []


def test_start_prediction_success_enqueues_once(monkeypatch):
    """条件 UPDATE 抢占成功（rowcount=1）：恰好入队一次。"""
    maker = _FakeSessionMaker(rowcount=1, row=None)
    monkeypatch.setattr(pe, "async_db_session", maker)
    enqueued: list = []
    _patch_enqueue(monkeypatch, enqueued)

    asyncio.run(pe.start_prediction(5))
    assert maker.session.executed == 1
    assert len(enqueued) == 1
