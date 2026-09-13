"""AI 调用日志查询服务（复用 ai_call_logs）。"""
from __future__ import annotations

from sqlalchemy import desc, func, or_, select

from app.core.database import async_db_session
from app.plugin.module_ai.overview.model import AiCallLogModel


def _log_dict(r: AiCallLogModel) -> dict:
    return {
        "id": r.id,
        "model_name": r.model_name,
        "usage": r.usage,
        "latency_ms": r.latency_ms,
        "result": r.result,
        "error": r.error,
        "app_id": r.app_id,
        "user_id": r.user_id,
        "created_time": r.created_time,
    }


class AiLogService:

    @classmethod
    async def page(
        cls,
        page_no: int = 1,
        page_size: int = 10,
        usage: str | None = None,
        result: str | None = None,
        keyword: str | None = None,
    ) -> dict:
        page_no = max(int(page_no or 1), 1)
        page_size = max(int(page_size or 10), 1)
        async with async_db_session() as db:
            stmt = select(AiCallLogModel).where(AiCallLogModel.is_deleted.is_(False))
            if usage:
                stmt = stmt.where(AiCallLogModel.usage == usage)
            if result:
                stmt = stmt.where(AiCallLogModel.result == result)
            if keyword:
                like = f"%{keyword}%"
                stmt = stmt.where(
                    or_(
                        AiCallLogModel.model_name.like(like),
                        AiCallLogModel.error.like(like),
                    )
                )
            total = int(
                await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
            )
            rows = (
                await db.execute(
                    stmt.order_by(
                        desc(AiCallLogModel.created_time), desc(AiCallLogModel.id)
                    )
                    .offset((page_no - 1) * page_size)
                    .limit(page_size)
                )
            ).scalars().all()
            return {
                "page_no": page_no,
                "page_size": page_size,
                "total": total,
                "has_next": page_no * page_size < total,
                "items": [_log_dict(r) for r in rows],
            }
