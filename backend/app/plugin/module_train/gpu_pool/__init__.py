"""GPU / 端口资源池——「每任务一容器」模式下的调度。

为什么需要它
------------
TorchKiln 服务不再常驻：每个任务起一个独立容器，容器内跑完整的 TorchKiln
服务并监听 8000，映射到宿主机的不同端口。带来两个必须集中管理的东西：

- **端口**：每个任务占一个宿主端口，必须唯一且及时回收；
- **GPU**：单卡机器上同时只能跑一个训练（多卡也有限），必须有地方排队。

空闲判定必须**双条件**，缺一不可（细节见 :mod:`.device` 与 :mod:`.port`）。

Redis 不可用时**降级到进程内字典**：此时端口安全（仍然真实 bind 探测），
GPU 可能被多 worker 超发——宁可放行也不要因为 Redis 挂了就完全不能训练。

模块划分
--------
这个文件原本是 505 行的单文件，承担了七类互不相干的职责：存储后端、端口池、
GPU 探测、分配编排、租约、就绪探测、看门狗。拆分后的依赖是单向的 DAG::

    _store  ─┬─>  port
             └─>  device ─┐
                          ├─>  alloc ─┬─>  lease
                          │           └─>  watchdog
                          └─────────────>  watchdog
    readiness  （与资源池无关，独立）

为什么要拆：一个文件里混着「Redis 不可用时怎么降级」「NVML 枚举失败怎么办」
「容器冷启动要等多久」三类知识，改任何一处都要通读全文；而这三类知识的**变化
频率与风险完全不同**（部署环境变 vs 框架升�� vs 镜像变大）。

本模块是**转发层**：所有名字都从这里再导出一次，因此外部
``from .gpu_pool import acquire, release`` 与 ``gpu_pool.acquire(...)``
两种用法都不需要改。转发必须**显式列出**（不能靠 ``from .x import *``），
因为 :func:`_store.redis_or_none` 这类私有名不进 ``__all__``，而测试和若干
调用点仍在引用它们。

⚠️ **转发层是别名，不是函数包装**。被调用方按**自己模块的全局**查找名字，
所以 patch ``gpu_pool.gpu_devices`` 不会影响真正调用它的 :mod:`.alloc`。
要伪造 GPU 列表，请 patch ``gpu_pool.device.gpu_devices``；要强制走 Redis 降级，
请 patch ``gpu_pool._store.redis_or_none``。这一点有测试守卫。
"""

from __future__ import annotations

from . import _store, alloc, device, lease, port, readiness, watchdog

# ---- 存储层 ----------------------------------------------------------------
from ._store import (
    K_GPU,
    K_PORT,
    LOCAL,
    LOCAL_GPUS,
    LOCAL_PORTS,
    OCCUPIED_TTL,
    redis_or_none,
)

# ---- 分配编排 ---------------------------------------------------------------
from .alloc import Allocation, acquire, allocation_of, release

# ---- GPU 探测与认领 ---------------------------------------------------------
from .device import claim_gpu, gpu_devices, release_gpu_list

# ---- 租约 / 就绪 / 看门狗 ---------------------------------------------------
from .lease import gpu_lease

# ---- 端口池 ----------------------------------------------------------------
from .port import claim_port, port_bindable, release_port
from .readiness import wait_service_ready
from .watchdog import (
    ALIVE_STATUSES,
    busy_task_count,
    cleanup_redis_by_task,
    reap_stale,
)

#: 拆分前的私有名，保留别名以便旧调用点继续工作（名字都变了：加前缀、下划线保留）。
#: ⚠️ 这些只是**绑定**：真正的实现仍在上面那些模块里，patch 它们请 patch 原模块。
_K_PORT = K_PORT
_K_GPU = K_GPU
_OCCUPIED_TTL = OCCUPIED_TTL
_local = LOCAL
_local_ports = LOCAL_PORTS
_local_gpus = LOCAL_GPUS
_redis = redis_or_none
_port_bindable = port_bindable
_claim_port = claim_port
_claim_gpu = claim_gpu
_release_gpu_list = release_gpu_list
_release_port = release_port
_cleanup_redis_by_task = cleanup_redis_by_task
_ALIVE_STATUSES = ALIVE_STATUSES

__all__ = [
    # 存储层
    "K_PORT", "K_GPU", "OCCUPIED_TTL", "LOCAL", "LOCAL_PORTS", "LOCAL_GPUS",
    "redis_or_none",
    # 端口
    "port_bindable", "claim_port", "release_port",
    # GPU
    "gpu_devices", "claim_gpu", "release_gpu_list",
    # 分配
    "Allocation", "acquire", "release", "allocation_of",
    # 租约 / 就绪 / 看门狗
    "gpu_lease", "wait_service_ready",
    "busy_task_count", "reap_stale", "cleanup_redis_by_task", "ALIVE_STATUSES",
    # 子模块（供测试 patch 用：monkeypatch.setattr(gpu_pool.device, ...)）
    "_store", "alloc", "device", "lease", "port", "readiness", "watchdog",
]
