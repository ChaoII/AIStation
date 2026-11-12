"""按计划文件处置指标：停用 / 改名。

为什么做成脚本：31 条要处置，逐条在界面上点容易漏、也难复核；计划放在 JSON 里
（`scripts/plans/*.json`），脚本只负责**执行**，不内置任何业务语义。

用法：
    python scripts/apply_metric_plan.py --plan scripts/plans/metric_plan_2026-11-13.json
    python scripts/apply_metric_plan.py --plan ... --apply
    python scripts/apply_metric_plan.py --plan ... --apply --only disable

规则：
- 默认 **dry-run**，只打印将要发生什么；
- `action=confirm` 一律跳过（字段含义待业务确认）；
- 目标指标必须存在且当前启用，否则整体失败（避免静默漏改）；
- 改名后指标名重复会报错（重名会让匹配歧义）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

from sqlalchemy import text  # noqa: E402

from app.core.database import async_db_session  # noqa: E402


def load_plan(path: str) -> dict:
    return json.loads(open(path, encoding="utf-8").read())


async def run(plan: dict, apply: bool, only: str | None) -> int:
    datasource = plan.get("datasource") or "ds:6"
    items = [it for it in plan.get("items") or [] if it.get("key")]
    if only:
        items = [it for it in items if it.get("action") == only]

    async with async_db_session() as db:
        rows = (await db.execute(text(
            "SELECT key, name, enabled FROM ai_query_metrics "
            "WHERE is_deleted=false AND datasource=:d"
        ), {"d": datasource})).fetchall()
    cur = {str(k): {"name": n, "enabled": bool(e)} for k, n, e in rows}

    errors: list[str] = []
    for it in items:
        if it["action"] == "confirm":
            continue
        if it["key"] not in cur:
            errors.append(f"指标不存在：{it['key']}")
        elif not cur[it["key"]]["enabled"]:
            errors.append(f"指标已停用（请确认是否重复处置）：{it['key']}")
        elif it["action"] == "rename" and not str(it.get("new_name") or "").strip():
            errors.append(f"缺少 new_name：{it['key']}")

    want_names: dict[str, str] = {}
    for it in items:
        if it["action"] != "rename":
            continue
        name = str(it.get("new_name") or "").strip()
        if name:
            if name in want_names:
                errors.append(f"改名重复：{name}（{want_names[name]} / {it['key']}）")
            want_names[name] = it["key"]
    existing_names = {v["name"]: k for k, v in cur.items()}
    for name, key in want_names.items():
        owner = existing_names.get(name)
        if owner and owner != key:
            errors.append(f"改名后与现有指标重名：{name}（已被 {owner} 使用）")

    if errors:
        print("PLAN_INVALID")
        for e in errors:
            print("  -", e)
        return 2

    counts = {"disable": 0, "rename": 0, "confirm": 0, "skip": 0}
    for it in items:
        action = it["action"]
        if action == "confirm":
            counts["confirm"] += 1
            print(f"[待确认] {it['name']}  → 建议 {it.get('suggest_name') or '（见 reason）'}")
            print(f"           {it.get('reason') or ''}")
            continue
        if action == "disable":
            counts["disable"] += 1
            print(f"[停用] {it['name']}  ({it['key']})")
        elif action == "rename":
            counts["rename"] += 1
            print(f"[改名] {it['name']}  →  {it['new_name']}")
        else:
            counts["skip"] += 1
            print(f"[跳过] 未知 action={action}: {it['key']}")

    print(
        "SUMMARY",
        f"disable={counts['disable']} rename={counts['rename']} "
        f"confirm={counts['confirm']} skip={counts['skip']}",
    )
    if not apply:
        print("DRY_RUN（加 --apply 才会写库）")
        return 0

    changed = {"disable": 0, "rename": 0}
    async with async_db_session.begin() as db:
        for it in items:
            if it["action"] == "disable":
                res = await db.execute(text(
                    "UPDATE ai_query_metrics SET enabled=false, updated_time=CURRENT_TIMESTAMP "
                    "WHERE key=:k AND datasource=:d AND is_deleted=false"
                ), {"k": it["key"], "d": datasource})
                changed["disable"] += res.rowcount or 0
            elif it["action"] == "rename":
                res = await db.execute(text(
                    "UPDATE ai_query_metrics SET name=:n, updated_time=CURRENT_TIMESTAMP "
                    "WHERE key=:k AND datasource=:d AND is_deleted=false"
                ), {"n": str(it["new_name"]).strip(), "k": it["key"], "d": datasource})
                changed["rename"] += res.rowcount or 0
    print("APPLIED", changed)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="按计划处置指标（默认 dry-run）")
    ap.add_argument("--plan", required=True, help="计划 JSON 路径")
    ap.add_argument("--apply", action="store_true", help="真正写库")
    ap.add_argument("--only", choices=["disable", "rename"], help="只执行某一类动作")
    args = ap.parse_args()

    from main import create_app

    create_app()
    return asyncio.run(run(load_plan(args.plan), args.apply, args.only))


if __name__ == "__main__":
    raise SystemExit(main())
