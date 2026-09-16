"""边缘事件实时广播总线：Redis pub/sub + 进程内 asyncio 降级。

设计要点：
- 发布统一走 Redis 频道 ``ai:edge:event``（多进程部署下各进程的 WS 端点都订阅该频道，
  避免单进程内存广播跨进程不一致）；
- Redis 未启用/不可用（含连接异常）时降级为进程内 asyncio 广播，并只告警一次，避免刷屏；
- WS 端点连接时用 ``set_redis`` 注入应用级 Redis 客户端，供同进程发布方复用；
  若注入前已有发布动作，则按配置惰性创建客户端。
"""
import asyncio
import json
import logging
import time

log = logging.getLogger(__name__)

# Redis 频道名
EDGE_EVENT_CHANNEL = "ai:edge:event"

# 进程内订阅者队列集合（Redis 降级通道）；WS 断开时必须注销，避免订阅泄漏
_local_subscribers: set[asyncio.Queue] = set()

# 应用级 Redis 客户端（由 WS 端点注入，或按配置惰性创建）
_redis_client = None

# Redis 降级告警只打一次
_redis_warned = False

# Redis 不可用时的冷却截止（monotonic）；冷却期内直接走本地广播，避免每条事件都重试连接
_redis_cooldown_until = 0.0


def set_redis(redis) -> None:
    """注入应用级 Redis 客户端（WS 端点调用，供同进程发布方复用同一实例）。"""
    global _redis_client, _redis_cooldown_until
    _redis_client = redis
    _redis_cooldown_until = 0.0


async def get_redis():
    """解析 Redis 客户端；未启用或不可用（含冷却期内）时返回 ``None``。"""
    global _redis_client, _redis_cooldown_until
    if _redis_client is not None:
        return _redis_client
    from app.config.setting import settings

    if not getattr(settings, "REDIS_ENABLE", False):
        return None
    if time.monotonic() < _redis_cooldown_until:
        # 冷却期内（上次连接失败）直接降级，避免每条事件都等待连接超时
        return None
    try:
        if getattr(settings, "TESTING", False):
            # 测试模式：与 app 生命周期一致使用内存 Redis，避免依赖外部服务
            import fakeredis.aioredis as fakeredis_aioredis

            _redis_client = fakeredis_aioredis.FakeRedis(decode_responses=True)
        else:
            from redis.asyncio import Redis

            _redis_client = await Redis.from_url(
                url=settings.REDIS_URI,
                encoding="utf-8",
                decode_responses=True,
                health_check_interval=20,
                socket_connect_timeout=float(getattr(settings, "TEMPORAL_REDIS_TIMEOUT", 0.5) or 0.5),
                socket_timeout=settings.POOL_TIMEOUT,
            )
        _redis_cooldown_until = 0.0
        return _redis_client
    except Exception as e:
        _enter_redis_cooldown(e)
        log.warning(f"边缘事件广播获取 Redis 连接失败: {e}")
        return None


def _enter_redis_cooldown(exc: Exception) -> None:
    """进入 Redis 冷却：冷却期内发布直接走本地广播，避免逐条重试拖慢事件接入。"""
    global _redis_client, _redis_cooldown_until
    _redis_client = None
    cooldown = 10.0
    try:
        from app.config.setting import settings

        cooldown = max(0.0, float(getattr(settings, "TEMPORAL_REDIS_COOLDOWN_SEC", 10.0) or 10.0))
    except Exception:  # noqa: BLE001 - 配置缺失时用默认冷却
        pass
    _redis_cooldown_until = time.monotonic() + cooldown
    _warn_redis_once(exc)


def subscribe_local() -> asyncio.Queue:
    """注册进程内订阅队列（Redis 不可用时的降级通道）。"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _local_subscribers.add(queue)
    return queue


def unsubscribe_local(queue) -> None:
    """注销进程内订阅队列；重复注销安全。"""
    _local_subscribers.discard(queue)


def local_subscriber_count() -> int:
    """当前进程内订阅者数量（测试/诊断）。"""
    return len(_local_subscribers)


def build_message(payload: dict) -> dict:
    """构造 WS 转发消息体。"""
    return {"type": "event", "data": payload}


def _warn_redis_once(exc: Exception) -> None:
    """Redis 降级只告警一次，避免刷屏。"""
    global _redis_warned
    if not _redis_warned:
        _redis_warned = True
        log.warning(f"边缘事件 Redis 广播不可用，降级为进程内广播: {exc}")


async def _broadcast_local(message: dict) -> None:
    """向进程内所有订阅队列投递；队列满则丢弃本条，避免阻塞发布方。"""
    for queue in list(_local_subscribers):
        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            log.debug("边缘事件进程内订阅队列已满，丢弃本条广播")


async def publish_edge_event(payload: dict) -> None:
    """发布一条边缘事件：优先 Redis 频道，失败降级进程内广播。

    参数:
    - payload (dict): 事件详情（与 detail 接口同结构，需可 JSON 序列化）。
    """
    message = build_message(payload)
    try:
        redis = await get_redis()
        if redis is None:
            raise RuntimeError("Redis 未启用或不可用")
        await redis.publish(
            EDGE_EVENT_CHANNEL, json.dumps(message, ensure_ascii=False, default=str)
        )
        return
    except Exception as e:
        # 发布失败同样进入冷却：避免 Redis 半可用时每条事件都重试连接拖慢接入
        _enter_redis_cooldown(e)
    await _broadcast_local(message)
