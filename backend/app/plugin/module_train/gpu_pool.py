"""GPU / 端口资源池——「每任务一容器」模式下的调度。

为什么需要它
------------
TorchKiln 服务不再常驻：每个训练任务起一个独立容器，容器内跑完整的 TorchKiln
服务并监听 8000，映射到宿主机的不同端口。带来两个必须集中管理的东西：

- **端口**：每个任务占一个宿主端口，必须唯一且及时回收；
- **GPU**：单卡机器上同时只能跑一个训练（多卡也有限），必须有地方排队。

空闲判定必须**双条件**，缺一不可：

======================  ==========================================  ==================
层                判据                                        缺了会怎样
======================  ==========================================  ==================
调度层            Redis 里该卡/该端口没有活跃作业占用         平台自己超发，两个
                                                                  任务抢同一张卡/端口
资源层            NVML 读显存已用占比 < 阈值（默认 5%）        漏掉**平台外**的
                                                                  占用者（用户手动
                                                                  起的调试容器、其它
                                                                  框架的训练容器）
======================  ==========================================  ==================

只看调度层会撞上外部占用；只看资源层会被瞬时抖动误导（训练进程刚起也占几百 MB，
所以阈值取 5% 而不是 0）。

Redis 不可用时**降级到进程内字典**：此时端口安全（仍然真实 bind 探测），
GPU 可能被多 worker 超发——宁可放行也不要因为 Redis 挂了就完全不能训练。
"""
from __future__ import annotations

import asyncio
import contextlib
import socket
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from app.config.setting import settings
from app.core.logger import log

# Redis 键前缀。``aist:`` 而非裸字符串，避免与其它模块撞键。
_K_PORT = "aist:tk:port:"
_K_GPU = "aist:tk:gpu:"
#: 占用键的 TTL。正常路径会在任务终止时主动删；TTL 是**兜底**——进程被 kill -9
#: 时释放逻辑不会执行，没有 TTL 的话端口/GPU 会被永久占死。
_OCCUPIED_TTL = 24 * 3600

_async_redis = None
_redis_unavailable_until = 0.0


async def _redis():
    """惰性取 async Redis；不可用返回 None（调用方降级到进程内）。"""
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


@dataclass
class Allocation:
    """一次任务拿到的资源。用完必须 :func:`release`。"""

    task_id: int
    port: int
    gpu_indices: list[int] = field(default_factory=list)
    gpu_uuids: list[str] = field(default_factory=list)
    #: True = 资源由 Redis 记录，释放时要去删键
    via_redis: bool = False

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def device_ids(self) -> str:
        """给 ``run_container(gpu_id=...)`` 用的设备串（逗号分隔的序号）。

        用**序号**而非 UUID：``docker run --gpus device=N`` 认的是容器内可见的
        序号，而容器只暴露被选中的那一张卡，序号恒为 0。UUID 记在
        :attr:`gpu_uuids` 里仅用于排查与释放时匹配。
        """
        return ",".join(str(i) for i in self.gpu_indices)


#: 进程内回退记录：``task_id -> Allocation``。Redis 不可用时用它。
_local: dict[int, Allocation] = {}
#: 端口 -> task_id（进程内回退）
_local_ports: dict[int, int] = {}
#: gpu uuid -> task_id（进程内回退）
_local_gpus: dict[str, int] = {}


# ----------------------------------------------------------------- 端口


def _port_bindable(port: int) -> bool:
    """真实 bind 探测端口是否可用。

    为什么必须真探测而不能只信 Redis：占用它的进程可能已经异常退出（TTL 还没
    到），或者那个端口本来就被本机别的服务占了——只信 Redis 就会撞车。

    ⚠️ 故意**不设** ``SO_REUSEADDR``：Windows 上它允许抢占一个已被绑定的端口，
    会让探测假阳性（明明被占却报告可用）。代价只是刚被 TIME_WAIT 占用的端口
    会被短暂跳过；容器 listen 状态不会产生 TIME_WAIT，实际影响很小。
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


async def _claim_port(task_id: int, rd) -> int | None:
    start, end = int(settings.TORKILN_PORT_START), int(settings.TORKILN_PORT_END)
    if end < start:
        log.error(f"[gpu_pool] 端口段配置非法: {start}~{end}")
        return None
    for port in range(start, end + 1):
        if rd is not None:
            ok = await rd.set(f"{_K_PORT}{port}", str(task_id),
                              nx=True, ex=_OCCUPIED_TTL)
            if not ok:
                continue
            # Redis 说空闲，但仍要真探测：可能已被本机其它进程占用
            if not _port_bindable(port):
                await rd.delete(f"{_K_PORT}{port}")
                continue
        else:
            if port in _local_ports:
                continue
            if not _port_bindable(port):
                continue
            _local_ports[port] = task_id
        return port
    return None


# ----------------------------------------------------------------- GPU


def gpu_devices() -> list[dict]:
    """经 NVML 枚举 GPU。每张卡给 ``index`` / ``uuid`` / ``free`` / ``used`` / ``free_gb``。

    NVML 不可用（没装驱动 / 容器内无 GPU / 缺 pynvml）时返回空列表——调用方据此
    走「不指定 GPU」分支，而不是把训练判死。
    """
    try:
        import pynvml
    except ImportError as e:
        log.warning(f"[gpu_pool] 未安装 pynvml，跳过 GPU 空闲判定: {e}")
        return []
    try:
        pynvml.nvmlInit()
    except Exception as e:  # noqa: BLE001
        log.warning(f"[gpu_pool] NVML 初始化失败，跳过 GPU 空闲判定: {e}")
        return []
    out: list[dict] = []
    try:
        for i in range(int(pynvml.nvmlDeviceGetCount())):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            uuid = pynvml.nvmlDeviceGetUUID(handle)
            if isinstance(uuid, bytes):
                uuid = uuid.decode("utf-8", "ignore")
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            total = max(1, int(mem.total))
            free = int(mem.free)
            out.append({
                "index": i,
                "uuid": str(uuid),
                "total": total,
                "used": int(mem.used),
                "free": free,
                "free_gb": free / (1024 ** 3),
                "used_ratio": int(mem.used) / total,
            })
    except Exception as e:  # noqa: BLE001
        log.warning(f"[gpu_pool] NVML 枚举设备失败: {e}")
        return []
    finally:
        # NVML 是引用计数的，这里 shutdown 只减计数；监控页那套采集互不影响
        with contextlib.suppress(Exception):
            pynvml.nvmlShutdown()
    return out


async def _claim_gpu(task_id: int, need: int, rd,
                     devices: list[dict], need_mem_gb: float) -> tuple[list[int], list[str]]:
    """认领 ``need`` 张**可用显存够**的卡。

    判据是**可用显存绝对值**而不是「已用占比 < x%」——这���后者在带桌面环境的
    Windows 上永远不成立：实测本机 dwm.exe + Edge 硬件加速就常驻占 3.2GB（20%），
    一个正在训练的进程反而只占 28%，按占比判会得出「卡被占满、不敢派活」，
    于是平台在这台机器上永远排队。绝对值直接回答「这张卡装不装得下这次训练」。
    """
    max_used_ratio = float(settings.TORKILN_GPU_MAX_USED_RATIO)
    indices: list[int] = []
    uuids: list[str] = []
    for dev in devices:
        if len(indices) >= need:
            break
        # 双重保险：既要有足够可用显存，也不能已经用到几乎枯竭
        if dev["free_gb"] < need_mem_gb or dev["used_ratio"] > max_used_ratio:
            continue
        uuid = dev["uuid"]
        if rd is not None:
            ok = await rd.set(f"{_K_GPU}{uuid}", str(task_id),
                              nx=True, ex=_OCCUPIED_TTL)
            if not ok:
                continue
            # Redis 认领期间显存可能被抢走（外部进程刚好启动），复查一次
            if dev["used_ratio"] > max_used_ratio or dev["free_gb"] < need_mem_gb:
                await rd.delete(f"{_K_GPU}{uuid}")
                continue
        else:
            if uuid in _local_gpus:
                continue
            _local_gpus[uuid] = task_id
        indices.append(dev["index"])
        uuids.append(uuid)
    return indices, uuids


async def _release_gpu_list(uuids: list[str], rd) -> None:
    for uuid in uuids:
        if rd is not None:
            with contextlib.suppress(Exception):
                await rd.delete(f"{_K_GPU}{uuid}")
        _local_gpus.pop(uuid, None)


# ----------------------------------------------------------------- 对外


async def acquire(task_id: int, *, need_gpu: int = 1, need_mem_gb: float | None = None,
                  wait: bool = True) -> Allocation | None:
    """给任务分配「一个端口 + need_gpu 张够用显存的空闲卡」。

    ``need_mem_gb`` 缺省取 ``TORKILN_GPU_MIN_FREE_GB``；调用方（训练执行器）会传
    任务自己声明的 ``resources.gpu_memory_gb``，因为同一张卡对 2GB 的小模型够用、
    对 14GB 的大模型不够。

    没有资源时按配置轮询等待（``TORKILN_QUEUE_TIMEOUT=0`` 表示一直等）。
    返回 None 表示**明确失败**（配置非法 / 等待超时 / 无可用端口段）。
    """
    min_free = float(need_mem_gb if need_mem_gb is not None
                     else settings.TORKILN_GPU_MIN_FREE_GB)
    deadline = None
    if float(settings.TORKILN_QUEUE_TIMEOUT) > 0:
        deadline = time.monotonic() + float(settings.TORKILN_QUEUE_TIMEOUT)
    poll = max(0.5, float(settings.TORKILN_POLL_INTERVAL))

    while True:
        rd = await _redis()
        port = await _claim_port(task_id, rd)
        if port is None:
            # 端口比 GPU 更容易耗尽（段是固定的），先判断是不是该放弃了
            if not wait or (deadline and time.monotonic() >= deadline):
                log.error(f"[gpu_pool] 任务 {task_id} 拿不到端口 "
                          f"({settings.TORKILN_PORT_START}~{settings.TORKILN_PORT_END})")
                return None
            await asyncio.sleep(poll)
            continue

        # NVML 枚举只做一次：既用于分配，也用于「一张卡都枚举不到」的降级判断
        devices = gpu_devices()
        if need_gpu > 0 and not devices:
            # 没有可枚举的 GPU（无驱动 / 容器内无 GPU / 缺 pynvml）：**不能死等**，
            # 否则这台机器上的训练任务会永远卡在排队。降级为不指定 --gpus，
            # 让容器按 Docker 自己的规则走（无 GPU 时会报可读的错误，
            # 而不是被平台判成「等不到卡」）。
            log.warning(f"[gpu_pool] 未探测到 GPU，任务 {task_id} 不指定 --gpus 降级运行")
            alloc = Allocation(task_id=task_id, port=port, via_redis=rd is not None)
            _local[task_id] = alloc
            return alloc

        gpu_indices, gpu_uuids = await _claim_gpu(task_id, max(0, need_gpu),
                                                   rd, devices, min_free)
        if need_gpu > 0 and len(gpu_indices) < need_gpu:
            # 显存不够：**端口和已认领的那几张卡都要还回去**，否则等待一轮之后
            # 它们还挂在这个 task_id 名下，下一轮永远抢不到（泄漏）。
            await _release_gpu_list(gpu_uuids, rd)
            await _release_port(port, rd)
            if not wait or (deadline and time.monotonic() >= deadline):
                # 把每张卡的可用显存打出来：否则用户只看到「等不到空闲 GPU」，
                # 无从判断是别人在用这张卡、还是该等多久
                detail = "，".join(
                    f"GPU{d['index']} 可用 {d['free_gb']:.1f}GB"
                    f"（本次需要 {min_free:.1f}GB）" for d in devices)
                log.warning(f"[gpu_pool] 任务 {task_id} 等不到 {need_gpu} 张可用显存"
                            f"够 {min_free:.1f}GB 的 GPU（共 {len(devices)} 张）：{detail}")
                return None
            log.info(f"[gpu_pool] 任务 {task_id} 等待可用显存 ≥ {min_free:.1f}GB 的 GPU…")
            await asyncio.sleep(poll)
            continue

        alloc = Allocation(task_id=task_id, port=port, gpu_indices=gpu_indices,
                           gpu_uuids=gpu_uuids, via_redis=rd is not None)
        _local[task_id] = alloc
        return alloc


async def _release_port(port: int, rd) -> None:
    if rd is not None:
        with contextlib.suppress(Exception):
            await rd.delete(f"{_K_PORT}{port}")
    _local_ports.pop(port, None)


async def release(task_id: int) -> None:
    """归还任务占用的全部资源。重复调用安全。"""
    alloc = _local.pop(task_id, None)
    rd = await _redis()
    if alloc is None:
        # 进程重启后本地记录没了，仍要按 task_id 清理 Redis 上的残留
        await _cleanup_redis_by_task(task_id, rd)
        return
    await _release_port(alloc.port, rd)
    await _release_gpu_list(alloc.gpu_uuids, rd)
    log.info(f"[gpu_pool] 任务 {task_id} 释放：port={alloc.port} gpu={alloc.gpu_uuids}")


async def _cleanup_redis_by_task(task_id: int, rd) -> None:
    if rd is None:
        return
    try:
        for prefix in (_K_PORT, _K_GPU):
            async for key in rd.scan_iter(match=f"{prefix}*", count=200):
                if await rd.get(key) == str(task_id):
                    await rd.delete(key)
    except Exception as e:  # noqa: BLE001
        log.warning(f"[gpu_pool] 清理任务 {task_id} 的残留占用失败: {e}")


def allocation_of(task_id: int) -> Allocation | None:
    """取任务当前的资源（给恢复逻辑用；进程重启后为 None）。"""
    return _local.get(task_id)


#: 仍在进行中、因此**不该**回收资源的状态
_ALIVE_STATUSES = ("pending", "running")


async def reap_stale() -> int:
    """回收「任务已不在进行中」却仍占着 GPU / 端口的记录，返回回收条数。

    正常路径在任务终止时（``_execute`` 的 finally）就会 :func:`release`。但这些
    情况不会执行到：容器被 ``kill -9``、机器断电、finally 块本身抛异常、
    后端进程崩溃。届时只能等占用键的 24h TTL——对单卡机器而言等于**被占死两天**。

    判据只看**任务状态**，不猜容器死活：``pending``/``running`` 一律保留
    （``pending`` 可能是正在排队等卡的，它已经占着资源），其余（success /
    failed / cancelled / 任务已不存在）一律回收。
    """
    from app.core.database import async_db_session
    from app.plugin.module_train.model import TrainTask

    rd = await _redis()
    stale: list[int] = []
    if rd is not None:
        try:
            for prefix in (_K_PORT, _K_GPU):
                async for key in rd.scan_iter(match=f"{prefix}*", count=200):
                    val = await rd.get(key)
                    if val and val.isdigit():
                        stale.append(int(val))
        except Exception as e:  # noqa: BLE001
            log.warning(f"[gpu_pool] 看门狗扫描占用失败: {e}")
            return 0
    else:
        stale = list(_local_ports.values()) + list(_local_gpus.values())
    # 去重，并排除本进程内仍然活跃的
    candidates = {t for t in stale if t not in _local}
    if not candidates:
        return 0

    try:
        async with async_db_session() as db:
            from sqlalchemy import select
            rows = (await db.execute(
                select(TrainTask.id, TrainTask.status).where(
                    TrainTask.id.in_(list(candidates))))).all()
    except Exception as e:  # noqa: BLE001
        log.warning(f"[gpu_pool] 看门狗查任务状态失败: {e}")
        return 0

    alive = {int(i) for i, s in rows if str(getattr(s, "value", s)) in _ALIVE_STATUSES}
    reaped = 0
    for tid in sorted(candidates - alive):
        await release(tid)
        log.warning(
            f"[gpu_pool] 看门狗：任务 {tid} 已是终态或已不存在，却仍占着资源，已回收"
            f"（容器被强杀或后端崩溃过）")
        reaped += 1
    return reaped


# ----------------------------------------------------------------- 租约


@asynccontextmanager
async def gpu_lease(task_id: int, need_mem_gb: float | None = None):
    """把「占一张够显存的卡」包成上下文管理器，拿不到就抛。

    给**已经走容器模式、但用的是进程内信号量**的路径（评估 / 预测 / 部署 /
    paddlex / ultralytics）统一换到本池上：它们的信号量只认「本进程里排队的
    几个任务」，看不见别的框架、更看不见平台外占着卡的人，于是训练（走本池）
    和评估（走信号量）可能同时抢同一张卡——**两套排队互不知情是必撞的**。

    典型用法（不改动原有缩进）::

        async with get_train_semaphore(), gpu_lease(eval_id, need_mem) as lease:
            container = await run_container(..., gpu_id=lease.device_ids)

    信号量保留作进程内的快速闸门：它拒绝得比本池快，而本池负责跨进程/跨机器
    的精确判定（Redis 原子分配 + NVML 可用显存）。
    """
    alloc = await acquire(task_id, need_gpu=1, need_mem_gb=need_mem_gb)
    if alloc is None:
        raise RuntimeError(
            f"等不到可用显存 ≥ {need_mem_gb or settings.TORKILN_GPU_MIN_FREE_GB:.1f}GB 的 GPU"
            f"（详见后端日志中 gpu_pool 的明细）。若确定机器上无人训练，可调低 "
            f"TORKILN_GPU_MIN_FREE_GB 或改任务的 resources.gpu_memory_gb"
        )
    try:
        yield alloc
    finally:
        await release(task_id)


# ----------------------------------------------------------------- 就绪


async def wait_service_ready(port: int, timeout: float | None = None) -> None:
    """轮询容器内服务的 ``/healthz`` 直到就绪。

    为什么必须轮询而不是只看容器状态：容器内服务冷启动要 ``import torch``
    （本机实测 **23.4 秒**），这段时间里容器一直是 running，但 HTTP 端口还没
    监听。此时提交作业只会拿到连接拒绝。

    ``/healthz`` 不带鉴权依赖，所以不需要 token。
    """
    limit = float(timeout if timeout is not None
                  else settings.TORKILN_JOB_READY_TIMEOUT)
    deadline = time.monotonic() + limit
    url = f"http://127.0.0.1:{port}/healthz"
    last = "未开始探测"
    import httpx

    async with httpx.AsyncClient(timeout=5.0) as client:
        while time.monotonic() < deadline:
            try:
                r = await client.get(url)
                if r.status_code == 200:
                    return
                last = f"HTTP {r.status_code}"
            except Exception as e:  # noqa: BLE001
                last = f"{type(e).__name__}"
            await asyncio.sleep(1.0)
    raise TimeoutError(
        f"TorchKiln job 容器在 {limit:.0f}s 内未就绪（最后状态：{last}）。"
        f"容器内服务 import torch 约需 20~30s；若确实更久，请调大 "
        f"TORKILN_JOB_READY_TIMEOUT 或查看该容器日志。"
    )
