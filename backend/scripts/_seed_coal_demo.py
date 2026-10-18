"""燃煤库（ds:4）演示对象域：4 个对象 + 3 条关系，用于试跑 S1「本体对象查自定义数据源」。

幂等 upsert，可反复执行。对象/属性 code 与燃煤库真实列名（大写）保持一致。

用法（backend 下）::

    python scripts/_seed_coal_demo.py            # 建对象 + 跑演示查询
    python scripts/_seed_coal_demo.py --clean    # 软删本脚本建的对象/属性/关系
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

DS = 4  # 燃煤业务库

# 对象：code / name / backing_table / key_prop / name_prop / props[(code,name,type)]
OBJECTS = [
    {"code": "coal_fuelkind", "name": "煤种", "plural_name": "煤种", "table": "FUEL_CMCS_FUELKIND",
     "key_prop": "ID", "name_prop": "NAME",
     "props": [("ID", "编号", "string"), ("NAME", "名称", "string"),
               ("CODE", "编码", "string"), ("ISENABLE", "是否启用", "string")]},
    {"code": "coal_mine", "name": "矿点", "plural_name": "矿点", "table": "FUEL_CMCS_MINE",
     "key_prop": "ID", "name_prop": "NAME",
     "props": [("ID", "编号", "string"), ("NAME", "名称", "string"),
               ("CODE", "编码", "string"), ("ISENABLE", "是否启用", "string")]},
    {"code": "coal_batch", "name": "入厂煤批次", "plural_name": "入厂煤批次",
     "table": "FUEL_CMCS_INFACTORYBATCH", "key_prop": "ID", "name_prop": "FUELKINDNAME",
     "props": [("ID", "批次编号", "string"), ("MINEID", "矿点编号", "string"),
               ("FUELKINDID", "煤种编号", "string"), ("MINENAME", "矿点名称", "string"),
               ("FUELKINDNAME", "煤种名称", "string"),
               ("FACTARRIVEDATE", "实际到厂时间", "date"),
               ("TRANSPORTNUMBER", "运输车数", "number")]},
    {"code": "coal_assay", "name": "化验单", "plural_name": "化验单",
     "table": "FUEL_CMCS_ASSAY", "key_prop": "ID", "name_prop": "ASSAYCODE",
     "props": [("ID", "化验单编号", "string"), ("INFACTORYBATCHID", "入厂批次编号", "string"),
               ("ASSAYCODE", "化验编码", "string"), ("ASSAYDATE", "化验日期", "date")]},
]

# 关系：source → target（source_field 在 source 上，target_field 在 target 上）
LINKS = [
    {"source": "coal_batch", "target": "coal_mine", "name": "入厂批次_所属矿点",
     "card": "many_to_one", "join_method": "foreign_key",
     "source_field": "MINEID", "target_field": "ID"},
    {"source": "coal_batch", "target": "coal_fuelkind", "name": "入厂批次_所属煤种",
     "card": "many_to_one", "join_method": "foreign_key",
     "source_field": "FUELKINDID", "target_field": "ID"},
    {"source": "coal_assay", "target": "coal_batch", "name": "化验单_对应批次",
     "card": "many_to_one", "join_method": "foreign_key",
     "source_field": "INFACTORYBATCHID", "target_field": "ID"},
]


# 绑定型指标：object_code + agg_fn（口径由「对象属性 + 聚合」确定性推导，不写 SQL）
METRICS = [
    {"key": "coal_batch_count", "name": "入厂批次数", "object_code": "coal_batch",
     "property_code": "", "agg_fn": "count", "bound_dimensions": ["FUELKINDNAME", "MINENAME"]},
    {"key": "coal_assay_count", "name": "化验单数", "object_code": "coal_assay",
     "property_code": "", "agg_fn": "count", "bound_dimensions": []},
    {"key": "coal_fuelkind_count", "name": "煤种数", "object_code": "coal_fuelkind",
     "property_code": "", "agg_fn": "count", "bound_dimensions": []},
    {"key": "coal_mine_count", "name": "矿点数", "object_code": "coal_mine",
     "property_code": "", "agg_fn": "count", "bound_dimensions": []},
]


async def seed_metrics() -> None:
    from types import SimpleNamespace
    from app.plugin.module_ai.query import service as S

    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
    for m in METRICS:
        r = await S.AiQueryService.upsert_metric(
            SimpleNamespace(datasource=f"ds:{DS}", key=m["key"], name=m["name"],
                            description=f"{m['name']}（绑定燃煤库对象 {m['object_code']}）",
                            sql_template="SELECT 1 AS 数值", params=[], dimensions=[],
                            agg="count", unit="", permission_tag="", enabled=True, sort=0,
                            cache_ttl=0, object_code=m["object_code"],
                            property_code=m["property_code"], agg_fn=m["agg_fn"],
                            bound_dimensions=m["bound_dimensions"]),
            auth)
        print(f"  metric {m['key']:20s} -> object={r.get('object_code')} agg={r.get('agg_fn')}")


async def seed(ont) -> None:
    for o in OBJECTS:
        r = await ont.upsert_object({
            "code": o["code"], "name": o["name"], "plural_name": o["plural_name"],
            "datasource_id": DS, "backing_table": o["table"],
            "key_prop": o["key_prop"], "name_prop": o["name_prop"],
            "description": f"燃煤库演示对象（{o['table']}）",
        })
        print(f"  object {o['code']:16s} -> {r}")
        for code, name, typ in o["props"]:
            await ont.upsert_property({
                "object_code": o["code"], "code": code, "name": name,
                "prop_type": typ, "source_col": code,
            })
    for lk in LINKS:
        r = await ont.upsert_link({
            "source_object": lk["source"], "target_object": lk["target"],
            "name": lk["name"], "card": lk["card"], "join_method": lk["join_method"],
            "source_field": lk["source_field"], "target_field": lk["target_field"],
        })
        print(f"  link   {lk['name']:20s} -> {r}")


async def clean() -> None:
    from sqlalchemy import text
    from app.core.database import async_db_session

    codes = [o["code"] for o in OBJECTS]
    async with async_db_session.begin() as db:
        await db.execute(text("UPDATE ai_ont_object SET is_deleted=true WHERE code = ANY(:c)"),
                         {"c": codes})
        await db.execute(text("UPDATE ai_ont_property SET is_deleted=true WHERE object_code = ANY(:c)"),
                         {"c": codes})
        await db.execute(text("UPDATE ai_ont_link SET is_deleted=true WHERE source_object = ANY(:c) OR target_object = ANY(:c)"),
                         {"c": codes})
    print("已软删演示对象/属性/关系")


async def demo(ont, sec) -> None:
    principal = await sec.load_principal(1)
    print("\n===== 演示查询（全部走燃煤库 ds:4）=====")
    sr = await ont.instance_search("coal_mine", limit=5, principal=principal)
    print(f"[1] 矿点列表 ok={sr.get('ok')} total={sr.get('total')} "
          f"first={ (sr.get('items') or [{}])[0].get('props') }")
    ag = await ont.instance_aggregate("coal_batch", group_by="FUELKINDNAME",
                                      aggs=[{"fn": "count"}], principal=principal)
    print(f"[2] 入厂批次按煤种计数 ok={ag.get('ok')} series={ag.get('series')}")
    # 沿关系跳转：取一个「MINEID 非空」的批次，跳到它的矿点
    first = (await ont.instance_search(
        "coal_batch", filters={"MINEID": {"op": "not_empty"}},
        limit=1, principal=principal)).get("items") or []
    if first:
        bkey = first[0].get("key")
        links = await ont.list_links("coal_batch")
        mine_link = next((l for l in links if l["target_object"] == "coal_mine"), None)
        if mine_link:
            piv = await ont.instance_pivot("coal_batch", bkey, mine_link["id"], principal=principal)
            other = (piv.get("items") or [{}])[0].get("props") if piv.get("items") else None
            print(f"[3] 批次 {bkey} 跳转到矿点 ok={piv.get('ok')} -> {other}")


async def try_queries() -> None:
    """真跑问数：对象查询路径（LLM 出 IR）——验证 S1+S2 在燃煤库上的端到端效果。"""
    from types import SimpleNamespace
    from app.plugin.module_ai.query import service as S

    auth = SimpleNamespace(user=SimpleNamespace(id=1, is_superuser=True))
    print("\n===== 真跑问数（对象查询路径，燃煤库 ds:4）=====")
    for q in ["各煤种的入厂批次数", "各矿点的入厂批次数", "入厂批次一共有多少"]:
        ans = None
        try:
            ans = await S.AiQueryService._object_query_path(q, 1, f"ds:{DS}", auth)
        except Exception as e:  # noqa: BLE001
            print(f"[对象查询] {q} -> 异常 {type(e).__name__}: {str(e)[:100]}")
            continue
        if ans:
            print(f"[对象查询] {q}")
            print(f"    path={ans.get('path')}  cols={ans.get('columns')}")
            print(f"    rows={(ans.get('rows') or [])[:4]}")
            print(f"    ir={(ans.get('ir') or {})}")
        else:
            print(f"[对象查询] {q} -> 降级（返回 None）")


async def main() -> None:
    from main import create_app

    create_app()
    from app.scripts.init_app import _ensure_missing_columns
    from app.plugin.module_ai.ontology import security as sec
    from app.plugin.module_ai.ontology import service as ont

    if "--clean" in sys.argv:
        await clean()
        return
    await _ensure_missing_columns()   # 幂等补列（脚本不跑 lifespan）
    print("===== 建燃煤库演示对象域 =====")
    await seed(ont)
    await seed_metrics()
    if "--try" in sys.argv:
        await try_queries()
    else:
        await demo(ont, sec)


asyncio.run(main())
