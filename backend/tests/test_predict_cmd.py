"""预测命令、GPU 处理与启动守卫测试。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.plugin.module_train import predict_executor as pe
from app.plugin.module_train.model import TrainStatus
from app.plugin.module_train.predict_executor import build_predict_cmd, predict_gpu_id


def test_predict_gpu_id():
    assert predict_gpu_id("cpu") is None
    assert predict_gpu_id("") is None
    assert predict_gpu_id(None) is None
    assert predict_gpu_id("0") == "0"


def test_paddlex_predict_single_dash_o():
    cmd = build_predict_cmd("paddlex", "best_accuracy.pdparams",
                            {"mode": "det", "model_size": "small", "device": "cpu"})
    assert cmd[0] == "bash" and cmd[1] == "-c"
    inner = cmd[2]
    assert inner.count(" -o ") == 1            # 只有一个 -o
    assert "Global.infer_img=/data" in inner
    assert "Global.pretrained_model=/model/best_accuracy.pdparams" in inner
    assert "Global.save_res_path=/output/results.txt" in inner
    assert "Global.output_dir=/output" in inner
    assert "PP-OCRv6_small_det.yml" in inner
    assert "use_gpu=false" in inner            # device=cpu 时不启用 GPU

    cmd_gpu = build_predict_cmd("paddlex", "best_accuracy.pdparams",
                                {"mode": "det", "model_size": "small", "device": "0"})
    assert "use_gpu=true" in cmd_gpu[2]        # 指定 GPU id 时启用 GPU


def test_ultralytics_predict_has_device():
    cmd = build_predict_cmd("ultralytics", "best.pt", {"device": "cpu", "imgsz": 640})
    assert "device=cpu" in cmd


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
