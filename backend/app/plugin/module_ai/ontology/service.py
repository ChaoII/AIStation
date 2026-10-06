"""本体（Ontology）独立模块：对象类型 / 属性类型 / 关联类型 / 动作类型 的强类型元模型。

对标 Palantir Ontology —— 创建对象类型**不必先有数据库表**，由元模型驱动：
定义 Object + Property 后，可通过 ``materialize_object`` 生成真实表（本体驱动表），
供问数 / Agent / Workshop / 管道 / 治理消费。
"""
from __future__ import annotations

import json

from sqlalchemy import text as _t

from app.core.database import async_db_session
from app.core.exceptions import CustomException


# ---------------------------------------------------------------------------
# 元模型 CRUD
# ---------------------------------------------------------------------------
async def _exec(sql: str, params: dict | None = None):
    async with async_db_session() as db:
        return await db.execute(_t(sql), params or {})


async def _exec_write(sql: str, params: dict | None = None):
    async with async_db_session.begin() as db:
        return await db.execute(_t(sql), params or {})


async def list_objects() -> list[dict]:
    async with async_db_session() as db:
        rows = (await db.execute(_t(
            "SELECT id,code,name,icon,key_prop,name_prop,description,enabled "
            "FROM ai_ont_object WHERE is_deleted=false ORDER BY id DESC"))).fetchall()
    return [{"id": r[0], "code": r[1], "name": r[2], "icon": r[3] or "el-icon-Box",
             "key_prop": r[4] or "id", "name_prop": r[5] or "name",
             "description": r[6] or "", "enabled": bool(r[7]),
             "property_count": await _prop_count(r[1]),
             "link_count": await _link_count(r[1]),
             "action_count": await _action_count(r[1])} for r in rows]


async def _prop_count(code: str) -> int:
    r = await _exec("SELECT count(*) FROM ai_ont_property WHERE object_code=:c AND is_deleted=false", {"c": code})
    return r.scalar() or 0


async def _link_count(code: str) -> int:
    r = await _exec("SELECT count(*) FROM ai_ont_link WHERE (source_object=:c OR target_object=:c) AND is_deleted=false", {"c": code})
    return r.scalar() or 0


async def _action_count(code: str) -> int:
    r = await _exec("SELECT count(*) FROM ai_ont_action WHERE object_code=:c AND is_deleted=false", {"c": code})
    return r.scalar() or 0


async def upsert_object(data: dict) -> dict:
    code = (data.get("code") or "").strip()
    if not code:
        raise CustomException(msg="对象编码必填")
    if data.get("id"):
        await _exec_write("UPDATE ai_ont_object SET name=:n, icon=:i, key_prop=:k, name_prop=:np, "
                          "description=:d, enabled=:e, updated_time=now() WHERE id=:id",
                          {"n": data.get("name", code), "i": data.get("icon", "el-icon-Box"),
                           "k": data.get("key_prop", "id"), "np": data.get("name_prop", "name"),
                           "d": data.get("description", ""), "e": bool(data.get("enabled", True)),
                           "id": data["id"]})
        return {"id": data["id"]}
    try:
        r = await _exec_write(
            "INSERT INTO ai_ont_object(code,name,icon,key_prop,name_prop,description,enabled) "
            "VALUES (:c,:n,:i,:k,:np,:d,:e) RETURNING id",
            {"c": code, "n": data.get("name", code), "i": data.get("icon", "el-icon-Box"),
             "k": data.get("key_prop", "id"), "np": data.get("name_prop", "name"),
             "d": data.get("description", ""), "e": bool(data.get("enabled", True))})
        return {"id": r.scalar(), "code": code}
    except Exception as e:  # noqa: BLE001
        if "duplicate" in str(e).lower():
            raise CustomException(msg=f"对象编码 {code} 已存在")
        raise CustomException(msg=f"保存失败：{str(e)[:80]}")


async def list_properties(object_code: str) -> list[dict]:
    r = await _exec("SELECT id,object_code,name,code,prop_type,required,unique_col,sensitive,source_col,options,description "
                    "FROM ai_ont_property WHERE object_code=:c AND is_deleted=false ORDER BY id", {"c": object_code})
    rows = r.fetchall()
    return [{"id": x[0], "object_code": x[1], "name": x[2], "code": x[3], "prop_type": x[4],
             "required": bool(x[5]), "unique_col": bool(x[6]), "sensitive": bool(x[7]),
             "source_col": x[8] or "", "options": x[9] if isinstance(x[9], list) else (json.loads(x[9]) if x[9] else []),
             "description": x[10] or ""} for x in rows]


async def upsert_property(data: dict) -> dict:
    code = (data.get("code") or "").strip()
    obj = (data.get("object_code") or "").strip()
    if not code or not obj:
        raise CustomException(msg="属性编码/对象编码必填")
    opts = json.dumps(data.get("options") or [], ensure_ascii=False)
    if data.get("id"):
        await _exec_write("UPDATE ai_ont_property SET name=:n, prop_type=:p, required=:r, unique_col=:u, sensitive=:s, "
                          "source_col=:sc, options=:o, description=:d WHERE id=:id",
                          {"n": data.get("name", code), "p": data.get("prop_type", "string"),
                           "r": bool(data.get("required")), "u": bool(data.get("unique_col")),
                           "s": bool(data.get("sensitive")), "sc": data.get("source_col", ""),
                           "o": opts, "d": data.get("description", ""), "id": data["id"]})
        return {"id": data["id"]}
    r = await _exec_write("INSERT INTO ai_ont_property(object_code,name,code,prop_type,required,unique_col,sensitive,source_col,options,description) "
                          "VALUES (:oc,:n,:c,:p,:r,:u,:s,:sc,:o,:d) RETURNING id",
                          {"oc": obj, "n": data.get("name", code), "c": code, "p": data.get("prop_type", "string"),
                           "r": bool(data.get("required")), "u": bool(data.get("unique_col")),
                           "s": bool(data.get("sensitive")), "sc": data.get("source_col", ""),
                           "o": opts, "d": data.get("description", "")})
    return {"id": r.scalar()}


async def list_links(object_code: str | None = None) -> list[dict]:
    if object_code:
        r = await _exec("SELECT id,source_object,target_object,name,card,source_field,target_field,description "
                        "FROM ai_ont_link WHERE (source_object=:c OR target_object=:c) AND is_deleted=false ORDER BY id", {"c": object_code})
    else:
        r = await _exec("SELECT id,source_object,target_object,name,card,source_field,target_field,description "
                        "FROM ai_ont_link WHERE is_deleted=false ORDER BY id")
    rows = r.fetchall()
    return [{"id": x[0], "source_object": x[1], "target_object": x[2], "name": x[3], "card": x[4],
             "source_field": x[5] or "", "target_field": x[6] or "", "description": x[7] or ""} for x in rows]


async def upsert_link(data: dict) -> dict:
    if not (data.get("source_object") and data.get("target_object")):
        raise CustomException(msg="源/目标对象必填")
    if data.get("id"):
        await _exec_write("UPDATE ai_ont_link SET source_object=:s, target_object=:t, name=:n, card=:c, "
                          "source_field=:sf, target_field=:tf, description=:d WHERE id=:id",
                          {"s": data["source_object"], "t": data["target_object"], "n": data.get("name", ""),
                           "c": data.get("card", "many_to_one"), "sf": data.get("source_field", ""),
                           "tf": data.get("target_field", ""), "d": data.get("description", ""), "id": data["id"]})
        return {"id": data["id"]}
    r = await _exec_write("INSERT INTO ai_ont_link(source_object,target_object,name,card,source_field,target_field,description) "
                          "VALUES (:s,:t,:n,:c,:sf,:tf,:d) RETURNING id",
                          {"s": data["source_object"], "t": data["target_object"], "n": data.get("name", ""),
                           "c": data.get("card", "many_to_one"), "sf": data.get("source_field", ""),
                           "tf": data.get("target_field", ""), "d": data.get("description", "")})
    return {"id": r.scalar()}


async def list_actions(object_code: str | None = None) -> list[dict]:
    if object_code:
        r = await _exec("SELECT id,object_code,name,code,input_schema,white_fields,approval,target_table,method,description "
                        "FROM ai_ont_action WHERE object_code=:c AND is_deleted=false ORDER BY id", {"c": object_code})
    else:
        r = await _exec("SELECT id,object_code,name,code,input_schema,white_fields,approval,target_table,method,description "
                        "FROM ai_ont_action WHERE is_deleted=false ORDER BY id")
    rows = r.fetchall()
    return [{"id": x[0], "object_code": x[1], "name": x[2], "code": x[3],
             "input_schema": x[4] if isinstance(x[4], list) else (json.loads(x[4]) if x[4] else []),
             "white_fields": x[5] if isinstance(x[5], list) else (json.loads(x[5]) if x[5] else []),
             "approval": bool(x[6]), "target_table": x[7] or "", "method": x[8] or "update",
             "description": x[9] or ""} for x in rows]


async def upsert_action(data: dict) -> dict:
    code = (data.get("code") or "").strip()
    obj = (data.get("object_code") or "").strip()
    if not code or not obj:
        raise CustomException(msg="动作编码/对象编码必填")
    ins = json.dumps(data.get("input_schema") or [], ensure_ascii=False)
    wht = json.dumps(data.get("white_fields") or [], ensure_ascii=False)
    if data.get("id"):
        await _exec_write("UPDATE ai_ont_action SET name=:n, input_schema=:i, white_fields=:w, approval=:a, "
                          "target_table=:t, method=:m, description=:d WHERE id=:id",
                          {"n": data.get("name", code), "i": ins, "w": wht, "a": bool(data.get("approval")),
                           "t": data.get("target_table", ""), "m": data.get("method", "update"),
                           "d": data.get("description", ""), "id": data["id"]})
        return {"id": data["id"]}
    r = await _exec_write("INSERT INTO ai_ont_action(object_code,name,code,input_schema,white_fields,approval,target_table,method,description) "
                          "VALUES (:oc,:n,:c,:i,:w,:a,:t,:m,:d) RETURNING id",
                          {"oc": obj, "n": data.get("name", code), "c": code, "i": ins, "w": wht,
                           "a": bool(data.get("approval")), "t": data.get("target_table", ""),
                           "m": data.get("method", "update"), "d": data.get("description", "")})
    return {"id": r.scalar()}


async def delete_one(table: str, id: int) -> None:
    await _exec_write(f"UPDATE {table} SET is_deleted=true WHERE id=:id", {"id": id})


# ---------------------------------------------------------------------------
# 本体计算函数（Palantir Functions）：对象上的可复用计算，被问数/AIP 复用
# ---------------------------------------------------------------------------
async def list_functions(object_code: str | None = None) -> list[dict]:
    if object_code:
        r = await _exec("SELECT id,object_code,name,code,expr,description FROM ai_ont_function "
                        "WHERE object_code=:c AND is_deleted=false ORDER BY id", {"c": object_code})
    else:
        r = await _exec("SELECT id,object_code,name,code,expr,description FROM ai_ont_function "
                        "WHERE is_deleted=false ORDER BY id")
    rows = r.fetchall()
    return [{"id": x[0], "object_code": x[1], "name": x[2], "code": x[3],
             "expr": x[4] or "", "description": x[5] or ""} for x in rows]


async def upsert_function(data: dict) -> dict:
    code = (data.get("code") or "").strip()
    obj = (data.get("object_code") or "").strip()
    if not code or not obj:
        raise CustomException(msg="函数编码/对象编码必填")
    if data.get("id"):
        await _exec_write("UPDATE ai_ont_function SET name=:n, expr=:e, description=:d WHERE id=:id",
                          {"n": data.get("name", code), "e": data.get("expr", ""),
                           "d": data.get("description", ""), "id": data["id"]})
        return {"id": data["id"]}
    r = await _exec_write("INSERT INTO ai_ont_function(object_code,name,code,expr,description) "
                          "VALUES (:oc,:n,:c,:e,:d) RETURNING id",
                          {"oc": obj, "n": data.get("name", code), "c": code,
                           "e": data.get("expr", ""), "d": data.get("description", "")})
    return {"id": r.scalar()}


# ---------------------------------------------------------------------------
# 本体驱动表：把对象 + 属性物化成真实表（Palantir「本体驱动数据」）
# ---------------------------------------------------------------------------
async def materialize_object(code: str) -> dict:
    obj = (await _exec("SELECT code,name FROM ai_ont_object WHERE code=:c AND is_deleted=false", {"c": code})).fetchone()
    if not obj:
        return {"ok": False, "msg": f"对象 {code} 不存在"}
    props = await list_properties(code)
    if not props:
        return {"ok": False, "msg": "对象没有属性，无法物化"}
    table = f"ont_{code}"
    col_map = []
    cols_ddl = []
    for p in props:
        t = p["prop_type"]
        col_map.append({"prop": p["code"], "col": p["code"], "type": t})
        pg = "TEXT"
        if t == "number":
            pg = "NUMERIC"
        elif t == "date":
            pg = "TIMESTAMP"
        elif t == "boolean":
            pg = "BOOLEAN"
        elif t == "object_ref" or t == "enum":
            pg = "TEXT"
        cols_ddl.append(f'"{p["code"]}" {pg}')
    ddl = f'CREATE TABLE IF NOT EXISTS "{table}" (id BIGSERIAL PRIMARY KEY, {", ".join(cols_ddl)})'
    async with async_db_session() as db:
        await db.execute(_t(ddl))
    return {"ok": True, "table": table, "columns": [c["col"] for c in col_map],
            "msg": f"对象 {code} 已物化为表 {table}"}


async def object_full(code: str) -> dict:
    obj = (await _exec("SELECT code,name,icon,key_prop,name_prop,description FROM ai_ont_object "
                       "WHERE code=:c AND is_deleted=false", {"c": code})).fetchone()
    if not obj:
        return {"ok": False, "msg": "对象不存在"}
    return {"code": obj[0], "name": obj[1], "icon": obj[2], "key_prop": obj[3], "name_prop": obj[4],
            "description": obj[5], "properties": await list_properties(code),
            "links": await list_links(code), "actions": await list_actions(code)}
