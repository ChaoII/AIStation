from sqlalchemy import desc, select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.utils.trigger_util import TriggerUtil

from .schedule_model import TrainScheduleModel


def _resolve_trigger(cron_expr: str | None) -> tuple[str, str | None]:
    """把 `cron_expr` 入参解析为 `(trigger, trigger_args)`（统一层是唯一口径）。

    - 非空表达式：先 `TriggerUtil.validate`（非法 → `CustomException`，原因原样回显），
      再 `TriggerUtil.normalize` —— 写入即规范化（`0 9 * * 1-5` → `0 9 * * mon,tue,wed,thu,fri`）；
    - 空值：视为「未配置」（`trigger_args=None`），不调用校验（空串是「清空配置」的既有语义）。
    """
    if not cron_expr or not str(cron_expr).strip():
        return "cron", None
    ok, reason = TriggerUtil.validate("cron", cron_expr)
    if not ok:
        raise CustomException(msg=reason)
    trigger, args = TriggerUtil.normalize("cron", cron_expr)
    return trigger, args


def _schedule_to_dict(row) -> dict:
    """仅导出列，避免 dict(__dict__) 带入 _sa_instance_state 导致序列化 500。

    另附兼容字段 `cron_expr`（= `trigger == "cron"` 时的 `trigger_args`）：前端 C 阶段
    切到 `trigger`/`trigger_args` 之前，列表与表单仍读旧字段名。
    """
    data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    data["cron_expr"] = (data.get("trigger_args") or "") if data.get("trigger") == "cron" else ""
    return data


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

        trigger, trigger_args = _resolve_trigger(data.cron_expr)
        async with async_db_session.begin() as db:
            s = TrainScheduleModel(
                name=data.name,
                dataset_id=data.dataset_id,
                annotation_task_id=getattr(data, "annotation_task_id", None),
                framework=data.framework,
                hyperparams=data.hyperparams,
                trigger=trigger,
                trigger_args=trigger_args,
                created_id=auth.user.id,
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
            for key in (
                "name",
                "dataset_id",
                "annotation_task_id",
                "framework",
                "hyperparams",
                "enabled",
            ):
                val = getattr(data, key, None)
                if val is not None:
                    setattr(s, key, val)
            new_cron = getattr(data, "cron_expr", None)
            if new_cron is not None:
                s.trigger, s.trigger_args = _resolve_trigger(new_cron)
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
        """到期判定已移交中心调度器（阶段 B 的 `train_schedule:{id}` 业务作业）。

        旧实现用 `croniter` 自行判定到期：那既与统一层口径不一致（周字段语义相反），
        又在 A6 删掉 `cron_expr` 列后失效。本阶段不再由本循环触发定时训练，
        由阶段 B4 并入中心调度器（届时连 `scheduler.py` 里的调用段一并删除）。
        """
        return []
