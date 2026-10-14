"""大模型自动建模：对指定数据源生成绑定型指标 / 对象标注。

用法（backend 下）::

    python scripts/_auto_model.py --metrics [--dry]
    python scripts/_auto_model.py --annotate
    python scripts/_auto_model.py --all
    # 默认数据源 ds:4（燃煤业务库）
"""
from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS = "ds:4"
AUTH = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))


async def main() -> None:
    from main import create_app

    create_app()
    from app.scripts.init_app import _ensure_missing_columns
    from app.plugin.module_ai.query import modeling as M

    await _ensure_missing_columns()

    do_metrics = "--annotate" not in sys.argv or "--all" in sys.argv or "--metrics" in sys.argv
    do_annotate = "--annotate" in sys.argv or "--all" in sys.argv
    dry = "--dry" in sys.argv

    if do_metrics:
        print(f"===== 自动生成绑定型指标（{DS}{'，dry' if dry else ''}）=====")
        out = await M.generate_metrics(DS, AUTH, max_objects=12, dry=dry)
        print(f"  解析={out['parsed']} 通过/落库={out['saved']} 拒绝={out['rejected']}")
        for r in out.get("reasons") or []:
            print(f"    拒绝：{r}")

    if do_annotate:
        gen = getattr(M, "generate_annotations", None)
        if gen is None:
            print("（标注生成尚未实现，跳过）")
        else:
            print(f"===== 自动标注对象/属性（{DS}）=====")
            out = await gen(DS, AUTH, max_objects=12)
            print(f"  {out}")


asyncio.run(main())
