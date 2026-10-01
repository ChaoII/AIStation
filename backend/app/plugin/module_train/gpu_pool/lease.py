"""GPU 租约：把「占一张够显存的卡」包成上下文管理器，拿不到就抛。

给**已经走容器模式、但用的是进程内信号量**的路径（评估 / 预测 / 部署）
统一换到本池上：它们的信号量只认「本进程里排队的几个任务」，看不见别的框架、
更看不见平台外占着卡的人，于是训练（走本池）和评估（走信号量）可能同时抢同一张
卡——**两套排队互不知情是必撞的**。

信号量保留作进程内的快速闸门：它拒绝得比本池快，而本池负责跨进程/跨机器的精确
判定（Redis 原子分配 + NVML 可用显存）。两层分工见
:mod:`app.plugin.module_train.concurrency`。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from app.config.setting import settings

from .alloc import acquire, release


@asynccontextmanager
async def gpu_lease(task_id: int, need_mem_gb: float | None = None):
    """把「占一张够显存的卡」包成上下文管理器，拿不到就抛。

    典型用法（不改动原有缩进）::

        async with get_train_semaphore(), gpu_lease(eval_id, need_mem) as lease:
            container = await run_container(..., gpu_id=lease.device_ids)
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
