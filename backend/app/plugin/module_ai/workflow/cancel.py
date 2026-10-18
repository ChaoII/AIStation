"""工作流运行取消信号（内存 + Redis 双通道）。

为什么需要两层：

- **内存集合**：单进程（dev / 单 worker）即可生效，零依赖、零延迟；
- **Redis**：生产多 worker 时，取消请求可能落到**另一个** worker 的进程，
  只靠内存就成了"碰运气取消"（命中同一进程才生效）。Redis 让所有 worker 都看得到。

Redis 不可用时**降级为内存**（单进程仍可用）并告警一次，不阻断取消流程。
"""
from __future__ import annotations

from app.core.logger import log

#: 进程内取消集合
_LOCAL: set[str] = set()
#: Redis 键前缀与 TTL（TTL 取远大于单次运行的值，避免信号悬挂）
_PREFIX = "ai:wf:cancel:"
_TTL = 3600
_warned = False


def _key(run_key: str) -> str:
    return f"{_PREFIX}{run_key}"


async def request_cancel(run_key: str | int, redis=None) -> None:
    """请求取消某次运行：先标内存，再写 Redis（多 worker 广播）。"""
    global _warned
    _LOCAL.add(str(run_key))
    if redis is None:
        return
    try:
        await redis.set(_key(str(run_key)), "1", ex=_TTL)
    except Exception as e:  # noqa: BLE001 写 Redis 失败仍可本进程取消
        if not _warned:
            _warned = True
            log.warning(
                "[workflow] 取消信号写 Redis 失败（多 worker 下取消可能不生效）：{}",
                str(e)[:120],
            )


async def is_cancelled(run_key: str | int, redis=None) -> bool:
    """是否已请求取消：先查内存，再查 Redis（命中则回填内存，后续免往返）。"""
    key = str(run_key)
    if key in _LOCAL:
        return True
    if redis is None:
        return False
    try:
        if await redis.get(_key(key)):
            _LOCAL.add(key)
            return True
    except Exception:  # noqa: BLE001 查 Redis 失败视为未取消（不误杀运行）
        pass
    return False


async def clear_cancel(run_key: str | int, redis=None) -> None:
    """运行结束时清理信号（防止内存集合无界增长与 Redis 残留）。"""
    key = str(run_key)
    _LOCAL.discard(key)
    if redis is None:
        return
    try:
        await redis.delete(_key(key))
    except Exception:  # noqa: BLE001
        pass
