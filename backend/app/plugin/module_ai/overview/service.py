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
