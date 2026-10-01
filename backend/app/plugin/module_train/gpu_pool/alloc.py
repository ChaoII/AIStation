"""资源分配编排：把「一个端口 + N 张够显存的卡」作为一个整体借出/归还。

为什么单独成层
--------------
:mod:`.port` 与 :mod:`.device` 各自只管一种资源的认领，但对外必须是一个
**原子整体**：拿到端口却没拿到 GPU 时，端口要还回去（否则等待一轮之后它还挂在
这个 task_id 名下，下一轮永远抢不到——这是历史上真实发生过的泄漏）。
把「先端口后 GPU、失败回滚、轮询等待」这段顺序逻辑收在一处，就只有一处需要
在新增资源种类时修改。

对外的 :func:`acquire` / :func:`release` 保持与拆分前**完全一致的签名与语义**，
外部调用方（训练执行器、:mod:`.lease`、看门狗）无需改动。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.config.setting import settings
from app.core.logger import log

from . import _store
from . import device as device_mod
from . import port as port_mod
from ._store import LOCAL


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
        rd = await _store.redis_or_none()
        port = await port_mod.claim_port(task_id, rd)
        if port is None:
            # 端口比 GPU 更容易耗尽（段是固定的），先判断是不是该放弃了
            if not wait or (deadline and time.monotonic() >= deadline):
                log.error(f"[gpu_pool] 任务 {task_id} 拿不到端口 "
                          f"({settings.TORKILN_PORT_START}~{settings.TORKILN_PORT_END})")
                return None
            await asyncio.sleep(poll)
            continue

        # NVML 枚举只做一次：既用于分配，也用于「一张卡都枚举不到」的降级判断。
        # ⚠️ 走 device_mod.gpu_devices 而不是直接 import 名字：测试通过 patch
        #    模块属性来伪造 GPU 列表，直接 import 的绑定 patch 不到（转发层同款陷阱）。
        devices = device_mod.gpu_devices()
        if need_gpu > 0 and not devices:
            # 没有可枚举的 GPU（无驱动 / 容器内无 GPU / 缺 pynvml）：**不能死等**，
            # 否则这台机器上的训练任务会永远卡在排队。降级为不指定 --gpus，
            # 让容器按 Docker 自己的规则走（无 GPU 时会报可读的错误，
            # 而不是被平台判成「等不到卡」）。
            log.warning(f"[gpu_pool] 未探测到 GPU，任务 {task_id} 不指定 --gpus 降级运行")
            alloc = Allocation(task_id=task_id, port=port, via_redis=rd is not None)
            LOCAL[task_id] = alloc
            return alloc

        gpu_indices, gpu_uuids = await device_mod.claim_gpu(
            task_id, max(0, need_gpu), rd, devices, min_free)
        if need_gpu > 0 and len(gpu_indices) < need_gpu:
            # 显存不够：**端口和已认领的那几张卡都要还回去**，否则等待一轮之后
            # 它们还挂在这个 task_id 名下，下一轮永远抢不到（泄漏）。
            await device_mod.release_gpu_list(gpu_uuids, rd)
            await port_mod.release_port(port, rd)
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
        LOCAL[task_id] = alloc
        return alloc


async def release(task_id: int) -> None:
    """归还任务占用的全部资源。重复调用安全。"""
    alloc = LOCAL.pop(task_id, None)
    rd = await _store.redis_or_none()
    if alloc is None:
        # 进程重启后本地记录没了，仍要按 task_id 清理 Redis 上的残留。
        # 延迟导入：看门狗与本模块互相引用，顶层导入会成环。
        from .watchdog import cleanup_redis_by_task

        await cleanup_redis_by_task(task_id, rd)
        return
    await port_mod.release_port(alloc.port, rd)
    await device_mod.release_gpu_list(alloc.gpu_uuids, rd)
    log.info(f"[gpu_pool] 任务 {task_id} 释放：port={alloc.port} gpu={alloc.gpu_uuids}")


def allocation_of(task_id: int) -> Allocation | None:
    """取任务当前的资源（给恢复逻辑用；进程重启后为 None）。"""
    return LOCAL.get(task_id)
