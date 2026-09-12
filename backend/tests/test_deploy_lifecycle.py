"""部署生命周期决策测试：退出状态、端口复用、停止兜底、孤儿重建。

不启动真实容器：仅测试纯函数，以及用假会话 / monkeypatch 验证生命周期决策。
"""

import asyncio
from types import SimpleNamespace

from app.plugin.module_train import deploy_executor as de
from app.plugin.module_train.deploy_executor import deploy_exit_status, is_port_reusable


def test_deploy_exit_status():
    assert deploy_exit_status(cancel=True, exit_code=0) is None
    assert deploy_exit_status(cancel=False, exit_code=0) == "stopped"
    assert deploy_exit_status(cancel=False, exit_code=137) == "failed"


def test_is_port_reusable():
    assert is_port_reusable("stopped") is True
    assert is_port_reusable("failed") is True
    assert is_port_reusable("pending") is True
    assert is_port_reusable("running") is False
    assert is_port_reusable("deploying") is False


async def _async(value):
    return value


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


def test_stop_deployment_uses_db_container_id_when_registry_empty(monkeypatch):
    """内存注册表丢失（后端重启）后，stop 应从 DB 读 container_id 停真实容器。"""
    row = SimpleNamespace(id=3, container_id="cid-db", status="running")
    db = _FakeDB([row])
    monkeypatch.setattr(de, "async_db_session", db)
    stopped: list = []

    async def _stop(cid):
        stopped.append(cid)

    monkeypatch.setattr(de, "stop_container", _stop)
    de._deploy_running.clear()

    asyncio.run(de.stop_deployment(3))

    assert stopped == ["cid-db"]
    assert len(db.writes) == 1


def test_stop_deployment_falls_back_to_label_lookup(monkeypatch):
    """DB 也没有 container_id 时，按 label 查找残留容器并停掉。"""
    row = SimpleNamespace(id=4, container_id=None, status="running")
    db = _FakeDB([row])
    monkeypatch.setattr(de, "async_db_session", db)
    monkeypatch.setattr(de, "find_task_containers", lambda _kind, _tid: ["cid-label"])
    stopped: list = []

    async def _stop(cid):
        stopped.append(cid)

    monkeypatch.setattr(de, "stop_container", _stop)
    de._deploy_running.clear()

    asyncio.run(de.stop_deployment(4))

    assert stopped == ["cid-label"]
    assert len(db.writes) == 1


def test_stop_deployment_stops_registry_container(monkeypatch):
    """注册表有 entry 时直接停容器并置 cancel。"""
    row = SimpleNamespace(id=5, container_id=None, status="running")
    db = _FakeDB([row])
    monkeypatch.setattr(de, "async_db_session", db)
    stopped: list = []

    async def _stop(cid):
        stopped.append(cid)

    monkeypatch.setattr(de, "stop_container", _stop)
    de._deploy_running.clear()
    de._deploy_running[5] = {"container_id": "cid-mem", "cancel": False}

    asyncio.run(de.stop_deployment(5))

    assert stopped == ["cid-mem"]
    assert 5 not in de._deploy_running


def test_recover_orphan_rehydrates_live_container(monkeypatch):
    """存活容器：重建内存注册表（便于之后 stop），不改状态。"""
    row = SimpleNamespace(id=11, status="running", container_id="cid-11")
    db = _FakeDB([row])
    monkeypatch.setattr(de, "async_db_session", db)
    monkeypatch.setattr(de, "_container_exists", lambda _cid: _async(True))
    de._deploy_running.clear()

    asyncio.run(de.recover_orphan_deploys())

    assert de._deploy_running[11]["container_id"] == "cid-11"
    assert de._deploy_running[11]["cancel"] is False
    assert db.writes == []


def test_recover_orphan_marks_failed_when_container_missing(monkeypatch):
    """容器确认不存在：标记 failed 并清理。"""
    row = SimpleNamespace(id=12, status="deploying", container_id="cid-12")
    db = _FakeDB([row])
    monkeypatch.setattr(de, "async_db_session", db)
    monkeypatch.setattr(de, "_container_exists", lambda _cid: _async(False))
    de._deploy_running.clear()

    asyncio.run(de.recover_orphan_deploys())

    assert 12 not in de._deploy_running
    assert len(db.writes) == 1
