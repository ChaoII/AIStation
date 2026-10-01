"""资源占用记录的存储层：Redis 优先，不可用时降级到进程内。

为什么单独成一层
----------------
端口与 GPU 的**认领**逻辑（:mod:`.port` / :mod:`.device`）需要回答同一个问题：
「当前有没有别人占着？」而这个问题在两种后端下写法完全不同——Redis 走
``SET key val NX EX`` 原子认领，进程内走 dict 查键。

把「拿句柄 + 判断走哪个后端 + 降级」集中在这里，其余模块就只写一次判据、不再
关心后端差异。这也是整个池子里唯一允许知道 Redis 存在的地方。

降级语义（刻意如此）
------------------
Redis 不可用时**不报错、降级到进程内字典**：

- 端口安全性不受影响——占用判断之外还有一次**真实 bind 探测**（见 :func:`.port.port_bindable`），
  那才是端口是否可用的最终依据；
- 但 GPU 可能被多 worker 超发，因为进程内看不见别的进程。

宁可放行也不要因为 Redis 挂了就完全不能训练——这是权衡后的选择，不是疏漏。
连接失败后有 30 秒冷却，避免每个任务都去等一次连接超时。
"""

from __future__ import annotations

import time

from app.config.setting import settings
from app.core.logger import log

# Redis 键前缀。``aist:`` 而非裸字符串，避免与其它模块撞键。
K_PORT = "aist:tk:port:"
K_GPU = "aist:tk:gpu:"
#: 占用键的 TTL。正常路径会在任务终止时主动删；TTL 是**兜底**——进程被 kill -9
#: 时释放逻辑不会执行，没有 TTL 的话端口/GPU 会被永久占死。
OCCUPIED_TTL = 24 * 3600

_async_redis = None
_redis_unavailable_until = 0.0


async def redis_or_none():
    """惰性取 async Redis；不可用返回 ``None``（调用方降级到进程内）。

    测试要强制走降级路径时，patch 的是**本函数**，而不是某个模块里的别名——
    转发层的别名只是绑定，被调用方按自己模块的全局查找名字，patch 别名不生效
    （曾因此在 exporter 拆分时踩过：``monkeypatch.setattr(exporter, "async_db_session")``
    静默无效，症状是「DB 真被连上」）。
    """
    global _async_redis, _redis_unavailable_until
    if _async_redis is not None:
        return _async_redis
    if not settings.REDIS_ENABLE:
        return None
    # 失败后短暂冷却，避免每个任务都去等一次连接超时
    if _redis_unavailable_until and time.monotonic() < _redis_unavailable_until:
        return None
    try:
        if getattr(settings, "TESTING", False):
            import fakeredis.aioredis as fakeredis_aioredis

            _async_redis = fakeredis_aioredis.FakeRedis(decode_responses=True)
        else:
            from redis.asyncio import Redis

            _async_redis = await Redis.from_url(
                url=settings.REDIS_URI,
                encoding="utf-8",
                decode_responses=True,
                health_check_interval=20,
                max_connections=settings.REDIS_MAX_CONNECTIONS,
                socket_timeout=settings.POOL_TIMEOUT,
            )
        await _async_redis.ping()
        return _async_redis
    except Exception as e:  # noqa: BLE001
        log.warning(f"[gpu_pool] Redis 不可用，降级为进程内记录: {e}")
        _async_redis = None
        _redis_unavailable_until = time.monotonic() + 30.0
        return None


# ----------------------------------------------------------------- 进程内回退
#
# 三个字典是**降级后端**，被 :mod:`.port` / :mod:`.device` / :mod:`.alloc` 直接读写。
# 注意它们是**模块级可变对象**：测试里 ``_LOCAL.clear()`` 清的就是这里，
# 所以清理动作必须落在这一层，不能在别处复制一份。

#: ``task_id -> Allocation``。Redis 不可用时用它。
LOCAL: dict[int, object] = {}
#: 端口 -> task_id（进程内回退）
LOCAL_PORTS: dict[int, int] = {}
#: gpu uuid -> task_id（进程内回退）
LOCAL_GPUS: dict[str, int] = {}
