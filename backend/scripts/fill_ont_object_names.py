"""给「名字还是表名」的本体对象补中文名（本体语义桥的最后一公里）。

背景
----
指标匹配 / 问数召回都要靠「用户怎么称呼这张表」。很多对象是从数据源自动导入的，
``name`` 直接等于 ``code``/表名（实测 422 个对象里 162 个是这样），于是：

    问：区域一共有多少个？  指标：区域数量（对象 DTXY_QYXX，name=DTXY_QYXX）
    → 对象名对不上、问句里也没有列标签词 → 走 40 秒慢路径

真实的中文名其实**已经存在**，只是没同步过来：
- 数据源里的**表注释**（``obj_description``，业务库普遍写得很完整）；
- 平台侧的**资产别名**（``ai_query_assets.alias``）。

本脚本把这两处合并回填到 ``ai_ont_object.name``，只填「空 / 等于 code」的对象，
已有人工命名的**一律不覆盖**。

用法::

    cd backend
    uv run python scripts/fill_ont_object_names.py            # 只预览
    uv run python scripts/fill_ont_object_names.py --apply    # 真正写库
"""
from __future__ import annotations

import argparse
import asyncio
import re

from sqlalchemy import text

from app.core.database import async_db_session

#: 注释里常见的噪声前缀（"表"、"视图"等），保留原意即可，这里只做长度与有效性判断
_ASCII_ONLY = re.compile(r"^[\x00-\x7f]+$")


def _clean(comment: str | None, table: str) -> str:
    """清洗候选名：去掉多余空白、拒收等于表名/纯英文代码的候选。"""
    c = re.sub(r"\s+", " ", (comment or "")).strip()
    if not c:
        return ""
    if c.lower() == (table or "").lower():
        return ""
    # 候选里还带着表名（"数据 ai_access_rule"）说明它只是注释的片段，不是中文名
    if table and (table or "").lower() in c.lower():
        return ""
    if _ASCII_ONLY.match(c):
        # 纯 ASCII 的注释通常是英文描述，对中文问句帮助有限；仍允许，但排在后面
        return c if len(c) <= 40 else ""
    # 注释可能是一整段话，取第一个分句
    c = re.split(r"[。；;\n]", c)[0].strip()
    return c[:60]


async def _ds_table_comments() -> dict[tuple[int, str], str]:
    """从各数据源读**表注释**（table → comment），key=(datasource_id, table)。"""
    from app.plugin.module_ai.query import executor as _ex

    out: dict[tuple[int, str], str] = {}
    async with async_db_session() as db:
        rows = (await db.execute(text(
            "SELECT id, type, host, port, database, username, password "
            "FROM ai_query_datasources WHERE is_deleted=false"))).fetchall()
    for r in rows:
        cfg = {"type": r[1], "host": r[2], "port": r[3], "database": r[4],
               "username": r[5], "password": r[6]}
        try:
            recs = await _ex.introspect_schema(cfg)
        except Exception as e:  # noqa: BLE001 - 单个源连不上不影响其它源
            print(f"  ! 数据源 {r[0]} 探查失败（跳过）：{str(e)[:100]}")
            continue
        for rec in recs:
            cmt = (rec.get("comment") or "").strip()
            if cmt:
                out[(int(r[0]), rec["table"])] = cmt
    return out


async def _metric_names() -> dict[str, str]:
    """指标名 → 对象中文名（"区域数量" → "区域"）。

    指标名是**人工维护过**的，比表名可靠得多：一个对象若绑定了「区域数量」，
    它几乎一定就叫「区域」。这也是本体桥自带的语义来源。
    """
    from app.plugin.module_ai.query.service import _metric_name_core

    async with async_db_session() as db:
        rows = (await db.execute(text(
            "SELECT object_code, name FROM ai_query_metrics "
            "WHERE is_deleted=false AND coalesce(object_code,'')<>'' AND coalesce(name,'')<>'' "
            "ORDER BY enabled DESC, id"))).fetchall()
    out: dict[str, str] = {}
    for code, name in rows:
        core = _metric_name_core(name).strip()
        # 至少两个字，且不能退化成表名/纯 ASCII
        if len(core) >= 2 and not _ASCII_ONLY.match(core):
            out.setdefault(code, core)
    return out


async def _asset_alias() -> dict[str, str]:
    """平台侧资产别名（table → alias）。"""
    async with async_db_session() as db:
        rows = (await db.execute(text(
            "SELECT table_name, coalesce(alias,''), coalesce(description,'') "
            "FROM ai_query_assets WHERE is_deleted=false"))).fetchall()
    out: dict[str, str] = {}
    for t, alias, desc in rows:
        v = (alias or "").strip() or (desc or "").strip()
        if v:
            out[t] = v
    return out


async def main() -> None:  # pragma: no cover - 运维脚本
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写库（默认只预览）")
    args = ap.parse_args()

    async with async_db_session() as db:
        objects = (await db.execute(text(
            "SELECT code, name, coalesce(backing_table,''), coalesce(datasource_id,0) "
            "FROM ai_ont_object WHERE is_deleted=false ORDER BY id"))).fetchall()

    missing = [o for o in objects
               if not (o[1] or "").strip() or (o[1] or "").strip() == (o[0] or "").strip()]
    print(f"对象总数={len(objects)}  名字缺失/等于 code={len(missing)}")

    ds_comments = await _ds_table_comments()
    assets = await _asset_alias()
    metric_names = await _metric_names()

    plan: list[tuple[str, str, str]] = []  # (code, table, new_name)
    for code, _name, table, ds_id in missing:
        # 三个来源依次回退：数据源表注释 > 平台资产别名 > 绑定指标名（剥度量词）
        cand = _clean(ds_comments.get((int(ds_id), table)), table) if table else ""
        if not cand and table:
            cand = _clean(assets.get(table), table)
        if not cand:
            cand = _clean(metric_names.get(code), code)
        if cand:
            plan.append((code, table or code, cand))

    print(f"可回填={len(plan)}  仍无来源={len(missing) - len(plan)}\n")
    for code, table, new_name in plan[:40]:
        print(f"  {code:34s} {table:26s} → {new_name}")
    if len(plan) > 40:
        print(f"  …… 其余 {len(plan) - 40} 条略")

    if not args.apply:
        print("\n（预览模式，未写库；加 --apply 生效）")
        return

    async with async_db_session.begin() as db:
        for code, _table, new_name in plan:
            await db.execute(text(
                "UPDATE ai_ont_object SET name=:n, updated_time=now() WHERE code=:c"),
                {"n": new_name, "c": code})
    print(f"\n已回填 {len(plan)} 个对象的中文名（语义上下文缓存 60 秒内自动过期）")


if __name__ == "__main__":
    asyncio.run(main())
