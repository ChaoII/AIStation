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
        from app.plugin.module_ai.provider.model import AiModelModel
        from app.plugin.module_ai.providers.model import AiProviderModel
        from app.plugin.module_ai.report.model import AiReportModel

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
                "recent_calls": recent,
            }
