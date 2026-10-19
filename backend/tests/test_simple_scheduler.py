"""``simple_scheduler`` 动态并发调度测试（简单模式 bridge · Task 5）。

覆盖（不 mock ``acquire`` 本身，真实走实现；仅 patch NVML 枚举与 Redis 后端）：

1. 显存足够时**同卡两次** ``acquire`` 都成功（同卡多任务，不取整卡锁）；
2. 超过 ``TORKILN_SIMPLE_MAX_CONCURRENT`` 时返回 ``None``（排队）；
3. ``release`` 后并发计数回落、可再次 acquire；
4. ``usage_snapshot`` 结构（各卡 free/util/占用台账 + active_count）；
5. Redis 与进程内降级两种后端都要过（``_store.redis_or_none`` patch）。

本文件为纯逻辑测试（不碰 DB/HTTP），可用 ``PYTEST_NO_APP=1`` 快速模式跑；
由于与其它用例同进程共用临时库，task_id 用 2200+ 区间，避免跨文件冲突。

参考 ``tests/test_gpu_pool_split.py``：patch ``gpu_pool.device.gpu_devices`` 伪造
GPU 列表；patch ``gpu_pool._store.redis_or_none`` 走降级/内存 Redis。
"""
import asyncio

import pytest

from app.config.setting import settings
from app.plugin.module_train import simple_scheduler as ss

#: 本文件统一用 2200+，与 Task 3/4 的 (1)/(900+) 及本任务 2000+ 区间隔离
_TASK = 2200


def _run(coro):
    return asyncio.run(coro)


async def _async_none():
    return None


def _async(value):
    async def _inner():
        return value

    return _inner


@pytest.fixture(autouse=True)
def _fresh_scheduler(monkeypatch):
    """每个用例重置调度器进程内状态，并强制走进程内降级后端（默认）。"""
    monkeypatch.setattr(ss, "_LOCAL_ACTIVE", 0)
    monkeypatch.setattr(ss, "_LOCAL_TASKS", {})
    monkeypatch.setattr(ss, "_LOCAL_ENV", {})
    monkeypatch.setattr(ss._store, "redis_or_none", _async_none)


def _single_gpu(free_gb=20.0, used_ratio=0.1):
    return [
        {
            "index": 0,
            "uuid": "uuid-0",
            "total": int(20 * 1024 ** 3),
            "used": int(used_ratio * 20 * 1024 ** 3),
            "free": int(free_gb * 1024 ** 3),
            "free_gb": float(free_gb),
            "used_ratio": float(used_ratio),
        }
    ]


def test_acquire_same_card_twice(monkeypatch):
    """显存足够时同卡两次 acquire 都成功（允许同卡多任务，不取整卡锁）。"""
    monkeypatch.setattr(ss.device_mod, "gpu_devices", lambda: _single_gpu())
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_MAX_CONCURRENT", 4)

    a1 = _run(ss.acquire(_TASK + 1, 4.0, 4.0))
    a2 = _run(ss.acquire(_TASK + 2, 4.0, 4.0))
    assert a1 is not None, "显存足够时第一次 acquire 应成功"
    assert a2 is not None, "同卡多任务：第二次 acquire 应同样成功"
    assert a1.gpu_indices == [0] and a2.gpu_indices == [0], "应选中 GPU 0"
    assert ss.usage_snapshot()["active_count"] == 2


def test_acquire_rejects_insufficient_free_gb(monkeypatch):
    """可用显存不足（free_gb < 需求×1.2 或 util 超限）→ 返回 None。"""
    monkeypatch.setattr(
        ss.device_mod, "gpu_devices", lambda: _single_gpu(free_gb=2.0, used_ratio=0.1))
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_MAX_CONCURRENT", 4)

    a = _run(ss.acquire(_TASK + 3, 4.0, 4.0))
    assert a is None, "free_gb(2.0) < 4.0*1.2=4.8 应返回 None"


def test_acquire_rejects_high_util(monkeypatch):
    """当前利用率 ≥ 85% 的卡不选 → 返回 None。"""
    monkeypatch.setattr(
        ss.device_mod, "gpu_devices", lambda: _single_gpu(free_gb=20.0, used_ratio=0.9))
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_MAX_CONCURRENT", 4)

    a = _run(ss.acquire(_TASK + 4, 4.0, 4.0))
    assert a is None, "used_ratio(0.9) ≥ 0.85 应返回 None"


def test_acquire_over_max_returns_none(monkeypatch):
    """超过 MAX_CONCURRENT → 返回 None（排队），不占用资源。"""
    monkeypatch.setattr(ss.device_mod, "gpu_devices", lambda: _single_gpu())
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_MAX_CONCURRENT", 2)

    a1 = _run(ss.acquire(_TASK + 5, 4.0, 4.0))
    a2 = _run(ss.acquire(_TASK + 6, 4.0, 4.0))
    a3 = _run(ss.acquire(_TASK + 7, 4.0, 4.0))
    assert a1 is not None and a2 is not None, "前两个 acquire 应成功"
    assert a3 is None, "达到并发上限后应返回 None"


def test_release_decrements_and_allows_reacquire(monkeypatch):
    """release 后并发计数回落，可再次 acquire。"""
    monkeypatch.setattr(ss.device_mod, "gpu_devices", lambda: _single_gpu())
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_MAX_CONCURRENT", 2)

    assert _run(ss.acquire(_TASK + 8, 4.0, 4.0)) is not None
    assert _run(ss.acquire(_TASK + 9, 4.0, 4.0)) is not None
    assert _run(ss.acquire(_TASK + 10, 4.0, 4.0)) is None

    _run(ss.release(_TASK + 8))
    assert _run(ss.acquire(_TASK + 11, 4.0, 4.0)) is not None, "release 后应能再 acquire"


def test_release_idempotent(monkeypatch):
    """重复 release 不应把并发计数减成负数。"""
    monkeypatch.setattr(ss.device_mod, "gpu_devices", lambda: _single_gpu())
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_MAX_CONCURRENT", 4)

    _run(ss.release(_TASK + 12))  # 未 acquire 直接 release
    _run(ss.release(_TASK + 12))
    _run(ss.release(_TASK + 12))
    assert ss.usage_snapshot()["active_count"] == 0


def test_usage_snapshot_structure(monkeypatch):
    """``usage_snapshot`` 返回各卡 free/util/占用台账 + active_count。"""
    monkeypatch.setattr(ss.device_mod, "gpu_devices", lambda: _single_gpu())
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_MAX_CONCURRENT", 4)

    _run(ss.acquire(_TASK + 13, 4.0, 6.0))  # est_mem_gb=6.0
    snap = ss.usage_snapshot()
    assert "active_count" in snap, "必须有 active_count"
    assert snap["active_count"] == 1
    assert "gpus" in snap and 0 in snap["gpus"], "必须有每卡台账"
    card = snap["gpus"][0]
    assert {"free_gb", "used_ratio", "reserved_gb", "tasks"} <= set(card), (
        f"卡片缺少关键字段，实际 {sorted(card)}")
    assert card["reserved_gb"] == 6.0, "reserved_gb 应累加 est_mem_gb"
    assert _TASK + 13 in card["tasks"]


def test_acquire_with_fakeredis_backend(monkeypatch):
    """Redis 可用（fakeredis）时同样工作：并发计数与台账走 Redis 键。"""
    import json

    import fakeredis.aioredis

    rd = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(ss._store, "redis_or_none", _async(rd))
    monkeypatch.setattr(ss.device_mod, "gpu_devices", lambda: _single_gpu())
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_MAX_CONCURRENT", 4)

    a = _run(ss.acquire(_TASK + 14, 4.0, 4.0))
    assert a is not None, "内存 Redis 后端 acquire 应成功"
    assert a.gpu_indices == [0]
    ledger = json.loads(_run(rd.get(f"{ss.K_SIMPLE_TASK}{_TASK + 14}")))
    assert ledger["gpu_id"] == 0, "Redis 台账应包含选中的 gpu_id"

    # release 后 Redis 键被清、active 计数回落
    _run(ss.release(_TASK + 14))
    assert _run(rd.get(f"{ss.K_SIMPLE_TASK}{_TASK + 14}")) is None


def test_update_usage_env_and_step_backfill(monkeypatch):
    """``update_usage``：env 写台账快照；step 的 mem_reserved 回填任务台账。"""
    monkeypatch.setattr(ss.device_mod, "gpu_devices", lambda: _single_gpu())
    monkeypatch.setattr(settings, "TORKILN_SIMPLE_MAX_CONCURRENT", 4)
    _run(ss.acquire(_TASK + 15, 4.0, 4.0))

    env = {"task_id": _TASK + 15, "seq": 1, "ts": 1.0, "type": "env",
           "gpu": [{"id": 0, "util": 30.0}]}
    _run(ss.update_usage(env))
    assert _TASK + 15 in ss._LOCAL_ENV, "env 事件应写入环境台账快照"
    assert ss._LOCAL_ENV[_TASK + 15]["gpu"][0]["util"] == 30.0

    step = {"task_id": _TASK + 15, "seq": 2, "ts": 2.0, "type": "step",
            "mem_reserved": 3.2}
    _run(ss.update_usage(step))
    snap = ss.usage_snapshot()
    assert snap["gpus"][0]["reserved_gb"] == 3.2, "step 的 mem_reserved 应回填台账"
