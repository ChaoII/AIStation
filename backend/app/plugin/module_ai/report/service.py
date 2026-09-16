"""AI 报告服务：保存/列表/详情/删除。"""
from sqlalchemy import desc, select

from app.core.database import async_db_session

from .model import AiReportModel


def _to_dict(r: AiReportModel, with_content: bool = True) -> dict:
    d = {
        "id": r.id,
        "title": r.title,
        "source": r.source,
        "app_id": r.app_id,
        "session_id": r.session_id,
        "created_id": r.created_id,
        "created_time": r.created_time,
    }
    if with_content:
        d["content"] = r.content
    return d


class AiReportService:

    @classmethod
    async def create(
        cls,
        title: str,
        content: str,
        source: dict | None,
        user_id: int | None,
        app_id: int | None = None,
        session_id: int | None = None,
    ) -> dict:
        async with async_db_session.begin() as db:
            r = AiReportModel(
                title=title,
                content=content,
                source=source,
                created_id=user_id,
                app_id=app_id,
                session_id=session_id,
            )
            db.add(r)
            await db.flush()
            return {"id": r.id, "title": r.title}

    @classmethod
    async def list_reports(cls) -> list[dict]:
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiReportModel)
                    .where(AiReportModel.is_deleted.is_(False))
                    .order_by(desc(AiReportModel.id))
                )
            ).scalars().all()
            return [_to_dict(r, with_content=False) for r in rows]

    @classmethod
    async def get_report(cls, report_id: int) -> dict | None:
        async with async_db_session() as db:
            r = await db.get(AiReportModel, report_id)
            if not r or r.is_deleted:
                return None
            return _to_dict(r)

    @classmethod
    async def delete(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for rid in ids:
                r = await db.get(AiReportModel, rid)
                if r:
                    await db.delete(r)
