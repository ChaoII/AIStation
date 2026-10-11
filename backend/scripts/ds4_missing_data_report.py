"""生成 ds:4「缺数据清单」文档（业务表里 0 行的），供人工补数。

用法（backend 下）::

    python scripts/ds4_missing_data_report.py --out ../docs/ds4-missing-data.md
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", os.environ.get("ENVIRONMENT", "dev"))
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

DS_ID = 4
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ds4_table_scope_report import classify  # noqa: E402

#: 子域 → 判定（按表名前缀片段，顺序敏感）
SUBDOMAINS: list[tuple[str, tuple[str, ...]]] = [
    ("采购与结算", ("COALBALANCE", "COALCONTRACT", "CONTRACTTEMP", "QUALITYSETTING", "PURCHASE",
                    "BUYFUEL", "OPTSUPPLIER", "SUPPLIER", "MINE", "MZSTORAGE")),
    ("化验与煤质", ("ASSAY", "FUELQUALITY", "PROXIMATE", "SULFUR", "MOISTURE", "HEAT", "ELEMENT",
                    "ASHFUSION", "TEMPERATURE", "QUALITY")),
    ("采样制样", ("SAMPL", "MAKE", "RCCOAL", "RCSAMPLING", "RLSAMPLING")),
    ("煤场与库存", ("STORAGE", "STG_", "BUNKER", "SILO", "DEPOSIT", "INVENTORY", "ALLIN", "ALLOUT",
                    "COALCONFIG", "MIX_")),
    ("入炉与耗用", ("INFURNACE", "INCOAL", "OUTCOAL", "DAYCOAL", "PMY", "CONSUM")),
    ("运输与计量", ("TRANSPORT", "TRUCK", "WEIGHT", "BELT", "DISCHARGE", "GOODS", "AUTOTRUCK",
                    "CAR", "EPCCARD", "SIGNAL")),
    ("计划与报表", ("PLAN", "REPORT", "COST", "FACTORYCOST", "PURCHASEMONTH")),
    ("组织与基础", ("DTXY", "FR_", "CMMS_", "EQUIPMENT", "STATION", "MINE")),
]


def subdomain(name: str) -> str:
    n = str(name).upper()
    for label, keys in SUBDOMAINS:
        if any(k in n for k in keys):
            return label
    return "其它业务"


async def main(out_path: str) -> None:
    from main import create_app

    create_app()
    from sqlalchemy import text

    from app.core.database import async_db_session
    from app.plugin.module_ai.query import executor as _ex
    from app.plugin.module_ai.query.service import _ds_cfg_from_model, _load_ds

    ds = await _load_ds(DS_ID)
    cfg = _ds_cfg_from_model(ds)
    res = await _ex.execute_select(
        cfg,
        "SELECT c.relname, (xpath('/row/c/text()', query_to_xml("
        "  'SELECT count(*) AS c FROM ' || quote_ident(c.relname), false, true, ''"
        ")))[1]::text::int AS cnt "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relkind='r' AND n.nspname='public'",
    )
    counts = {str(r[0]).upper(): int(r[1] or 0) for r in res["rows"]}

    async with async_db_session() as db:
        meta = {
            str(r[0]).upper(): (str(r[1] or ""), str(r[2] or ""))
            for r in (
                await db.execute(
                    text(
                        "SELECT table_name, COALESCE(table_comment,''), "
                        "COALESCE((SELECT alias FROM ai_query_assets a WHERE "
                        "UPPER(a.table_name)=UPPER(s.table_name) AND a.is_deleted=false), '') "
                        "FROM ai_query_schema s WHERE s.is_deleted=false AND s.datasource=:c"
                    ),
                    {"c": f"ds:{DS_ID}"},
                )
            ).fetchall()
        }

    biz = {t: c for t, c in counts.items() if classify(t) == "business"}
    empty = sorted(t for t, c in biz.items() if c == 0)
    nonempty = sorted((t for t, c in biz.items() if c > 0), key=lambda t: -biz[t])

    groups: dict[str, list[str]] = defaultdict(list)
    for t in empty:
        groups[subdomain(t)].append(t)

    lines = [
        "# ds:4（燃煤外部库）缺数据清单",
        "",
        "> 由 `backend/scripts/ds4_missing_data_report.py` 生成（表行数取自目标库实时统计）。",
        "> 用途：把「业务表但 0 行」的表交给人工补数 —— 空表会让评测题退化为"
        "「任何 SQL 都算对」，指标也不可用。",
        "",
        "## 总览",
        "",
        f"- 目标库表（base table）：**{len(counts)}**",
        f"- 业务表：**{len(biz)}**，其中有数据 **{len(nonempty)}**、"
        f"**0 行 {len(empty)}**",
        f"- 已移出范围的技术/系统表：**{sum(1 for t in counts if classify(t) != 'business')}**",
        "",
        "## 已移出范围（技术/系统表，不参与检索）",
        "",
        "`SYS_*`、`EFMigrationsHistory`、`*_BAK/_LOG/_HISTORY`、`JIMU_*`、`OPS_*`、"
        "`QUALITYENCRYPT`、`QUANTITYENCRYPT` 等 —— 详见 "
        "`python scripts/ds4_table_scope_report.py --csv out.csv`。",
        "",
        "## 缺数据（业务表 0 行，按子域）",
        "",
    ]
    for label in sorted(groups):
        lines.append(f"### {label}（{len(groups[label])} 张）")
        lines.append("")
        lines.append("| 表名 | 表注释 |")
        lines.append("|------|--------|")
        for t in groups[label]:
            cmt = meta.get(t, ("", ""))[0] or meta.get(t, ("", ""))[1] or ""
            lines.append(f"| `{t}` | {cmt} |")
        lines.append("")

    lines += [
        "## 补数优先级建议",
        "",
        "1. **采购与结算**（`FUEL_CB_COALBALANCE` / `FUEL_CB_COALCONTRACT` 等）——"
        "现有 4 个指标里有 3 个直接建在这些表上，全为 0 行，指标目前返回 NULL；"
        "这也是评测集里「平均合同单价/结算总量」等题的来源。",
        "2. **化验与煤质**（`FUEL_CMCS_FUELQUALITY` 等）——`avg_lf`/`avg_rz` 两个指标依赖的"
        "`DTXY_PMXX` 有 77 行但 `LF/RZ` 是**文本**列，需要补可数值化的数据或改指标口径。",
        "3. **煤场与库存 / 入炉与耗用**（`FUEL_CMCS_INCOALHISTORY` 已有 118 万行，"
        "但 `FUEL_CMCS_INCOALBUNKER` 之外的明细多为空）——库存/耗用类问题的数据基础。",
        "4. **计划与报表**——计划/报表类问题（月报/日报）几乎全空。",
        "",
        "## 有数据的业务表（Top 20，评测与指标的可用基础）",
        "",
        "| 表名 | 行数 |",
        "|------|------|",
    ]
    for t in nonempty[:20]:
        lines.append(f"| `{t}` | {biz[t]:,} |")
    lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"已写出 {out_path}：业务表 {len(biz)}，缺数据 {len(empty)}，有数据 {len(nonempty)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("..", "docs", "ds4-missing-data.md"))
    a = ap.parse_args()
    asyncio.run(main(a.out))
