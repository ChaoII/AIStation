"""验证保活机制：连续两次极小请求，看"冷 → 热"的差距（证明焐热有效）。"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


async def main() -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query.keepalive import _ping_once

    for i in (1, 2):
        ms = await _ping_once()
        print(f"  第 {i} 次 ping = {ms:.0f}ms", flush=True)


asyncio.run(main())
