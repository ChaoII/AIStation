from datetime import datetime

from sqlalchemy import desc, select

from app.core.database import async_db_session

from .schedule_model import TrainScheduleModel


def _schedule_to_dict(row) -> dict:
    """仅导出列，避免 dict(__dict__) 带入 _sa_instance_state 导致序列化 500。"""
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


class ScheduleService:

    @classmethod
    async def list_schedules(cls) -> list[dict]:
        async with async_db_session() as db:
            result = await db.execute(
                select(TrainScheduleModel).order_by(desc(TrainScheduleModel.created_time))
            )
            return [_schedule_to_dict(r) for r in result.scalars().all()]

    @classmethod
    async def create_schedule(cls, data, auth) -> dict:
        from .retired import ensure_active

        # Ultralytics / PaddleX 已退场，当场拒绝。定时训练尤其要挡：它靠 cron 触发，
        # 建错了当时没反馈，要等到下一个调度点才炸，且是以「任务失败」的形式炸——
        # 用户根本看不出根源是建计划时选了个已退场的框架。
        ensure_active(data.framework, action="定时训练")

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
            # 改框架同样要挡：否则能把一个已退场的框架"改回去"，让本来建好的
            # TorchKiln 计划变成永远不会成功的计划。
            from .retired import ensure_active

            new_fw = getattr(data, "framework", None)
            if new_fw is not None:
                ensure_active(new_fw, action="定时训练")
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
