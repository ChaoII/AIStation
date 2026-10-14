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
    size = 12
    batches = 1
    if "--size" in sys.argv:
        i = sys.argv.index("--size")
        size = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 12
    if "--batches" in sys.argv:
        i = sys.argv.index("--batches")
        batches = int(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 1

    if do_metrics:
        print(f"===== 自动生成绑定型指标（{DS}{'，dry' if dry else ''}，"
              f"{batches} 批 × {size} 对象）=====")
        saved = rejected = parsed = 0
        for k in range(batches):
            out = await M.generate_metrics(DS, AUTH, max_objects=size, dry=dry, offset=k * size)
            parsed += out.get("parsed", 0)
            saved += out.get("saved", 0)
            rejected += out.get("rejected", 0)
            print(f"  批次 {k + 1}/{batches}：解析={out.get('parsed')} "
                  f"落库={out.get('saved')} 拒绝={out.get('rejected')}")
            for r in (out.get("reasons") or [])[:3]:
                print(f"    拒绝：{r}")
        print(f"  指标合计：解析 {parsed} / 落库 {saved} / 拒绝 {rejected}")

    if do_annotate:
        gen = getattr(M, "generate_annotations", None)
        if gen is None:
            print("（标注生成尚未实现，跳过）")
        else:
            print(f"===== 自动标注对象/属性（{DS}，{batches} 批 × {size} 对象）=====")
            tot = 0
            for k in range(batches):
                out = await gen(DS, AUTH, max_objects=size, offset=k * size)
                tot += out.get("saved", 0)
                print(f"  批次 {k + 1}/{batches}：{out}")
            print(f"  标注合计落库 {tot}")


asyncio.run(main())
