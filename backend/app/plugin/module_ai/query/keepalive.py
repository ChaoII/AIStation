"""LLM 保活：定期给模型发一个**极小**请求，避免"冷启动"把首次问数拖到 30 秒。

实测（同一后端进程）：
- 后端重启后**第一次**问数的 agno 调用 = **29.7 秒**
- 紧接着的重试（同题）       = **1.8 秒**

差别就是模型/网关的冷启动。用周期性的极小请求把它焐热，用户就不用替我们等预热。

配置：
- ``llm_keepalive_enabled``（默认 true）
- ``llm_keepalive_interval``（默认 240 秒；下限 30 秒）

注意：**必须走 agno**（平台硬约束），这里复用问数自身的生成入口，不新开调用链路。
"""

from __future__ import annotations

import asyncio
import time

from app.core.logger import log


async def _ping_once() -> float:
    """发一次极小请求，返回耗时（毫秒）。"""
    from .service import AiQueryService

    rt = await AiQueryService._get_runtime()
    t0 = time.perf_counter()
    await AiQueryService._plan_llm("ping", rt, 0.0)
    return (time.perf_counter() - t0) * 1000


async def start_llm_keepalive() -> None:
    """周期焐热模型。**任何异常都不得影响主进程**（保活只是优化，不是功能）。"""
    from .service import AiQueryService

    # 先让后端启动流程走完，避免和初始化抢资源
    await asyncio.sleep(30)
    while True:
        try:
            cfg = await AiQueryService._cfg()
            if not AiQueryService._cfg_bool(cfg, "llm_keepalive_enabled", True):
                await asyncio.sleep(60)
                continue
            ms = await _ping_once()
            interval = max(30, AiQueryService._cfg_int(cfg, "llm_keepalive_interval", 240))
            log.warning("[keepalive] 模型焐热 ok {}ms（下次 {}s 后）", int(ms), interval)
        except Exception as e:  # noqa: BLE001
            # 焐热失败不能刷屏、更不能退出循环；缩短间隔下次再试
            log.warning("[keepalive] 焐热失败（忽略）: {}", str(e)[:120])
            interval = 120
        await asyncio.sleep(interval)
