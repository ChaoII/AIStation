import asyncio
import os
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import find_task_containers
from .model import TrainStatus, TrainTask
from .paths import work_dir
from .task_executor import TaskExecutor
from .ws import broadcast_log

_scheduler_task: asyncio.Task | None = None

# 后台任务持有集合：防止 asyncio.create_task 返回的 Task 在进程退出时被 cancel
# 而留下半成品；任务完成/取消后自动丢弃引用。
_bg_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    """创建后台任务并持有引用，完成/取消时自动丢弃。"""
    task = asyncio.create_task(coro)
    if task is not None:
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    return task


# 注：原先这里有 ``MODELS_CACHE_DIR`` / ``_MODEL_DOWNLOAD_BASE`` / ``_MODEL_MIRROR``
# 与 ``_ensure_model_file()``，用于从 GitHub 预下载 30 个 Ultralytics 权重。
# Ultralytics 通路已退场，这些权重不再被任何训练路径使用，故一并移除。
# TorchKiln 的权重由其镜像内自带的 ``resolve_pretrained`` 解析，不走这套缓存。


def _send_notify(user_id: int, title: str, content: str | None, type_: str, module: str, module_id: int | None):
    """Fire-and-forget notification; non-blocking on best-effort basis."""
    try:
        import asyncio

        from app.api.v1.module_system.notification.service import NotificationService
        asyncio.ensure_future(NotificationService.create_notification(
            user_id=user_id, title=title, content=content,
            type=type_, module=module, module_id=module_id,
        ))
    except Exception:
        pass


async def start_scheduler():
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())
        log.info("train scheduler started")


def build_scheduled_task_data(schedule) -> SimpleNamespace:
    """把计划行转成 create_task 所需的数据对象（签名与 TrainService.create_task 一致）。"""
    return SimpleNamespace(
        name=f"[定时] {schedule.name}",
        dataset_id=schedule.dataset_id,
        annotation_task_id=getattr(schedule, "annotation_task_id", None),
        framework=schedule.framework,
        hyperparams=getattr(schedule, "hyperparams", None) or {},
        base_model_id=getattr(schedule, "base_model_id", None),
    )


async def _scheduler_loop():
    """维护循环：触发定时训练 + 周期孤儿恢复（交由 TrainExecutor.recover_orphans）。"""
    while True:
        try:
            # Check for due training schedules
            try:
                from .schedule_model import TrainScheduleModel
                from .schedule_service import ScheduleService
                due = await ScheduleService.get_due_schedules()
                for s in due:
                    try:
                        from .service import TrainService
                        # Create a mock auth object - schedules run as superuser

                        class _ScheduleAuth:
                            class user:
                                id = s.created_id or 1
                        task_data = build_scheduled_task_data(s)
                        result = await TrainService.create_task(task_data, _ScheduleAuth())
                        new_id = result.get("id")
                        if new_id:
                            await start_training(new_id)
                    except Exception as e:
                        new_id = None
                        log.error(f"scheduled training failed for schedule {s.id}: {e}")
                    finally:
                        async with async_db_session.begin() as db:
                            await db.execute(
                                update(TrainScheduleModel).where(TrainScheduleModel.id == s.id).values(
                                    last_run_at=datetime.now(), last_task_id=new_id
                                )
                            )
            except Exception as e:
                log.error(f"schedule check error: {e}")

            # Periodic orphan recovery (base executor owns registry/DB state)
            await TrainExecutor.recover_orphans()

            # GPU/端口看门狗：容器被强杀或后端崩溃时，任务终止路径上的 release
            # 不会执行，占用会一直挂到 24h TTL——单卡机器等于被占死。
            from . import gpu_pool
            try:
                await gpu_pool.reap_stale()
            except Exception as e:
                log.error(f"gpu pool watchdog error: {e}")
        except Exception as e:
            log.error(f"train scheduler error: {e}")
        await asyncio.sleep(30)


async def _build_export_dir(task_id: int) -> str:
    export_dir = work_dir("train_output", task_id)
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def _cleanup_export_data(data_dir: str | None) -> None:
    """失败后清理本次导出的 data 临时目录（保留日志文件供排查）。

    目录由框架在 temp 下统一管理（cleanup_loop 兜底），此处仅清理失败的
    半成品导出数据，避免占留大量图片。
    """
    if not data_dir:
        return
    import shutil
    shutil.rmtree(data_dir, ignore_errors=True)


# hp dict key → (yolo CLI flag, 默认值, 校验lambda)。仅当 key 在 hp 且值非 None 时拼入命令。
async def _resolve_task_type(task) -> str:
    """解析训练任务对应标注任务的 ``task_type``；无标注任务时默认 ``detection``。

    ``_build_cmd`` 同样读取该字段，但还需要 ``classification_mode``，故各自查询。
    """
    if not getattr(task, "annotation_task_id", None):
        return "detection"
    from app.api.v1.module_annotation.task.model import AnnotationTaskModel
    async with async_db_session() as db:
        ann_task = await db.get(AnnotationTaskModel, task.annotation_task_id)
    tt = getattr(ann_task, "task_type", None) if ann_task else None
    if not tt:
        return "detection"
    # 枚举成员取裸值（AnnotationType.CLASSIFICATION -> "classification"）
    return getattr(tt, "value", tt)


class TrainExecutor(TaskExecutor):
    """已退场框架（Ultralytics / PaddleX）的训练入口——**只拒绝，不再执行**。

    ⚠️ 名字保留是因为 ``_executor_for()`` 仍需要它来处理历史任务行：库里还有 37 条
    ``framework='ULTRALYTICS'/'PADDLEX'`` 的训练任务，其中可能残留 RUNNING 行，
    要靠本类继承的 ``recover_orphans`` 收敛掉。删掉这个类，那些行会永远显示
    「运行中」，比退场本身更糟。

    真正的训练能力已整体移除：超参白名单、命令构建、权重预下载、容器编排
    （原 ~340 行）都不在这里了。遇到已退场框架时明确报错，而不是静默不动——
    用户看到「已退场」才知道该用 TorchKiln 重训，而不是以为系统卡了。
    """

    name = "train"
    task_kind = "train"
    status_enum = TrainStatus
    model_class = TrainTask
    _concurrency = 1

    @classmethod
    async def _execute(cls, task_id: int):
        async with async_db_session() as db:
            task = await db.get(TrainTask, task_id)
            if not task:
                return
            fw = getattr(task, "framework", None)
            task_name = getattr(task, "name", str(task_id))
            created_id = getattr(task, "created_id", None)

        from .framework_utils import framework_value

        shown = framework_value(fw) or str(fw)
        message = (
            f"训练框架 {shown} 已退场，执行通路已移除。"
            f"请用 TorchKiln 重新训练（历史任务与模型记录仍可查看，但不能再启动训练）。"
        )
        log.warning(f"[scheduler] 任务 {task_id} 拒绝执行：{message}")
        await broadcast_log(task_id, f"[scheduler] {message}")

        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainTask).where(TrainTask.id == task_id).values(
                    status=TrainStatus.FAILED, error_log=message,
                    finished_at=datetime.now()))
        if created_id:
            _send_notify(created_id, f"训练无法启动: {task_name}", message,
                         "training_failed", "train", task_id)

    @classmethod
    async def reattach(cls, task_id: int, container_id: str | None = None) -> None:
        """已退场框架没有可重连的容器；清掉注册表让 recover_orphans 继续收敛。"""
        ids = [container_id] if container_id else find_task_containers(cls.task_kind, task_id)
        log.warning(f"[train] 任务 {task_id} 属于已退场框架，"
                    f"无可重连容器（找到 {len(ids)} 个）；将交由 recover_orphans 标记终态")
        cls._registry.pop(task_id, None)


async def start_training(task_id: int):
    # 预检（在原子抢占前执行，避免把未完成任务置为 RUNNING）：
    # 任务存在 + 非运行中 + 标注任务已完成。
    async with async_db_session() as db:
        task = await db.get(TrainTask, task_id)
        if not task:
            raise Exception(f"训练任务 {task_id} 不存在")

        if task.status == TrainStatus.RUNNING:
            raise Exception("任务正在运行，请勿重复启动")

        # If annotation_task_id is set, verify the annotation task is completed (live check)
        if task.annotation_task_id:
            from app.api.v1.module_annotation.task.model import AnnotationTaskModel
            from app.api.v1.module_annotation.task.service import TaskService
            ann_task = await db.get(AnnotationTaskModel, task.annotation_task_id)
            if ann_task:
                try:
                    prog = await TaskService._calc_progress(db, ann_task.id, ann_task.dataset_id)
                except Exception:
                    prog = {"status": "pending"}
                if prog.get("status") != "completed":
                    raise Exception(
                        f"标注任务「{ann_task.name}」尚未完成"
                    )

    # 原子守卫：单条条件 UPDATE 抢占，避免并发 start 的 TOCTOU 重复入队
    async with async_db_session.begin() as db:
        result = await db.execute(
            update(TrainTask)
            .where(TrainTask.id == task_id, TrainTask.status != TrainStatus.RUNNING)
            .values(
                status=TrainStatus.RUNNING, started_at=datetime.now(),
                progress=0, error_log=None,
                metrics_log=None, best_metrics=None, last_metrics=None,
                finished_at=None,
            )
        )
        if result.rowcount == 0:
            # 影响 0 行：已运行（读到的状态过期），拒绝重复启动
            raise Exception("任务正在运行，请勿重复启动")
    # ⚠️ 必须用 framework_value 归一化后比较，**不能**直接 `task.framework ==
    # TrainFramework.X`：PG 里 SAEnum 存的是枚举**成员名**（"TORKILN"），读回来
    # 是 str 而非枚举成员，与 TrainFramework.TORKILN（值 "torchkiln"）比较恒为
    # False，会静默落进 ultralytics 分支——本项目已踩过这个坑。
    _exec = _executor_for(task)
    log.info(
        "[scheduler] 派发训练任务 %s: framework=%r -> executor=%s",
        task_id, getattr(task, "framework", None), _exec.name,
    )
    _spawn(_exec.run(task_id))


def _executor_for(task):
    """按框架取执行器类（start/stop 共用，避免两处 if 走偏）。

    只剩 TorchKiln 一条通路。保留这层间接而不是直接返回 ``TorchKilnExecutor``：
    历史任务里仍有 ``framework='ULTRALYTICS'/'PADDLEX'`` 的行，它们要落到
    ``TrainExecutor``（恢复逻辑），才能在遇到已退场框架时给出明确提示，
    而不是掉进无人处理的分支被静默跳过。
    """
    from .framework_utils import framework_value

    if task is None:
        return TrainExecutor
    fw = framework_value(getattr(task, "framework", None))
    if fw == "torchkiln":
        # 自研训练平台：HTTP 客户端形态，排队/容器生命周期都在 TorchKiln 服务里
        from .torchkiln_executor import TorchKilnExecutor
        return TorchKilnExecutor
    return TrainExecutor


async def stop_training(task_id: int) -> None:
    async with async_db_session() as db:
        task = await db.get(TrainTask, task_id)
    await _executor_for(task).stop(task_id)
