"""AI 智能体并发闸门（方案 A：排队执行）。

**为什么需要**（实测踩过的坑）：
- 同一个 agent 同时跑两个 run：模型调用翻倍，活动表（一 agent 一行）互相覆盖，
  先结束的把人改成「待命」而另一个还在干 —— 状态看起来全乱；
- 办公室 Team 的 agno 会话按**用户**共享（``office-team-{user_id}``），
  同一用户两轮派活并发会串台：追问接到上一单的上下文；
- 定时任务有自己的闸门（``_RUNNING_CRONS``），但**不检查目标 agent 是否在忙**，
  于是办公室派活和定时任务能同时压到同一个 agent 上。

**策略**（用户选定 A）：
- 键：``agent:{id}``、``team:user:{id}``；
- 同一键串行；排队上限 ``queue_limit``（默认 2），超出立刻拒绝，避免无限堆积；
- 定时任务**不排队**：忙就跳过本轮并记一笔（``try_acquire``）；
- 锁是进程内的（与 ``_RUNNING_CRONS`` 同一限制）：单实例够用，多副本需要 Redis 锁。

**为什么用显式 acquire 而不是 ``async with``**：办公室派活在拿锁前要先给前端发一帧
「排队中（前面 N 个）」，生成器里必须先 yield 再等待；显式租约（``Lease``）的
``release()`` 是同步的，生成器被取消（页面关闭/点停止）时 finally 里也能安全释放。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.core.logger import log

# 键 -> 锁
_LOCKS: dict[str, asyncio.Lock] = {}
# 键 -> 正在排队等锁的人数（用于「前面还有几个」与上限判定）
_WAITING: dict[str, int] = {}
# 键 -> 持锁开始时间（monotonic），只用于僵尸锁告警
_HOLD_SINCE: dict[str, float] = {}
_HOLD_WARN_SEC = 15 * 60


def agent_key(agent_id: int | None) -> str:
    return f"agent:{int(agent_id)}" if agent_id else ""


def user_key(user_id: int | None) -> str:
    return f"team:user:{int(user_id)}" if user_id else "team:user:anon"


@dataclass
class Lease:
    """一次占用。``busy=True`` 表示被拒绝（没拿到锁）。"""

    keys: list[str] = field(default_factory=list)
    ahead: int = 0
    busy: bool = False
    reason: str = ""
    _released: bool = False

    def release(self) -> None:
        """同步释放（生成器 finally 里也能安全调用）。"""
        if self._released:
            return
        self._released = True
        for k in reversed(self.keys):
            lock = _LOCKS.get(k)
            if lock is None or not lock.locked():
                continue
            _HOLD_SINCE.pop(k, None)
            try:
                lock.release()
            except RuntimeError:  # 已经释放（极端并发下的重复调用）
                pass

    def __enter__(self) -> Lease:
        return self

    def __exit__(self, *exc) -> None:
        self.release()


async def acquire(
    keys: list[str], *, queue_limit: int = 2, wait: bool = True, who: str = ""
) -> Lease:
    """按 key 排序依次拿锁（排序避免死锁）。

    - ``wait=True``：排队等待；排队人数超过 ``queue_limit`` 直接返回 ``busy``；
    - ``wait=False``：拿不到就返回 ``busy``（定时任务用）。
    """
    ordered = sorted({k for k in keys if k})
    if not ordered:
        return Lease()

    lease = Lease(keys=[])
    for k in ordered:
        lock = _LOCKS.setdefault(k, asyncio.Lock())
        if lock.locked():
            queued = _WAITING.get(k, 0)
            if not wait or queued >= queue_limit:
                lease.release()
                lease.busy = True
                lease.reason = (
                    f"目标正在处理别的任务（队列已满 {queue_limit} 个），请稍后再试"
                    if wait
                    else "目标正在处理别的任务"
                )
                return lease
            _WAITING[k] = queued + 1
            lease.ahead = max(lease.ahead, queued + 1)
            try:
                await lock.acquire()
            finally:
                _WAITING[k] = max(0, _WAITING.get(k, 1) - 1)
        else:
            await lock.acquire()
        lease.keys.append(k)
        _HOLD_SINCE[k] = time.monotonic()

    if lease.ahead:
        log.info(f"[gate] {who or '任务'} 排队 {lease.ahead} 位后拿到 {ordered}")
    return lease


async def try_acquire(keys: list[str], *, who: str = "") -> Lease:
    """不排队版本（定时任务）：忙就返回 busy，调用方跳过本轮。"""
    return await acquire(keys, wait=False, who=who)


def snapshot() -> dict[str, dict]:
    """排查用：当前持锁/排队的键。"""
    out: dict[str, dict] = {}
    now = time.monotonic()
    for k, lock in _LOCKS.items():
        if not lock.locked() and not _WAITING.get(k):
            continue
        since = _HOLD_SINCE.get(k)
        out[k] = {
            "locked": lock.locked(),
            "waiting": _WAITING.get(k, 0),
            "held_sec": round(now - since) if (since and lock.locked()) else 0,
        }
    for k, v in out.items():
        if v["held_sec"] > _HOLD_WARN_SEC:
            log.warning(f"[gate] {k} 已持有 {v['held_sec']}s，疑似卡死（排查：/ai/agents/gate）")
    return out
