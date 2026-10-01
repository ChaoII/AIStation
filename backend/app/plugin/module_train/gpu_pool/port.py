"""端口池：给每个任务容器一个唯一的宿主端口。

双重判据，缺一不可
------------------
1. **调度层**（Redis / 进程内字典）：该端口没有活跃作业占用；
2. **资源层**（真实 bind 探测）：这个端口在本机确实绑得上。

只查第 1 条会撞车：占用的进程可能已异常退出（TTL 还没到），或者这个端口本来
就被本机别的服务占了。只做第 2 条则会与别的平台实例抢同一端口。

第 2 条是**最终依据**——即便 Redis 说空闲，也一定要真探测。
"""

from __future__ import annotations

import contextlib
import socket

from app.config.setting import settings
from app.core.logger import log

from ._store import K_PORT, LOCAL_PORTS, OCCUPIED_TTL


def port_bindable(port: int) -> bool:
    """真实 bind 探测端口是否可用。

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


async def claim_port(task_id: int, rd) -> int | None:
    """认领一个端口。段被占满返回 ``None``。

    扫描顺序固定为**从小到大**，所以低端口先被占；这是刻意的——端口号本身没有
    含义，稳定顺序让「同一个任务重跑两次拿到同一个端口」成为可能，排障时省事。
    """
    start, end = int(settings.TORKILN_PORT_START), int(settings.TORKILN_PORT_END)
    if end < start:
        log.error(f"[gpu_pool] 端口段配置非法: {start}~{end}")
        return None
    for port in range(start, end + 1):
        if rd is not None:
            ok = await rd.set(f"{K_PORT}{port}", str(task_id),
                              nx=True, ex=OCCUPIED_TTL)
            if not ok:
                continue
            # Redis 说空闲，但仍要真探测：可能已被本机其它进程占用
            if not port_bindable(port):
                await rd.delete(f"{K_PORT}{port}")
                continue
        else:
            if port in LOCAL_PORTS:
                continue
            if not port_bindable(port):
                continue
            LOCAL_PORTS[port] = task_id
        return port
    return None


async def release_port(port: int, rd) -> None:
    """归还端口。两种后端都清——进程内那份不能因为「Redis 可用」就留着，
    否则同一进程后续的探测会把刚释放的端口误判成「已被自己某个任务占用」。"""
    if rd is not None:
        with contextlib.suppress(Exception):
            await rd.delete(f"{K_PORT}{port}")
    LOCAL_PORTS.pop(port, None)
