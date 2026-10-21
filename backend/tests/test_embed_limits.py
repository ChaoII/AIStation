# tests/test_embed_limits.py （PYTEST_NO_APP=1）
"""嵌入限流与配额（固定窗口 + 按日配额）纯逻辑测试。

覆盖 Review Focus 第 5 条：cap=1 时第二发 429 且中文文案可读；redis 缺失降级放行。
"""
import asyncio
from types import SimpleNamespace

import pytest

from app.config.setting import settings
from app.core.exceptions import CustomException
from app.plugin.module_ai.develop.embed import EmbedService


class _FakeRedis:
    """最小 Redis 桩：只实现 INCR / EXPIRE。"""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.store[key] = int(self.store.get(key, 0)) + 1
        return self.store[key]

    async def expire(self, key: str, ttl: int) -> bool:
        return True


def _ctx(quota=None, token: str = "abcdef123456"):
    return SimpleNamespace(token_hash12=token, app_id=1, quota=quota)


def test_rate_limit_token_second_call_429(monkeypatch):
    monkeypatch.setattr(settings, "EMBED_RATE_TOKEN_PER_MIN", 1)
    monkeypatch.setattr(settings, "EMBED_RATE_IP_PER_MIN", 100)
    redis = _FakeRedis()
    asyncio.run(EmbedService.check_limits(redis, _ctx(), "1.2.3.4"))
    with pytest.raises(CustomException) as ei:
        asyncio.run(EmbedService.check_limits(redis, _ctx(), "1.2.3.4"))
    assert ei.value.status_code == 429 and "频繁" in ei.value.msg


def test_rate_limit_ip_second_call_429(monkeypatch):
    monkeypatch.setattr(settings, "EMBED_RATE_TOKEN_PER_MIN", 100)
    monkeypatch.setattr(settings, "EMBED_RATE_IP_PER_MIN", 1)
    redis = _FakeRedis()
    asyncio.run(EmbedService.check_limits(redis, _ctx(token="aaaa11112222"), "9.9.9.9"))
    with pytest.raises(CustomException) as ei:
        asyncio.run(EmbedService.check_limits(redis, _ctx(token="bbbb11112222"), "9.9.9.9"))
    assert ei.value.status_code == 429


def test_quota_daily_429(monkeypatch):
    monkeypatch.setattr(settings, "EMBED_RATE_TOKEN_PER_MIN", 100)
    monkeypatch.setattr(settings, "EMBED_RATE_IP_PER_MIN", 100)
    redis = _FakeRedis()
    ctx = _ctx(quota={"embed": 1})
    asyncio.run(EmbedService.check_limits(redis, ctx, "1.1.1.1"))
    with pytest.raises(CustomException) as ei:
        asyncio.run(EmbedService.check_limits(redis, ctx, "1.1.1.1"))
    assert ei.value.status_code == 429 and "配额" in ei.value.msg


def test_quota_zero_means_unlimited(monkeypatch):
    monkeypatch.setattr(settings, "EMBED_RATE_TOKEN_PER_MIN", 100)
    monkeypatch.setattr(settings, "EMBED_RATE_IP_PER_MIN", 100)
    redis = _FakeRedis()
    ctx = _ctx(quota={"embed": 0})
    for _ in range(5):
        asyncio.run(EmbedService.check_limits(redis, ctx, "1.1.1.2"))  # 不抛


def test_no_redis_skips():
    asyncio.run(EmbedService.check_limits(None, _ctx(quota={"embed": 1}), "1.1.1.1"))


def test_issue_limit_appid_second_call_429(monkeypatch):
    """换票端点限流：同 appid 连发超限 → 429（防无限铸票）。"""
    monkeypatch.setattr(settings, "EMBED_TOKEN_RATE_PER_MIN", 1)
    redis = _FakeRedis()
    asyncio.run(EmbedService.check_issue_limit(redis, "ai_testapp", "1.1.1.1"))
    with pytest.raises(CustomException) as ei:
        asyncio.run(EmbedService.check_issue_limit(redis, "ai_testapp", "1.1.1.1"))
    assert ei.value.status_code == 429 and "换票" in ei.value.msg


def test_issue_limit_ip_covers_multiple_appids(monkeypatch):
    """换票限流的 IP 键跨 appid 累计（每 IP 额度为单 appid 的 2 倍）。"""
    monkeypatch.setattr(settings, "EMBED_TOKEN_RATE_PER_MIN", 1)
    redis = _FakeRedis()
    asyncio.run(EmbedService.check_issue_limit(redis, "ai_app_a", "9.9.9.9"))
    asyncio.run(EmbedService.check_issue_limit(redis, "ai_app_b", "9.9.9.9"))
    with pytest.raises(CustomException) as ei:
        asyncio.run(EmbedService.check_issue_limit(redis, "ai_app_c", "9.9.9.9"))
    assert ei.value.status_code == 429


def test_issue_limit_no_redis_skips():
    asyncio.run(EmbedService.check_issue_limit(None, "ai_testapp", "1.1.1.1"))
