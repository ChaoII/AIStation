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
    ) -> None:
        try:
            async with async_db_session.begin() as db:
                db.add(
                    AiCallLogModel(
                        model_name=model_name or "",
                        usage=usage or "chat",
                        latency_ms=int(latency_ms or 0),
                        result=result,
                        error=(error or "")[:2000] or None,
                        app_id=app_id,
                        user_id=user_id,
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
                "recent_calls": recent,
            }
