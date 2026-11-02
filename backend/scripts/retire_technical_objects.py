"""把「平台自身元数据 / 备份表 / 系统表」从问数本体里停用（可逆）。

为什么
------
本体里混进了不少跟业务无关的表，它们**没有中文名**（name 就是表名），问数检索时
既召不回真业务表、又可能被列标签误命中——纯噪声：

- ``ai_*``：平台自己的元数据表（写作规则、管道、动作日志……），不是业务数据；
- ``*_BAK``：备份副本，和正表内容重复；
- ``sys_*``：系统表。

判断条件很保守（三个都要满足才停用）：
1. ``name`` 为空或等于 ``code``（说明它从来没有中文名，本来也匹配不上）；
2. **没有绑定指标**（有指标的说明是业务入口，不能动）；
3. 命中上面三类技术命名。

保留不动的（有意为之，别"顺手"扩大）：
- ``view_aikb_*`` / ``VIEW_*``：**视图是专门为问数建的**，恰恰是最该留的对象；
- ``annotation_*`` / ``train_*``：平台业务表，缺的是中文名（应该补名，不是停用）；
- ``FUEL_*`` 业务表：包括 ``CONTROLLOG`` 这类，仍属业务数据。

用法::

    cd backend
    uv run python scripts/retire_technical_objects.py            # 预览
    uv run python scripts/retire_technical_objects.py --apply    # 停用
    uv run python scripts/retire_technical_objects.py --revert   # 恢复启用
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.core.database import async_db_session

#: 平台自身元数据 / 系统表
_TECH_PREFIXES = ("ai_", "sys_")
#: 备份表
_TECH_SUFFIXES = ("_bak",)


def _reason(code: str) -> str:
    """命中哪条规则（空串 = 不是技术表）。"""
    low = (code or "").lower()
    for p in _TECH_PREFIXES:
        if low.startswith(p):
            return f"前缀 {p}*"
    for s in _TECH_SUFFIXES:
        if low.endswith(s):
            return f"后缀 *{s}"
    return ""


async def _candidates() -> list[tuple[str, str, str]]:
    """(code, name, reason) —— 未命名 + 无绑定指标 + 技术命名。"""
    async with async_db_session() as db:
        rows = (await db.execute(text(
            "SELECT o.code, coalesce(o.name,''), "
            "  (SELECT count(*) FROM ai_query_metrics m "
            "    WHERE m.object_code=o.code AND m.is_deleted=false) AS n_metric "
            "FROM ai_ont_object o "
            "WHERE o.is_deleted=false AND o.enabled=true "
            "  AND (o.name=o.code OR o.name IS NULL OR trim(o.name)='') "
            "ORDER BY o.code"))).fetchall()
    out = []
    for code, name, n_metric in rows:
        if n_metric:
            continue
        r = _reason(code)
        if r:
            out.append((code, name, r))
    return out


async def main() -> None:  # pragma: no cover - 运维脚本
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--apply", action="store_true", help="停用（enabled=false）")
    g.add_argument("--revert", action="store_true", help="恢复启用")
    args = ap.parse_args()

    rows = await _candidates()
    async with async_db_session() as db:
        before = (await db.execute(text(
            "SELECT count(*) FROM ai_ont_object WHERE is_deleted=false AND enabled=true"
        ))).scalar()

    print(f"当前启用对象={before}  命中技术表={len(rows)}\n")
    for code, name, reason in rows:
        print(f"  {code:34s} name={name:28s} ({reason})")

    if not (args.apply or args.revert):
        print("\n（预览模式；--apply 停用 / --revert 恢复）")
        return

    enable = bool(args.revert)
    async with async_db_session.begin() as db:
        for code, _n, _r in rows:
            await db.execute(text(
                "UPDATE ai_ont_object SET enabled=:e, updated_time=now() WHERE code=:c"),
                {"e": enable, "c": code})
    async with async_db_session() as db:
        after = (await db.execute(text(
            "SELECT count(*) FROM ai_ont_object WHERE is_deleted=false AND enabled=true"
        ))).scalar()
    verb = "恢复启用" if enable else "停用"
    print(f"\n已{verb} {len(rows)} 个对象；启用数 {before} → {after}（本体语义缓存 60 秒内过期）")


if __name__ == "__main__":
    asyncio.run(main())
