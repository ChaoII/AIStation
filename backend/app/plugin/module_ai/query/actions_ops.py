"""动作 / 写回 / 审批（2026-11-08 从 service.py 拆出）。

这一组方法只依赖 ``async_db_session`` 与 ``cls`` 上的其它方法，互相内聚：
定义（``list_actions`` / ``upsert_action``）、权限（``_action_writable_for`` /
``_user_role_codes_by_id`` / ``_is_superuser``）、执行（``execute_action``）、
审批（``pending`` / ``approve`` / ``reject``）、审计（``list_action_logs``）。

搬进 mixin 而不是独立模块函数，是为了让 ``cls`` 仍是 ``AiQueryService``：
``execute_action`` 里的 ``cls.list_actions()`` 等跨方法调用照旧解析。
"""
from __future__ import annotations

from app.core.database import async_db_session


class ActionsOps:
    @classmethod
    async def list_actions(cls) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            res = await db.execute(_t(
                "SELECT id,name,object_table,writable_cols,writable_by_role,validation,approve,enabled "
                "FROM ai_query_writeback WHERE is_deleted=false ORDER BY id DESC"))
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "name": r[1], "object_table": r[2],
            "writable_cols": r[3] if isinstance(r[3], list) else (_json.loads(r[3]) if r[3] else []),
            "writable_by_role": r[4] if isinstance(r[4], dict) else (_json.loads(r[4]) if r[4] else {}),
            "validation": r[5] or "", "approve": bool(r[6]), "enabled": bool(r[7]),
        } for r in rows]

    @classmethod
    async def upsert_action(cls, data: dict) -> dict:
        import json as _json
        cols = _json.dumps(data.get("writable_cols") or [], ensure_ascii=False)
        wr = _json.dumps(data.get("writable_by_role") or {}, ensure_ascii=False)
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            if data.get("id"):
                await db.execute(_t(
                    "UPDATE ai_query_writeback SET name=:n, object_table=:o, writable_cols=:w, writable_by_role=:wr, "
                    "validation=:v, approve=:a, enabled=:e, updated_time=now() WHERE id=:i"), {
                    "n": data.get("name", ""), "o": data.get("object_table", ""), "w": cols, "wr": wr,
                    "v": data.get("validation", ""), "a": bool(data.get("approve", True)),
                    "e": bool(data.get("enabled", True)), "i": data["id"]})
                return {"id": data["id"]}
            res = await db.execute(_t(
                "INSERT INTO ai_query_writeback(name,object_table,writable_cols,writable_by_role,validation,approve,enabled) "
                "VALUES (:n,:o,:w,:wr,:v,:a,:e) ON CONFLICT (name) DO UPDATE SET object_table=:o, "
                "writable_cols=:w, writable_by_role=:wr, validation=:v, approve=:a, enabled=:e RETURNING id"), {
                "n": data.get("name", ""), "o": data.get("object_table", ""), "w": cols, "wr": wr,
                "v": data.get("validation", ""), "a": bool(data.get("approve", True)),
                "e": bool(data.get("enabled", True))})
            return {"id": res.scalar()}

    @classmethod
    async def _user_role_codes_by_id(cls, user_id) -> set[str]:
        """按 user_id 查询其角色 code 集合（sys_user_roles → sys_role）。"""
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            uid = 0
        if not uid:
            return set()
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                rows = (await db.execute(_t(
                    "SELECT r.code FROM sys_role r JOIN sys_user_roles ur ON ur.role_id=r.id "
                    "WHERE ur.user_id=:u AND r.is_deleted=false"), {"u": uid})).fetchall()
            return {r[0] for r in rows}
        except Exception:  # noqa: BLE001
            return set()

    @classmethod
    async def _action_writable_for(cls, act: dict, operator: str) -> set[str]:
        """动作可写字段：超管/未配角色字段 → 全局 writable_cols；否则收窄为该角色允许字段的交集。"""
        writable = set(act.get("writable_cols") or [])
        wr = act.get("writable_by_role") or {}
        if not wr:
            return writable
        try:
            if await cls._is_superuser(operator):
                return writable
        except Exception:  # noqa: BLE001
            pass
        roles = await cls._user_role_codes_by_id(operator)
        role_allowed: set[str] = set()
        for r in roles:
            role_allowed |= set(wr.get(r) or [])
        if role_allowed:
            return writable & role_allowed
        return writable

    @classmethod
    async def execute_action(cls, name: str, object_key: str, params: dict, operator: str, approve: bool = False) -> dict:
        """P1·Action 写回：校验动作+可写字段，更新对象行，写审计日志。approve 未通过则只返回待审批。"""
        from sqlalchemy import text as _t
        actions = await cls.list_actions()
        act = next((a for a in actions if a["name"] == name), None)
        if not act or not act.get("enabled"):
            return {"ok": False, "msg": "动作不存在或未启用"}
        table = act["object_table"]
        writable = await cls._action_writable_for(act, operator)
        if not writable:
            return {"ok": False, "msg": "该动作未配置可写字段"}
        # 审批门禁：需审批且未批准 → 落审批单（pending），返回待审批 id
        if act.get("approve") and not approve:
            import json as _json
            async with async_db_session.begin() as db:
                pres = await db.execute(_t(
                    "INSERT INTO ai_query_writeback_log(action_name,object_table,object_key,params,operator,result,detail) "
                    "VALUES (:n,:t,:k,:p,:o,'pending','待审批') RETURNING id"), {
                    "n": name, "t": table, "k": object_key,
                    "p": _json.dumps(params, ensure_ascii=False), "o": operator or ""})
                pid = pres.scalar()
            return {"ok": False, "msg": "该操作需人工审批后执行", "needs_approval": True,
                    "approval_id": pid, "pending": {"params": params, "key": object_key}}
        # 校验 params 列均在可写集合
        cols = list(params.keys())
        bad = [c for c in cols if c not in writable]
        if bad:
            return {"ok": False, "msg": f"以下字段不可写：{','.join(bad)}"}
        if not object_key:
            return {"ok": False, "msg": "缺少对象关键值"}
        sets = ", ".join(f'"{c}" = :{c}' for c in cols)
        try:
            from .ddl_dialect import cast_text

            # 主键可能是 int/bigint，写入侧拿到的是字符串 → 两边都转文本再比。
            # 不能写 `"id"::text`：SQLite 不认 `::`（near "::": syntax error），
            # 而这里只有一个 try，失败即整个写回动作报「执行失败」。
            key_expr = cast_text('"id"')
            async with async_db_session.begin() as db:
                res = await db.execute(_t(
                    f'UPDATE "{table}" SET {sets} WHERE {key_expr} = :__k'), {**params, "__k": str(object_key)})
                detail = f"action={name} {table}#{object_key} cols={cols}"
            # 审计
            import json as _json
            async with async_db_session.begin() as db2:
                await db2.execute(_t(
                    "INSERT INTO ai_query_writeback_log(action_name,object_table,object_key,params,operator,result,detail) "
                    "VALUES (:n,:t,:k,:p,:o,:r,:d)"), {
                    "n": name, "t": table, "k": object_key,
                    "p": _json.dumps(params, ensure_ascii=False), "o": operator or "",
                    "r": "success" if res.rowcount else "noop", "d": detail})
            return {"ok": True, "rows": int(res.rowcount or 0), "msg": "已执行并留痕"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"执行失败：{str(e)[:120]}"}

    @classmethod
    async def _is_superuser(cls, user_id) -> bool:
        """按 user_id 判断是否超管（用于审批人约束）。"""
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            uid = 0
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                r = (await db.execute(_t(
                    "SELECT is_superuser FROM sys_user WHERE id=:id AND is_deleted=false"),
                    {"id": uid})).fetchone()
            return bool(r and r[0])
        except Exception:  # noqa: BLE001
            return False

    @classmethod
    async def list_pending_actions(cls, limit: int = 50) -> list[dict]:
        """待审批的 Action 写回请求（result='pending'）。"""
        import json as _json
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            res = await db.execute(_t(
                "SELECT id,action_name,object_table,object_key,params,operator,created_time "
                "FROM ai_query_writeback_log WHERE result='pending' AND is_deleted=false "
                "ORDER BY id DESC LIMIT :n"), {"n": max(1, min(limit, 200))})
            rows = res.fetchall()
        return [{
            "id": r[0], "action": r[1], "table": r[2], "key": r[3],
            "params": r[4] if isinstance(r[4], dict) else (_json.loads(r[4]) if r[4] else {}),
            "operator": r[5], "time": str(r[6]) if r[6] else "",
        } for r in rows]

    @classmethod
    async def approve_action(cls, approval_id: int, operator: str) -> dict:
        """批准待审批的 Action：执行真实写回（可写字段校验）+ 落审计，审批单置为 approved。

        审批人约束：仅超管可批准写回。
        """
        if not await cls._is_superuser(operator):
            return {"ok": False, "msg": "仅超管可审批写回操作"}
        import json as _json

        from sqlalchemy import text as _t
        async with async_db_session() as db:
            row = (await db.execute(_t(
                "SELECT action_name,object_table,object_key,params FROM ai_query_writeback_log "
                "WHERE id=:i AND result='pending' AND is_deleted=false"), {"i": approval_id})).fetchone()
        if not row:
            return {"ok": False, "msg": "审批单不存在或已处理"}
        name, table, key, params = row[0], row[1], row[2], row[3]
        params = params if isinstance(params, dict) else (_json.loads(params) if params else {})
        actions = await cls.list_actions()
        act = next((a for a in actions if a["name"] == name), None)
        if not act or not act.get("enabled"):
            return {"ok": False, "msg": "动作不存在或未启用"}
        writable = await cls._action_writable_for(act, operator)
        cols = list(params.keys())
        bad = [c for c in cols if c not in writable]
        if bad:
            return {"ok": False, "msg": f"以下字段不可写：{','.join(bad)}"}
        if not key:
            return {"ok": False, "msg": "缺少对象关键值"}
        sets = ", ".join(f'"{c}" = :{c}' for c in cols)
        try:
            from .ddl_dialect import cast_text

            key_expr = cast_text('"id"')  # 方言无关的「主键转文本再比较」，见 execute_action
            async with async_db_session.begin() as db:
                res = await db.execute(_t(
                    f'UPDATE "{table}" SET {sets} WHERE {key_expr} = :__k'),
                    {**params, "__k": str(key)})
                await db.execute(_t(
                    "UPDATE ai_query_writeback_log SET result='approved', detail=:d, operator=:o WHERE id=:i"),
                    {"d": f"已批准，影响 {res.rowcount} 行", "o": operator or "", "i": approval_id})
            return {"ok": True, "rows": int(res.rowcount or 0), "msg": "已批准并执行留痕"}
        except Exception as e:  # noqa: BLE001
            async with async_db_session.begin() as db:
                await db.execute(_t(
                    "UPDATE ai_query_writeback_log SET result='rejected', detail=:d WHERE id=:i"),
                    {"d": f"批准执行失败：{str(e)[:100]}", "i": approval_id})
            return {"ok": False, "msg": f"执行失败：{str(e)[:120]}"}

    @classmethod
    async def reject_action(cls, approval_id: int, operator: str) -> dict:
        """驳回待审批的 Action。审批人约束：仅超管可驳回。"""
        if not await cls._is_superuser(operator):
            return {"ok": False, "msg": "仅超管可驳回写回操作"}
        from sqlalchemy import text as _t
        async with async_db_session.begin() as db:
            await db.execute(_t(
                "UPDATE ai_query_writeback_log SET result='rejected', detail=:d WHERE id=:i AND result='pending'"),
                {"d": f"已驳回 by {operator or ''}", "i": approval_id})
        return {"ok": True, "msg": "已驳回"}

    @classmethod
    async def list_action_logs(cls, limit: int = 100) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            res = await db.execute(_t(
                "SELECT id,action_name,object_table,object_key,params,operator,result,detail,created_time "
                "FROM ai_query_writeback_log WHERE is_deleted=false ORDER BY id DESC LIMIT :n"), {"n": max(1, min(limit, 200))})
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "action": r[1], "table": r[2], "key": r[3],
            "params": r[4] if isinstance(r[4], dict) else (_json.loads(r[4]) if r[4] else {}),
            "operator": r[5], "result": r[6], "detail": r[7] or "", "time": str(r[8]) if r[8] else "",
        } for r in rows]
