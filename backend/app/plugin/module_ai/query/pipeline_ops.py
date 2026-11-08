"""数据管道：定义、图、执行、取数（2026-11-08 从 service.py 拆出）。

管道 = 「源表 → 节点（筛选/聚合/关联）→ 目标表」，执行结果落 ``ai_pipeline_run``；
``pipeline_graph`` 供前端画布读取，``pipeline_data`` 供预览取数。
"""
from __future__ import annotations

from types import SimpleNamespace

from app.core.database import async_db_session

from . import service as _svc
from .schema import QueryAssetUpsert


class PipelineOps:
    @classmethod
    async def pipeline_run_status(cls) -> dict[str, int]:
        """数据管道运行状态分布（`ai_pipeline_run` 按 status 计数）。"""
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rows = (
                await db.execute(
                    _t(
                        "SELECT status, count(*) FROM ai_pipeline_run "
                        "WHERE is_deleted=false GROUP BY status"
                    )
                )
            ).fetchall()
        return {str(r[0]): int(r[1]) for r in rows}

    @classmethod
    async def pipeline_graph(cls) -> dict:
        """数据管道(ELT)编排图：源表 → 管道 → 本体对象，返回 nodes/edges（number id 供 GraphCanvas）。"""
        pipes = await cls.list_pipelines()
        nodes: list[dict] = []
        edges: list[dict] = []
        idmap: dict[str, int] = {}

        def nid(key: str) -> int:
            if key not in idmap:
                idmap[key] = len(idmap) + 1
            return idmap[key]

        def add_node(key: str, name: str, etype: str) -> None:
            if key in idmap:
                return
            i = nid(key)
            nodes.append({"id": i, "name": name or "-", "etype": etype, "weight": 1})

        for p in pipes:
            src = f"src:{p.get('source_table')}"
            pipe = f"pipe:{p.get('name')}"
            tgt = f"obj:{p.get('target_object')}"
            add_node(pipe, p.get("name") or "管道", "pipeline")
            if p.get("source_table"):
                add_node(src, p["source_table"], "source")
                edges.append({"source": nid(src), "target": nid(pipe), "rtype": "to", "weight": 1})
            if p.get("target_object"):
                add_node(tgt, p["target_object"], "object")
                edges.append({"source": nid(pipe), "target": nid(tgt), "rtype": "writes", "weight": 1})
        return {"nodes": nodes, "edges": edges}

    @classmethod
    async def list_pipelines(cls, datasource: str | None = None) -> list[dict]:
        datasource = await _svc._norm_datasource(datasource)
        async with async_db_session() as db:
            from sqlalchemy import inspect
            from sqlalchemy import text as _t

            # `datasource` 是后补列：SQLite 不支持 `ADD COLUMN IF NOT EXISTS`，老测试库可能没有。
            # 探测列是否存在而不是「先查再兜底异常」，避免事务被污染。
            has_ds = await db.run_sync(
                lambda s: "datasource" in {
                    c["name"] for c in inspect(s.connection()).get_columns("ai_pipeline")
                }
            )
            ds_col = "p.datasource" if has_ds else "''"
            sql = (
                "SELECT p.id,p.name,p.source_connection,p.source_table,p.target_object,p.mappings,p.enabled,"
                "(SELECT status FROM ai_pipeline_run r WHERE r.pipeline_id=p.id AND r.is_deleted=false ORDER BY r.id DESC LIMIT 1) AS last_status,"
                "(SELECT ran_at FROM ai_pipeline_run r WHERE r.pipeline_id=p.id AND r.is_deleted=false ORDER BY r.id DESC LIMIT 1) AS last_at,"
                f"{ds_col} "
                "FROM ai_pipeline p WHERE p.is_deleted=false")
            params: dict = {}
            if datasource and has_ds:
                sql += " AND p.datasource=:ds"
                params["ds"] = datasource
            sql += " ORDER BY p.id DESC"
            rows = (await db.execute(_t(sql), params)).fetchall()
        import json as _json
        return [{
            "id": r[0], "name": r[1] or "", "source_connection": r[2] or "", "source_table": r[3] or "",
            "target_object": r[4] or "",
            "mappings": r[5] if isinstance(r[5], list) else (_json.loads(r[5]) if r[5] else []),
            "enabled": bool(r[6]), "last_status": r[7] or "", "last_at": str(r[8]) if r[8] else "",
            "datasource": r[9] or "",
        } for r in rows]

    @classmethod
    async def upsert_pipeline(cls, data: dict) -> dict:
        import json as _json
        mp = _json.dumps(data.get("mappings") or [], ensure_ascii=False)
        ds = await _svc._norm_datasource((data.get("datasource") or "").strip()) or ""
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            if data.get("id"):
                await db.execute(_t(
                    "UPDATE ai_pipeline SET name=:n, source_connection=:sc, source_table=:st, "
                    "target_object=:to, mappings=:m, enabled=:e, datasource=:ds, updated_time=now() WHERE id=:i"), {
                    "n": data.get("name", ""), "sc": data.get("source_connection", ""),
                    "st": data.get("source_table", ""), "to": data.get("target_object", ""),
                    "m": mp, "e": bool(data.get("enabled", True)), "ds": ds, "i": data["id"]})
                return {"id": data["id"]}
            res = await db.execute(_t(
                "INSERT INTO ai_pipeline(name,source_connection,source_table,target_object,mappings,enabled,datasource) "
                "VALUES (:n,:sc,:st,:to,:m,:e,:ds) RETURNING id"), {
                "n": data.get("name", ""), "sc": data.get("source_connection", ""),
                "st": data.get("source_table", ""), "to": data.get("target_object", ""),
                "m": mp, "e": bool(data.get("enabled", True)), "ds": ds})
            return {"id": res.scalar()}

    @classmethod
    async def run_pipeline(cls, pipeline_id: int) -> dict:
        """P3-⑤ 真实数据接入：从外部数据源/本系统拉取源表数据，按映射落库到目标对象表，并同步资产与运行血缘。

        source_connection 为数字 → 视为外部数据源 id（走 executor 真实连接拉数）；
        否则 / 空 → 视为本系统表。目标数据落到 ``ai_pipeline_data_{id}`` 运行物化表。
        """
        import json as _json
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            row = (await db.execute(_t(
                "SELECT name,source_connection,source_table,target_object,mappings FROM ai_pipeline "
                "WHERE id=:i AND is_deleted=false"), {"i": pipeline_id})).fetchone()
        if not row:
            return {"ok": False, "msg": "管道不存在"}
        name, sc, st, to, mp_raw = row[0], row[1], row[2], row[3], row[4]
        mappings = mp_raw if isinstance(mp_raw, list) else (_json.loads(mp_raw) if mp_raw else [])
        # 映射键名兼容两种口径：界面保存的是 {from,to}，早期/接口保存的是 {source_col,target_col}。
        # 只认后者会让「界面上新建的管道」运行时 target_cols 全空 → 落库必失败（真实断层）。
        norm_maps = []
        for mp in mappings:
            if not isinstance(mp, dict):
                continue
            s = str(mp.get("source_col") or mp.get("from") or "").strip()
            t = str(mp.get("target_col") or mp.get("to") or s).strip()
            if s or t:
                norm_maps.append({"source_col": s, "target_col": t or s})
        mappings = norm_maps
        # 1) 拉取源数据
        try:
            if str(sc).strip().isdigit() and int(sc) > 0:
                ds = await _svc._load_ds(int(sc))
                cfg = _svc._ds_cfg_from_model(ds)
                from . import executor as _ex
                res = await _ex.execute_select(cfg, f'SELECT * FROM "{st}" LIMIT 200')
                src_cols, src_rows = res.get("columns") or [], res.get("rows") or []
                source_desc = f"{ds.name}({ds.type})"
            else:
                async with async_db_session() as db:
                    from sqlalchemy import text as _t
                    src = (await db.execute(_t(
                        f'SELECT * FROM "{st}" LIMIT 200'))).mappings().fetchall()
                src_cols = list(src[0].keys()) if src else []
                src_rows = [[str(v) if v is not None else None for v in r.values()] for r in src]
                source_desc = f"本系统 {st}"
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"拉取源数据失败：{str(e)[:120]}"}
        # 2) 按映射构建目标行
        col_idx = {c: i for i, c in enumerate(src_cols)}
        target_cols: list[str] = []
        for mp in mappings:
            t = mp.get("target_col") or mp.get("source_col")
            if t and t not in target_cols:  # 去重：同名列重复会让建表 DDL 冲突
                target_cols.append(t)
        target_rows: list[list] = []
        for r in src_rows:
            out = []
            for mp in mappings:
                s = mp.get("source_col", "")
                val = r[col_idx[s]] if s in col_idx else None
                out.append(val)
            target_rows.append(out)
        # 3) 物化到 ai_pipeline_data_{id}（全量刷新）
        materialized = 0
        try:
            async with async_db_session.begin() as db:
                from sqlalchemy import text as _t
                tname = f"ai_pipeline_data_{pipeline_id}"
                cols_ddl = ", ".join(f'"{c}" TEXT' for c in target_cols) if target_cols else ""
                await db.execute(_t(
                    f'CREATE TABLE IF NOT EXISTS "{tname}" (id BIGSERIAL PRIMARY KEY, {cols_ddl})'))
                await db.execute(_t(f'DELETE FROM "{tname}"'))
                for r in target_rows:
                    ph = ", ".join(f":c{i}" for i in range(len(r)))
                    cols_sql = ", ".join(f'"{c}"' for c in target_cols) if target_cols else ""
                    params = {f"c{i}": v for i, v in enumerate(r)}
                    await db.execute(_t(
                        f'INSERT INTO "{tname}" ({cols_sql}) VALUES ({ph})'), params)
                    materialized += 1
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"落库失败：{str(e)[:120]}"}
        # 3.5) 目标为本体对象 → 把数据同步进本体对象表 ont_{to}（数据与集成支撑本体）
        ont_synced = 0
        try:
            objs = await cls._ont_objs()
            if to in objs:
                ont_table = f"ont_{to}"
                props = await cls._ont_props(to)
                prop_codes = [p["code"] for p in props] or target_cols
                cols_ddl = ", ".join(f'"{c}" TEXT' for c in prop_codes)
                async with async_db_session.begin() as db:
                    from sqlalchemy import text as _t
                    await db.execute(_t(
                        f'CREATE TABLE IF NOT EXISTS "{ont_table}" (id BIGSERIAL PRIMARY KEY, {cols_ddl})'))
                    await db.execute(_t(f'DELETE FROM "{ont_table}"'))
                    for r in target_rows:
                        # 仅写入本体属性列
                        mapped = dict(zip(target_cols, r, strict=False))
                        ins_cols = [c for c in prop_codes if c in mapped]
                        if not ins_cols:
                            continue
                        ph = ", ".join(f":c{i}" for i in range(len(ins_cols)))
                        cols_sql = ", ".join(f'"{c}"' for c in ins_cols)
                        params = {f"c{i}": mapped[c] for i, c in enumerate(ins_cols)}
                        await db.execute(_t(
                            f'INSERT INTO "{ont_table}" ({cols_sql}) VALUES ({ph})'), params)
                        ont_synced += 1
        except Exception:  # noqa: BLE001
            ont_synced = 0
        # 4) 同步资产元数据（对象可见 + 映射目标列描述）
        meta = (await cls._asset_tmeta()).get(to) or {}
        try:
            await cls.upsert_asset(QueryAssetUpsert(
                table_name=to, alias=meta.get("alias") or to, domain=meta.get("domain") or "接入",
                description=meta.get("description") or f"由管道 {name} 接入", business_scenarios="",
                included=True, remark="", object_enabled=True, object_key_col="id",
                object_name_col="name", object_icon="el-icon-Connection"),
                SimpleNamespace(user=SimpleNamespace(id=1)))
            async with async_db_session.begin() as db:
                from sqlalchemy import text as _t
                for mp in mappings:
                    tgt = mp.get("target_col") or mp.get("source_col")
                    upd = await db.execute(_t(
                        "UPDATE ai_query_asset_columns SET description=:d WHERE table_name=:t AND column_name=:c AND is_deleted=false"),
                        {"t": to, "c": tgt, "d": f"自 {source_desc}.{st}#{mp.get('source_col')} 接入"})
                    if not (upd.rowcount or 0):
                        await db.execute(_t(
                            "INSERT INTO ai_query_asset_columns(table_name,column_name,description,included,is_deleted) "
                            "VALUES (:t,:c,:d,true,false)"), {"t": to, "c": tgt, "d": f"自 {source_desc}.{st}#{mp.get('source_col')} 接入"})
        except Exception:  # noqa: BLE001
            pass
        # 5) 记录运行
        msg = f"自 {source_desc}.{st} 拉取 {len(src_rows)} 行，落库 {materialized} 行到对象 {to}"
        async with async_db_session.begin() as db:
            from sqlalchemy import text as _t
            await db.execute(_t(
                "INSERT INTO ai_pipeline_run(pipeline_id,status,message,rows) VALUES (:p,'success',:m,:r)"),
                {"p": pipeline_id, "m": msg, "r": materialized})
        _SCHEMA_CACHE = None
        _ASSET_TMETA = None
        return {"ok": True, "msg": msg, "synced": len(mappings), "rows": materialized, "ont_synced": ont_synced}

    @classmethod
    async def pipeline_data(cls, pipeline_id: int, limit: int = 50) -> dict:
        """P3-⑤ 查看管道落库结果（物化表 ai_pipeline_data_{id}）。"""
        tname = f"ai_pipeline_data_{pipeline_id}"
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                res = await db.execute(_t(f'SELECT * FROM "{tname}" ORDER BY id DESC LIMIT :n'), {"n": limit})
                cols = list(res.keys())
                rows = [list(r) for r in res.fetchall()]
            return {"ok": True, "columns": cols, "rows": rows}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "msg": f"暂无落库结果：{str(e)[:80]}"}
