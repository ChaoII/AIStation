"""资产版本：快照、对比、发布、回滚（2026-11-08 从 service.py 拆出）。

- 资产写入前 ``_record_version`` 落一份写前快照；
- ``version_diff`` 给字段级差异，``asset_publish`` / ``asset_releases`` 做发布；
- ``rollback_version`` 回滚到指定版本（先记当前态，回滚本身也可回滚）。
"""
from __future__ import annotations

from app.core.database import async_db_session


class VersionOps:
    @classmethod
    async def _record_version(cls, table_name: str, snapshot: dict, field_name: str = "", operator: str = "") -> None:
        import json as _json
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t

            n = (await db.execute(_t(
                "SELECT COALESCE(MAX(version_no),0) FROM ai_asset_version WHERE table_name=:t AND field_name=:f AND is_deleted=false"),
                {"t": table_name, "f": field_name})).scalar() or 0
            await db.execute(_t(
                "INSERT INTO ai_asset_version(table_name,field_name,snapshot,version_no,operator) "
                "VALUES (:t,:f,:s,:n,:o)"), {
                "t": table_name, "f": field_name, "s": _json.dumps(snapshot, ensure_ascii=False),
                "n": int(n) + 1, "o": operator or ""})

    @classmethod
    async def list_versions(cls, table_name: str) -> list[dict]:
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            res = await db.execute(_t(
                "SELECT id,table_name,field_name,snapshot,version_no,operator,created_time "
                "FROM ai_asset_version WHERE table_name=:t AND is_deleted=false ORDER BY id DESC LIMIT 50"),
                {"t": table_name})
            rows = res.fetchall()
        import json as _json
        return [{
            "id": r[0], "table": r[1], "field": r[2],
            "snapshot": r[3] if isinstance(r[3], dict) else (_json.loads(r[3]) if r[3] else {}),
            "version": r[4], "operator": r[5] or "", "time": str(r[6]) if r[6] else "",
        } for r in rows]

    @classmethod
    async def version_diff(cls, id_a: int, id_b: int) -> dict:
        """版本 diff：对比两个版本快照，输出新增/删除/变更的字段（表级或字段级）。"""
        import json as _json
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            ra = (await db.execute(_t("SELECT table_name,field_name,snapshot,version_no FROM ai_asset_version WHERE id=:i AND is_deleted=false"), {"i": id_a})).fetchone()
            rb = (await db.execute(_t("SELECT table_name,field_name,snapshot,version_no FROM ai_asset_version WHERE id=:i AND is_deleted=false"), {"i": id_b})).fetchone()
        if not ra or not rb:
            return {"ok": False, "msg": "版本不存在"}

        def _load(raw):
            return raw if isinstance(raw, dict) else (_json.loads(raw) if raw else {})
        sa, sb = _load(ra[2]), _load(rb[2])
        keys = set(sa.keys()) | set(sb.keys())
        changed = []
        for k in sorted(keys):
            va, vb = sa.get(k), sb.get(k)
            if va != vb:
                changed.append({"key": k, "from": va, "to": vb})
        return {"ok": True, "table": ra[0], "field": ra[1] or "", "field_b": rb[1] or "",
                "version_a": ra[3], "version_b": rb[3],
                "changed": changed, "changed_count": len(changed)}

    @classmethod
    async def asset_publish(cls, table_name: str, version_id: int, auth) -> dict:
        """数据集/对象版本发布：把指定版本标记为当前发布版本（可回滚发布）。"""
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            v = (await db.execute(_t(
                "SELECT table_name,field_name,snapshot,version_no FROM ai_asset_version WHERE id=:i AND is_deleted=false"),
                {"i": version_id})).fetchone()
        if not v:
            return {"ok": False, "msg": "版本不存在"}
        if v[0] != table_name:
            return {"ok": False, "msg": "版本不属于该对象"}
        from datetime import datetime
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            await cls._ensure_asset_publish(db)
            # 跨库 upsert：先删后插（PG/MySQL/SQLite 通用；避免 SQLite 专属 INSERT OR REPLACE）
            await db.execute(_t("DELETE FROM ai_asset_publish WHERE table_name=:t"), {"t": table_name})
            await db.execute(_t(
                "INSERT INTO ai_asset_publish(table_name,version_id,published_time,operator) "
                "VALUES (:t,:v,:now,:op)"),
                {"t": table_name, "v": int(version_id),
                 "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 "op": str(getattr(getattr(auth, "user", None), "id", ""))})
        return {"ok": True, "table": table_name, "version": v[3], "msg": f"已发布版本 {v[3]}"}

    @staticmethod
    async def _ensure_asset_publish(db) -> None:
        """幂等创建「发布版本」记录表（asset_releases 查询前 / 发布前都需保证存在）。

        历史缺陷：建表只写在「发布」动作里，而「版本」弹窗先查 asset_releases，
        表不存在时直接 400。这里统一建表，兼容 PG（VARCHAR 主键）。"""
        from sqlalchemy import text as _t
        await db.execute(_t(
            "CREATE TABLE IF NOT EXISTS ai_asset_publish "
            "(table_name VARCHAR(255) PRIMARY KEY, version_id INTEGER, "
            "published_time VARCHAR(64), operator VARCHAR(64))"))

    @classmethod
    async def asset_releases(cls, table_name: str) -> dict:
        """当前发布版本 + 该对象的版本列表（含是否已发布）。"""
        import json as _json
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            await cls._ensure_asset_publish(db)
            version_rows = (await db.execute(_t(
                "SELECT id,field_name,snapshot,version_no,created_time FROM ai_asset_version "
                "WHERE table_name=:t AND is_deleted=false ORDER BY version_no DESC LIMIT 50"),
                {"t": table_name})).fetchall()
            pub = (await db.execute(_t(
                "SELECT version_id,published_time FROM ai_asset_publish WHERE table_name=:t"),
                {"t": table_name})).fetchone()
        published_version_id = int(pub[0]) if pub else None
        versions = []
        for r in version_rows:
            snap = r[2] if isinstance(r[2], dict) else (_json.loads(r[2]) if r[2] else {})
            versions.append({"id": r[0], "field": r[1] or "", "snapshot": snap,
                             "version": r[3], "time": str(r[4]) if r[4] else "",
                             "published": (r[0] == published_version_id)})
        return {"table": table_name, "published_version_id": published_version_id,
                "published_time": str(pub[1]) if pub and pub[1] else "",
                "versions": versions}

    @classmethod
    async def rollback_version(cls, version_id: int, auth) -> dict:
        import json as _json
        async with async_db_session() as db:
            from sqlalchemy import text as _t

            v = (await db.execute(_t(
                "SELECT table_name,field_name,snapshot,version_no FROM ai_asset_version WHERE id=:i AND is_deleted=false"),
                {"i": version_id})).fetchone()
        if not v:
            return {"ok": False, "msg": "版本不存在"}
        table, field, snap_raw, vno = v[0], v[1], v[2], v[3]
        snap = snap_raw if isinstance(snap_raw, dict) else (_json.loads(snap_raw) if snap_raw else {})
        if field:
            # 字段级回滚
            async with async_db_session.begin() as db:
                from sqlalchemy import text as _t
                await db.execute(_t(
                    "UPDATE ai_query_asset_columns SET description=:d, business_scenarios=:s, "
                    "related_table=:rt, related_field=:rf, sensitive=:se "
                    "WHERE table_name=:t AND column_name=:c AND is_deleted=false"), {
                    "d": snap.get("description", ""), "s": snap.get("business_scenarios", ""),
                    "rt": snap.get("related_table") or "", "rf": snap.get("related_field") or "",
                    "se": bool(snap.get("sensitive", False)), "t": table, "c": field})
        else:
            async with async_db_session.begin() as db:
                from sqlalchemy import text as _t
                await db.execute(_t(
                    "UPDATE ai_query_assets SET alias=:a, domain=:d, description=:de, business_scenarios=:b, "
                    "included=:i, object_enabled=:oe, object_key_col=:ok, object_name_col=:on, object_icon=:oi "
                    "WHERE table_name=:t AND is_deleted=false"), {
                    "a": snap.get("alias", ""), "d": snap.get("domain", ""), "de": snap.get("description", ""),
                    "b": snap.get("business_scenarios", ""), "i": bool(snap.get("included", True)),
                    "oe": bool(snap.get("object_enabled", False)), "ok": snap.get("object_key_col") or "id",
                    "on": snap.get("object_name_col") or "name", "oi": snap.get("object_icon") or "el-icon-Box",
                    "t": table})
        await cls._record_version(table, snap, field, operator=str(getattr(getattr(auth, "user", None), "id", "")))
        _SCHEMA_CACHE = None
        _ASSET_TMETA = None
        return {"ok": True, "msg": f"已回滚到版本 {vno}"}
