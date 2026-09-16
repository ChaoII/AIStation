"""时序状态存储并发回归：确认事件循环不被同步 Redis 阻塞（审计 §并发-5）。

手段：注入一个「每次 Redis 操作都 sleep」的阻塞客户端，让时序规则评估在
线程池中执行；同时跑一个心跳协程统计事件循环 tick，断言 tick 持续推进
（若仍在事件循环内同步执行，tick 会长时间停滞）。
"""
import asyncio
import time

from app.api.v1.module_video.inference import service
from app.api.v1.module_video.inference.temporal import TemporalStore

_SLEEP = 0.05


class _BlockingRedis:
    """模拟慢 Redis：所有操作阻塞 _SLEEP 秒。"""

    def hgetall(self, key):
        time.sleep(_SLEEP)
        return {}

    def hset(self, key, mapping=None):
        time.sleep(_SLEEP)
        return 1

    def expire(self, key, ttl):
        time.sleep(_SLEEP)
        return True

    def scan_iter(self, match=None):
        time.sleep(_SLEEP)
        return iter(())

    def get(self, key):
        time.sleep(_SLEEP)
        return None

    def setex(self, key, ttl, value):
        time.sleep(_SLEEP)
        return True


class _BlockingStore(TemporalStore):
    def __init__(self):
        super().__init__(prefer_redis=True)
        self._fake = _BlockingRedis()

    def _get_redis(self):
        return self._fake


class _Rule:
    id = 1
    severity = "WARNING"
    interval_seconds = 0
    # dwell 叶子：无历史状态 → 未命中，评估不会触碰 DB
    conditions = {"op": "and", "children": [{"subject": "dwell", "label": "person", "min_sec": 5}]}


def test_event_loop_not_blocked_by_temporal_redis(monkeypatch):
    monkeypatch.setattr(service, "temporal_store", _BlockingStore())

    event = {"camera_id": 1, "algorithm_type": "ALGO", "detections": [{"label": "person", "bbox": {}}]}

    async def scenario():
        ticks = 0
        running = True

        async def heartbeat():
            nonlocal ticks
            while running:
                await asyncio.sleep(0.01)
                ticks += 1

        hb = asyncio.create_task(heartbeat())
        started = time.perf_counter()
        # 每条规则评估约 4 次阻塞 I/O（≈0.2s）；N=6 → 同步执行会令 tick 完全停滞
        await asyncio.gather(
            *[
                service._evaluate_rule(
                    _Rule(), event, event["detections"], 1, "ALGO", time.time(), None
                )
                for _ in range(6)
            ]
        )
        elapsed = time.perf_counter() - started
        running = False
        hb.cancel()
        try:
            await hb
        except asyncio.CancelledError:
            pass
        return ticks, elapsed

    ticks, elapsed = asyncio.run(scenario())
    # 事件循环仍在推进：阻塞期间心跳持续 tick（同步执行时 ticks≈0）
    assert ticks >= 20, f"事件循环疑似被阻塞（ticks={ticks}, elapsed={elapsed:.2f}s)"
    assert elapsed >= _SLEEP  # 确实发生了阻塞 I/O（测试有效性）


def test_temporal_redis_timeout_is_short():
    """超时必须亚秒级，避免 Redis 抖动时长时间阻塞（审计建议）。"""
    from app.config.setting import settings

    assert 0 < settings.TEMPORAL_REDIS_TIMEOUT <= 1.0
    assert settings.TEMPORAL_REDIS_COOLDOWN_SEC > 0


def test_redis_failure_enters_cooldown_and_recovers(monkeypatch):
    """失败进入冷却（不逐条重试），冷却结束后可重连（不再永久降级）。"""
    from app.config.setting import settings

    store = TemporalStore(prefer_redis=True)

    calls = {"n": 0}

    class _Flaky:
        def __init__(self):
            self.connected = False

        def ping(self):
            calls["n"] += 1
            raise ConnectionError("redis down")

    import redis as redis_mod

    # 直接驱动失败路径：注入一个必然失败的客户端工厂
    monkeypatch.setattr(store, "_prefer_redis", True)
    monkeypatch.setattr(settings, "REDIS_ENABLE", True)
    monkeypatch.setattr(settings, "TESTING", False)
    monkeypatch.setattr(redis_mod.Redis, "from_url", staticmethod(lambda *a, **k: _Flaky()))
    monkeypatch.setattr(settings, "TEMPORAL_REDIS_COOLDOWN_SEC", 0.05)

    assert store._get_redis() is None
    assert store._redis_failed is True
    assert calls["n"] == 1
    # 冷却期内再次获取不应重试（非阻塞）
    assert store._get_redis() is None
    assert calls["n"] == 1
    # 冷却结束后允许重连（再次尝试）
    time.sleep(0.06)
    assert store._get_redis() is None
    assert calls["n"] == 2
