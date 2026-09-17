"""数据库连接池配置与启动期预热测试（审计·并发 #11）。

覆盖：
- 预热并发签出 ``POOL_SIZE`` 条连接并全部归还（顺序复用只会命中同一条）；
- 非启动期 / TESTING / SQLite 下跳过预热；
- 默认池配置为「保留 POOL_SIZE 条、MAX_OVERFLOW=0」，避免溢出建连风暴。
"""
import asyncio

from app.config.setting import settings
from app.core import database


class _FakeConn:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class _FakeEngine:
    def __init__(self) -> None:
        self.conns: list[_FakeConn] = []

    async def connect(self):
        conn = _FakeConn()
        self.conns.append(conn)
        return conn


def _use_warmable_postgres(monkeypatch, size: int = 5) -> _FakeEngine:
    engine = _FakeEngine()
    monkeypatch.setattr(database, "async_engine", engine)
    monkeypatch.setattr(settings, "SQL_DB_ENABLE", True)
    monkeypatch.setattr(settings, "TESTING", False)
    monkeypatch.setattr(settings, "DATABASE_TYPE", "postgres")
    monkeypatch.setattr(settings, "POOL_SIZE", size)
    monkeypatch.setattr(settings, "DB_POOL_WARMUP", True)
    return engine


def test_warmup_acquires_and_returns_pool_size_connections(monkeypatch):
    """启动期并发签出 POOL_SIZE 条连接，并全部归还（防止顺序复用只建一条）。"""
    engine = _use_warmable_postgres(monkeypatch, size=5)
    asyncio.run(database.async_pool_warmup(app=None, status=True))
    assert len(engine.conns) == 5
    assert all(conn.closed for conn in engine.conns)


def test_warmup_skips_when_not_startup(monkeypatch):
    """关停阶段（status=False）不预热。"""
    engine = _use_warmable_postgres(monkeypatch)
    asyncio.run(database.async_pool_warmup(app=None, status=False))
    assert engine.conns == []


def test_warmup_skips_in_testing_and_sqlite(monkeypatch):
    """TESTING 或 SQLite 下跳过预热（测试无需真实连接）。"""
    engine = _use_warmable_postgres(monkeypatch)
    monkeypatch.setattr(settings, "TESTING", True)
    asyncio.run(database.async_pool_warmup(app=None, status=True))
    assert engine.conns == []

    monkeypatch.setattr(settings, "TESTING", False)
    monkeypatch.setattr(settings, "DATABASE_TYPE", "sqlite")
    asyncio.run(database.async_pool_warmup(app=None, status=True))
    assert engine.conns == []


def test_warmup_failure_does_not_raise(monkeypatch):
    """预热失败只告警、不抛异常，绝不阻断启动。"""

    class _BoomEngine:
        async def connect(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(database, "async_engine", _BoomEngine())
    monkeypatch.setattr(settings, "SQL_DB_ENABLE", True)
    monkeypatch.setattr(settings, "TESTING", False)
    monkeypatch.setattr(settings, "DATABASE_TYPE", "postgres")
    monkeypatch.setattr(settings, "DB_POOL_WARMUP", True)
    asyncio.run(database.async_pool_warmup(app=None, status=True))


def test_default_pool_has_no_overflow_churn():
    """默认池配置：保留连接 + 0 溢出，避免并发突发反复「建连→关闭」。"""
    assert settings.POOL_SIZE > 0
    assert settings.MAX_OVERFLOW == 0
    assert settings.POOL_USE_LIFO is True
    assert getattr(settings, "DB_POOL_WARMUP", False) is True
