from sqlalchemy import desc, select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.utils.trigger_util import TriggerUtil

from .schedule_model import TrainScheduleModel

#: 启用中的定时计划必须有触发表达式：空表达式 = 「已启用但永不触发」的静默失效。
#: 三处写入路径（工作台 / 工作流 / 训练）口径必须一致（同文案）。
_EMPTY_TRIGGER_MSG = "请先配置触发时间（分 时 日 月 周）"


def _resolve_trigger(cron_expr: str | None, enabled: bool) -> tuple[str, str | None]:
    """把 `cron_expr` 入参解析为 `(trigger, trigger_args)`（统一层是唯一口径）。

    - 非空表达式：先 `TriggerUtil.validate`（非法 → 400，原因原样回显），再 `TriggerUtil.normalize`
      —— 写入即规范化（`0 9 * * 1-5` → `0 9 * * mon,tue,wed,thu,fri`）；
    - 空值 + **启用中**：明确报错（不留「已启用但永不触发」的静默失效）；
    - 空值 + 未启用：视为「未配置」（`trigger_args=None`），保住「关闭调度 / 清空配置」语义。
    """
    if not cron_expr or not str(cron_expr).strip():
        if enabled:
            raise CustomException(msg=_EMPTY_TRIGGER_MSG, code=400, status_code=400)
        return "cron", None
    ok, reason = TriggerUtil.validate("cron", cron_expr)
    if not ok:
        raise CustomException(msg=reason, code=400, status_code=400)
    trigger, args = TriggerUtil.normalize("cron", cron_expr)
    return trigger, args


def _schedule_to_dict(row) -> dict:
    """仅导出列，避免 dict(__dict__) 带入 _sa_instance_state 导致序列化 500。

    另附兼容字段 `cron_expr`（= `trigger` 为 `cron` 时的 `trigger_args`）：前端 C 阶段
    切到 `trigger`/`trigger_args` 之前，列表与表单仍读旧字段名。`trigger` 为 NULL 的历史行
    按 `cron` 兜底，与另两处响应（`_cron_dict` / `_schedule_dict`）口径一致。
    """
    data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    is_cron = (data.get("trigger") or "cron") == "cron"
    data["cron_expr"] = (data.get("trigger_args") or "") if is_cron else ""
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

        # 新建的定时计划默认启用（`TrainScheduleModel.enabled` 默认 True，创建 schema 无该字段），
        # 因此空表达式必须当场报错，不能落一条永不触发的行。
        trigger, trigger_args = _resolve_trigger(data.cron_expr, True)
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
                # `s.enabled` 已按本次请求更新（上面循环），故按「生效后是否启用」判定
                s.trigger, s.trigger_args = _resolve_trigger(new_cron, bool(s.enabled))
            elif getattr(data, "enabled", None) is True and not s.trigger_args:
                # 本次请求显式「启用」而库里没有表达式：同样不留「已启用但永不触发」的行
                # （仅改名字等其它字段时不拦，避免把历史坏行变成改不动的行）
                raise CustomException(msg=_EMPTY_TRIGGER_MSG, code=400, status_code=400)
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
