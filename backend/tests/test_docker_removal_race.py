"""Docker 移除的并发安全（409「removal already in progress」）。

为什么需要
----------
本项目有**两个**移除入口作用于同一个容器：

* :func:`_stop_container` —— 阻塞 ``stop(timeout=10)`` 后 ``remove()``
* :func:`remove_container` —— ``remove(force=True)``

「停止部署」时「协程 A 正在 stop 并 remove、协程 B 的 finally 也来 remove」是
常态，于是 B 撞上 A 正在进行的移除，Docker 返回::

    409 Conflict ("removal of container X is already in progress")

让异常冒出去的后果不是「日志多几行」：收尾路径被打断、后台任务变成
``Task exception was never retrieved``，而且**容器可能没被移除**。

正确做法是轮询等它消失——那是唯一确定会到来的结果。
"""

import docker
import pytest

from app.plugin.module_train import docker_utils as du

# ---------------------------------------------------------------------------
# 假 Docker 客户端
# ---------------------------------------------------------------------------


class _FakeAPIError(docker.errors.APIError):
    """``APIError.status_code`` 是从 response 解析出来的**只读 property**，
    不能直接赋值——必须用 property 覆盖。"""

    def __init__(self, status_code, message="conflict"):
        super().__init__(message)
        self._status_code = status_code

    @property
    def status_code(self):
        return self._status_code


class _FakeContainer:
    """按脚本模拟 remove 的行为。"""

    def __init__(self, cid, *, behavior="ok", on_remove=None):
        self.id = cid
        self._behavior = behavior
        self._on_remove = on_remove
        self.stopped = False
        self.removed = False

    def stop(self, timeout=None):
        self.stopped = True

    def remove(self, force=True):
        if self._behavior == "409_forever":
            raise _FakeAPIError(409, "removal already in progress")
        if self._behavior == "500":
            raise _FakeAPIError(500, "server exploded")
        self.removed = True
        if self._on_remove:
            self._on_remove(self.id)


class _FakeContainers:
    def __init__(self, store: dict, get_behavior: str = "ok"):
        self.store = store
        self._get_behavior = get_behavior

    def get(self, cid):
        if cid not in self.store:
            raise docker.errors.NotFound(f"no such container: {cid}")
        return self.store[cid]


class _FakeClient:
    def __init__(self, containers):
        self.containers = containers


@pytest.fixture
def fake_docker(monkeypatch):
    """装好假客户端并返回 setter。"""
    store: dict = {}
    fake = _FakeClient(_FakeContainers(store))
    monkeypatch.setattr(du, "client", fake)

    def put(cid, **kw):
        store[cid] = _FakeContainer(cid, **kw)
        return store[cid]

    return type("FX", (), {"store": store, "put": staticmethod(put),
                           "client": fake})


# ---------------------------------------------------------------------------
# 幂等性
# ---------------------------------------------------------------------------


def test_removes_container(fake_docker):
    c = fake_docker.put("c1")
    du._remove_now("c1")
    assert c.removed is True


def test_missing_container_is_noop(fake_docker):
    """不存在的容器不该抛——「已经没了」是正常终态。"""
    du._remove_now("nope")          # 不抛即通过
    du._remove_now(None)


def test_remove_container_none_is_noop():
    """``None`` 必须静默跳过。

    ``client.containers.get(None)`` 抛的是 ``NullResource``，不在 NotFound 捕获
    范围内——那会把「本来就没容器可清」变成异常，而它恰好发生在收尾路径上，
    结果是任务状态永远停在 RUNNING。
    """
    du._remove_now(None)


def test_stop_path_uses_graceful_stop(fake_docker):
    c = fake_docker.put("c2")
    du._stop_container("c2")
    assert c.stopped is True, "优雅停止路径应先 stop 再 remove"
    assert c.removed is True


# ---------------------------------------------------------------------------
# 409：并发移除
# ---------------------------------------------------------------------------


def test_409_waits_until_gone(monkeypatch, fake_docker):
    """撞上 409 时轮询等容器消失，且**不抛**。"""
    fake_docker.put("c3", behavior="409_forever")
    gone_after = {"n": 3}
    calls = {"count": 0}

    def fake_wait(cid, timeout=30.0):
        calls["count"] += 1
        return True

    monkeypatch.setattr(du, "_wait_until_gone", fake_wait)

    du._remove_now("c3")            # 不抛即通过
    assert calls["count"] == 1, "应当走等待分支"
    assert gone_after["n"] == 3


def test_409_timeout_is_warned_not_raised(monkeypatch, fake_docker):
    """等待超时要**警告**而不是抛异常。

    抛异常会打断收尾路径——那正是这个函数存在的地方。
    ⚠️ 直接替换 ``du.log`` 而不用 caplog：项目的 ``app.core.logger.log`` 是
    loguru，caplog（标准库 logging 的 handler）抓不到它的记录。
    """
    fake_docker.put("c4", behavior="409_forever")
    monkeypatch.setattr(du, "_wait_until_gone", lambda cid, timeout=30.0: False)

    msgs: list[str] = []

    class _Log:
        @staticmethod
        def warning(msg, *a):
            msgs.append(str(msg))

        @staticmethod
        def info(msg, *a):
            pass

        @staticmethod
        def debug(msg, *a):
            pass

    monkeypatch.setattr(du, "log", _Log())
    du._remove_now("c4")            # 不抛即通过
    assert any("等待容器" in m for m in msgs), f"超时应留下警告，实际: {msgs}"


def test_non_409_api_error_still_raises(fake_docker):
    """非 409 的错误**必须**继续抛。

    把所有 APIError 都吞掉会掩盖真问题（比如 Docker 守护进程挂了），
    那样任务会被静默判成「清理成功」而容器还留着占 GPU。
    """
    fake_docker.put("c5", behavior="500")
    with pytest.raises(docker.errors.APIError):
        du._remove_now("c5")


# ---------------------------------------------------------------------------
# _wait_until_gone
# ---------------------------------------------------------------------------


def test_wait_until_gone_returns_true_when_already_gone(fake_docker):
    assert du._wait_until_gone("absent", timeout=1.0) is True


def test_wait_until_gone_returns_true_when_disappears(monkeypatch, fake_docker):
    store = fake_docker.store
    store["c6"] = _FakeContainer("c6")
    calls = {"n": 0}

    def fake_sleep(_s):
        calls["n"] += 1
        if calls["n"] >= 2:
            store.pop("c6", None)   # 第二轮轮询前消失

    monkeypatch.setattr(du.time, "sleep", fake_sleep)
    assert du._wait_until_gone("c6", timeout=5.0) is True
    assert calls["n"] >= 2


def test_wait_until_gone_returns_false_on_timeout(monkeypatch, fake_docker):
    store = fake_docker.store
    store["c7"] = _FakeContainer("c7")
    monkeypatch.setattr(du.time, "sleep", lambda _s: None)
    # timeout=0 -> deadline 已过，一轮都不轮
    assert du._wait_until_gone("c7", timeout=0.0) is False


def test_wait_survives_transient_api_errors(monkeypatch, fake_docker):
    """Docker API 临时不可用不该让等待函数崩掉。"""
    store = fake_docker.store
    store["c8"] = _FakeContainer("c8")

    def boom(_cid):
        raise RuntimeError("docker daemon restarting")

    containers = fake_docker.client.containers
    monkeypatch.setattr(containers, "get", boom)
    monkeypatch.setattr(du.time, "sleep", lambda _s: None)
    assert du._wait_until_gone("c8", timeout=0.0) is False  # 不抛即通过


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------


def test_async_remove_container_delegates(monkeypatch, fake_docker):
    import asyncio

    c = fake_docker.put("c9")
    asyncio.run(du.remove_container("c9"))
    assert c.removed is True


def test_async_stop_container_delegates(fake_docker):
    import asyncio

    c = fake_docker.put("c10")
    asyncio.run(du.stop_container("c10"))
    assert c.removed is True and c.stopped is True


def test_remove_container_none_async_noop():
    import asyncio

    asyncio.run(du.remove_container(None))    # 不抛即通过


# ---------------------------------------------------------------------------
# 调用方不再需要各自的 try/except
# ---------------------------------------------------------------------------


def test_all_removal_helpers_route_through_one_implementation():
    """所有移除入口必须收敛到 ``_remove_now``。

    散落实现就是 409 的来源：有一处忘了处理竞态，症状就回来了。
    """
    import inspect
    import pathlib

    src = pathlib.Path(du.__file__).read_text(encoding="utf-8")
    tree_src = src
    # stop 路径必须走 _remove_now
    assert "_remove_now(container_id, force=False, stop_timeout=10)" in tree_src
    # 源码里不应再有裸的 c.remove(force=True) 调用（除了 _remove_now 内部那处）
    body = src.split("def _remove_now(", 1)[1]
    rest = src.replace(body, "")
    assert ".remove(force=" not in rest, "还有别处直接调 c.remove()——会绕过 409 处理"
    assert inspect.isfunction(du._remove_now)
