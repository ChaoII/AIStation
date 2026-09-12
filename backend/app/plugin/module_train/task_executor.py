"""统一任务执行器基类：并发控制、孤儿恢复、容器生命周期、日志管道。"""
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import (
    find_task_containers,
    follow_container_logs,
    get_container,
    remove_container,
    stop_container,
    stop_task_containers,
)
from .framework_utils import framework_value


def recovery_decision(has_live_container: bool, started_at, now, timeout_sec: float) -> str:
    """重启恢复决策：存活→重连；否则未超时→等待、超时→标记失败。"""
    if has_live_container:
        return "reattach"
    if started_at and (now - started_at).total_seconds() > timeout_sec:
        return "fail"
    return "wait"


class TaskExecutor(ABC):
    """抽象基类。子类：TrainExecutor / EvalExecutor / PredictExecutor。

    每个子类通过 __init_subclass__ 维护独立 registry 与信号量。
    并发上限由 _concurrency 控制。
    """
    name: str = "task"
    task_kind: str = "task"  # 容器 label 值：train/eval/predict/deploy
    status_enum = None  # TrainStatus 等
    model_class = None  # TrainTask / TrainEval / TrainPredict
    _concurrency: int = 1
    _registry: dict[int, dict] = {}
    _semaphore: asyncio.Semaphore | None = None
    _recovery_task: asyncio.Task | None = None
    _orphan_timeout_sec: float = 1800.0

    def __init_subclass__(cls, **kwargs):
        """每个子类获得独立的 registry / semaphore / recovery task。"""
        super().__init_subclass__(**kwargs)
        cls._registry = {}
        cls._semaphore = None
        cls._recovery_task = None

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        if cls._semaphore is None:
            cls._semaphore = asyncio.Semaphore(cls._concurrency)
        return cls._semaphore

    @classmethod
    async def run(cls, task_id: int) -> None:
        cls._registry[task_id] = {"queued": True}
        sem = cls._get_semaphore()
        async with sem:
            await cls._execute_with_state(task_id)

    @classmethod
    async def _execute_with_state(cls, task_id: int):
        try:
            # If cancelled while queued, don't execute
            if cls._registry.get(task_id, {}).get("cancel"):
                await cls._mark_status(task_id, "cancelled", finished_at=datetime.now())
                return
            await cls._mark_status(task_id, "running", started_at=datetime.now())
            await cls._execute(task_id)
        except Exception as e:
            log.error(f"[{cls.name}] task {task_id} failed: {e}")
            await cls._mark_status(task_id, "failed", error_log=str(e), finished_at=datetime.now())
        finally:
            cls._registry.pop(task_id, None)

    @classmethod
    @abstractmethod
    async def _execute(cls, task_id: int) -> None:
        """子类实现：pull image → 导出数据 → run container → 收集产物 → 标记状态。"""

    @classmethod
    async def _mark_status(cls, task_id: int, status: str, **fields) -> None:
        values = {"status": status, **fields}
        async with async_db_session.begin() as db:
            await db.execute(update(cls.model_class).where(cls.model_class.id == task_id).values(**values))

    @classmethod
    async def stop(cls, task_id: int) -> None:
        entry = cls._registry.get(task_id)
        if entry:
            entry["cancel"] = True
            if entry.get("container_id"):
                await stop_container(entry["container_id"])
        else:
            # 后端重启后内存 registry 丢失，按容器 label 兜底停止
            await stop_task_containers(cls.task_kind, task_id)
        async with async_db_session.begin() as db:
            await db.execute(
                update(cls.model_class)
                .where(cls.model_class.id == task_id, cls.model_class.status == cls.status_enum.RUNNING)
                .values(status=cls.status_enum.CANCELLED, finished_at=datetime.now())
            )

    @classmethod
    async def follow_logs(cls, container_id: str, log_file: str, broadcast_fn, parse_fn=None):
        """统一日志管道：写文件 + 广播 + 可选指标解析。返回 metrics_log。"""
        metrics_log: list = []
        log_queue = await follow_container_logs(container_id)
        with open(log_file, "w", encoding="utf-8") as lf:
            while True:
                line = await log_queue.get()
                if line == "__EOF__":
                    break
                lf.write(line + "\n")
                lf.flush()
                if broadcast_fn:
                    try:
                        await broadcast_fn(line)
                    except Exception:
                        pass
                if parse_fn:
                    parsed = parse_fn(line)
                    if parsed:
                        metrics_log.append(parsed)
        return metrics_log

    @classmethod
    async def _get_exit_code(cls, container):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: container.wait(timeout=600)["StatusCode"])

    @classmethod
    async def reattach(cls, task_id: int, container_id: str | None = None) -> None:
        """重启后重连存活容器并收尾。

        基类默认行为：该框架暂不支持自动重连（无法收集产物），因此把仍处于
        RUNNING 的任务落到终态 FAILED，避免任务永久卡在 RUNNING（容器以
        all=True 查询会被反复重选为 reattach）。子类（如 TrainExecutor）可覆盖
        此方法实现真正的重连收尾。
        """
        try:
            # 仅当任务行仍存在且仍为 RUNNING 时才处理，避免覆盖已到终态的任务
            async with async_db_session() as db:
                task = await db.get(cls.model_class, task_id)
            if not task or getattr(task, "status", None) != cls.status_enum.RUNNING:
                return

            container = None
            if container_id:
                try:
                    container = await get_container(container_id)
                except Exception as e:
                    # 容器不存在 / daemon 不可达：无产物可收，按失败落终态
                    log.warning(f"[{cls.name}] 任务 {task_id} 重连失败：无法获取容器 {container_id}: {e}")

            if container is None:
                # 拿不到容器时仍可能有残留容器按 label 存活，落失败前先清理
                await stop_task_containers(cls.task_kind, task_id)

            if container is not None and getattr(container, "status", None) == "running":
                # 容器仍存活：等待其退出（阻塞 wait 放线程池，避免卡事件循环）
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None, lambda: container.wait(timeout=cls._orphan_timeout_sec)
                    )
                except Exception as e:
                    log.warning(f"[{cls.name}] 任务 {task_id} 等待容器退出失败: {e}")

            # 写终态前重新读取任务行：若已被并发取消/落到其它终态则不再覆盖
            async with async_db_session() as db:
                fresh = await db.get(cls.model_class, task_id)
            if fresh and getattr(fresh, "status", None) == cls.status_enum.RUNNING:
                await cls._mark_status(
                    task_id, cls.status_enum.FAILED,
                    error_log="后端重启后无法恢复产物收集（该框架暂不支持自动重连）",
                    finished_at=datetime.now(),
                )
            if container is not None:
                await remove_container(container.id)
        finally:
            # 无论如何都要从 registry 移除，否则下一轮恢复仍会重复处理该任务
            cls._registry.pop(task_id, None)

    @classmethod
    def _collect_recovery_registry(cls) -> dict:
        """返回用于判定任务是否仍在运行的 registry；子类可合并多个 registry。"""
        return cls._registry

    @classmethod
    def _recover_row_applies(cls, row) -> bool:
        """该 RUNNING 行是否由本执行器负责恢复（PaddleX 由 PaddleXOCR* 负责）。"""
        framework = getattr(row, "framework", None)
        if framework_value(framework) == "paddlex" and "PaddleXOCR" not in cls.__name__:
            return False
        return True

    @classmethod
    async def recover_orphans(cls) -> None:
        """DB 中 RUNNING 但不在 registry 的任务：存活容器→重连；否则超时→标记失败。"""
        registry = cls._collect_recovery_registry()
        async with async_db_session() as db:
            from sqlalchemy import select
            rows = (await db.execute(select(cls.model_class).where(
                cls.model_class.status == cls.status_enum.RUNNING
            ))).scalars().all()
            for r in rows:
                if r.id in registry:
                    continue
                if not cls._recover_row_applies(r):
                    continue
                container_ids = find_task_containers(cls.task_kind, r.id)
                decision = recovery_decision(
                    bool(container_ids), r.started_at, datetime.now(), cls._orphan_timeout_sec
                )
                if decision == "reattach":
                    # 记录 registry，避免下一轮重复重连；重连会长时间跟随日志，放后台执行
                    entry = cls._registry.setdefault(r.id, {})
                    entry["container_id"] = container_ids[0]
                    log.warning(
                        f"[{cls.name}] task {r.id} 容器仍存活（{container_ids[0][:12]}），重连而非标记失败"
                    )
                    # 保存任务引用，防止后台任务被 GC
                    entry["reattach_task"] = asyncio.create_task(cls.reattach(r.id, container_ids[0]))
                elif decision == "fail":
                    async with async_db_session.begin() as db2:
                        await db2.execute(
                            update(cls.model_class).where(cls.model_class.id == r.id).values(
                                status=cls.status_enum.FAILED,
                                error_log="任务会话已断开（后端重启或容器丢失）",
                                finished_at=datetime.now(),
                            )
                        )
                    await stop_task_containers(cls.task_kind, r.id)

    @classmethod
    async def start_recovery_loop(cls) -> None:
        if cls._recovery_task is None or cls._recovery_task.done():
            cls._recovery_task = asyncio.create_task(cls._recovery_loop())

    @classmethod
    async def _recovery_loop(cls) -> None:
        while True:
            try:
                await cls.recover_orphans()
            except Exception as e:
                log.error(f"[{cls.name}] recovery error: {e}")
            await asyncio.sleep(30)
