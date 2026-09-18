"""训练/评估/部署原子判重、导出批量查询与 tempdir 鉴权测试。

- start_evaluation：条件 UPDATE + rowcount 守卫，避免并发重复启动；
- start_training / start_deployment：原子判重；
- 导出不再逐图查询（IN 批量）；
- /train/system/tempdir 需鉴权。
"""

import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.plugin.module_train import deploy_executor as de
from app.plugin.module_train import eval_scheduler as es
from app.plugin.module_train import exporter, scheduler
from app.plugin.module_train.model import TrainStatus

# ---------------------------------------------------------------------------
# start_evaluation 原子守卫
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _FakeSession:
    def __init__(self, rowcount, row):
        self._rowcount = rowcount
        self._row = row
        self.executed = 0

    async def execute(self, _stmt):
        self.executed += 1
        return _FakeResult(self._rowcount)

    async def get(self, _model, _row_id):
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


def _patch_enqueue(monkeypatch, module, calls):
    """拦截 asyncio.create_task，记录并关闭协程（避免未 await 警告）。"""

    def _create_task(coro):
        calls.append(coro)
        close = getattr(coro, "close", None)
        if close:
            close()
        return None

    monkeypatch.setattr(module.asyncio, "create_task", _create_task)


def test_start_evaluation_refuses_running(monkeypatch):
    """已运行：抛异常且不入队第二次运行。"""
    row = SimpleNamespace(id=5, status=TrainStatus.RUNNING)
    monkeypatch.setattr(es, "async_db_session", _FakeSessionMaker(rowcount=0, row=row))
    enqueued: list = []
    _patch_enqueue(monkeypatch, es, enqueued)

    with pytest.raises(Exception, match="评估任务正在运行"):
        asyncio.run(es.start_evaluation(5))
    assert enqueued == []


def test_start_evaluation_atomic_guard_loses_race(monkeypatch):
    """TOCTOU：读到的状态过期（非 RUNNING），但条件 UPDATE 影响 0 行 → 拒绝。"""
    stale = SimpleNamespace(id=5, status=TrainStatus.PENDING)
    monkeypatch.setattr(es, "async_db_session", _FakeSessionMaker(rowcount=0, row=stale))
    enqueued: list = []
    _patch_enqueue(monkeypatch, es, enqueued)

    with pytest.raises(Exception, match="评估任务正在运行"):
        asyncio.run(es.start_evaluation(5))
    assert enqueued == []


def test_start_evaluation_not_found(monkeypatch):
    """行不存在：抛异常且不入队。"""
    monkeypatch.setattr(es, "async_db_session", _FakeSessionMaker(rowcount=0, row=None))
    enqueued: list = []
    _patch_enqueue(monkeypatch, es, enqueued)

    with pytest.raises(Exception, match="评估任务 5 不存在"):
        asyncio.run(es.start_evaluation(5))
    assert enqueued == []


def test_start_evaluation_success_enqueues_once(monkeypatch):
    """条件 UPDATE 抢占成功（rowcount=1）：恰好入队一次。"""
    maker = _FakeSessionMaker(rowcount=1, row=None)
    monkeypatch.setattr(es, "async_db_session", maker)
    enqueued: list = []
    _patch_enqueue(monkeypatch, es, enqueued)

    asyncio.run(es.start_evaluation(5))
    assert maker.session.executed == 1
    assert len(enqueued) == 1


# ---------------------------------------------------------------------------
# start_training 原子判重
# ---------------------------------------------------------------------------

class _ReadSession:
    def __init__(self, row):
        self._row = row

    async def execute(self, _stmt):
        return _FakeResult(0)

    async def get(self, _model, _row_id):
        return self._row


class _WriteSession:
    def __init__(self, rowcount):
        self._rowcount = rowcount
        self.executed = 0

    async def execute(self, _stmt):
        self.executed += 1
        return _FakeResult(self._rowcount)

    async def get(self, _model, _row_id):
        return None


class _TrainDB:
    """支持 __call__（读）与 begin()（写）两种会话。"""

    def __init__(self, row, rowcount):
        self._row = row
        self._rowcount = rowcount
        self.write_session = _WriteSession(rowcount)

    def __call__(self):
        return _FakeCtx(_ReadSession(self._row))

    def begin(self):
        return _FakeCtx(self.write_session)


def test_start_training_refuses_running(monkeypatch):
    row = SimpleNamespace(id=7, status=TrainStatus.RUNNING, framework="ultralytics", annotation_task_id=None)
    monkeypatch.setattr(scheduler, "async_db_session", _TrainDB(row, rowcount=0))
    enqueued: list = []
    _patch_enqueue(monkeypatch, scheduler, enqueued)

    with pytest.raises(Exception, match="任务正在运行"):
        asyncio.run(scheduler.start_training(7))
    assert enqueued == []


def test_start_training_atomic_guard_loses_race(monkeypatch):
    """读到的状态非 RUNNING，但条件 UPDATE 影响 0 行 → 拒绝。"""
    row = SimpleNamespace(id=7, status=TrainStatus.PENDING, framework="ultralytics", annotation_task_id=None)
    monkeypatch.setattr(scheduler, "async_db_session", _TrainDB(row, rowcount=0))
    enqueued: list = []
    _patch_enqueue(monkeypatch, scheduler, enqueued)

    with pytest.raises(Exception, match="任务正在运行"):
        asyncio.run(scheduler.start_training(7))
    assert enqueued == []


def test_start_training_not_found(monkeypatch):
    monkeypatch.setattr(scheduler, "async_db_session", _TrainDB(None, rowcount=0))
    enqueued: list = []
    _patch_enqueue(monkeypatch, scheduler, enqueued)

    with pytest.raises(Exception, match="训练任务 7 不存在"):
        asyncio.run(scheduler.start_training(7))
    assert enqueued == []


def test_start_training_success_enqueues_once(monkeypatch):
    """原子抢占成功：恰好入队一次。"""
    row = SimpleNamespace(id=7, status=TrainStatus.PENDING, framework="ultralytics", annotation_task_id=None)
    db = _TrainDB(row, rowcount=1)
    monkeypatch.setattr(scheduler, "async_db_session", db)
    enqueued: list = []
    _patch_enqueue(monkeypatch, scheduler, enqueued)

    asyncio.run(scheduler.start_training(7))
    assert db.write_session.executed == 1
    assert len(enqueued) == 1


# ---------------------------------------------------------------------------
# start_deployment 原子判重
# ---------------------------------------------------------------------------

def test_start_deployment_refuses_running(monkeypatch):
    """已 deploying/running：条件 UPDATE 影响 0 行 → 不执行。"""
    monkeypatch.setattr(de, "async_db_session", _DeployDB(rowcount=0))
    calls: list = []

    async def _noop(_id):
        calls.append(_id)

    monkeypatch.setattr(de, "_execute_deployment", _noop)
    _patch_enqueue(monkeypatch, de, calls)

    asyncio.run(de.start_deployment(3))
    assert calls == []


def test_start_deployment_success_spawns_once(monkeypatch):
    """原子抢占成功（rowcount=1）：恰好执行一次。"""
    monkeypatch.setattr(de, "async_db_session", _DeployDB(rowcount=1))
    calls: list = []
    _patch_enqueue(monkeypatch, de, calls)

    asyncio.run(de.start_deployment(3))
    assert len(calls) == 1


class _DeployWriteSession:
    def __init__(self, rowcount):
        self._rowcount = rowcount

    async def execute(self, stmt):
        return _FakeResult(self._rowcount)


class _DeployDB:
    def __init__(self, rowcount):
        self._rowcount = rowcount

    def begin(self):
        return _FakeCtx(_DeployWriteSession(self._rowcount))

    def __call__(self):
        return _FakeCtx(_DeployWriteSession(self._rowcount))


# ---------------------------------------------------------------------------
# 导出批量查询（不再逐图 N+1）
# ---------------------------------------------------------------------------

class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _CountSession:
    """计数 AnnotationRecordModel 查询次数，其余返回空。"""

    def __init__(self):
        self.annotation_queries = 0

    async def execute(self, stmt):
        desc = getattr(stmt, "column_descriptions", None) or []
        entity = desc[0].get("entity") if desc else None
        if entity is not None and entity.__name__ == "AnnotationRecordModel":
            self.annotation_queries += 1
        return SimpleNamespace(
            scalars=lambda: _FakeScalars([]), scalar_one_or_none=lambda: None
        )


class _CountDb:
    def __init__(self):
        self.session = _CountSession()

    def __call__(self):
        return _FakeCtx(self.session)


class _FakeS3:
    def download_fileobj(self, key):
        return SimpleNamespace(read=lambda: b"img-bytes")


def _images(n):
    return [
        SimpleNamespace(id=i, filename=f"img_{i}.jpg", object_key=f"k{i}", width=100, height=100)
        for i in range(1, n + 1)
    ]


def test_export_yolo_batches_annotation_query(monkeypatch, tmp_path):
    """导出 N 张图只应发 1 次 AnnotationRecordModel 查询（IN 批量），而非逐图 N 次。"""
    db = _CountDb()
    monkeypatch.setattr(exporter, "async_db_session", db)
    with patch("app.utils.s3_client.s3_client", _FakeS3()):
        asyncio.run(exporter._export_yolo(
            1, 1, _images(5), str(tmp_path / "out"), task_type="detection",
        ))
    assert db.session.annotation_queries == 1


# ---------------------------------------------------------------------------
# tempdir 接口需鉴权
# ---------------------------------------------------------------------------

def test_tempdir_endpoint_requires_auth():
    """/train/system/tempdir 必须挂 AuthPermission（module_train:model:query）。"""
    from app.plugin.module_train import controller
    src = inspect.getsource(controller.get_tempdir)
    assert "Depends(AuthPermission" in src
    assert "module_train:model:query" in src
