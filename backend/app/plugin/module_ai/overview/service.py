"""AI 概览统计与调用日志。"""
from sqlalchemy import desc, func, select

from app.core.database import async_db_session

from .model import AiCallLogModel


class AiOverviewService:

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
