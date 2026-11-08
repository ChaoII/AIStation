"""资产描述与自主行动（2026-11-08 从 service.py 拆出）。

- ``generate_asset_descriptions``：用 LLM 给表/字段补中文描述（带数据画像；人工校对后生效）；
- ``autopilot`` / ``autopilot_execute`` / ``autopilot_auto_fix``：治理体检 → 候选行动 → 执行/自愈；
- ``derived_objects`` / ``list_derived_metrics`` / ``compute_derived_metric``：派生指标与派生对象；
- ``list_plugins``：已安装插件清单；
- ``security_audit`` / ``count_writeback_actions``：审计计数（概览看板用）；
- ``_maybe_auto_index``：热度驱动的「对象自动建索引」判定（失败只记日志，绝不影响本次问答）。

``_actor_id`` / ``SYSTEM_DS`` 仍归 ``service.py``，这里用 ``_svc.`` 解析。
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.core.database import async_db_session
from app.core.logger import log

from . import service as _svc
from .llm_schemas import AssetDescriptionOut
from .model import AiQueryAssetColumnModel, AiQueryAssetModel


class AutopilotOps:
    @classmethod
    async def generate_asset_descriptions(cls, auth, force: bool = False) -> dict:
        """用 LLM 为表/字段生成中文描述（带数据画像；人工校对后生效）。

        force=True 时对全部已纳入资产重建，否则仅处理缺描述的。

        ``auth`` 允许为 ``None``（自主巡检/调度器在后台触发时没有 HTTP 用户上下文），
        此时审计列 ``updated_id`` 留空，**不做**任何归属过滤放行。
        """
        actor = _svc._actor_id(auth)
        async with async_db_session() as db:
            from sqlalchemy import select as _sel

            tables = (
                await db.execute(
                    _sel(AiQueryAssetModel).where(
                        AiQueryAssetModel.is_deleted.is_(False),
                        AiQueryAssetModel.included.is_(True),
                    )
                )
            ).scalars().all()
            columns = (
                await db.execute(
                    _sel(AiQueryAssetColumnModel).where(
                        AiQueryAssetColumnModel.is_deleted.is_(False),
                        AiQueryAssetColumnModel.included.is_(True),
                    )
                )
            ).scalars().all()
        # 仅处理缺描述的；force 时全部重建
        need_tables = [(t.table_name, t) for t in tables if force or not (t.description or "").strip()]
        colmap: dict[str, list[tuple[str, Any]]] = {}
        for c in columns:
            if force or not (c.description or "").strip():
                colmap.setdefault(c.table_name, []).append((c.column_name, c))
        if not need_tables and not colmap:
            return {"tables": 0, "columns": 0}
        updated_tables = updated_cols = 0
        # 按表批量生成（带数据画像）
        for tname, trow in need_tables:
            cols = [c[0] for c in colmap.get(tname, [])] or ["(无字段)"]
            profile = await cls._profile_table(tname, cols)
            prof_lines = [f"表 {tname}：共 {profile['rows']} 行"]
            for cname, info in profile["cols"].items():
                if not info:
                    continue
                seg = f"  {cname}: 可空率{info['null_pct']}%、去重后{info['distinct']}个值"
                if info.get("values"):
                    seg += f"，取值[{','.join(info['values'])}]"
                prof_lines.append(seg)
            prompt = (
                "你是数据库元数据专家。请根据字段名与数据画像，为这张数据库表及字段生成简洁的中文业务描述"
                "（每个不超过30字，只说业务含义）。\n"
                f"表名：{tname}\n字段：{', '.join(cols)}\n数据画像：\n" + "\n".join(prof_lines)
            )
            try:
                out = await cls._llm_structured(prompt, AssetDescriptionOut, temperature=0,
                                                max_tokens=2000, tag="aistation-dict")
                data = out.model_dump()
            except Exception as e:  # noqa: BLE001
                log.warning(f"[query] 生成表描述失败 {tname}: {e}")
                continue
            tdesc = (data.get("table") or "").strip()
            async with async_db_session.begin() as dbt:
                obj = await dbt.get(AiQueryAssetModel, trow.id)
                if obj and tdesc:
                    obj.description = tdesc
                    obj.updated_id = actor
                    updated_tables += 1
                cdesc = data.get("columns") or {}
                for colname, cobj in colmap.get(tname, []):
                    d = (cdesc.get(colname) or "").strip()
                    if d and isinstance(cobj, AiQueryAssetColumnModel):
                        cobj.description = d
                        cobj.updated_id = actor
                        updated_cols += 1
        return {"tables": updated_tables, "columns": updated_cols}

    @classmethod
    async def autopilot(cls) -> dict:
        """AIP Autopilot 自主行动中心：规则扫描治理/质量/安全/审批，生成候选自主行动。"""
        actions: list[dict] = []
        try:
            assets = await cls.list_assets()
        except Exception:  # noqa: BLE001
            assets = []
        # 1) 缺中文描述 → 建议生成
        no_desc = [a for a in assets if not a.get("alias") and not a.get("description")][:5]
        if no_desc:
            actions.append({"id": "desc", "type": "enrich", "severity": "low", "target": "资产描述",
                            "suggestion": f"{len(no_desc)} 张表缺少中文描述，建议补齐后可问数更准确",
                            "tables": [a["table_name"] for a in no_desc], "executable": "generate_desc"})
        # 2) DQ 低分 → 建议重扫
        try:
            dq = await cls.dq_overview()
            risk = [x["table"] for x in dq.get("items", []) if (x.get("score") or 0) < 60][:5]
            if risk:
                actions.append({"id": "dq", "type": "repair", "severity": "medium", "target": "数据质量",
                                "suggestion": f"{len(risk)} 个对象 DQ<60，建议重新扫描校验",
                                "tables": risk, "executable": "dq_scan"})
        except Exception:  # noqa: BLE001
            pass
        # 3) 未识别敏感 → 建议敏感扫描
        no_sens = [a["table_name"] for a in assets if (a.get("sensitive_count") or 0) == 0][:5]
        if no_sens:
            actions.append({"id": "sensitive", "type": "audit", "severity": "medium", "target": "敏感识别",
                            "suggestion": f"{len(no_sens)} 张表未识别出敏感字段，建议自动敏感扫描",
                            "tables": no_sens, "executable": "scan_sensitive"})
        # 4) 审批积压 → 建议处理
        try:
            pend = int((await cls.approval_center()).get("total", 0))
            if pend:
                actions.append({"id": "approval", "type": "review", "severity": "high", "target": "审批",
                                "suggestion": f"{pend} 项待人工审批，请及时处理", "tables": [], "executable": "none"})
        except Exception:  # noqa: BLE001
            pass
        # 5) 数据源停用 → 建议确认
        try:
            dss = await cls.list_datasources()
            off = [d["name"] for d in dss if not d.get("enabled")][:5]
            if off:
                actions.append({"id": "ds", "type": "config", "severity": "low", "target": "数据连接",
                                "suggestion": f"{len(off)} 个数据源停用：{'、'.join(off)}，请确认是否启用",
                                "tables": [], "executable": "none"})
        except Exception:  # noqa: BLE001
            pass
        order = {"audit": 0, "repair": 1, "review": 2, "enrich": 3, "config": 4}
        actions.sort(key=lambda a: order.get(a["type"], 9))
        return {"total": len(actions), "actions": actions}

    @classmethod
    async def autopilot_execute(cls, executable: str, table: str = "", auth=None) -> dict:
        """执行一个安全的自主行动：敏感扫描 / DQ 重扫 / 补全描述 / 启用数据源。"""
        if executable == "scan_sensitive" and table:
            r = await cls.scan_sensitive(table)
            return {"ok": True, "msg": f"已对 {table} 完成敏感扫描，识别 {r.get('count', 0)} 个敏感字段"}
        if executable == "dq_scan" and table:
            try:
                await cls.dq_run(table)
                return {"ok": True, "msg": f"已对 {table} 重跑数据质量扫描"}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "msg": f"DQ 重扫失败：{e}"}
        if executable == "generate_desc":
            try:
                # 原来这里是**占位实现**：只把 alias 写成 "数据表 X"（假描述），
                # 前端看是"已补全"，实际一句中文描述都没生成；
                # 而真正调 LLM 的 generate_asset_descriptions / assets/generate-desc
                # 在前端**零入口**。现在两者接上（生成器按"缺描述的资产"批量处理，
                # 只补缺的，不覆盖人工填过的内容）。
                # 注意：生成器是**批量**动作（自己扫描所有缺描述资产），
                # table 参数对它没有意义，所以这里不再要求 table 非空——
                # 否则自主修复（无 table）会掉到"暂不支持"分支。
                r = await cls.generate_asset_descriptions(auth, force=False) or {}
                return {
                    "ok": True,
                    "msg": (
                        f"AI 生成描述完成：表 {r.get('tables', 0)} 条、"
                        f"字段 {r.get('columns', 0)} 条（人工校对后生效）"
                    ),
                }
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "msg": f"补全描述失败：{e}"}
        if executable == "enable_ds" and table:
            try:
                async with async_db_session.begin() as db:
                    from sqlalchemy import text as _t
                    await db.execute(_t(
                        "UPDATE ai_query_datasources SET enabled=true WHERE name=:n AND is_deleted=false"),
                        {"n": table})
                return {"ok": True, "msg": f"已启用数据源 {table}"}
            except Exception as e:  # noqa: BLE001
                return {"ok": False, "msg": f"启用数据源失败：{e}"}
        return {"ok": False, "msg": "该行动为信息项/暂不支持自动执行，请在对应模块处理"}

    @classmethod
    async def autopilot_auto_fix(cls) -> dict:
        """AIP 自主修复全自动调度：自动批量执行所有可执行的自主行动（敏感扫描/补全描述/DQ重扫）。"""
        plan = await cls.autopilot()
        results: list[dict] = []
        # `generate_desc` 本身是**批量**动作（一次扫描全部缺描述资产），只能触发一次。
        # 旧实现把它和「按表」行动放在同一个循环里 → N 张表就全量重跑 N 轮 LLM
        # （白烧 token，且每轮结果互相覆盖）。这里单独处理、只跑一次。
        desc_done = False
        for a in plan["actions"]:
            if a["executable"] not in ("scan_sensitive", "generate_desc", "dq_scan") or not a.get("tables"):
                continue
            if a["executable"] == "generate_desc":
                if desc_done:
                    continue
                desc_done = True
                try:
                    r = await cls.autopilot_execute("generate_desc", "")
                    results.append({"action": a["type"], "table": "",
                                    "ok": bool(r.get("ok")), "msg": r.get("msg", "")})
                except Exception as e:  # noqa: BLE001
                    results.append({"action": a["type"], "table": "", "ok": False, "msg": str(e)})
                continue
            for t in a["tables"]:
                try:
                    r = await cls.autopilot_execute(a["executable"], t)
                    results.append({"action": a["type"], "table": t,
                                    "ok": bool(r.get("ok")), "msg": r.get("msg", "")})
                except Exception as e:  # noqa: BLE001
                    results.append({"action": a["type"], "table": t, "ok": False, "msg": str(e)})
        fixed = sum(1 for r in results if r["ok"])
        return {"attempted": len(results), "fixed": fixed, "results": results}

    @classmethod
    async def derived_objects(cls) -> dict:
        """Ontology 派生对象：从启用了对象的资产派生对象（按数据域聚类 + 派生属性）。"""
        assets = await cls.list_assets()
        objs = [a for a in assets if a.get("object_enabled")]
        domains: dict[str, list[str]] = {}
        for a in objs:
            d = a.get("domain") or "未分域"
            domains.setdefault(d, []).append(a["table_name"])
        derived = [{"name": f"{d}域对象", "base_objects": tables, "count": len(tables),
                    "group": d} for d, tables in domains.items()]
        # 派生属性：为每个派生对象汇总列数/敏感/血缘
        for do in derived:
            do["attributes"] = {
                "total_columns": sum(next((a.get("column_count", 0) for a in objs if a["table_name"] == t), 0) for t in do["base_objects"]),
                "sensitive_fields": sum(next((a.get("sensitive_count", 0) for a in objs if a["table_name"] == t), 0) for t in do["base_objects"]),
                "lineage_count": sum(next((a.get("lineage_count", 0) for a in objs if a["table_name"] == t), 0) for t in do["base_objects"]),
            }
        return {"base_objects": len(objs), "derived_objects": derived,
                "total_derived": len(derived), "domains": list(domains.keys())}

    @classmethod
    async def list_derived_metrics(cls) -> list[dict]:
        """派生指标规则引擎：基于基础指标自动推导（分子/分母/除数）。"""
        metrics = await cls.list_metrics(_svc.SYSTEM_DS)
        name_map = {m["key"]: m["name"] for m in metrics}
        out = []
        for r in cls._DERIVED_RULES:
            base = []
            if r.get("num"):
                base.append({"ref": r["num"], "name": name_map.get(r["num"], r["num"])})
            if r.get("den"):
                base.append({"ref": r["den"], "name": name_map.get(r["den"], r["den"])})
            out.append({
                "key": r["key"], "name": r["name"], "unit": r["unit"],
                "desc": r["desc"], "base": base,
                "formula": (f"{r['num']}" + (f" / {r['den']}" if r.get("den") else "") +
                            (f" / {r['divisor']}" if r.get("divisor") else "")),
            })
        return out

    @classmethod
    async def compute_derived_metric(cls, key: str) -> dict:
        """计算派生指标值（基于基础指标真实执行 SQL）。"""
        r = next((x for x in cls._DERIVED_RULES if x["key"] == key), None)
        if not r:
            return {"ok": False, "msg": "派生指标不存在"}
        num = await cls._metric_value(r["num"])
        if num is None:
            return {"ok": False, "msg": f"基础指标 {r['num']} 不可计算"}
        if r.get("den"):
            den = await cls._metric_value(r["den"])
            if den is None:
                return {"ok": False, "msg": f"基础指标 {r['den']} 不可计算"}
            value = num / den if den else 0
        else:
            divisor = r.get("divisor") or 1
            value = num / divisor if divisor else 0
        value = round(value, 2)
        return {"ok": True, "key": key, "name": r["name"], "value": value, "unit": r["unit"],
                "base": {"num": num, "den": (r.get("den") and await cls._metric_value(r["den"])) or None}}

    @classmethod
    async def list_plugins(cls) -> list[dict]:
        """AIP 插件目录：为 Agent/应用提供扩展工具能力。"""
        return [
            {"key": "web_fetch", "name": "网页抓取", "kind": "数据接入", "enabled": True,
             "desc": "抓取外部网页内容，供 Agent 阅读理解"},
            {"key": "table_export", "name": "表格导出", "kind": "输出", "enabled": True,
             "desc": "将问数结果导出为 Excel/CSV"},
            {"key": "email_send", "name": "邮件发送", "kind": "消息", "enabled": True,
             "desc": "把分析报告/告警通过邮件推送"},
            {"key": "report_generate", "name": "报告生成", "kind": "产出", "enabled": True,
             "desc": "AI 自动生成结构化报告"},
            {"key": "data_pipeline", "name": "数据管道", "kind": "数据接入", "enabled": True,
             "desc": "通过管道（ELT）拉取外部数据落库"},
        ]

    @classmethod
    async def security_audit(cls, limit: int = 30) -> dict:
        """数据安全与访问审计中心：敏感资产/字段 + 数据源安全 + ABAC 规则 + 访问审计日志 + 安全评分。"""
        assets = await cls.list_assets()
        sens_assets = [a for a in assets if (a.get("sensitive_count") or 0) > 0]
        sens_fields = sum(a.get("sensitive_count", 0) for a in assets)
        rules = await cls.list_access_rules()
        ds = await cls.list_datasources()
        ds_security = [{"name": d["name"], "type": d["type"],
                        "read_only": bool(d.get("read_only")), "enabled": bool(d.get("enabled"))}
                       for d in ds]
        logs = await cls.list_action_logs(limit)
        # 安全评分（覆盖敏感识别/权限规则/数据源只读）
        dims = []
        if assets:
            cover = len(sens_assets) / len(assets)
            dims.append({"key": "sens", "name": "敏感识别", "score": round(cover * 100),
                         "detail": f"{len(sens_assets)}/{len(assets)} 资产识别到敏感字段"})
        else:
            dims.append({"key": "sens", "name": "敏感识别", "score": 100, "detail": "无数据资产"})
        dims.append({"key": "access", "name": "ABAC 规则", "score": 100 if rules else 0,
                     "detail": f"{len(rules)} 条权限规则"})
        read_only_cnt = sum(1 for d in ds_security if d["read_only"])
        ds_score = 100 if not ds_security or read_only_cnt == len(ds_security) else round(read_only_cnt / len(ds_security) * 100)
        dims.append({"key": "ds", "name": "连接只读", "score": ds_score,
                     "detail": f"{read_only_cnt}/{len(ds_security)} 数据源只读"})
        overall = round(sum(d["score"] for d in dims) / len(dims)) if dims else 0
        issues = [{"level": d["score"] < 60 and "danger" or d["score"] < 80 and "warning" or "success",
                   "msg": f"{d['name']}：{d['detail']}"} for d in dims]
        return {"score": overall, "dims": dims, "issues": issues,
                "assets": len(assets), "sensitive_assets": len(sens_assets),
                "sensitive_fields": sens_fields, "access_rules": len(rules),
                "datasources": ds_security, "action_logs": logs, "log_count": len(logs)}

    @classmethod
    async def count_writeback_actions(cls) -> int:
        """动作回写（`ai_query_writeback`）条数——控制台统一审计的跨模块取数入口。

        ⚠️ 该表 ``is_deleted`` 是 **boolean**，PG 下写 ``is_deleted=0`` 会直接报
        ``operator does not exist: bool``（历史调用方在 except 里吞掉，导致这个数字
        恒为 0）。
        """
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            return int(
                (
                    await db.execute(
                        _t("SELECT COUNT(*) FROM ai_query_writeback WHERE is_deleted=false")
                    )
                ).scalar()
                or 0
            )

    @classmethod
    async def _maybe_auto_index(cls, object_code: str, cfg: dict) -> None:
        """热度驱动自动建索引（G4）：命中次数达阈值且尚未建过 → 后台按建议建索引。

        为什么需要：对象查询的执行后端是实例层，**它的快慢直接取决于过滤/分组字段
        有没有索引**。让高频对象自动补索引，比让用户自己去「索引」页手动点更现实。

        设计取舍：只做**热度触发 + 后台执行**，不新建索引体系（复用 ``indexing.py``）；
        失败不阻断问答，且允许下次重试。
        """
        if not object_code:
            return
        if not cls._cfg_bool(cfg, "object_query_auto_index_enabled", False):
            return
        threshold = cls._cfg_int(cfg, "object_query_auto_index_after", 20)
        _svc._OQ_HEAT[object_code] = _svc._OQ_HEAT.get(object_code, 0) + 1
        if _svc._OQ_HEAT[object_code] < threshold or object_code in _svc._OQ_INDEXED:
            return
        _svc._OQ_INDEXED.add(object_code)      # 先占位：并发命中时只建一次
        asyncio.create_task(cls._auto_index(object_code))   # 后台执行，不阻塞本次问答
