"""AI 概览统计与调用日志。"""
from sqlalchemy import desc, func, select

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
        """AI 健康/异常监控：聚合近 N 天调用量/错误率/平均延迟/成本 + 健康状态与告警。"""
        from datetime import datetime, timedelta
        from sqlalchemy import func as _f, select as _sel
        since = datetime.utcnow() - timedelta(days=max(1, days))
        async with async_db_session() as db:
            base = _sel(
                _f.count().label("n"),
                _f.count().filter(AiCallLogModel.result == "error").label("e"),
                _f.avg(AiCallLogModel.latency_ms).label("lat"),
                _f.sum(AiCallLogModel.cost).label("cost"),
            ).where(AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= since)
            row = (await db.execute(base)).one()
        calls = int(row.n or 0)
        errors = int(row.e or 0)
        avg_latency = int(row.lat or 0)
        total_cost = round(float(row.cost or 0), 2)
        error_rate = round(errors / calls, 4) if calls else 0.0
        alerts = []
        if error_rate > 0.05:
            alerts.append({"level": "critical", "msg": f"近{days}天错误率 {error_rate*100:.1f}% 超过 5%"})
        elif error_rate > 0.02:
            alerts.append({"level": "warning", "msg": f"近{days}天错误率 {error_rate*100:.1f}% 超过 2%"})
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
        """AI 调用合规审计：未鉴权(user_id 为空)调用/失败调用/高成本调用，输出合规报告。"""
        from datetime import datetime, timedelta
        from sqlalchemy import func as _f, select as _sel
        since = datetime.utcnow() - timedelta(days=max(1, days))
        async with async_db_session() as db:
            total = (await db.execute(_sel(_f.count()).select_from(AiCallLogModel).where(
                AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= since))).scalar() or 0
            anon = (await db.execute(_sel(_f.count()).select_from(AiCallLogModel).where(
                AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= since,
                AiCallLogModel.user_id.is_(None)))).scalar() or 0
            errs = (await db.execute(_sel(_f.count()).select_from(AiCallLogModel).where(
                AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= since,
                AiCallLogModel.result == "error"))).scalar() or 0
            high_cost = (await db.execute(_sel(_f.count()).select_from(AiCallLogModel).where(
                AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= since,
                AiCallLogModel.cost > 1.0))).scalar() or 0
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
        from app.plugin.module_ai.apps.model import AiAppModel
        from app.plugin.module_ai.workflow.model import AiWorkflowModel
        from app.plugin.module_ai.provider.model import AiModelModel
        from app.plugin.module_ai.agent.model import AiAgentModel
        from sqlalchemy import select as _sel, func as _f
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
        from sqlalchemy import select as _sel
        async with async_db_session() as db:
            rows = (await db.execute(
                _sel(AiCallLogModel)
                .where(AiCallLogModel.is_deleted.is_(False))
                .order_by(AiCallLogModel.created_time.desc())
                .limit(min(limit, 50))
            )).scalars().all()
        runs = []
        for r in rows:
            runs.append({
                "id": r.id, "model": r.model_name, "usage": r.usage,
                "latency_ms": r.latency_ms, "result": r.result, "user_id": r.user_id,
                "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                "cost": round(float(r.cost or 0), 4), "error": r.error,
                "time": r.created_time.strftime("%m-%d %H:%M") if r.created_time else "",
            })
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
        from datetime import datetime, timedelta
        from sqlalchemy import func as _f, select as _sel
        since = datetime.utcnow() - timedelta(days=max(1, days))
        async with async_db_session() as db:
            rows = (await db.execute(
                _sel(_f.date(AiCallLogModel.created_time).label("d"),
                     _f.count().label("n"),
                     _f.count().filter(AiCallLogModel.result == "error").label("e"),
                     _f.avg(AiCallLogModel.latency_ms).label("lat"))
                .where(AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= since)
                .group_by(_f.date(AiCallLogModel.created_time))
                .order_by(_f.date(AiCallLogModel.created_time))
            )).fetchall()
        lats = [int(r[3] or 0) for r in rows]
        base_lat = sum(lats) / len(lats) if lats else 0
        anomalies = []
        for r in rows:
            d = str(r[0]); n = int(r[1] or 0); e = int(r[2] or 0); lat = int(r[3] or 0)
            er = e / n if n else 0
            if er > 0.10:
                anomalies.append({"date": d, "type": "error_rate", "severity": "high",
                                  "value": round(er * 100, 1),
                                  "msg": f"{d} 错误率 {er*100:.1f}% 异常升高（>10%）"})
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
                decisions.append({"title": "处理 AI 调用异常", "reason": a["msg"],
                                  "impact": "影响 AI 稳定性", "action": "查看 AIP 运行追踪定位",
                                  "pri": "high"})
        except Exception:  # noqa: BLE001
            pass
        try:
            audit = await cls.audit_check(7)
            if not audit.get("compliant"):
                decisions.append({"title": "消除合规风险", "reason": f"{len(audit.get('issues', []))} 项合规问题",
                                  "impact": "数据安全合规", "action": "处理审计问题", "pri": "high"})
        except Exception:  # noqa: BLE001
            pass
        try:
            plan = await AiQueryService.autopilot()
            if plan["total"]:
                decisions.append({"title": "执行自主修复", "reason": f"{plan['total']} 项待修复建议",
                                  "impact": "提升数据质量/安全", "action": "运行 AIP 自动修复", "pri": "medium"})
        except Exception:  # noqa: BLE001
            pass
        try:
            pend = int((await AiQueryService.approval_center()).get("total", 0))
            if pend:
                decisions.append({"title": "处理待审批", "reason": f"{pend} 项待审批",
                                  "impact": "打通发布/写回闭环", "action": "前往审批中心", "pri": "medium"})
        except Exception:  # noqa: BLE001
            pass
        order = {"high": 0, "medium": 1, "low": 2}
        decisions.sort(key=lambda d: order.get(d["pri"], 3))
        return {"total": len(decisions), "decisions": decisions}

    @classmethod
    async def activity_timeline(cls, days: int = 7, limit: int = 60) -> dict:
        """统一活动时间线：聚合 AI 调用 / 动作 / 审批为时间线视图。"""
        from datetime import datetime, timedelta
        from sqlalchemy import select as _sel
        since = datetime.utcnow() - timedelta(days=max(1, days))
        events: list[dict] = []
        async with async_db_session() as db:
            rows = (await db.execute(
                _sel(AiCallLogModel)
                .where(AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= since)
                .order_by(AiCallLogModel.created_time.desc())
                .limit(limit)
            )).scalars().all()
            for r in rows:
                events.append({"time": str(r.created_time), "kind": "ai_call",
                               "title": f"{r.model_name} · {r.usage}",
                               "result": r.result, "detail": f"延迟 {r.latency_ms}ms",
                               "actor": f"user#{r.user_id}" if r.user_id else "匿名"})
            try:
                from sqlalchemy import text as _t
                al = (await db.execute(_t(
                    "SELECT action_name, object_table, result, operator, created_time "
                    "FROM ai_action_log WHERE is_deleted=0 ORDER BY id DESC LIMIT :n"),
                    {"n": limit})).fetchall()
                for r in al:
                    events.append({"time": str(r[4]), "kind": "action",
                                   "title": f"动作 {r[0]}", "result": r[2] or "",
                                   "detail": f"对象 {r[1] or ''}",
                                   "actor": str(r[3] or "系统")})
            except Exception:  # noqa: BLE001
                pass
        events.sort(key=lambda e: str(e["time"]), reverse=True)
        return {"total": len(events), "events": events[:limit]}

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
                # 幂等补列（新库由 create_all 建，旧库这里补齐）
                for col, ddl in (
                    ("prompt_tokens", "INTEGER DEFAULT 0"),
                    ("completion_tokens", "INTEGER DEFAULT 0"),
                    ("cost", "NUMERIC DEFAULT 0"),
                ):
                    await db.execute(
                        _t(f"ALTER TABLE ai_call_logs ADD COLUMN IF NOT EXISTS {col} {ddl}")
                    )
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
        from app.plugin.module_ai.apps.model import AiAppModel
        from app.plugin.module_ai.knowledge.model import AiKnowledgeBaseModel
        from app.plugin.module_ai.provider.model import AiModelModel
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
            calls = await db.scalar(
                select(func.count()).select_from(AiCallLogModel).where(
                    AiCallLogModel.is_deleted.is_(False)
                )
            )
            errors = await db.scalar(
                select(func.count()).select_from(AiCallLogModel).where(
                    AiCallLogModel.is_deleted.is_(False), AiCallLogModel.result == "error"
                )
            )
            avg_latency = await db.scalar(
                select(func.avg(AiCallLogModel.latency_ms)).where(
                    AiCallLogModel.is_deleted.is_(False), AiCallLogModel.result == "success"
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
            from datetime import datetime, timedelta

            since = datetime.now() - timedelta(days=7)
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            today = await db.scalar(
                select(func.count()).select_from(AiCallLogModel).where(
                    AiCallLogModel.is_deleted.is_(False), AiCallLogModel.created_time >= today_start
                )
            )
            trend_rows = (
                await db.execute(
                    select(
                        func.date(AiCallLogModel.created_time).label("d"),
                        func.count().label("n"),
                        func.count().filter(AiCallLogModel.result == "error").label("e"),
                    )
                    .where(
                        AiCallLogModel.is_deleted.is_(False),
                        AiCallLogModel.created_time >= since,
                    )
                    .group_by(func.date(AiCallLogModel.created_time))
                    .order_by(func.date(AiCallLogModel.created_time))
                )
            ).all()
            by_model_rows = (
                await db.execute(
                    select(
                        AiCallLogModel.model_name,
                        func.count().label("n"),
                        func.count().filter(AiCallLogModel.result == "error").label("e"),
                        func.sum(AiCallLogModel.prompt_tokens).label("pt"),
                        func.sum(AiCallLogModel.completion_tokens).label("ct"),
                        func.sum(AiCallLogModel.cost).label("cost"),
                    )
                    .where(AiCallLogModel.is_deleted.is_(False))
                    .group_by(AiCallLogModel.model_name)
                    .order_by(func.count().desc())
                )
            ).all()
            rows = (
                await db.execute(
                    select(AiCallLogModel)
                    .where(AiCallLogModel.is_deleted.is_(False))
                    .order_by(desc(AiCallLogModel.id))
                    .limit(20)
                )
            ).scalars().all()
            recent = [
                {
                    "id": r.id,
                    "model_name": r.model_name,
                    "usage": r.usage,
                    "latency_ms": r.latency_ms,
                    "result": r.result,
                    "error": r.error,
                    "created_time": r.created_time,
                }
                for r in rows
            ]
            return {
                "providers": providers or 0,
                "models": models or 0,
                "reports": reports or 0,
                "calls": calls or 0,
                "errors": errors or 0,
                "avg_latency_ms": int(avg_latency or 0),
                "knowledge_bases": kbs or 0,
                "apps": apps or 0,
                "workflows": workflows or 0,
                "today_calls": int(today or 0),
                "success_rate": round((calls - errors) / calls, 4) if calls else 0,
                "trend": [
                    {"date": str(r[0]), "count": int(r[1]), "error": int(r[2])}
                    for r in trend_rows
                ],
                "by_model": [
                    {
                        "name": r[0] or "—",
                        "count": int(r[1]),
                        "error": int(r[2]),
                        "prompt_tokens": int(r[3] or 0),
                        "completion_tokens": int(r[4] or 0),
                        "cost": float(r[5] or 0.0),
                    }
                    for r in by_model_rows
                ],
                "recent_calls": recent,
            }
