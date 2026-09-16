"""重启恢复测试：存活容器判定 + 重连决策。不启动真实容器。"""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.plugin.module_train import docker_utils as du
from app.plugin.module_train import scheduler as sch
from app.plugin.module_train import task_executor as te
from app.plugin.module_train.model import TrainFramework, TrainStatus, TrainTask
from app.plugin.module_train.task_executor import TaskExecutor, recovery_decision


def test_recovery_decision_reattach_when_container_alive():
    now = datetime.now()
    assert recovery_decision(True, now - timedelta(hours=2), now, 1800) == "reattach"


def test_recovery_decision_wait_before_timeout():
    now = datetime.now()
    assert recovery_decision(False, now - timedelta(seconds=30), now, 1800) == "wait"


def test_recovery_decision_fail_after_timeout():
    now = datetime.now()
    assert recovery_decision(False, now - timedelta(hours=2), now, 1800) == "fail"


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _ReadSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)

    async def get(self, _model, row_id):
        for r in self._rows:
            if getattr(r, "id", None) == row_id:
                return r
        return None


class _WriteSession:
    def __init__(self, writes):
        self.writes = writes

    async def execute(self, stmt):
        self.writes.append(stmt)


class _Ctx:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *_exc):
        return False


class _FakeDB:
    """模拟 async_db_session：读取返回固定行，写入记录语句。"""

    def __init__(self, rows):
        self.rows = rows
        self.writes = []

    def __call__(self):
        return _Ctx(_ReadSession(self.rows))

    def begin(self):
        return _Ctx(_WriteSession(self.writes))


class _FakeExecutor(TaskExecutor):
    name = "fake_train"
    task_kind = "train"
    status_enum = TrainStatus
    model_class = TrainTask
    _concurrency = 1
    reattach_calls: list = []

    @classmethod
    async def _execute(cls, task_id):
        return None

    @classmethod
    async def reattach(cls, task_id, container_id=None):
        cls.reattach_calls.append((task_id, container_id))


def _row(task_id, started_at, framework=None):
    return SimpleNamespace(id=task_id, status=TrainStatus.RUNNING, started_at=started_at, framework=framework)


def test_recover_orphans_reattaches_live_container(monkeypatch):
    """存活容器：重连而不是标记失败，也不清理容器。"""
    db = _FakeDB([_row(7, datetime.now() - timedelta(hours=2))])
    monkeypatch.setattr(te, "async_db_session", db)
    monkeypatch.setattr(te, "find_task_containers", lambda _kind, _tid: ["c1"])
    stops: list = []

    async def _stop(kind, tid):
        stops.append((kind, tid))

    monkeypatch.setattr(te, "stop_task_containers", _stop)
    _FakeExecutor.reattach_calls = []
    _FakeExecutor._registry = {}

    async def _main():
        await _FakeExecutor.recover_orphans()
        await asyncio.sleep(0)

    asyncio.run(_main())
    assert _FakeExecutor.reattach_calls == [(7, "c1")]
    assert db.writes == []
    assert stops == []


def test_recover_orphans_waits_without_container_before_timeout(monkeypatch):
    """无存活容器但未超时：保持不动。"""
    db = _FakeDB([_row(8, datetime.now() - timedelta(seconds=30))])
    monkeypatch.setattr(te, "async_db_session", db)
    monkeypatch.setattr(te, "find_task_containers", lambda _kind, _tid: [])
    stops: list = []

    async def _stop(kind, tid):
        stops.append((kind, tid))

    monkeypatch.setattr(te, "stop_task_containers", _stop)
    _FakeExecutor.reattach_calls = []
    _FakeExecutor._registry = {}

    asyncio.run(_FakeExecutor.recover_orphans())
    assert _FakeExecutor.reattach_calls == []
    assert db.writes == []
    assert stops == []


def test_recover_orphans_fails_and_stops_after_timeout_without_container(monkeypatch):
    """无存活容器且超时：标记失败并清理容器。"""
    db = _FakeDB([_row(9, datetime.now() - timedelta(hours=2))])
    monkeypatch.setattr(te, "async_db_session", db)
    monkeypatch.setattr(te, "find_task_containers", lambda _kind, _tid: [])
    stops: list = []

    async def _stop(kind, tid):
        stops.append((kind, tid))

    monkeypatch.setattr(te, "stop_task_containers", _stop)
    _FakeExecutor.reattach_calls = []
    _FakeExecutor._registry = {}

    asyncio.run(_FakeExecutor.recover_orphans())
    assert _FakeExecutor.reattach_calls == []
    assert len(db.writes) == 1
    assert stops == [("train", 9)]


def test_recover_orphans_skips_paddlex_for_base_executor(monkeypatch):
    """基类执行器不处理 PADDLEX 行（由 PaddleX 执行器负责），即使超时也不标记失败。"""
    db = _FakeDB([_row(10, datetime.now() - timedelta(hours=2), framework=TrainFramework.PADDLEX)])
    monkeypatch.setattr(te, "async_db_session", db)
    monkeypatch.setattr(te, "find_task_containers", lambda _kind, _tid: [])
    stops: list = []

    async def _stop(kind, tid):
        stops.append((kind, tid))

    monkeypatch.setattr(te, "stop_task_containers", _stop)
    _FakeExecutor._registry = {}

    asyncio.run(_FakeExecutor.recover_orphans())
    assert db.writes == []
    assert stops == []


def test_find_task_containers_warns_on_error(monkeypatch):
    """Docker 查询异常时必须记录 warning 并返回空列表（不再静默失败）。"""

    class _Bad:
        def list(self, **_kwargs):
            raise RuntimeError("daemon down")

    monkeypatch.setattr(du, "client", SimpleNamespace(containers=_Bad()))
    warnings: list = []
    monkeypatch.setattr(du, "log", SimpleNamespace(warning=lambda msg: warnings.append(msg)))

    assert du.find_task_containers("train", 7) == []
    assert len(warnings) == 1
    assert "train" in warnings[0] and "7" in warnings[0]


class _FakeContainer:
    def __init__(self, cid, status="running"):
        self.id = cid
        self.status = status

    def wait(self, timeout=None):
        return {"StatusCode": 0}


def test_train_executor_reattach_reuses_finalize(monkeypatch):
    """TrainExecutor.reattach 解析 export_dir 后复用 _finalize 收尾，并清理 registry。"""
    container = _FakeContainer("cid-1")
    monkeypatch.setattr(sch, "get_container", lambda _cid: _async(container))
    monkeypatch.setattr(sch, "_build_export_dir", lambda _tid: _async("expdir"))
    monkeypatch.setattr(sch, "broadcast_log", lambda *_a, **_k: _async(None))

    calls: list = []

    async def _fake_finalize(task_id, cont, export_dir, task=None):
        calls.append((task_id, cont, export_dir))

    monkeypatch.setattr(sch.TrainExecutor, "_finalize", _fake_finalize)
    sch.TrainExecutor._registry = {5: {"container_id": "cid-1"}}

    asyncio.run(sch.TrainExecutor.reattach(5, "cid-1"))
    assert calls == [(5, container, "expdir")]
    assert 5 not in sch.TrainExecutor._registry


def test_train_executor_reattach_without_container_does_nothing(monkeypatch):
    """找不到容器时只告警、不调用 _finalize，且早退也要清理 registry（防泄漏）。"""
    monkeypatch.setattr(sch, "find_task_containers", lambda _kind, _tid: [])
    called: list = []

    async def _fake_finalize(*_a, **_k):
        called.append(True)

    warnings: list = []
    monkeypatch.setattr(sch, "log", SimpleNamespace(warning=lambda msg: warnings.append(msg), error=lambda msg: None))
    monkeypatch.setattr(sch.TrainExecutor, "_finalize", _fake_finalize)
    # 预置残留注册表项，模拟 recover_orphans 预种子；早退必须将其移除
    sch.TrainExecutor._registry = {6: {"container_id": "stale"}}

    asyncio.run(sch.TrainExecutor.reattach(6, None))
    assert called == []
    assert warnings and "6" in warnings[0]
    assert 6 not in sch.TrainExecutor._registry


def test_train_executor_reattach_get_container_error_pops_registry(monkeypatch):
    """获取容器抛异常时早退，同样必须清理 registry。"""
    def _boom(_cid):
        raise RuntimeError("daemon down")

    monkeypatch.setattr(sch, "find_task_containers", lambda _kind, _tid: ["cid-x"])
    errors: list = []
    monkeypatch.setattr(
        sch, "log",
        SimpleNamespace(warning=lambda msg: None, error=lambda msg: errors.append(msg)),
    )
    monkeypatch.setattr(sch, "get_container", _boom)
    sch.TrainExecutor._registry = {7: {"container_id": "cid-x"}}

    asyncio.run(sch.TrainExecutor.reattach(7, "cid-x"))
    assert errors and "7" in errors[0]
    assert 7 not in sch.TrainExecutor._registry


async def _async(value):
    return value


def test_recovery_row_routing_between_yolo_and_paddlex():
    """PaddleX 行只由 PaddleXOCR* 恢复；YOLO 行只由 TrainExecutor 恢复。"""
    from app.plugin.module_train.paddlex_executor import PaddleXOCRDetExecutor
    from app.plugin.module_train.scheduler import TrainExecutor

    paddlex_row = SimpleNamespace(id=1, framework=TrainFramework.PADDLEX)
    yolo_row = SimpleNamespace(id=2, framework=TrainFramework.ULTRALYTICS)

    assert PaddleXOCRDetExecutor._recover_row_applies(paddlex_row) is True
    assert PaddleXOCRDetExecutor._recover_row_applies(yolo_row) is False
    assert TrainExecutor._recover_row_applies(paddlex_row) is False
    assert TrainExecutor._recover_row_applies(yolo_row) is True


class _UnsupportedExecutor(TaskExecutor):
    """未实现 reattach 的执行器（如 Eval / Predict / PaddleX）：走基类默认行为。"""

    name = "fake_unsupported"
    task_kind = "eval"
    status_enum = TrainStatus
    model_class = TrainTask
    _concurrency = 1

    @classmethod
    async def _execute(cls, task_id):
        return None


def test_base_reattach_marks_failed_and_pops_registry(monkeypatch):
    """不支持的框架：基类 reattach 把 RUNNING 行落到 FAILED 并清理 registry。"""
    db = _FakeDB([_row(21, datetime.now())])
    monkeypatch.setattr(te, "async_db_session", db)
    container = _FakeContainer("cid-21")  # 默认 status="running"，覆盖等待退出路径
    monkeypatch.setattr(te, "get_container", lambda _cid: _async(container))
    removed: list = []

    async def _remove(cid):
        removed.append(cid)

    monkeypatch.setattr(te, "remove_container", _remove)
    _UnsupportedExecutor._registry = {21: {"container_id": "cid-21"}}

    asyncio.run(_UnsupportedExecutor.reattach(21, "cid-21"))

    assert 21 not in _UnsupportedExecutor._registry
    assert len(db.writes) == 1
    assert removed == ["cid-21"]


def test_base_reattach_resolves_exited_container_to_failed(monkeypatch):
    """容器已退出：基类 reattach 同样标记 FAILED 并移除容器。"""
    db = _FakeDB([_row(22, datetime.now())])
    monkeypatch.setattr(te, "async_db_session", db)
    container = _FakeContainer("cid-22", status="exited")
    monkeypatch.setattr(te, "get_container", lambda _cid: _async(container))
    removed: list = []

    async def _remove(cid):
        removed.append(cid)

    monkeypatch.setattr(te, "remove_container", _remove)
    _UnsupportedExecutor._registry = {22: {"container_id": "cid-22"}}

    asyncio.run(_UnsupportedExecutor.reattach(22, "cid-22"))

    assert 22 not in _UnsupportedExecutor._registry
    assert len(db.writes) == 1
    assert removed == ["cid-22"]


def test_base_reattach_skips_task_not_running(monkeypatch):
    """任务已不在 RUNNING：基类 reattach 不改状态，但仍清理 registry。"""
    row = _row(23, datetime.now())
    row.status = TrainStatus.SUCCESS
    db = _FakeDB([row])
    monkeypatch.setattr(te, "async_db_session", db)
    monkeypatch.setattr(te, "get_container", lambda _cid: _async(_FakeContainer("cid-23")))
    removed: list = []

    async def _remove(cid):
        removed.append(cid)

    monkeypatch.setattr(te, "remove_container", _remove)
    _UnsupportedExecutor._registry = {23: {"container_id": "cid-23"}}

    asyncio.run(_UnsupportedExecutor.reattach(23, "cid-23"))

    assert 23 not in _UnsupportedExecutor._registry
    assert db.writes == []
    assert removed == []


def test_base_reattach_stops_leftover_container_when_fetch_fails(monkeypatch):
    """拿不到容器（返回 None）时，落失败前先按 label 停止残留容器。"""
    db = _FakeDB([_row(24, datetime.now())])
    monkeypatch.setattr(te, "async_db_session", db)
    monkeypatch.setattr(te, "get_container", lambda _cid: _async(None))
    stopped: list = []
    removed: list = []

    async def _stop(kind, tid):
        stopped.append((kind, tid))

    async def _remove(cid):
        removed.append(cid)

    monkeypatch.setattr(te, "stop_task_containers", _stop)
    monkeypatch.setattr(te, "remove_container", _remove)
    _UnsupportedExecutor._registry = {24: {"container_id": "cid-24"}}

    asyncio.run(_UnsupportedExecutor.reattach(24, "cid-24"))

    assert stopped == [("eval", 24)]
    assert 24 not in _UnsupportedExecutor._registry
    assert len(db.writes) == 1
    assert removed == []


class _SequencedDB:
    """按读取次序返回不同行的会话，用于模拟并发取消后的二次读取。"""

    def __init__(self, rows):
        self._rows = list(rows)
        self.writes = []
        self._read_count = 0

    def __call__(self):
        idx = min(self._read_count, len(self._rows) - 1)
        self._read_count += 1
        return _Ctx(_ReadSession([self._rows[idx]]))

    def begin(self):
        return _Ctx(_WriteSession(self.writes))


def test_base_reattach_does_not_clobber_concurrent_cancel(monkeypatch):
    """写终态前二次读取发现已被取消：不覆盖状态，但清理容器与 registry。"""
    running = _row(25, datetime.now())
    cancelled = _row(25, datetime.now())
    cancelled.status = TrainStatus.CANCELLED
    db = _SequencedDB([running, cancelled])
    monkeypatch.setattr(te, "async_db_session", db)
    container = _FakeContainer("cid-25")
    monkeypatch.setattr(te, "get_container", lambda _cid: _async(container))
    removed: list = []

    async def _remove(cid):
        removed.append(cid)

    monkeypatch.setattr(te, "remove_container", _remove)
    _UnsupportedExecutor._registry = {25: {"container_id": "cid-25"}}

    asyncio.run(_UnsupportedExecutor.reattach(25, "cid-25"))

    assert db.writes == []
    assert 25 not in _UnsupportedExecutor._registry
    assert removed == ["cid-25"]
