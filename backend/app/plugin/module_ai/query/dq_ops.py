"""数据质量：规则校验 / 表体检 / 总览 / 告警（2026-11-08 从 service.py 拆出）。

- ``dq_rules_run``：非空率、唯一性（``table``/``column`` 先过「标识符 + 按用户白名单」，
  拼 SQL 前校验，fail-closed）；
- ``dq_run``：单表体检（行数、空值、枚举、敏感列、主键唯一性…），产出健康分与问题清单；
- ``dq_overview`` / ``dq_scan_all`` / ``dq_alert``：批量扫描、总览与预警汇总。

``_load_ds`` / ``_ds_code`` / ``SYSTEM_DS`` 仍归 ``service.py``，这里用 ``_svc.`` 解析。
"""
from __future__ import annotations

from app.core.database import async_db_session
from app.core.logger import log

from . import service as _svc


class DqOps:
    @classmethod
    async def dq_rules_list(cls) -> list[dict]:
        metrics = await cls.list_metrics(_svc.SYSTEM_DS)
        return [dict(t) | {"on": bool(metrics)} for t in cls._DQ_RULE_TEMPLATES]

    @classmethod
    async def dq_rules_run(cls, table: str, column: str, rule_type: str, auth) -> dict:
        """执行数据质量规则：非空率/唯一性。"""
        # P0-1：table/column 都被拼进 SELECT，先过「标识符 + 按用户白名单」校验
        table = await cls._require_queryable_table(table, auth)
        column = cls._require_ident(column, "列名")
        if rule_type == "not_null":
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                try:
                    total = (await db.execute(_t(f'SELECT COUNT(*) FROM "{table}"'))).scalar() or 0
                    nonnull = (await db.execute(_t(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" IS NOT NULL'))).scalar() or 0
                except Exception:  # noqa: BLE001
                    return {"ok": False, "msg": f"无法校验表 {table} 字段 {column}"}
            rate = round(nonnull / total * 100, 1) if total else 100.0
            return {"ok": True, "rule": "not_null", "table": table, "column": column,
                    "total": total, "valid": nonnull, "pass_rate": rate, "passed": rate >= 99}
        if rule_type == "unique":
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                try:
                    total = (await db.execute(_t(f'SELECT COUNT(*) FROM "{table}"'))).scalar() or 0
                    uniq = (await db.execute(_t(f'SELECT COUNT(DISTINCT "{column}") FROM "{table}"'))).scalar() or 0
                except Exception:  # noqa: BLE001
                    return {"ok": False, "msg": f"无法校验表 {table} 字段 {column}"}
            rate = round(uniq / total * 100, 1) if total else 100.0
            return {"ok": True, "rule": "unique", "table": table, "column": column,
                    "total": total, "valid": uniq, "pass_rate": rate, "passed": rate >= 99}
        return {"ok": False, "msg": "不支持的规则类型"}

    @classmethod
    async def dq_run(cls, table_name: str, *, schema: dict | None = None,
                     engine=None) -> dict:
        """P3-⑦ 数据质量(DQ)：对业务对象扫描 完整性/唯一性/新鲜度 并打分落库。

        对象既可能落在**系统库**（本地会话直查），也可能落在**业务数据源**
        （如 ds:4 燃煤业务库，需走远端只读连接）。旧实现只认系统 schema，
        导致业务对象在 DQ 页「有对象却不能扫」（点扫描必报「不在可用 schema」），
        属于对象源与扫描能力不一致的断层。

        ``schema`` / ``engine`` 可由 ``dq_scan_all`` 传入复用（避免逐表重新探 schema、
        逐表新建远端连接——业务库对象多时那会建立上百条连接）。
        """
        import json as _json
        objs = await cls.list_objects()
        obj = next((o for o in objs if o["table"] == table_name), None)
        if not obj:
            return {"ok": False, "msg": f"{table_name} 不是业务对象，暂不支持 DQ"}
        if schema is None:
            schema = await cls._system_schema()
        ds_id = int(obj.get("datasource_id") or 0)
        local_ok = table_name in schema
        if not local_ok and not ds_id:
            # 表可能真实存在但不在系统库白名单（如 sys_dept/sys_position 这类本体对象）——
            # 白名单只约束「问数可查范围」，不该让 DQ 对存在的表直接判「不支持」。
            async with async_db_session() as db:
                from sqlalchemy import text as _t

                local_ok = bool((await db.execute(
                    _t("SELECT to_regclass(:t)"), {"t": table_name})).scalar())
        if not local_ok and not ds_id:
            return {"ok": False, "msg": f"{table_name} 不在可用 schema"}
        name_col, key_col = obj["name_col"], obj["key_col"]
        total = 0
        name_null = name_distinct = key_distinct = None
        fresh_ts = None
        if local_ok:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                total = (await db.execute(_t(f'SELECT count(*) FROM "{table_name}"'))).scalar() or 0
                try:
                    name_null = (await db.execute(_t(
                        f'SELECT count(*) FROM "{table_name}" WHERE "{name_col}" IS NULL'))).scalar() or 0
                    name_distinct = (await db.execute(_t(
                        f'SELECT count(DISTINCT "{name_col}") FROM "{table_name}"'))).scalar() or 0
                except Exception:  # noqa: BLE001
                    pass
                try:
                    key_distinct = (await db.execute(_t(
                        f'SELECT count(DISTINCT "{key_col}") FROM "{table_name}"'))).scalar() or 0
                except Exception:  # noqa: BLE001
                    pass
                for c in ("updated_time", "created_time"):
                    try:
                        mv = (await db.execute(_t(f'SELECT max({c}) FROM "{table_name}"'))).scalar()
                        if mv:
                            fresh_ts = mv
                            break
                    except Exception:  # noqa: BLE001
                        pass
        else:
            # 业务数据源：远端只读扫描（口径与系统库一致）
            from . import executor as _ex

            own_engine = engine is None
            if own_engine:
                ds = await _svc._load_ds(ds_id)
                engine = _ex.build_engine(_svc._ds_cfg_from_model(ds))

            async def _one_multiline(sql: str):
                async with engine.connect() as conn:
                    from sqlalchemy import text as _t

                    return (await conn.execute(_t(sql))).scalar()

            try:
                total = int(await _one_multiline(f'SELECT count(*) FROM "{table_name}"') or 0)
                try:
                    name_null = int(await _one_multiline(
                        f'SELECT count(*) FROM "{table_name}" WHERE "{name_col}" IS NULL') or 0)
                    name_distinct = int(await _one_multiline(
                        f'SELECT count(DISTINCT "{name_col}") FROM "{table_name}"') or 0)
                except Exception:  # noqa: BLE001
                    name_null = name_distinct = None
                try:
                    key_distinct = int(await _one_multiline(
                        f'SELECT count(DISTINCT "{key_col}") FROM "{table_name}"') or 0)
                except Exception:  # noqa: BLE001
                    key_distinct = None
                time_col = await cls._pick_time_col(table_name, _svc._ds_code(ds_id))
                if time_col:
                    try:
                        fresh_ts = await _one_multiline(
                            f'SELECT max("{time_col}") FROM "{table_name}"')
                    except Exception:  # noqa: BLE001
                        fresh_ts = None
            finally:
                if own_engine and engine is not None:
                    await engine.dispose()
        if isinstance(fresh_ts, str):
            try:
                from datetime import datetime as _dt

                fresh_ts = _dt.fromisoformat(str(fresh_ts).replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                fresh_ts = None
        # 打分
        comp = round(100 - (name_null / total * 100) if total else 100, 1) if name_null is not None else 100
        if total and name_distinct is not None:
            uniq = round(name_distinct / total * 100, 1)
        elif total and key_distinct is not None:
            uniq = round(key_distinct / total * 100, 1)
        else:
            uniq = 100.0
        from datetime import date, datetime, time, timezone

        if isinstance(fresh_ts, date) and not isinstance(fresh_ts, datetime):
            # 业务库的「新鲜度列」可能只到日期精度（max(date_col) 返回 date），
            # 直接读 .tzinfo 会 AttributeError，整表扫描失败（实测 view_aikb_* 系列）。
            fresh_ts = datetime.combine(fresh_ts, time(0, 0), tzinfo=timezone.utc)
        if fresh_ts:
            if fresh_ts.tzinfo is None:
                fresh_ts = fresh_ts.replace(tzinfo=timezone.utc)
            days = max(0, (datetime.now(timezone.utc) - fresh_ts).days)
            fresh = round(max(0.0, 100 - days * 5), 1)
        else:
            fresh = 0.0
        score = round(comp * 0.4 + uniq * 0.3 + fresh * 0.3, 1)
        issues = []
        if name_null is not None and total and name_null / total > 0.05:
            issues.append(f"名称列 {name_col} 空值率 {round(name_null / total * 100, 1)}%")
        if total and name_distinct is not None and name_distinct < total:
            issues.append(f"名称列 {name_col} 有 {total - name_distinct} 条重名")
        if total and key_distinct is not None and key_distinct < total:
            issues.append(f"主键列 {key_col} 不唯一（{total - key_distinct} 重复）")
        if fresh_ts is None:
            issues.append("无更新时间列，新鲜度未知")
        # 注意：本项目是「请求作用域会话」，同一请求内 ``async_db_session()`` 返回同一个
        # session；这里若用 ``begin()`` 会在已有事务上再开事务而报错，把整个请求事务打挂
        # （实测 dq/scan 全量扫描时 250 个对象连续失败）。改为显式 commit。
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            await db.execute(_t(
                "UPDATE ai_dq_report SET is_deleted=true WHERE table_name=:t"), {"t": table_name})
            await db.execute(_t(
                "INSERT INTO ai_dq_report(table_name,alias,total,score,completeness,uniqueness,freshness,issues,checked_at) "
                "VALUES (:t,:a,:n,:s,:c,:u,:f,:i,now())"), {
                "t": table_name, "a": obj["alias"], "n": total, "s": score,
                "c": comp, "u": uniq, "f": fresh,
                "i": _json.dumps(issues, ensure_ascii=False)})
            await db.commit()
        return {"ok": True, "table": table_name, "alias": obj["alias"], "total": total,
                "score": score, "completeness": comp, "uniqueness": uniq, "freshness": fresh,
                "issues": issues}

    @classmethod
    async def dq_overview(cls) -> dict:
        """P3-⑦ DQ 总览：对象源与「对象列表」同源（本体对象），质量分读 ai_dq_report 缓存。

        旧实现对象源取 ``ai_query_assets(object_enabled)``，而预警/治理总览取本体对象，
        两者口径不一 → 业务数据源对象（ds:4 燃煤表）在 DQ 页根本不出现。
        """
        objs = await cls._objects_light()
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rep_rows = (await db.execute(_t(
                "SELECT table_name,alias,total,score,completeness,uniqueness,freshness,issues,checked_at "
                "FROM ai_dq_report WHERE is_deleted=false"))).fetchall()
        cache = {r[0]: {"alias": r[1], "total": r[2], "score": float(r[3]),
                        "completeness": float(r[4]), "uniqueness": float(r[5]),
                        "freshness": float(r[6]), "issues": r[7],
                        "checked_at": str(r[8]) if r[8] else ""} for r in rep_rows}
        results = []
        for o in objs:
            t = o["table"]
            results.append(cache.get(t, {"table": t, "alias": o.get("alias") or t, "total": 0,
                                         "score": 0, "completeness": 0, "uniqueness": 0,
                                         "freshness": 0, "issues": [], "checked_at": "",
                                         "scanned": False})
                           | {"table": t, "scanned": t in cache})
        scored = [x for x in results if x.get("scanned")]
        avg = round(sum((x["score"] or 0) for x in scored) / len(scored), 1) if scored else 0
        return {"avg_score": avg, "total_objects": len(results),
                "healthy": sum(1 for x in scored if (x["score"] or 0) >= 80),
                "risk": sum(1 for x in scored if (x["score"] or 0) < 60),
                "items": results}

    @classmethod
    async def dq_scan_all(cls) -> dict:
        """P3-⑦ 显式全量扫描全部业务对象。

        按数据源分组：系统库复用一次 schema 探取，业务数据源每个源只建一条引擎，
        扫完即释放（旧实现逐表新建引擎，对象一多就会建立上百条远端连接）。
        """
        objs = await cls.list_objects()
        try:
            schema = await cls._system_schema()
        except Exception:  # noqa: BLE001
            schema = {}
        from . import executor as _ex

        engines: dict[int, object] = {}
        scanned = 0
        failed: list[str] = []
        try:
            for o in objs:
                ds_id = int(o.get("datasource_id") or 0)
                engine = None
                if o["table"] not in schema and ds_id:
                    engine = engines.get(ds_id)
                    if engine is None:
                        try:
                            ds = await _svc._load_ds(ds_id)
                            engine = _ex.build_engine(_svc._ds_cfg_from_model(ds))
                            engines[ds_id] = engine
                        except Exception:  # noqa: BLE001
                            failed.append(o["table"])
                            continue
                try:
                    r = await cls.dq_run(o["table"], schema=schema, engine=engine)
                except Exception as e:  # noqa: BLE001
                    log.warning(f"[query] DQ 扫描失败 {o['table']}: {str(e)[:120]}")
                    failed.append(o["table"])
                    continue
                if r.get("ok"):
                    scanned += 1
        finally:
            for eng in engines.values():
                try:
                    await eng.dispose()
                except Exception:  # noqa: BLE001
                    pass
        msg = f"已扫描 {scanned} 个对象"
        if failed:
            msg += f"，{len(failed)} 个失败"
        return {"ok": True, "scanned": scanned, "failed": len(failed), "msg": msg}

    @classmethod
    async def dq_alert(cls) -> dict:
        """P3-⑧ DQ 预警 + 影响联动：风险对象(健康分<60) → 血缘下游影响(对象/指标/管道/概念)。"""
        ov = await cls.dq_overview()
        objs = {o["table"]: o for o in await cls._objects_light()}
        obmap = await cls._object_backing_map()
        pipelines = await cls.list_pipelines()
        metrics = await cls.list_metrics()
        concepts = await cls.list_concepts()
        alerts = []
        for it in ov["items"]:
            # 未扫描对象不按 0 分计入预警（避免 mes_equipment/orders 等未扫描对象误导口径）
            if not it.get("scanned"):
                continue
            if (it["score"] or 0) < 60:
                t = it["table"]
                async with async_db_session() as db:
                    from sqlalchemy import text as _t
                    deps = (await db.execute(_t(
                        "SELECT DISTINCT related_table FROM ai_query_asset_columns "
                        "WHERE related_table=:t AND is_deleted=false"), {"t": t})).fetchall()
                dep_objs = [objs.get(r[0], {}).get("alias") or r[0] for r in deps if r[0] and r[0] != t]
                rel_mets = [m["name"] for m in metrics if t in (m.get("sql_template") or "")]
                rel_pips = [p["name"] for p in pipelines
                            if p["target_object"] == t
                            or (obmap.get(str(p["target_object"])) or "").upper() == t.upper()]
                rel_concepts = [c["name"] for c in concepts if t in (c.get("tables") or [])]
                alerts.append({
                    "table": it["table"], "alias": it["alias"],
                    "score": it["score"], "issues": it["issues"] or [],
                    "downstream": {"objects": dep_objs, "metrics": rel_mets,
                                   "pipelines": rel_pips, "concepts": rel_concepts},
                })
        return {"count": len(alerts), "alerts": alerts}

    @classmethod
    async def _dq_warning_for_sql(cls, sql: str) -> list[dict]:
        """DQ 联动：若问数 SQL 涉及 DQ 风险对象表（健康分 <60），返回警告（温和提示，不硬拦）。"""
        if not sql:
            return []
        try:
            overview = await cls.dq_overview()
        except Exception:  # noqa: BLE001
            return []
        risk = {x.get("table"): x.get("score") for x in overview.get("items", [])
                if (x.get("score") or 0) < 60}
        if not risk:
            return []
        used = [t for t in risk if t in sql]
        return [{"table": t, "score": risk[t]} for t in used]
