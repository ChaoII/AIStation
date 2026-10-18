from sqlalchemy import desc, select

from app.core.database import async_db_session
from app.core.exceptions import CustomException
from app.core.logger import log
from app.utils.trigger_util import TriggerUtil

from .schedule_model import TrainScheduleModel

#: 启用中的定时计划必须有触发表达式：空表达式 = 「已启用但永不触发」的静默失效。
#: 三处写入路径（工作台 / 工作流 / 训练）口径必须一致（同文案）。
_EMPTY_TRIGGER_MSG = "请先配置触发时间（分 时 日 月 周）"

#: 本模块在中心调度器里的作业前缀。**按模块同步必须传自己的前缀**（B1 审查约定）：
#: `sync_business_jobs` 只清理该前缀内的残留，绝不误删别的模块的业务作业。
_JOB_PREFIX = "train_schedule:"

#: 列表回显「下次运行时间」的格式（与统一层 `TriggerUtil` 的预览输出一致）
_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def train_schedule_job_key(schedule_id: int) -> str:
    """计划 id → 中心调度器里的作业键（`train_schedule:{id}`）。"""
    return f"{_JOB_PREFIX}{schedule_id}"


def sync_train_schedule_job(
    schedule_id: int, trigger: str | None, trigger_args, enabled: bool
) -> None:
    """按调度行「生效后」的状态同步中心调度器里的作业（幂等）。

    - 启用 + 有触发表达式 → 注册（同键替换，改表达式即换触发器）；
    - 启用 + `trigger="now"`（立即执行）→ 同样注册：`now` 按契约**无参数**
      （`trigger_args` 恒为 `None`），由统一层构造 `DateTrigger(now + 2s)` 的一次性作业
      （守卫口径与工作流侧逐字一致，A9 修「立即执行」静默失效）；
    - 禁用 / 未配置表达式 → 移除（幂等，不留幽灵作业）；
    - 遗留脏表达式（迁移被跳过、Quartz 写法）注册失败：**不留幽灵作业、也不把请求打成 500**
      —— 该行在列表里由统一层标 `needs_review`，提示人工改写。
    """
    from app.core.ap_scheduler import SchedulerUtil

    from .scheduler import run_scheduled_training

    job_key = train_schedule_job_key(schedule_id)
    if not (enabled and (trigger_args or trigger == "now")):
        remove_train_schedule_job(schedule_id)
        return
    try:
        SchedulerUtil.register_business_trigger(
            job_key,
            trigger or "cron",
            trigger_args,
            run_scheduled_training,
            args=(schedule_id,),
        )
    except Exception as e:  # noqa: BLE001 - 单行脏配置不得拖垮增改接口
        remove_train_schedule_job(schedule_id)
        log.warning(f"定时训练计划 {schedule_id} 的触发配置无法注册作业，已跳过：{e!s}")


def remove_train_schedule_job(schedule_id: int) -> bool:
    """移除某计划的作业（计划删除时调用；不存在也返回 False 而不抛）。

    调度器未启动时 APScheduler 抛的是 `SchedulerNotRunningError`（**不是** `JobLookupError`），
    一并吞掉：调度器不可用不得把「删除计划 / 禁用计划」的请求打成 500。
    """
    from app.core.ap_scheduler import SchedulerUtil

    try:
        return SchedulerUtil.remove_business_job(train_schedule_job_key(schedule_id))
    except Exception as e:  # noqa: BLE001 - 调度器不可用只记日志，接口照常成功
        log.warning(f"移除定时训练计划 {schedule_id} 的作业失败（调度器不可用？）：{e!s}")
        return False


def _job_next_run_time(schedule_id: int) -> str | None:
    """从中心调度器的作业读「下次运行时间」（状态单一真源，训练模块不再自算）。

    作业不存在（禁用 / 未配置 / 注册失败）时返回 `None`：与列表的 `needs_review`
    一起，让「有计划但调度不上」在界面上可见，而不是显示一个凭空的时刻。
    """
    try:
        from app.core.ap_scheduler import scheduler

        job = scheduler.get_job(train_schedule_job_key(schedule_id))
    except Exception as e:  # noqa: BLE001 - 调度器不可用不得让列表接口 500
        # 用 warning 而非 exception：列表逐行调用，调度器不可用时会刷出 N 条完整 traceback
        log.warning(f"读取定时训练计划 {schedule_id} 的作业失败（调度器不可用？）：{e!s}")
        return None
    next_fire = getattr(job, "next_run_time", None)
    return next_fire.strftime(_DATETIME_FORMAT) if next_fire else None


def _resolve_trigger(
    trigger: str | None, trigger_args, legacy_cron: str | None, enabled: bool
) -> tuple[str, object | None]:
    """把请求里的触发配置解析为落库值 `(trigger, trigger_args)`。

    **字段优先**：`trigger` 显式提供（非空串）时以它为准；兼容字段 `cron_expr` **仅在
    `trigger` 缺省时**才被解读 —— 非 cron 类型的前端仍会带上 `cron_expr: ""`，若先看旧字段
    会把它误判成「空表达式 + 启用」而误报 400（C4 审查钉死的缺口）。

    - cron 表达式为空（未提供 / 显式空串）：**启用中** → 400（`_EMPTY_TRIGGER_MSG`，不留
      「已启用但永不触发」的静默失效）；**未启用** → `("cron", None)`（「未配置 / 清空配置」语义）；
    - 其余情况：统一层 `TriggerUtil.validate`（非法 → 400，原因原样回显）+ `normalize`
      （写入即规范化：`0 9 * * 1-5` → `0 9 * * mon,tue,wed,thu,fri`）。
    """
    name = trigger.strip() if isinstance(trigger, str) else ""
    args = trigger_args if name else legacy_cron
    if not name:
        name = "cron"
    if name == "cron" and (args is None or (isinstance(args, str) and not args.strip())):
        if enabled:
            raise CustomException(msg=_EMPTY_TRIGGER_MSG, code=400, status_code=400)
        return "cron", None
    ok, reason = TriggerUtil.validate(name, args)
    if not ok:
        raise CustomException(msg=reason, code=400, status_code=400)
    return TriggerUtil.normalize(name, args)


def _schedule_to_dict(row) -> dict:
    """仅导出列，避免 dict(__dict__) 带入 _sa_instance_state 导致序列化 500。

    - `trigger_args` 按类型还原（interval 的 JSON 串 → 对象，供前端组件直接用）；
    - 新增 `trigger_describe`（统一层人话描述，空/脏数据无法描述时为 `None`）；
    - 另附兼容字段 `cron_expr`（= `trigger` 为 `cron` 时的 `trigger_args`）：前端 C 阶段
      切到 `trigger`/`trigger_args` 之前，列表与表单仍读旧字段名。`trigger` 为 NULL 的历史行
      按 `cron` 兜底，与另两处响应（`_cron_dict` / `_schedule_dict`）口径一致。
    """
    data = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    trigger = data.get("trigger") or "cron"
    raw_args = data.get("trigger_args")
    data["trigger_args"] = TriggerUtil.load_args(trigger, raw_args)
    data["trigger_describe"] = TriggerUtil.describe_args(trigger, raw_args)
    data["cron_expr"] = (raw_args or "") if trigger == "cron" else ""
    return data


class ScheduleService:

    @classmethod
    async def list_schedules(cls) -> list[dict]:
        async with async_db_session() as db:
            result = await db.execute(
                select(TrainScheduleModel).order_by(desc(TrainScheduleModel.created_time))
            )
            rows = [_schedule_to_dict(r) for r in result.scalars().all()]
        # 下次运行时间取自中心调度器的作业（单一真源）：模块不再自算，避免两套口径
        for row in rows:
            row["next_run_time"] = _job_next_run_time(row["id"])
        return rows

    @classmethod
    async def collect_job_specs(cls) -> list[tuple]:
        """收集「启用且有触发表达式且非 `now`」的计划规格，供启动期 `sync_business_jobs` 注册。

        每项为 5 元组 `(job_key, trigger, trigger_args, func, func_args)`。脏表达式不在
        这里过滤：`sync_business_jobs` 会逐条跳过并告警，不会因一行坏配置抹掉其余作业。
        **一律排除 `now`**（同工作台 / 工作流口径）：`now` 是「保存时的一次性事件」，
        统一层在**注册时**才把它算成 `DateTrigger(now + 2s)` —— 启动期重建等于
        「每次服务重启都重跑一次」。
        """
        from .scheduler import run_scheduled_training

        specs: list[tuple] = []
        for row in await cls.list_schedules():
            if not row.get("enabled") or (row.get("trigger") or "cron") == "now":
                continue
            if not row.get("trigger_args"):
                continue
            specs.append((
                train_schedule_job_key(row["id"]),
                row.get("trigger") or "cron",
                row["trigger_args"],
                run_scheduled_training,
                (row["id"],),
            ))
        return specs

    @classmethod
    async def sync_train_schedule_jobs(cls) -> dict[str, int]:
        """把库里「启用」的计划同步到中心调度器（幂等，可反复调用）。

        **只清理本模块前缀**（`train_schedule:`）：多调用方各自管自己的命名空间，
        绝不跨模块误删（B1 审查钉死的调用约定）。
        """
        from app.core.ap_scheduler import SchedulerUtil

        specs = await cls.collect_job_specs()
        return SchedulerUtil.sync_business_jobs(specs, prefixes=(_JOB_PREFIX,))

    @classmethod
    async def create_schedule(cls, data, auth) -> dict:
        from .retired import ensure_active

        # Ultralytics / PaddleX 已退场，当场拒绝。定时训练尤其要挡：它靠 cron 触发，
        # 建错了当时没反馈，要等到下一个调度点才炸，且是以「任务失败」的形式炸——
        # 用户根本看不出根源是建计划时选了个已退场的框架。
        ensure_active(data.framework, action="定时训练")

        # 新建的定时计划默认启用（`TrainScheduleModel.enabled` 默认 True，创建 schema 无该字段），
        # 因此未提供触发配置必须当场报错，不能落一条永不触发的行。
        trigger, trigger_args = _resolve_trigger(
            getattr(data, "trigger", None),
            getattr(data, "trigger_args", None),
            getattr(data, "cron_expr", None),
            True,
        )
        async with async_db_session.begin() as db:
            s = TrainScheduleModel(
                name=data.name,
                dataset_id=data.dataset_id,
                annotation_task_id=getattr(data, "annotation_task_id", None),
                framework=data.framework,
                hyperparams=data.hyperparams,
                trigger=trigger,
                trigger_args=TriggerUtil.dump_args(trigger, trigger_args),
                created_id=auth.user.id,
            )
            db.add(s)
            await db.flush()
            schedule_id = s.id
        # 事务提交后再注册作业：注册失败/回滚不会留下指向不存在计划的幽灵作业
        sync_train_schedule_job(schedule_id, trigger, trigger_args, enabled=True)
        return {"id": schedule_id}

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
            trigger_in = getattr(data, "trigger", None)
            args_in = getattr(data, "trigger_args", None)
            legacy_in = getattr(data, "cron_expr", None)
            if TriggerUtil.args_provided(trigger_in, legacy_in):
                # `s.enabled` 已按本次请求更新（上面循环），故按「生效后是否启用」判定
                trigger, trigger_args = _resolve_trigger(
                    trigger_in, args_in, legacy_in, bool(s.enabled)
                )
                s.trigger = trigger
                s.trigger_args = TriggerUtil.dump_args(trigger, trigger_args)
            elif (
                getattr(data, "enabled", None) is True
                and not s.trigger_args
                and (s.trigger or "cron") != "now"
            ):
                # 本次请求显式「启用」而库里没有表达式：同样不留「已启用但永不触发」的行
                # （仅改名字等其它字段时不拦，避免把历史坏行变成改不动的行）。
                # `now` 例外：它按契约**本就没有参数**（`trigger_args` 恒为 NULL），
                # 不是「未配置」——否则 `now` 行连「重新启用」都会被误报 400
                # （口径同工作台 `update_cron` / 工作流 `set_schedule`）。
                raise CustomException(msg=_EMPTY_TRIGGER_MSG, code=400, status_code=400)
            # 提交前取值：会话关闭后实例已过期，属性访问会触发 DetachedInstanceError
            state = (s.trigger, s.trigger_args, bool(s.enabled))
        # 事务提交后再同步作业（启用→注册 / 禁用→移除；改表达式→同键替换）
        sync_train_schedule_job(schedule_id, *state)
        return {"id": schedule_id}

    @classmethod
    async def delete_schedules(cls, ids: list[int]) -> None:
        async with async_db_session.begin() as db:
            for sid in ids:
                s = await db.get(TrainScheduleModel, sid)
                if s:
                    await db.delete(s)
        # 行删除后再移除作业：注册表里不留指向已删计划的幽灵作业（幂等，不存在也无妨）
        for sid in ids:
            remove_train_schedule_job(sid)
