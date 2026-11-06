"""旧权限 → 显式策略的迁移**入口**（2026-11 复审 I5）。

为什么要这个脚本
----------------
``policy.backfill.backfill_policies`` 早就实现并有单测覆盖，但**没有任何可执行入口**
—— 运维在切 ``shadow`` / ``enforce`` 前既不能预演影响面、也不能真正落地，
等于这条能力不存在。本脚本就是那唯一入口，口径与 ``query_policy_smoke.py`` 一致。

用法::

    cd backend
    uv run python scripts/query_policy_backfill.py --dry-run   # 只看影响面（不写库）
    uv run python scripts/query_policy_backfill.py --apply     # 真写策略 + 迁移台账

输出 ``created`` / ``skipped`` / ``by_source``；退出码非 0 即失败。

说明
----
- 需要**数据库**（``backend/env/.env.dev`` 的 PG；worktree 里先拷环境文件），
  不需要起后端服务；连不上库会明确报错并退出 1；
- ``--apply`` 幂等：判重靠 ``ai_policy_migration`` 台账，重复执行只补新增的旧数据；
- ``--dry-run`` **连迁移台账都不建**，只做规划（切 enforce 前评估影响面用）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

# ``python scripts/xxx.py`` 只把 scripts/ 放进 sys.path，backend 根目录不在里面。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Windows 控制台默认 GBK：输出 ✅/❌ 会 UnicodeEncodeError 把脚本炸掉。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 非终端/被重定向时没有 reconfigure
        pass

# 必须在 import app.* 之前设置：Settings 用 ``.env.{ENVIRONMENT}`` 定位环境文件。
os.environ.setdefault("ENVIRONMENT", "dev")


def _load_orm_models() -> None:
    """先导入 ``UserModel``：策略/设置模型的关系（created_by/updated_by）指向它。

    缺了它 mapper 配置直接 ``InvalidRequestError: expression 'UserModel' failed to
    locate a name``（与冒烟脚本同一个坑）。
    """
    from app.api.v1.module_system.user.model import UserModel  # noqa: F401


def _print_report(result: dict, *, apply: bool) -> None:
    created = int(result.get("created") or 0)
    skipped = list(result.get("skipped") or [])
    by_source = result.get("by_source") or {}

    print()
    print(f"{'✅ 已落地' if apply else '🔍 预演（未写库）'}")
    print(f"   新建策略 created = {created}")
    print(f"   跳过条目 skipped = {len(skipped)}")
    print(f"   按来源 by_source = {json.dumps(by_source, ensure_ascii=False)}")
    for item in skipped[:20]:
        source = item.get("source") or "(未知)"
        reason = item.get("reason") or ""
        extra = {
            k: v for k, v in item.items() if k not in ("source", "reason")
        }
        tail = f" {json.dumps(extra, ensure_ascii=False)}" if extra else ""
        print(f"   - [{source}] {reason}{tail}")
    if len(skipped) > 20:
        print(f"   …… 其余 {len(skipped) - 20} 条略（完整明细见日志）")


async def main() -> int:
    ap = argparse.ArgumentParser(
        description="把旧权限机制迁移成显式 ai_policy（幂等）"
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="只规划、不写库（也不建台账）")
    mode.add_argument("--apply", action="store_true", help="真的写策略 + 迁移台账")
    args = ap.parse_args()

    started = time.perf_counter()
    _load_orm_models()

    from app.plugin.module_ai.query.policy.backfill import backfill_policies

    try:
        if args.apply:
            # 策略表必须先存在（幂等建表）
            from app.plugin.module_ai.query.policy.model import ensure_policy_tables

            await ensure_policy_tables()
        result = await backfill_policies(dry_run=bool(args.dry_run))
    except Exception as e:  # noqa: BLE001
        print(f"❌ 迁移失败：{type(e).__name__}: {e}")
        print("   本脚本不需要 HTTP 服务，但需要可用的数据库：")
        print("   - 确认 PG 在跑、backend/env/.env.dev 存在（worktree 里先拷一份）；")
        print("   - 连不上时不做任何写入，直接退出 1。")
        return 1

    _print_report(result, apply=bool(args.apply))
    elapsed = time.perf_counter() - started
    print(f"\n{'✅' if args.apply else '🔍'} 完成（{elapsed:.1f}s）")
    if args.dry_run:
        print("   下一步：确认影响面后执行 --apply 落地。")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
