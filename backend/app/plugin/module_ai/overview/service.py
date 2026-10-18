"""AI 概览统计与调用日志。"""
from sqlalchemy import func, select

from app.core.database import async_db_session

from .model import AiCallLogModel


class AiOverviewService:

    @classmethod
    def eval_match(cls, text: str, keywords: list[str] | None) -> bool:
        """评估器（影子回归核心）：实际输出是否包含全部关键断言（大小写不敏感）。"""
        t = (text or "").lower()
        return all((k or "").strip().lower() in t for k in (keywords or []) if str(k).strip())

    @classmethod
    async def run_eval(cls, samples: list[dict]) -> dict:
        """AI 能力评估（影子对比）：对每个 sample {input, expected_keywords, actual} 判通过，输出精度。

        expected_keywords 为"关键断言子串"，命中即通过；适合评估问数/知识库/摘要等产出。
        """
        total = len(samples)
        passed = 0
        rows = []
        for s in samples:
            ok = cls.eval_match(s.get("actual"), s.get("expected_keywords"))
            if ok:
                passed += 1
            rows.append({"input": s.get("input"), "ok": ok})
        return {"total": total, "passed": passed,
                "precision": round(passed / total, 4) if total else 0, "rows": rows}

    @classmethod
    async def health_check(cls, days: int = 7) -> dict:
        """AI 健康/异常监控：聚合近 N 天调用量/错误率/平均延迟/成本 + 健康状态与告警。

        取数走 `logs_center`（`ai_call_logs` 的读 owner），本方法只负责阈值判定与告警文案。
        """
        from app.plugin.module_ai.logs_center.service import AiLogService

        agg = await AiLogService.health_aggregate(days)
        calls = agg["calls"]
        errors = agg["errors"]
        avg_latency = agg["avg_latency_ms"]
        total_cost = agg["total_cost"]
        error_rate = round(errors / calls, 4) if calls else 0.0
        alerts = []
        if error_rate > 0.05:
            alerts.append({"level": "critical", "msg": f"近{days}天错误率 {error_rate * 100:.1f}% 超过 5%"})
        elif error_rate > 0.02:
            alerts.append({"level": "warning", "msg": f"近{days}天错误率 {error_rate * 100:.1f}% 超过 2%"})
        if avg_latency > 5000:
            alerts.append({"level": "warning", "msg": f"近{days}天平均延迟 {avg_latency}ms 超过 5s"})
        if alerts:
            status = "critical" if any(a["level"] == "critical" for a in alerts) else "warning"
        else:
            status = "healthy"
        return {"days": days, "calls": calls, "errors": errors, "error_rate": error_rate,
                "avg_latency_ms": avg_latency, "total_cost": total_cost, "status": status,
                "alerts": alerts}

    @classmethod
    async def audit_check(cls, days: int = 7) -> dict:
        """AI 调用合规审计：未鉴权(user_id 为空)调用/失败调用/高成本调用，输出合规报告。

        取数走 `logs_center`，本方法只负责合规判定与问题文案。
        """
        from app.plugin.module_ai.logs_center.service import AiLogService

        agg = await AiLogService.audit_aggregate(days)
        total = agg["total"]
        anon = agg["anonymous_calls"]
        errs = agg["error_calls"]
        high_cost = agg["high_cost_calls"]
        issues = []
        if anon:
            issues.append({"level": "warning", "msg": f"近{days}天有 {anon} 条未鉴权调用（缺用户ID）"})
        if errs:
            issues.append({"level": "warning", "msg": f"近{days}天有 {errs} 条失败调用"})
        if high_cost:
            issues.append({"level": "warning", "msg": f"近{days}天有 {high_cost} 条高成本调用(>1元)"})
        return {"days": days, "total": total, "anonymous_calls": anon,
                "error_calls": errs, "high_cost_calls": high_cost,
                "compliant": not issues, "issues": issues}

    @classmethod
    async def runtime_status(cls) -> dict:
        """系统运行监控（Palantir Observability）：聚合 应用/工作流/模型/Agent/管道 运行状态 + AI 健康。"""
        from sqlalchemy import func as _f
        from sqlalchemy import select as _sel

        from app.plugin.module_ai.agent.model import AiAgentModel
        from app.plugin.module_ai.apps.model import AiAppModel
        from app.plugin.module_ai.models.model import AiModelModel
        from app.plugin.module_ai.workflow.model import AiWorkflowModel
        async with async_db_session() as db:
            apps = (await db.execute(_sel(_f.count()).select_from(AiAppModel).where(AiAppModel.is_deleted.is_(False)))).scalar() or 0
            workflows = (await db.execute(_sel(_f.count()).select_from(AiWorkflowModel).where(AiWorkflowModel.is_deleted.is_(False)))).scalar() or 0
            models = (await db.execute(_sel(_f.count()).select_from(AiModelModel).where(AiModelModel.is_deleted.is_(False)))).scalar() or 0
            agents = (await db.execute(_sel(_f.count()).select_from(AiAgentModel).where(AiAgentModel.is_deleted.is_(False)))).scalar() or 0
            try:
                from sqlalchemy import text as _t
                preset_status = (await db.execute(_t(
                    "SELECT status, count(*) FROM ai_pipeline_run WHERE is_deleted=false GROUP BY status"))).fetchall()
                pipeline_status = {r[0]: int(r[1]) for r in preset_status}
            except Exception:  # noqa: BLE001
                pipeline_status = {}
        health = await cls.health_check(7)
        return {"apps": apps, "workflows": workflows, "models": models, "agents": agents,
                "pipeline_status": pipeline_status,
                "health": {"status": health["status"], "error_rate": health["error_rate"],
                           "avg_latency_ms": health["avg_latency_ms"], "calls": health["calls"]}}

    @classmethod
    async def aip_control(cls, limit: int = 20) -> dict:
        """AIP 控制台（Palantir AIP Control）：Agent/AI 运行追踪 + 用途分布 + 人工审核队列。"""
        from app.plugin.module_ai.logs_center.service import AiLogService

        runs = await AiLogService.recent_runs(limit)
        usage_dist: dict[str, int] = {}
        for r in runs:
            usage_dist[r["usage"]] = usage_dist.get(r["usage"], 0) + 1
        pending_review = 0
        try:
            from app.plugin.module_ai.query.service import AiQueryService
            pending_review = int((await AiQueryService.approval_center()).get("total", 0))
        except Exception:  # noqa: BLE001
            pending_review = 0
        return {"runs": runs, "usage_dist": usage_dist,
                "pending_review": pending_review, "total": len(runs)}

    @classmethod
    async def compliance_posture(cls) -> dict:
        """安全与合规姿态评分（0-100）：敏感识别/权限覆盖/数据域/DQ/审批/调用合规 分维度。"""
        from app.plugin.module_ai.query.service import AiQueryService
        dims: list[dict] = []
        try:
            assets = await AiQueryService.list_assets()
        except Exception:  # noqa: BLE001
            assets = []
        # 1) 敏感识别覆盖
        if assets:
            covered = sum(1 for a in assets if (a.get("sensitive_count") or 0) > 0)
            ratio = covered / len(assets)
            dims.append({"key": "sensitive", "name": "敏感识别", "score": round(ratio * 100),
                         "detail": f"{covered}/{len(assets)} 资产已识别敏感字段"})
        else:
            dims.append({"key": "sensitive", "name": "敏感识别", "score": 100, "detail": "暂无数据资产"})
        # 2) 权限规则覆盖
        try:
            rules = await AiQueryService.list_access_rules()
            rule_score = 100 if len(rules) >= 1 else 0
            dims.append({"key": "access", "name": "权限规则", "score": rule_score,
                         "detail": f"{len(rules)} 条 ABAC 权限策略"})
        except Exception:  # noqa: BLE001
            dims.append({"key": "access", "name": "权限规则", "score": 0, "detail": "无法统计"})
        # 3) 数据域覆盖
        try:
            domains = await AiQueryService.list_domains()
            dims.append({"key": "domain", "name": "数据域", "score": 100 if len(domains) >= 1 else 0,
                         "detail": f"{len(domains)} 个数据域"})
        except Exception:  # noqa: BLE001
            dims.append({"key": "domain", "name": "数据域", "score": 0, "detail": "无法统计"})
        # 4) 数据质量
        try:
            dq = await AiQueryService.dq_overview()
            dims.append({"key": "dq", "name": "数据质量", "score": int(dq.get("avg_score", 0)),
                         "detail": f"平均 {dq.get('avg_score', 0)} 分"})
        except Exception:  # noqa: BLE001
            dims.append({"key": "dq", "name": "数据质量", "score": 0, "detail": "无法统计"})
        # 5) 审批积压
        pending = 0
        try:
            pending = int((await AiQueryService.approval_center()).get("total", 0))
        except Exception:  # noqa: BLE001
            pending = 0
        dims.append({"key": "approval", "name": "审批积压", "score": max(0, 100 - pending * 10) if pending else 100,
                     "detail": f"{pending} 项待审批" if pending else "无积压"})
        # 6) 调用合规
        audit = await cls.audit_check(7)
        dims.append({"key": "audit", "name": "调用合规", "score": 100 if audit.get("compliant") else 60,
                     "detail": f"{len(audit.get('issues', []))} 项合规问题"})
        findings = [{"level": d["score"] < 60 and "danger" or d["score"] < 80 and "warning" or "success",
                     "msg": f"{d['name']}：{d['detail']}"} for d in dims]
        overall = round(sum(d["score"] for d in dims) / len(dims)) if dims else 0
        return {"score": overall, "dims": dims,
                "findings": findings,
                "pending_approvals": pending,
                "level": "excellent" if overall >= 90 else "good" if overall >= 70 else "needs_attention"}

    @classmethod
    async def anomaly_detect(cls, days: int = 7) -> dict:
        """AI 异常检测：按日聚合调用，对比基线识别错误率/延迟异常。"""
        from app.plugin.module_ai.logs_center.service import AiLogService

        rows = await AiLogService.daily_trend(days)
        lats = [r["avg_latency_ms"] for r in rows]
        base_lat = sum(lats) / len(lats) if lats else 0
        anomalies = []
        for r in rows:
            d = r["date"]
            n = r["count"]
            e = r["error"]
            lat = r["avg_latency_ms"]
            er = e / n if n else 0
            if er > 0.10:
                anomalies.append({"date": d, "type": "error_rate", "severity": "high",
                                  "value": round(er * 100, 1),
                                  "msg": f"{d} 错误率 {er * 100:.1f}% 异常升高（>10%）"})
            if base_lat > 0 and lat > base_lat * 3:
                anomalies.append({"date": d, "type": "latency", "severity": "medium",
                                  "value": lat,
                                  "msg": f"{d} 平均延迟 {lat}ms，为基线 {int(base_lat)}ms 的 3 倍以上"})
        return {"days": days, "baseline_latency_ms": int(base_lat),
                "anomalies": anomalies[:20], "total": len(anomalies)}

    @classmethod
    async def decision_center(cls) -> dict:
        """AIP 决策建议中心：从 异常/合规/自主修复/审批 汇聚行动决策建议。"""
        from app.plugin.module_ai.query.service import AiQueryService
        decisions: list[dict] = []
        try:
            an = await cls.anomaly_detect(7)
            for a in an["anomalies"][:3]:
                decisions.append({"key": "anomaly", "title": "处理 AI 调用异常", "reason": a["msg"],
                                  "impact": "影响 AI 稳定性", "action": "查看 AIP 运行追踪定位",
                                  "pri": "high", "executable": "navigate", "target": "/ai/overview"})
        except Exception:  # noqa: BLE001
            pass
        try:
            audit = await cls.audit_check(7)
            if not audit.get("compliant"):
                decisions.append({"key": "compliance", "title": "消除合规风险", "reason": f"{len(audit.get('issues', []))} 项合规问题",
                                  "impact": "数据安全合规", "action": "处理审计问题", "pri": "high",
                                  "executable": "navigate", "target": "/ai/overview"})
        except Exception:  # noqa: BLE001
            pass
        try:
            plan = await AiQueryService.autopilot()
            if plan["total"]:
                decisions.append({"key": "autopilot", "title": "执行自主修复", "reason": f"{plan['total']} 项待修复建议",
                                  "impact": "提升数据质量/安全", "action": "运行 AIP 自动修复", "pri": "medium",
                                  "executable": "autopilot"})
        except Exception:  # noqa: BLE001
            pass
        try:
            pend = int((await AiQueryService.approval_center()).get("total", 0))
            if pend:
                decisions.append({"key": "approval", "title": "处理待审批", "reason": f"{pend} 项待审批",
                                  "impact": "打通发布/写回闭环", "action": "前往审批中心", "pri": "medium",
                                  "executable": "navigate", "target": "/ai/query"})
        except Exception:  # noqa: BLE001
            pass
        order = {"high": 0, "medium": 1, "low": 2}
        decisions.sort(key=lambda d: order.get(d["pri"], 3))
        return {"total": len(decisions), "decisions": decisions}

    @classmethod
    async def decision_execute(cls, key: str) -> dict:
        """执行决策建议：autopilot 走自动修复，其余为跳转指引。"""
        from app.plugin.module_ai.query.service import AiQueryService
        if key == "autopilot":
            r = await AiQueryService.autopilot_auto_fix()
            return {"ok": True, "msg": f"自动修复完成 {r.get('fixed', 0)}/{r.get('attempted', 0)}", "data": r}
        return {"ok": False, "msg": "该项为跳转指引，请在对应页面操作", "navigate": True}

    @classmethod
    async def activity_timeline(cls, days: int = 7, limit: int = 60) -> dict:
        """统一活动时间线：聚合 AI 调用 / 动作回写为时间线视图。

        取数分别走 `logs_center`（调用日志）与 `catalog`（回写审计）：跨模块共享表不直读。
        """
        from app.plugin.module_ai import catalog
        from app.plugin.module_ai.logs_center.service import AiLogService

        events: list[dict] = []
        for r in await AiLogService.recent_runs(limit, days=days):
            events.append({
                "time": r["created_time"], "kind": "ai_call",
                "title": f"{r['model']} · {r['usage']}",
                "result": r["result"], "detail": f"延迟 {r['latency_ms']}ms",
                "actor": f"user#{r['user_id']}" if r["user_id"] else "匿名",
            })
        for r in await catalog.list_writebacks(limit):
            events.append({
                "time": r["created_time"], "kind": "action",
                "title": f"动作 {r['action_name']}", "result": r["result"],
                "detail": f"对象 {r['object_table']}",
                "actor": r["operator"] or "系统",
            })
        events.sort(key=lambda e: str(e["time"]), reverse=True)
        return {"total": len(events), "events": events[:limit]}

    # ---------------------------------------------------------------- #
    # AIP 评测基准（制品化回归）
    # ---------------------------------------------------------------- #
    @classmethod
    async def _ensure_eval_bench_table(cls, db) -> None:
        from sqlalchemy import text as _t
        dialect = (db.bind.dialect.name if db.bind else "")
        if dialect == "postgresql":
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_eval_bench ("
                "id BIGSERIAL PRIMARY KEY, name VARCHAR(128), precision NUMERIC, "
                "total INTEGER, operator TEXT, created_time TIMESTAMP)"))
        else:
            await db.execute(_t(
                "CREATE TABLE IF NOT EXISTS ai_eval_bench ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, precision REAL, "
                "total INTEGER, operator TEXT, created_time TEXT)"))

    @classmethod
    async def eval_bench_run(cls, samples: list[dict], name: str, auth=None) -> dict:
        """运行评测并固化结果（制品化），支持多次对比。"""
        from datetime import datetime
        result = await cls.run_eval(samples)
        operator = str(getattr(getattr(auth, "user", None), "id", ""))
        async with async_db_session.begin() as db:
            await cls._ensure_eval_bench_table(db)
            from sqlalchemy import text as _t
            await db.execute(_t(
                "INSERT INTO ai_eval_bench(name,precision,total,operator,created_time) "
                "VALUES (:n,:p,:t,:o,:now)"),
                {"n": name or "默认基准", "p": result["precision"], "t": result["total"],
                 "o": operator, "now": datetime.now()})
        return {"ok": True, "name": name or "默认基准",
                "precision": result["precision"], "total": result["total"]}

    @classmethod
    async def eval_bench_list(cls, limit: int = 30) -> list[dict]:
        async with async_db_session.begin() as db:
            await cls._ensure_eval_bench_table(db)
        async with async_db_session() as db:
            from sqlalchemy import text as _t
            rows = (await db.execute(_t(
                "SELECT id,name,precision,total,operator,created_time FROM ai_eval_bench "
                "ORDER BY id DESC LIMIT :n"), {"n": max(1, min(limit, 100))})).fetchall()
        return [{"id": r[0], "name": r[1], "precision": float(r[2] or 0),
                 "total": r[3], "operator": r[4] or "", "time": str(r[5]) if r[5] else ""}
                for r in rows]

    @classmethod
    async def unified_audit(cls, days: int = 7) -> dict:
        """跨模块统一审计：AI 调用 / 动作写回 / 本体发布 全链路一处看。

        AI 调用取数走 `logs_center`（该表读 owner）。
        注：`ai_query_writeback` / `ai_ont_version` 仍是就地计数——它们分属问数/本体的表，
        要收敛得先在那两个模块开口子，留作后续（不属本次 ai_call_logs 收敛范围）。
        """
        from app.plugin.module_ai import catalog
        from app.plugin.module_ai.logs_center.service import AiLogService

        agg = await AiLogService.health_aggregate(days)
        approvals = await catalog.count_writebacks(result="pending")
        actions = 0
        publishes = 0
        try:
            async with async_db_session() as db:
                from sqlalchemy import text as _t
                actions = int((await db.execute(_t(
                    "SELECT COUNT(*) FROM ai_query_writeback "
                    "WHERE is_deleted=0"))).scalar() or 0)
                publishes = int((await db.execute(_t(
                    "SELECT COUNT(*) FROM ai_ont_version "
                    "WHERE is_deleted=0 AND status='pending'"))).scalar() or 0)
        except Exception:  # noqa: BLE001
            pass
        return {"days": days, "ai_calls": agg["calls"], "ai_errors": agg["errors"],
                "actions": actions, "approvals": approvals,
                "publishes": publishes,
                "audit_log": (await cls.activity_timeline(days, 30))["events"]}

    @classmethod
    async def add_log(
        cls,
        model_name: str,
        usage: str,
        latency_ms: int,
        result: str = "success",
        error: str | None = None,
        app_id: int | None = None,
        user_id: int | None = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cost: float = 0.0,
    ) -> None:
        try:
            from sqlalchemy import text as _t

            async with async_db_session.begin() as db:
                # 幂等补列（新库由 create_all 建，旧库这里补齐；sqlite 不支持 ADD COLUMN IF NOT EXISTS，逐个容错）
                for col, ddl in (
                    ("prompt_tokens", "INTEGER DEFAULT 0"),
                    ("completion_tokens", "INTEGER DEFAULT 0"),
                    ("cost", "NUMERIC DEFAULT 0"),
                ):
                    try:
                        await db.execute(
                            _t(f"ALTER TABLE ai_call_logs ADD COLUMN IF NOT EXISTS {col} {ddl}")
                        )
                    except Exception:  # noqa: BLE001  # sqlite 等方言不支持，忽略
                        pass
                db.add(
                    AiCallLogModel(
                        model_name=model_name or "",
                        usage=usage or "chat",
                        latency_ms=int(latency_ms or 0),
                        result=result,
                        error=(error or "")[:2000] or None,
                        app_id=app_id,
                        user_id=user_id,
                        prompt_tokens=int(prompt_tokens or 0),
                        completion_tokens=int(completion_tokens or 0),
                        cost=float(cost or 0.0),
                    )
                )
        except Exception as e:
            from app.core.logger import logger

            logger.warning(f"写入 AI 调用日志失败: {e}")

    @classmethod
    async def stats(cls) -> dict:
        # 平台概览统计：AI 实体计数 + 调用概览。
        # 职责边界：overview 负责平台实体计数与监控/治理；ai_call_logs 的读取、
        # 统计与明细统一由 logs_center 提供（复用 AiLogService.console_overview），避免重复 SQL。
        from app.plugin.module_ai.apps.model import AiAppModel
        from app.plugin.module_ai.knowledge.model import AiKnowledgeBaseModel
        from app.plugin.module_ai.logs_center.service import AiLogService
        from app.plugin.module_ai.models.model import AiModelModel
        from app.plugin.module_ai.providers.model import AiProviderModel
        from app.plugin.module_ai.report.model import AiReportModel
        from app.plugin.module_ai.workflow.model import AiWorkflowModel

        async with async_db_session() as db:
            providers = await db.scalar(
                select(func.count()).select_from(AiProviderModel).where(
                    AiProviderModel.is_deleted.is_(False)
                )
            )
            models = await db.scalar(
                select(func.count()).select_from(AiModelModel).where(
                    AiModelModel.is_deleted.is_(False)
                )
            )
            reports = await db.scalar(
                select(func.count()).select_from(AiReportModel).where(
                    AiReportModel.is_deleted.is_(False)
                )
            )
            kbs = await db.scalar(
                select(func.count()).select_from(AiKnowledgeBaseModel).where(
                    AiKnowledgeBaseModel.is_deleted.is_(False)
                )
            )
            apps = await db.scalar(
                select(func.count()).select_from(AiAppModel).where(
                    AiAppModel.is_deleted.is_(False)
                )
            )
            workflows = await db.scalar(
                select(func.count()).select_from(AiWorkflowModel).where(
                    AiWorkflowModel.is_deleted.is_(False)
                )
            )

        call = await AiLogService.console_overview()
        return {
            "providers": providers or 0,
            "models": models or 0,
            "reports": reports or 0,
            "knowledge_bases": kbs or 0,
            "apps": apps or 0,
            "workflows": workflows or 0,
            **call,
        }
