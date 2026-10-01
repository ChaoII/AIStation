"""GPU 探测与认领（NVML）。

空闲判定必须**双条件**，缺一不可：

======================  ==========================================  ==================
层                      判据                                        缺了会怎样
======================  ==========================================  ==================
调度层                  Redis 里该卡没有活跃作业占用                 平台自己超发，两个
                                                                  任务抢同一张卡
资源层                  NVML 读可用显存 ≥ 本次需要                   漏掉**平台外**的
                                                                  占用者（用户手动
                                                                  起的调试容器、其它
                                                                  框架的训练容器）
======================  ==========================================  ==================

只看调度层会撞上外部占用；只看资源层会被瞬时抖动误导（训练进程刚起也占几百 MB）。

NVML 不可用（没装驱动 / 容器内无 GPU / 缺 pynvml）时枚举返回**空列表**，
调用方据此走「不指定 ``--gpus``」分支，而不是把训练判死——让容器按 Docker 自己
的规则报错，那条信息比「等不到卡」有��用得多。
"""

from __future__ import annotations

import contextlib

from app.config.setting import settings
from app.core.logger import log

from ._store import K_GPU, LOCAL_GPUS, OCCUPIED_TTL


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


async def claim_gpu(task_id: int, need: int, rd,
                    devices: list[dict], need_mem_gb: float) -> tuple[list[int], list[str]]:
    """认领 ``need`` 张**可用显存够**的卡。

    判据是**可用显存绝对值**而不是「已用占比 < x%」——后者在带桌面环境的
    Windows 上永远不成立：实测本机 dwm.exe + Edge 硬件加速就常驻占 3.2GB（20%），
    一个正在训练的进程反而只占 28%，按占比判会得出「卡被占满、不敢派活」，
    于是平台在这台机器上永远排队。绝对值直接回答「这张卡装不装得下这次训练」。

    认领后**再复查一次**显存：Redis ``SET NX`` 与外部进程启动之间存在窗口，
    不复查就会把一张刚被别人抢走的卡派出去。
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
            ok = await rd.set(f"{K_GPU}{uuid}", str(task_id),
                              nx=True, ex=OCCUPIED_TTL)
            if not ok:
                continue
            # Redis 认领期间显存可能被抢走（外部进程刚好启动），复查一次
            if dev["used_ratio"] > max_used_ratio or dev["free_gb"] < need_mem_gb:
                await rd.delete(f"{K_GPU}{uuid}")
                continue
        else:
            if uuid in LOCAL_GPUS:
                continue
            LOCAL_GPUS[uuid] = task_id
        indices.append(dev["index"])
        uuids.append(uuid)
    return indices, uuids


async def release_gpu_list(uuids: list[str], rd) -> None:
    """归还一批 GPU 认领。两种后端都清。"""
    for uuid in uuids:
        if rd is not None:
            with contextlib.suppress(Exception):
                await rd.delete(f"{K_GPU}{uuid}")
        LOCAL_GPUS.pop(uuid, None)
