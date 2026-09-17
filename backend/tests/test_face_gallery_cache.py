"""多 worker 人脸底库缓存一致性：Redis 版本号失效 + TTL 读穿兜底。

背景（B3 遗留）：底库缓存原为纯进程内，多 worker 部署下 A 实例录入后 B 实例不可见。
修复后：录入/删除递增 Redis 全局版本号；事件热路径 ``sync_cache()`` 发现版本变化即重读 DB，
Redis 不可用时按 TTL 读穿，保证跨进程变更最终可见（有界延迟）。
"""
import asyncio
import time

import pytest

from app.api.v1.module_video.face_gallery import service as svc
from app.api.v1.module_video.face_gallery.store import FaceGalleryStore, face_gallery_store


class _FakeRedis:
    """最小 Redis 替身：仅实现版本号所需的 get/incr。"""

    def __init__(self) -> None:
        self.data: dict[str, int] = {}

    def get(self, key: str):
        return self.data.get(key)

    def incr(self, key: str) -> int:
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]


@pytest.fixture(autouse=True)
def _reset_store():
    face_gallery_store.clear()
    face_gallery_store.mark_version(0)
    yield
    face_gallery_store.clear()
    face_gallery_store.mark_version(0)


def test_store_staleness_and_version():
    """缓存新鲜度与版本号的纯逻辑（TTL/从未加载）。"""
    store = FaceGalleryStore(ttl_sec=5.0)
    assert store.is_stale() is True  # 从未加载
    store.replace([{"id": 1, "embedding": [1.0]}])
    assert store.is_stale() is False
    # 人为置旧 → 过期
    store._loaded_at = time.monotonic() - 6.0
    assert store.is_stale() is True

    store.replace([{"id": 1, "embedding": [1.0]}], version=7)
    assert store.version == 7
    assert store.is_stale() is False


def test_sync_cache_refreshes_on_version_change(monkeypatch):
    """其他 worker 递增版本号后，本进程 sync_cache 必须重读 DB 并更新缓存。"""
    fake = _FakeRedis()
    monkeypatch.setattr(svc, "_get_redis", lambda: fake)
    calls = {"n": 0}
    fresh = [{"id": 2, "name": "B", "embedding": [1.0, 0.0], "dimension": 2}]

    async def _fetch(db=None):
        calls["n"] += 1
        return fresh

    monkeypatch.setattr(svc.FaceGalleryService, "_fetch_entries", staticmethod(_fetch))

    # 初始：本地空、版本 0；远端被另一 worker 递增到 1
    asyncio.run(svc.FaceGalleryService.refresh_cache())
    assert calls["n"] == 1
    fake.incr(svc._VERSION_KEY)

    assert asyncio.run(svc.FaceGalleryService.sync_cache()) is True
    assert face_gallery_store.version == 1
    assert face_gallery_store.snapshot()[0]["id"] == 2

    # 版本未变且缓存新鲜 → 不再重读（避免热路径反复查库）
    assert asyncio.run(svc.FaceGalleryService.sync_cache()) is False
    assert calls["n"] == 2


def test_sync_cache_ttl_fallback_without_redis(monkeypatch):
    """Redis 不可用时按 TTL 读穿：过期才重读，未过期不查库。"""
    monkeypatch.setattr(svc, "_get_redis", lambda: None)
    calls = {"n": 0}

    async def _fetch(db=None):
        calls["n"] += 1
        return [{"id": 1, "name": "A", "embedding": [1.0], "dimension": 1}]

    monkeypatch.setattr(svc.FaceGalleryService, "_fetch_entries", staticmethod(_fetch))

    face_gallery_store._loaded_at = 0.0  # 从未加载 → stale
    assert asyncio.run(svc.FaceGalleryService.sync_cache()) is True
    assert calls["n"] == 1

    # 刚刷新 → 不 stale → 不再重读
    assert asyncio.run(svc.FaceGalleryService.sync_cache()) is False
    assert calls["n"] == 1

    # 人为置旧 → 重新读穿
    face_gallery_store._loaded_at = time.monotonic() - 10_000
    assert asyncio.run(svc.FaceGalleryService.sync_cache()) is True
    assert calls["n"] == 2
