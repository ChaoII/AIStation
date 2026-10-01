"""作业容器内服务的就绪探测。

单独成模块是因为它和资源池**完全无关**：不分配端口、不碰 GPU、不读 Redis，
只发 HTTP 请求。它是「容器起来了但服务还没监听」这最后一公里的守门人，
混在 gpu_pool 里会让人误以为它也是调度的一部分。
"""

from __future__ import annotations

import asyncio
import time

from app.config.setting import settings


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
