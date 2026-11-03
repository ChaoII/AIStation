"""给燃料业务表补**字段级敏感标记**（本体为准，同时同步资产侧，避免两套口径打架）。

背景
----
字段级 ACL 的链路是通的（`semantic.sensitive_fields()` → `_execute_one` fail-closed），
但**燃料域一条敏感字段都没有**：20 条标记全在 `SYS_*` / `ai_*` / `JIMU_*` / `OPS_*`。
也就是说，合约金额、单价、运费这些字段目前对普通用户是**敞开的** ——
不是机制没做，是数据没填。

判定规则（保守，宁少勿多）
--------------------------
只看**字段中文名/描述**里出现这些词：金额、单价、价格、成本、税款、运费、利润、
账户、银行、联系电话、手机号、身份证、联系人、地址。
纯数字统计字段（数量/吨数/占比）一律不算。

用法::

    cd backend
    uv run python scripts/seed_fuel_sensitive_fields.py            # 预览
    uv run python scripts/seed_fuel_sensitive_fields.py --apply    # 写库
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.core.database import async_db_session

#: 命中即视为敏感（宁可漏，不可误伤普通统计字段）
HINTS = (
    "金额", "单价", "价格", "成本", "税款", "税价", "运费", "利润",
    "账户", "银行", "电话", "手机", "身份证", "联系人", "地址",
)
#: 明确排除：这些词里也含"价/费"，但统计口径无关
EXCLUDE = ("数量", "吨数", "占比", "比例", "次数", "条数", "个数")


#: 说明性字段：名字本身就是"说明/备注/条款"，不是可被统计的金额值
_DESCRIPTIVE = ("说明", "备注", "描述", "条款", "解释", "tooltip")


def _hit(name: str, desc: str) -> str:
    if any(x in (name or "").lower() for x in _DESCRIPTIVE):
        return ""
    hay = f"{name} {desc}"
    if any(x in hay for x in EXCLUDE) and not any(
            x in hay for x in ("金额", "单价", "价格", "账户", "银行")):
        return ""
    for h in HINTS:
        if h in hay:
            return h
    return ""


async def main() -> None:  # pragma: no cover - 运维脚本
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    async with async_db_session() as db:
        rows = (await db.execute(text(
            "SELECT p.object_code, p.code, coalesce(p.name,''), coalesce(p.description,''), "
            "       p.sensitive "
            "FROM ai_ont_property p "
            "JOIN ai_ont_object o ON o.code = p.object_code AND o.is_deleted = false "
            "WHERE p.is_deleted = false AND o.backing_table LIKE 'FUEL%' "
            "ORDER BY p.object_code, p.code"))).fetchall()

    picks: list[tuple[str, str, str]] = []
    for code, prop, name, desc, sens in rows:
        if sens:
            continue
        why = _hit(name or prop, desc)
        if why:
            picks.append((code, prop, f"{name or prop}（命中「{why}」）"))

    print(f"燃料对象属性总数={len(rows)}  本次将标记={len(picks)}\n")
    for obj, prop, label in picks[:40]:
        print(f"  {obj}.{prop:<26} {label}")
    if len(picks) > 40:
        print(f"  …… 其余 {len(picks) - 40} 条略")

    if not args.apply:
        print("\n（预览模式；--apply 写库）")
        return
    if not picks:
        return

    async with async_db_session.begin() as db:
        for obj, prop, _ in picks:
            await db.execute(text(
                "UPDATE ai_ont_property SET sensitive=true "
                "WHERE object_code=:o AND code=:c AND is_deleted=false"),
                {"o": obj, "c": prop})
            # 资产侧同步（两套标记不一致时，资产页与本体页会互相矛盾）
            await db.execute(text(
                "UPDATE ai_query_asset_columns SET sensitive=true "
                "WHERE table_name=(SELECT backing_table FROM ai_ont_object WHERE code=:o) "
                "AND column_name=:c AND is_deleted=false"),
                {"o": obj, "c": prop})
    print(f"\n已标记 {len(picks)} 个敏感字段（本体 + 资产两处同步）")


if __name__ == "__main__":
    asyncio.run(main())
