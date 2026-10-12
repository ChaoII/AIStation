"""回归验证：asyncio 导入修复后，慢路径必须能真实跑通（我曾把主链路弄坏过）。"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


async def main() -> None:
    from app.plugin.module_ai.query import service as S

    print("asyncio 已导入:", hasattr(S, "asyncio"), flush=True)
    from main import create_app

    create_app()
    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
    t0 = time.perf_counter()
    d = await S.AiQueryService.ask(
        "统计每个摄像头的告警数量", auth, None, "system", force_slow=True
    )
    print(f"真实慢路径: {time.perf_counter() - t0:.1f}s "
          f"is_error={d.get('is_error')} rows={len(d.get('rows') or [])}", flush=True)
    print("summary:", str(d.get("summary"))[:70], flush=True)
    assert not d.get("is_error"), "慢路径仍报错！"


asyncio.run(main())
