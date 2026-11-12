"""给本体对象补**业务别名**（期初库存/盘点/配煤分仓/成本项目…），用于表消歧。

为什么需要（2026-11-12 实测）：
- 留出集 v2 的 8 条失败，正确表**根本没被召回**（例如「期初库存明细」召回的是
  `FUEL_STG_INVENTORYREPORT`，不是 `FUEL_STG_STORAGEINITIALIZEDETAIL`）；
- 召回里本体的「别名」通道是**第一优先级、权重最高**，但 `ai_ont_object.aliases` 全是空数组，
  等于这条通道不存在；
- 别名是**业务说法**，不是题面：加「期初库存明细」「盘点报表」这类词，任何同义问法都能命中。

用法：
    uv run python scripts/seed_ontology_aliases.py --dry-run
    uv run python scripts/seed_ontology_aliases.py --apply
幂等：只在别名缺失时追加，不删除人工维护的别名。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ENVIRONMENT", "dev")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

#: 对象 code → 业务别名（口语/报表里的说法，2~10 字；不含具体年份/条件）
ALIASES: dict[str, list[str]] = {
    # 期初库存 / 盘点（v2 里最容易混的两族）
    "FUEL_STG_STORAGEINITIALIZE": ["期初库存单", "期初库存主表", "库存初始化单"],
    "FUEL_STG_STORAGEINITIALIZEDETAIL": ["期初库存明细", "初始库存明细", "期初库存明细表"],
    "FUEL_STG_INVENTORYREPORT": ["盘点报表", "库存盘点报表", "盘点主表", "盘点"],
    "FUEL_STG_INVENTORYREPORTDETAIL": ["盘点明细", "库存报告明细", "盘点明细表"],
    # 厂内成本
    "FUEL_CMCS_FACTORYCOSTPOINT": ["成本项目", "费用项目", "厂内费用指标"],
    "FUEL_CMCS_FACTORYCOSTYEAR": ["年度厂内费用", "年度费用主表"],
    "FUEL_CMCS_FACTORYCOSTYEARDETAIL": ["年度费用明细", "厂内费用年度明细"],
    # 配煤
    "FUEL_MIX_COALSCHEME": ["配煤方案", "掺配方案"],
    "FUEL_MIX_COALSCHEMEBUNKER": ["配煤方案分仓明细", "分仓明细", "配煤分仓"],
    "FUEL_MIX_COALSCHEMERESULT": ["配煤结果", "掺配结果", "配煤方案结果"],
    "FUEL_MIX_COALSCHEMEREUSLTDETAIL": ["配煤结果明细", "掺配结果明细"],
    # 化验
    "coal_assay": ["化验单", "化验记录", "煤质化验"],
    "FUEL_CMCS_ASSAY": ["化验单", "化验记录", "煤质化验"],
    "FUEL_CMCS_ASSAYCHECK": ["化验审核记录", "化验审核"],
    "FUEL_CMCS_ASSAYCHECKSUGGESTION": ["化验审核建议", "化验审批意见", "审核建议"],
    "FUEL_CMCS_ASSAYRECHECK": ["化验复检", "复检记录"],
    "FUEL_CMCS_ASSAYCONTRAST": ["化验对比", "超差记录"],
    # 采购计划
    "FUEL_CMCS_PURCHASEPLAN": ["采购计划主表", "月度采购计划", "采购计划"],
    "FUEL_CMCS_PURCHASEPLANDETAIL": ["采购计划明细", "月度采购计划明细"],
    # 供应商
    "FUEL_CMCS_SUPPLIER": ["供应商", "供应商台账"],
    "FUEL_CMCS_SUPPLIERQUALITYLIMIT": ["供应商煤质限制", "煤质限制", "供应商质量限制"],
    "FUEL_CMCS_SUPPLIERMINE": ["供应商矿点", "矿点关系", "供煤矿别"],
    # 运输 / 皮带
    "FUEL_CMCS_TRANSPORTPLAN": ["运输计划", "调运计划"],
    "FUEL_CMCS_TRANSPORTPLANDETAIL": ["运输计划明细", "调运明细"],
    "FUEL_CMCS_TRANSPORTTYPE": ["运输方式", "运输类型"],
    "FUEL_CMCS_BELT": ["皮带", "皮带台账"],
    "FUEL_CMCS_BELTMODEL": ["皮带型号", "皮带模型"],
    "FUEL_MIX_BUNKERREALTIME": ["煤仓实时", "煤仓实时数据"],
    # 日计划 / 上煤
    "FUEL_CMCS_PLANDAY": ["日计划主表", "生产日计划"],
    "FUEL_CMCS_PLANDAYDETAIL": ["日计划明细", "生产日计划明细"],
    "FUEL_STG_DAYCOALINFO": ["每日上煤信息", "日上煤"],
    "FUEL_STG_DAYCOALINFODETAIL": ["每日上煤明细", "上煤明细"],
    # 合同 / 结算
    "FUEL_CB_COALCONTRACT": ["燃煤合同", "采购合同", "合同主表"],
    "FUEL_CB_COALBALANCE": ["结算主表", "采购结算", "燃煤结算"],
    "FUEL_CB_COALBALANCEDETAIL": ["结算明细", "采购结算明细"],
    # 批次 / 入炉 / 筒仓
    "coal_batch": ["入厂煤批次", "入厂批次", "进煤批次"],
    "FUEL_CMCS_INFACTORYBATCH": ["入厂煤批次", "入厂批次", "进煤批次"],
    "FUEL_CMCS_INFURNACEDETAIL": ["入炉明细", "入炉煤明细"],
    "FUEL_CMCS_INSILOHISTORY": ["筒仓历史", "筒仓煤量历史"],
    # 煤场 / 报表
    "FUEL_STG_FUELSTORAGEAREA": ["煤场区域", "存煤区域", "存储区"],
    "FUEL_STG_FUELSTORAGE": ["煤场设置", "煤场主表"],
    "FUEL_REPORT_DAYINOUTSTORAGE": ["每日耗用量", "出入库日报", "日耗用"],
    "FUEL_REPORT_DAYCOALSTORAGELEDGER": ["存煤台账", "日存煤台账"],
    "DTXY_PMXX": ["煤质信息", "煤质", "煤品信息"],
    "FUEL_CMCS_STATION": ["站点", "煤场站点"],
    "FUEL_STG_CONTROLLOG_CHANGEHISTORY": ["变更历史", "皮带操作变更"],
    # 指标护栏补全：这些表没有别名时，「多少条」类指标会被证据规则挡掉（105 快路径 7 条退化）
    "coal_fuelkind": ["煤种", "煤种类型", "燃料种类"],
    "coal_mine": ["矿点", "矿点信息", "供煤矿点"],
    "DTXY_QYXX": ["区域", "企业信息", "区域信息"],
    "FR_PERSONNELINFO": ["人员", "人员信息", "人脸人员"],
    "FUEL_STG_ALLOUTMIDDLE": ["取煤记录", "出煤记录", "取煤流水"],
}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not (args.dry_run or args.apply):
        ap.print_help()
        return

    from main import create_app

    create_app()

    import json

    from sqlalchemy import text

    from app.core.database import async_db_session

    async with async_db_session() as db:
        rows = (await db.execute(text(
            "SELECT code, COALESCE(aliases::text,'[]') FROM ai_ont_object WHERE is_deleted=false"
        ))).fetchall()
    current = {}
    for code, raw in rows:
        try:
            arr = json.loads(raw) if isinstance(raw, str) else (raw or [])
        except Exception:  # noqa: BLE001
            arr = []
        current[code] = [str(x) for x in (arr or []) if str(x).strip()]

    # 不在本体里的表（如 FR_PERSONNELINFO）退回到资产目录的 alias 字段：
    # 指标护栏读的是「表名/业务别名」，资产 alias 同样算证据。
    async with async_db_session() as db:
        asset_rows = (await db.execute(text(
            "SELECT table_name, COALESCE(alias,'') FROM ai_query_assets WHERE is_deleted=false"
        ))).fetchall()
    asset_alias = {str(r[0]).upper(): str(r[1] or "") for r in asset_rows}
    asset_fill: list[tuple[str, str]] = []
    for code, aliases in ALIASES.items():
        if code in current:
            continue
        up = code.upper()
        key = up if up in asset_alias else (f"ONT_{up}" if f"ONT_{up}" in asset_alias else "")
        cur = (asset_alias.get(key) or "").strip() if key else ""
        # 资产 alias 常常就是影子表名（`ont_X`）或表名本身 —— 等同"没写"，可以覆盖
        if key and (not cur or cur.upper() in (up, f"ONT_{up}")):
            asset_fill.append((code, aliases[0]))

    plan: list[tuple[str, list[str], list[str]]] = []
    for code, aliases in ALIASES.items():
        if code not in current:
            continue
        have = {a.strip() for a in current[code]}
        add = [a for a in aliases if a.strip() and a.strip() not in have]
        if add:
            plan.append((code, current[code], add))

    print(f"[plan] 待补别名对象 {len(plan)} 个、资产别名 {len(asset_fill)} 个"
          f"（总映射 {len(ALIASES)}，库内对象 {len(current)}）")
    for code, alias in asset_fill[:10]:
        print("  ASSET", code, "→", alias)
    for code, _have, add in plan[:10]:
        print("  ADD", code, "→", "、".join(add))
    if args.dry_run:
        return

    for code, have, add in plan:
        merged = have + add
        async with async_db_session.begin() as db:
            await db.execute(text(
                "UPDATE ai_ont_object SET aliases=CAST(:a AS jsonb), updated_time=now() "
                "WHERE code=:c AND is_deleted=false"
            ), {"a": json.dumps(merged, ensure_ascii=False), "c": code})
    for code, alias in asset_fill:
        async with async_db_session.begin() as db:
            await db.execute(text(
                "UPDATE ai_query_assets SET alias=:a, updated_time=now() "
                "WHERE (upper(table_name)=:c OR upper(table_name)=:c2) "
                "AND is_deleted=false "
                "AND (COALESCE(alias,'')='' OR upper(alias) IN (:c,:c2))"
            ), {"a": alias, "c": code.upper(), "c2": f"ONT_{code.upper()}"})
    print(f"[ok] 已补 {len(plan)} 个对象别名、{len(asset_fill)} 个资产别名")


if __name__ == "__main__":
    asyncio.run(main())
