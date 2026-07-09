from datetime import datetime

from sqlalchemy import desc, select

from app.core.database import async_db_session

from .schedule_model import TrainScheduleModel


class ScheduleService:

    @classmethod
    async def list_schedules(cls) -> list[dict]:
        async with async_db_session() as db:
            result = await db.execute(
                select(TrainScheduleModel).order_by(desc(TrainScheduleModel.created_time))
            )
            return [dict(r.__dict__) for r in result.scalars().all()]

    @classmethod
    async def create_schedule(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            s = TrainScheduleModel(
                name=data.name, dataset_id=data.dataset_id,
                annotation_task_id=getattr(data, "annotation_task_id", None),
                framework=data.framework, hyperparams=data.hyperparams,
                cron_expr=data.cron_expr, created_id=auth.user.id,
            )
            db.add(s)
            await db.flush()
            return {"id": s.id}

    @classmethod
    async def update_schedule(cls, schedule_id: int, data) -> dict | None:
        async with async_db_session.begin() as db:
            s = await db.get(TrainScheduleModel, schedule_id)
            if not s:
                return None
            for key in ("name", "dataset_id", "annotation_task_id", "framework",
                        "hyperparams", "cron_expr", "enabled"):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(s, key, val)
            return {"id": s.id}

    @classmethod
    async def delete_schedules(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for sid in ids:
                s = await db.get(TrainScheduleModel, sid)
                if s:
                    await db.delete(s)

    @classmethod
    async def get_due_schedules(cls) -> list[TrainScheduleModel]:
        """Return enabled schedules whose cron_expr matches current time"""
        from croniter import croniter
        now = datetime.now()
        async with async_db_session() as db:
            result = await db.execute(
                select(TrainScheduleModel).where(TrainScheduleModel.enabled == True)
            )
            due = []
            for s in result.scalars().all():
                try:
                    cron = croniter(s.cron_expr, s.last_run_at or s.created_time)
                    next_run = cron.get_next(datetime)
                    if next_run <= now:
                        due.append(s)
                except Exception:
                    pass
            return due
