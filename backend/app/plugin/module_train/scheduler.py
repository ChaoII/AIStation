import asyncio
import os
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .model import TrainStatus, TrainTask
from .paths import work_dir

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
    """维护循环：触发定时训练 + 周期孤儿恢复（归并到唯一的 TorchKiln 执行器）。"""
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
            await _executor_for(None).recover_orphans()

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
    """取训练执行器类（start/stop 共用）。

    只剩 TorchKiln 一条通路，不再按框架分派。原先这里还有一层 ``TrainExecutor``
    兜底，专门接住 ``framework='ULTRALYTICS'/'PADDLEX'`` 的历史任务行并给出退场
    提示——那两个框架的数据已按显式 id 白名单删净、枚举值也已从 PG 里
    ``ALTER TYPE`` 移除，那层兜底成了永远走不到的死分支，故随之删除。

    ⚠️ 退场框架的拒绝**不靠这里**，而是靠 service 层入口的
    ``retired.ensure_active()``：请求体里的 ``framework`` 是字符串，客户端能传
    任意值，走到执行器之前就该被挡下。
    """
    # 自研训练平台：HTTP 客户端形态，排队/容器生命周期都在 TorchKiln 服务里
    from .torchkiln_executor import TorchKilnExecutor

    return TorchKilnExecutor


async def stop_training(task_id: int) -> None:
    async with async_db_session() as db:
        task = await db.get(TrainTask, task_id)
    await _executor_for(task).stop(task_id)
