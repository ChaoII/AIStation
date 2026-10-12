"""探针：极小 prompt 的单次调用延迟分布 —— 判定「是网关/推理侧慢」还是「我们的请求慢」。

如果连 10 个字的请求都会偶发几十秒/几百秒 → 与 prompt 无关，是网关/推理侧排队。
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

N = 6


async def main() -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query.service import AiQueryService

    runtime = await AiQueryService._get_runtime()
    print(f"模型={runtime.get('model')} base_url={runtime.get('base_url')}", flush=True)

    ts: list[float] = []
    for i in range(N):
        t0 = time.perf_counter()
        try:
            out = await AiQueryService._plan_llm("只回答：1+1=?", runtime, 0.0)
            dt = time.perf_counter() - t0
            ts.append(dt)
            print(f"  #{i+1} {dt:7.2f}s  回答={str(out)[:30]!r}", flush=True)
        except Exception as e:  # noqa: BLE001
            dt = time.perf_counter() - t0
            ts.append(dt)
            print(f"  #{i+1} {dt:7.2f}s  失败={type(e).__name__}: {str(e)[:60]}", flush=True)

    ts.sort()
    print(f"\n极小请求：中位={ts[len(ts)//2]:.2f}s 最短={ts[0]:.2f}s 最长={ts[-1]:.2f}s", flush=True)
    if ts[-1] > 30:
        print("→ **极小请求也偶发 30s+** ⇒ 网关/推理侧排队或 stall，与 prompt 大小无关", flush=True)
    else:
        print("→ 极小请求都很快 ⇒ 慢在我们发的请求/解析链路上", flush=True)


asyncio.run(main())
