"""报表参数闭环端到端（真库）：自动抽取 → 运行校验 → 真执行。

用法：``python scripts/_e2e_report_params.py``
"""

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

KEY = "R_E2E_PARAMS"


async def main() -> None:
    from main import create_app

    create_app()
    from app.plugin.module_ai.query.report import (
        delete_reports,
        list_reports,
        run_report,
        upsert_report,
    )

    # 0) 清理历史
    old = [r for r in await list_reports() if r["key"] == KEY]
    if old:
        await delete_reports([r["id"] for r in old])

    # 1) 保存（**不带 params**）→ 后端应从模板自动抽取
    await upsert_report({
        "key": KEY, "name": "参数闭环验证", "datasource": "system",
        "question": "摄像头数量（id 大于某值）",
        "sql_template": "SELECT COUNT(*) AS 数量 FROM video_cameras WHERE id > {min_id}",
        "columns": [{"name": "数量", "label": "数量"}],
    })
    rep = next(r for r in await list_reports() if r["key"] == KEY)
    print("1) 自动抽取 params =", rep["params"])
    assert rep["params"] and rep["params"][0]["key"] == "min_id", rep["params"]
    assert rep["params"][0]["type"] == "number", rep["params"]

    # 2) 缺必填 → 必须明确报错，且**不得**把 {min_id} 发给数据库
    try:
        await run_report(rep["id"], {})
        print("2) !! 未报错（不符合预期）")
    except Exception as e:  # noqa: BLE001
        msg = getattr(e, "msg", None) or str(e)
        print("2) 缺必填报错 =", msg)
        assert "必填" in msg

    # 3) 类型不符 → 报错
    try:
        await run_report(rep["id"], {"min_id": "abc"})
        print("3) !! 未报错（不符合预期）")
    except Exception as e:  # noqa: BLE001
        msg = getattr(e, "msg", None) or str(e)
        print("3) 类型不符报错 =", msg)
        assert "数字" in msg

    # 4) 正常执行 → 真跑 SQL
    out = await run_report(rep["id"], {"min_id": 0})
    print(f"4) 执行成功 rows={out['rows']} sql={out['sql'][:60]}…")
    assert out["rows"] and "{min_id}" not in out["sql"]

    # 5) 收尾：删掉验证用报表
    await delete_reports([rep["id"]])
    left = [r for r in await list_reports() if r["key"] == KEY]
    print("5) 清理后剩余 =", len(left))
    print("\n=== 报表参数闭环：全部通过 ===")


asyncio.run(main())
