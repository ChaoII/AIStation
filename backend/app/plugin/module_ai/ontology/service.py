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
        # DQ 健康分（该对象物化表对应 ai_dq_report）
        dq = {}
        try:
            dr = (await db.execute(_t(
                "SELECT table_name, score FROM ai_dq_report WHERE is_deleted=false"))).fetchall()
            dq = {x[0]: (float(x[1]) if x[1] is not None else None) for x in dr}
        except Exception:  # noqa: BLE001
            dq = {}
    return [{"id": r[0], "code": r[1], "name": r[2], "icon": r[3] or "el-icon-Box",
             "key_prop": r[4] or "id", "name_prop": r[5] or "name",
             "description": r[6] or "", "enabled": bool(r[7]),
             "property_count": await _prop_count(r[1]),
             "link_count": await _link_count(r[1]),
             "action_count": await _action_count(r[1]),
             "sensitive_count": await _sensitive_count(r[1]),
             "dq_score": dq.get(r[1])} for r in rows]


async def _dq_score(code: str):
    r = await _exec("SELECT score FROM ai_dq_report WHERE table_name=:c AND is_deleted=false", {"c": code})
    v = r.scalar()
    return float(v) if v is not None else None


async def _sensitive_count(code: str) -> int:
    r = await _exec("SELECT count(*) FROM ai_ont_property WHERE object_code=:c AND sensitive=true AND is_deleted=false", {"c": code})
    return r.scalar() or 0


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
    r = await _exec("SELECT id,object_code,name,code,prop_type,required,unique_col,sensitive,source_col,options,description,roles "
                    "FROM ai_ont_property WHERE object_code=:c AND is_deleted=false ORDER BY id", {"c": object_code})
    rows = r.fetchall()
    return [{"id": x[0], "object_code": x[1], "name": x[2], "code": x[3], "prop_type": x[4],
             "required": bool(x[5]), "unique_col": bool(x[6]), "sensitive": bool(x[7]),
             "source_col": x[8] or "", "options": x[9] if isinstance(x[9], list) else (json.loads(x[9]) if x[9] else []),
             "description": x[10] or "", "roles": x[11] if isinstance(x[11], list) else (json.loads(x[11]) if x[11] else [])} for x in rows]


async def upsert_property(data: dict) -> dict:
    code = (data.get("code") or "").strip()
    obj = (data.get("object_code") or "").strip()
    if not code or not obj:
        raise CustomException(msg="属性编码/对象编码必填")
    opts = json.dumps(data.get("options") or [], ensure_ascii=False)
    roles = json.dumps(data.get("roles") or [], ensure_ascii=False)
    if data.get("id"):
        await _exec_write("UPDATE ai_ont_property SET name=:n, prop_type=:p, required=:r, unique_col=:u, sensitive=:s, "
                          "source_col=:sc, options=:o, description=:d, roles=:roles WHERE id=:id",
                          {"n": data.get("name", code), "p": data.get("prop_type", "string"),
                           "r": bool(data.get("required")), "u": bool(data.get("unique_col")),
                           "s": bool(data.get("sensitive")), "sc": data.get("source_col", ""),
                           "o": opts, "d": data.get("description", ""), "roles": roles, "id": data["id"]})
        return {"id": data["id"]}
    r = await _exec_write("INSERT INTO ai_ont_property(object_code,name,code,prop_type,required,unique_col,sensitive,source_col,options,description,roles) "
                          "VALUES (:oc,:n,:c,:p,:r,:u,:s,:sc,:o,:d,:roles) RETURNING id",
                          {"oc": obj, "n": data.get("name", code), "c": code, "p": data.get("prop_type", "string"),
                           "r": bool(data.get("required")), "u": bool(data.get("unique_col")),
                           "s": bool(data.get("sensitive")), "sc": data.get("source_col", ""),
                           "o": opts, "d": data.get("description", ""), "roles": roles})
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


async def _log_change(object_code: str, kind: str, action: str, detail: str = "", created_id: int = 0) -> None:
    """本体变更留痕（对象/属性/Link/Action/函数 增删改）。"""
    try:
        await _exec_write(
            "INSERT INTO ai_ont_change_log(object_code,kind,action,detail,created_id) VALUES (:o,:k,:a,:d,:uid)",
            {"o": object_code or "-", "k": kind, "a": action, "d": detail[:250] or "", "uid": created_id or 0})
    except Exception:  # noqa: BLE001
        pass


async def list_changelog(object_code: str | None = None, limit: int = 50) -> list[dict]:
    if object_code:
        r = await _exec("SELECT id,object_code,kind,action,detail,created_id,created_time FROM ai_ont_change_log "
                        "WHERE object_code=:c AND is_deleted=false ORDER BY id DESC LIMIT :n",
                        {"c": object_code, "n": limit})
    else:
        r = await _exec("SELECT id,object_code,kind,action,detail,created_id,created_time FROM ai_ont_change_log "
                        "WHERE is_deleted=false ORDER BY id DESC LIMIT :n", {"n": limit})
    rows = r.fetchall()
    return [{"id": x[0], "object_code": x[1], "kind": x[2], "action": x[3],
             "detail": x[4] or "", "created_id": x[5], "created_time": str(x[6]) if x[6] else ""} for x in rows]


async def delete_one(table: str, id: int) -> None:
    await _exec_write(f"UPDATE {table} SET is_deleted=true WHERE id=:id", {"id": id})


# ---------------------------------------------------------------------------
# 本体对象定义版本：快照 + 列表 + 回滚（本体定义同资产一样可版本化）
# ---------------------------------------------------------------------------
async def _is_superuser(user_id) -> bool:
    """判断用户是否超管（用于本体发布/回滚等高危操作校验）。"""
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        uid = 0
    if not uid:
        return False
    try:
        r = await _exec("SELECT is_superuser FROM sys_user WHERE id=:id AND is_deleted=false", {"id": uid})
        row = r.fetchone()
        return bool(row and row[0])
    except Exception:  # noqa: BLE001
        return False


async def _do_publish(object_code: str) -> dict:
    """真正快照发布对象定义到新版本 + 写发布留痕。"""
    obj = await object_full(object_code)
    if not obj.get("ok"):
        return {"ok": False, "msg": "对象不存在"}
    snapshot = {
        "object": {k: obj[k] for k in ("code", "name", "icon", "key_prop", "name_prop", "description")},
        "properties": obj["properties"], "links": obj["links"],
        "actions": obj["actions"], "functions": await list_functions(object_code),
    }
    async with async_db_session() as db:
        from sqlalchemy import text as _t
        n = (await db.execute(_t(
            "SELECT coalesce(max(version),0) FROM ai_ont_version WHERE object_code=:c AND is_deleted=false"),
            {"c": object_code})).scalar() or 0
        n += 1
    import json as _json
    r = await _exec_write("INSERT INTO ai_ont_version(object_code,version,snapshot) VALUES (:c,:v,:s) RETURNING id",
                          {"c": object_code, "v": n, "s": _json.dumps(snapshot, ensure_ascii=False)})
    await _log_change(object_code, "version", "publish", f"发布版本 v{n}")
    return {"ok": True, "id": r.scalar(), "version": n}


async def publish_version(object_code: str, operator: int = 0) -> dict:
    """发布本体对象版本：超管直接发布；非超管 → 落待审批，超管批准后真正发布。"""
    operator = int(operator or 0)
    if operator and not await _is_superuser(operator):
        # 非超管：写待审批留痕，返回审批单
        import json as _json
        detail = _json.dumps({"action": "publish", "object_code": object_code, "operator": operator})
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            res = await db.execute(_t(
                "INSERT INTO ai_ont_change_log(object_code,kind,action,detail,created_id) "
                "VALUES (:o,'version','version_pending',:d,0) RETURNING id"),
                {"o": object_code, "d": detail})
            cid = res.scalar()
        return {"ok": False, "needs_approval": True, "pending_id": int(cid or 0),
                "msg": "发布需超管审批，已生成审批单"}
    return await _do_publish(object_code)


async def list_version_pending(limit: int = 50) -> list[dict]:
    """待审批的本体发布单（changelog action='version_pending'）。"""
    import json as _json
    r = await _exec("SELECT id,object_code,detail,created_time FROM ai_ont_change_log "
                    "WHERE action='version_pending' AND is_deleted=false ORDER BY id DESC LIMIT :n", {"n": limit})
    rows = r.fetchall()
    out = []
    for x in rows:
        detail = x[2]
        try:
            d = _json.loads(detail) if isinstance(detail, str) else (detail or {})
        except Exception:  # noqa: BLE001
            d = {}
        out.append({"id": x[0], "object_code": x[1], "detail": d, "created_time": str(x[3]) if x[3] else ""})
    return out


async def approve_version_publish(pending_id: int, operator: int = 0) -> dict:
    """超管批准本体发布：真正发布 + 更新审批单为 approved。"""
    operator = int(operator or 0)
    if operator and not await _is_superuser(operator):
        return {"ok": False, "msg": "仅超管可批准本体发布"}
    rv = (await _exec("SELECT object_code FROM ai_ont_change_log WHERE id=:i AND action='version_pending' AND is_deleted=false",
                      {"i": pending_id})).fetchone()
    if not rv:
        return {"ok": False, "msg": "审批单不存在或已处理"}
    code = rv[0]
    res = await _do_publish(code)
    await _exec_write("UPDATE ai_ont_change_log SET action='version_approved' WHERE id=:i", {"i": pending_id})
    return {"ok": res.get("ok", False), "version": res.get("version"), "msg": res.get("msg", "已批准发布")}


async def version_diff(version_id: int) -> dict:
    """版本对比：某版本快照的属性 vs 当前定义，返回 新增/删除/变更 属性。"""
    import json as _json
    rv = (await _exec("SELECT object_code,snapshot FROM ai_ont_version WHERE id=:id AND is_deleted=false",
                      {"id": version_id})).fetchone()
    if not rv:
        return {"ok": False, "msg": "版本不存在"}
    code, snap_raw = rv[0], rv[1]
    snap = snap_raw if isinstance(snap_raw, dict) else _json.loads(snap_raw)
    cur = await object_full(code)
    cur_props = {p["code"]: p for p in cur.get("properties", [])}
    old_props = {p["code"]: p for p in snap.get("properties", [])}
    added = [c for c in cur_props if c not in old_props]
    removed = [c for c in old_props if c not in cur_props]
    changed = []
    for c in old_props:
        if c in cur_props:
            o, n = old_props[c], cur_props[c]
            if (o.get("prop_type") != n.get("prop_type")) or (bool(o.get("sensitive")) != bool(n.get("sensitive"))):
                changed.append(c)
    return {"ok": True, "object_code": code, "added": added, "removed": removed, "changed": changed}


async def list_versions(object_code: str | None = None) -> list[dict]:
    if object_code:
        r = await _exec("SELECT id,object_code,version,created_time FROM ai_ont_version "
                        "WHERE object_code=:c AND is_deleted=false ORDER BY version DESC", {"c": object_code})
    else:
        r = await _exec("SELECT id,object_code,version,created_time FROM ai_ont_version "
                        "WHERE is_deleted=false ORDER BY id DESC")
    rows = r.fetchall()
    return [{"id": x[0], "object_code": x[1], "version": x[2], "created_time": str(x[3]) if x[3] else ""} for x in rows]


async def rollback_version(version_id: int) -> dict:
    """把本体定义回滚到指定版本快照。"""
    import json as _json
    rv = (await _exec("SELECT object_code,snapshot FROM ai_ont_version WHERE id=:id AND is_deleted=false",
                      {"id": version_id})).fetchone()
    if not rv:
        return {"ok": False, "msg": "版本不存在"}
    code, snap_raw = rv[0], rv[1]
    snap = snap_raw if isinstance(snap_raw, dict) else _json.loads(snap_raw)
    ob = snap.get("object") or {}
    # 恢复对象主字段
    await _exec_write("UPDATE ai_ont_object SET name=:n, icon=:i, key_prop=:k, name_prop=:np, description=:d "
                      "WHERE code=:c", {"n": ob.get("name", code), "i": ob.get("icon", "el-icon-Box"),
                                        "k": ob.get("key_prop", "id"), "np": ob.get("name_prop", "name"),
                                        "d": ob.get("description", ""), "c": code})
    # 清空并重建 属性/Link/Action/函数
    await _exec_write("UPDATE ai_ont_property SET is_deleted=true WHERE object_code=:c", {"c": code})
    await _exec_write("UPDATE ai_ont_link SET is_deleted=true WHERE source_object=:c OR target_object=:c", {"c": code})
    await _exec_write("UPDATE ai_ont_action SET is_deleted=true WHERE object_code=:c", {"c": code})
    await _exec_write("UPDATE ai_ont_function SET is_deleted=true WHERE object_code=:c", {"c": code})
    for p in snap.get("properties", []):
        await upsert_property({"object_code": code, "name": p.get("name"), "code": p.get("code"),
                               "prop_type": p.get("prop_type", "string"), "required": p.get("required"),
                               "unique_col": p.get("unique_col"), "sensitive": p.get("sensitive"),
                               "source_col": p.get("source_col", ""), "options": p.get("options", []),
                               "roles": p.get("roles", []), "description": p.get("description", "")})
    for lk in snap.get("links", []):
        await upsert_link({"source_object": lk.get("source_object"), "target_object": lk.get("target_object"),
                           "name": lk.get("name"), "card": lk.get("card", "many_to_one"),
                           "source_field": lk.get("source_field", ""), "target_field": lk.get("target_field", ""),
                           "description": lk.get("description", "")})
    for a in snap.get("actions", []):
        await upsert_action({"object_code": code, "name": a.get("name"), "code": a.get("code"),
                             "input_schema": a.get("input_schema", []), "white_fields": a.get("white_fields", []),
                             "approval": a.get("approval"), "target_table": a.get("target_table", ""),
                             "method": a.get("method", "update"), "description": a.get("description", "")})
    for f in snap.get("functions", []):
        await upsert_function({"object_code": code, "name": f.get("name"), "code": f.get("code"),
                               "expr": f.get("expr", ""), "description": f.get("description", "")})
    await _log_change(code, "version", "rollback", f"回滚到版本 {rv[2] if len(rv) > 2 else ''}")
    return {"ok": True, "msg": f"已回滚到版本快照 {snap.get('object', {}).get('name', code)}"}


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
# 本体能力（Palantir：能力可挂在本体上，Agent 从本体装配能力）
# ---------------------------------------------------------------------------
_CAP_ONTOLOGY_TYPES = {"function", "action", "grounding"}
_CAP_TOOL_TYPES = {"query", "governance"}


def _cap_meta(t: str) -> tuple[str, str]:
    """能力 type → (source, kind)。source: ontology/platform；kind: tool/component。"""
    t = (t or "generic").lower()
    if t in _CAP_ONTOLOGY_TYPES:
        return "ontology", "tool"
    if t in _CAP_TOOL_TYPES:
        return "platform", "tool"
    return "platform", "component"


async def list_capabilities() -> list[dict]:
    r = await _exec("SELECT id,code,name,type,description,enabled FROM ai_ont_capability "
                    "WHERE is_deleted=false ORDER BY id DESC")
    rows = r.fetchall()
    out = []
    for x in rows:
        source, kind = _cap_meta(x[3])
        out.append({"id": x[0], "code": x[1], "name": x[2], "type": x[3],
                    "description": x[4] or "", "enabled": bool(x[5]),
                    "source": source, "kind": kind})
    return out


async def upsert_capability(data: dict) -> dict:
    code = (data.get("code") or "").strip()
    if not code:
        raise CustomException(msg="能力编码必填")
    if data.get("id"):
        await _exec_write("UPDATE ai_ont_capability SET name=:n, type=:t, description=:d, enabled=:e WHERE id=:id",
                          {"n": data.get("name", code), "t": data.get("type", "generic"),
                           "d": data.get("description", ""), "e": bool(data.get("enabled", True)), "id": data["id"]})
        return {"id": data["id"]}
    try:
        r = await _exec_write("INSERT INTO ai_ont_capability(code,name,type,description,enabled) "
                              "VALUES (:c,:n,:t,:d,:e) RETURNING id",
                              {"c": code, "n": data.get("name", code), "t": data.get("type", "generic"),
                               "d": data.get("description", ""), "e": bool(data.get("enabled", True))})
        return {"id": r.scalar()}
    except Exception as e:  # noqa: BLE001
        if "duplicate" in str(e).lower():
            raise CustomException(msg=f"能力编码 {code} 已存在")
        raise CustomException(msg=f"保存失败：{str(e)[:80]}")


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
    return {"ok": True, "code": obj[0], "name": obj[1], "icon": obj[2], "key_prop": obj[3], "name_prop": obj[4],
            "description": obj[5], "properties": await list_properties(code),
            "links": await list_links(code), "actions": await list_actions(code)}


# ---------------------------------------------------------------------------
# 本体深度建模分析（连通性 / 中心度 / 主键缺失 / 关系完备性）
# ---------------------------------------------------------------------------
async def analyze_ontology() -> dict:
    """对本体元模型做关系图分析并给出建模建议（纯读现有模型，零迁移）。"""
    from collections import Counter, defaultdict

    objs = (await _exec("SELECT code,name FROM ai_ont_object WHERE is_deleted=false")).fetchall()
    props = (await _exec("SELECT object_code,required,unique_col FROM ai_ont_property WHERE is_deleted=false")).fetchall()
    links = (await _exec("SELECT source_object,target_object,card FROM ai_ont_link WHERE is_deleted=false")).fetchall()
    acts = (await _exec("SELECT object_code FROM ai_ont_action WHERE is_deleted=false")).fetchall()

    obj_codes = [r[0] for r in objs]
    obj_name = {r[0]: r[1] for r in objs}
    degree = defaultdict(lambda: {"in": 0, "out": 0})
    for s, t, _c in links:
        if s:
            degree[s]["out"] += 1
        if t:
            degree[t]["in"] += 1
    pk_obj = {p[0] for p in props if p[1] or p[2]}          # required/unique 视为主键候选
    no_pk = [c for c in obj_codes if c not in pk_obj]
    isolated = [c for c in obj_codes if degree[c]["in"] == 0 and degree[c]["out"] == 0]
    card_dist = Counter((l[2] or "many_to_one") for l in links)

    adj = defaultdict(set)
    for s, t, _c in links:
        adj[s].add(t)
        adj[t].add(s)
    seen, comps = set(), []
    for c in obj_codes:
        if c in seen:
            continue
        stack, comp = [c], []
        seen.add(c)
        while stack:
            n = stack.pop()
            comp.append(n)
            for m in adj[n]:
                if m in obj_codes and m not in seen:
                    seen.add(m)
                    stack.append(m)
        comps.append(comp)

    centrality = sorted(obj_codes, key=lambda c: degree[c]["in"] + degree[c]["out"], reverse=True)
    top = [{"code": c, "name": obj_name.get(c, c),
            "degree": degree[c]["in"] + degree[c]["out"],
            "in": degree[c]["in"], "out": degree[c]["out"]} for c in centrality[:8]]

    recs = []
    if no_pk:
        recs.append(f"{len(no_pk)} 个对象缺少主键/必填属性，建议补充唯一或必填属性")
    if isolated:
        recs.append(f"{len(isolated)} 个对象无任何关系，建议接入关系或标记为非业务对象")
    if len(comps) > 1:
        recs.append(f"关系图存在 {len(comps)} 个连通分量，建议打通孤立对象")
    if recs:
        recs.append("可对中心度高的对象优先定义动作与治理规则")
    else:
        recs.append("本体关系结构良好，无显著缺口")

    n_links = len(links)
    n_objs = len(obj_codes)
    return {
        "objects": n_objs, "properties": len(props), "links": n_links, "actions": len(acts),
        "isolated": len(isolated), "no_pk": len(no_pk), "components": len(comps),
        "density": round((2 * n_links / (n_objs * (n_objs - 1))), 4) if n_objs > 1 else 0,
        "card_dist": dict(card_dist),
        "top_central": top,
        "recommendations": recs,
        "nodes": [{"code": c, "name": obj_name.get(c, c),
                   "degree": degree[c]["in"] + degree[c]["out"],
                   "isolated": c in isolated} for c in obj_codes],
        "edges": [{"source": s, "target": t, "card": (c or "many_to_one")} for s, t, c in links],
    }
