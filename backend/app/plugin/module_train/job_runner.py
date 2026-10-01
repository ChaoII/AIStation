"""一次性容器作业的共享骨架。

为什么抽这个
------------
``eval_scheduler`` 与 ``predict_executor`` 原本各写一遍「起一次性容器跑命令」的完整
流程：申请 GPU → 起容器 → 跟日志 → 等退出 → 按退出码收尾 → 清理。两份实现
逐行对应，只有「成功时要写什么字段」不同。

这份重复**已经付出过代价**：预测的结果收集逻辑曾写成「找到文件后反而只去看
``exp/``」，结果落在 ``vis/`` 或 ``output/`` 时会静默返回空——而评估那份没这个问题。
两处独立演进，就会漂移。所以抽出来不是洁癖，是止损。

分层
----
- :func:`gpu_slot`      进程内信号量 + 跨进程 GPU 租约（含"等待期间被取消"的检查）
- :func:`run_and_follow` 起容器 → 注册 → 跟日志 → 等退出码
- :func:`settle`        按「取消 / 成功 / 失败」三态收尾并清理容器
- :func:`mark_failed`   异常兜底：记 FAILED 并清理临时目录

刻意**不**抽的部分：成功时要落库的字段、导出数据/下载权重、命令拼装、指标解析。
这些各链路确实不同，硬塞进参数化模板只会得到一堆关键字参数。
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config.setting import settings
from app.core.logger import log

from .concurrency import get_train_semaphore
from .docker_utils import (
    get_container_error_tail,
    remove_container,
    run_container,
)
from .gpu_pool import gpu_lease
from .model import TrainStatus


def needed_gpu_memory(hyperparams: dict | None) -> float:
    """本次作业需要多少显存（GB）。

    取 ``hyperparams.resources.gpu_memory_gb``，没填则用全局最小空闲阈值
    ``settings.TORKILN_GPU_MIN_FREE_GB``。
    """
    hp = hyperparams or {}
    return float((hp.get("resources") or {}).get("gpu_memory_gb")
                 or settings.TORKILN_GPU_MIN_FREE_GB)


@contextlib.asynccontextmanager
async def gpu_slot(executor: Any, job_id: int, hyperparams: dict | None):
    """申请一块 GPU：进程内信号量 + 跨进程租约。

    两层缺一不可：信号量只认**本进程里排队**的任务，看不见别的框架、更看不见平台外
    占着卡的人；而 ``gpu_pool`` 负责跨进程的精确判定（Redis + NVML）。两套排队互不
    知情必然撞卡，所以先过信号量（拒绝得快）再向 gpu_pool 租（判得准）。

    进入时若作业已被取消，直接抛 :class:`JobCancelled`——**不要**起容器。等待租约的
    时间可能很长，期间用户点停止是很正常的。
    """
    async with get_train_semaphore(), gpu_lease(job_id, needed_gpu_memory(hyperparams)) as lease:
        if cancelled(executor, job_id):
            raise JobCancelled
        yield lease


def cancelled(executor: Any, job_id: int) -> bool:
    """该作业是否已被请求取消（读执行器的 registry）。"""
    return bool(executor._registry.get(job_id, {}).get("cancel"))


class JobCancelled(Exception):
    """作业在拿到 GPU 之前/期间被取消。不应记为失败。"""


@dataclass
class JobOutcome:
    """一次容器作业的结果。"""

    exit_code: int | None = None
    container_id: str | None = None
    error_tail: str = ""


async def run_and_follow(
    executor: Any,
    job_id: int,
    *,
    image: str,
    cmd: list[str],
    volumes: dict,
    gpu_id: Any,
    log_path: str,
    broadcast,
    parse_fn=None,
) -> JobOutcome:
    """起容器 → 注册到 registry → 跟日志 → 等退出码。

    ``gpu_id`` 传的是**期望**的设备；真实传入容器的是租约分配的 ``device_ids``
    （为空才回退到 ``gpu_id``）。

    日志跟随与退出码等待都在这里完成，调用方拿到 :class:`JobOutcome` 后只关心
    「成功时要写什么」。
    """
    container = await run_container(
        image, cmd,
        volumes=volumes,
        gpu_id=gpu_id,
        shm_size="4g",
        labels={"aistation.task_kind": executor.task_kind,
                "aistation.task_id": str(job_id)},
    )
    container_id = container.id
    entry = executor._registry.get(job_id) or {}
    entry.update({"container_id": container_id})
    executor._registry[job_id] = entry

    await executor.follow_logs(
        container_id, log_path, broadcast, parse_fn,
    )
    exit_code = await executor._get_exit_code(container)
    return JobOutcome(
        exit_code=exit_code,
        container_id=container_id,
        error_tail=(await get_container_error_tail(container_id)).strip()
        if exit_code else "",
    )


async def _finish(
    executor: Any,
    job_id: int,
    *,
    cancelled_now: bool,
    succeeded: bool,
    error: str,
    container_id: str | None,
    success_fields: dict | None,
) -> None:
    """三态收尾的**唯一**实现。:func:`settle` 与 :func:`settle_by_status` 都走它。

    - 取消：只改状态，不读容器日志（容器可能已在移除中）
    - 成功：写 ``success_fields``
    - 失败：错误文案写进 ``log`` 与 ``error_log``——``error_log`` 只在失败时有值，
      也是前端弹错误提示的依据

    ⚠️ ``progress`` **只在成功时写 100**。以前三个分支一律写 100，于是列表页上
    失败/取消的作业也显示满格进度条——和「成功」唯一的区别只剩颜色，容易被误读
    成「已经跑完了」。失败/取消一律不碰这一列，保留它自己的值（训练由指标 flush
    顺带写入，评估/预测保持启动时写的 10）。
    """
    if cancelled_now:
        await remove_container(container_id)
        await executor._mark_status(job_id, TrainStatus.CANCELLED,
                                    finished_at=datetime.now())
        return

    await remove_container(container_id)
    if succeeded:
        await executor._mark_status(job_id, TrainStatus.SUCCESS,
                                    **(success_fields or {}),
                                    finished_at=datetime.now(), progress=100)
    else:
        msg = error or "job failed"
        await executor._mark_status(job_id, TrainStatus.FAILED,
                                    log=msg, error_log=msg,
                                    finished_at=datetime.now())


async def settle(
    executor: Any,
    job_id: int,
    *,
    was_cancelled: bool,
    container_id: str | None,
    exit_code: int | None,
    error_tail: str = "",
    success_fields: dict | None = None,
    failure_message: str = "job failed",
) -> None:
    """按「取消 / 成功 / 失败」三态收尾，并移除容器（一次性容器作业用）。

    判据是**容器退出码**。三态的判定顺序与副作用刻意固定在 :func:`_finish` 一处：
    以前两处各写一遍，已经漂移过一次（一处漏了 ``error_log``、一处给失败也写了
    ``progress=100``）。
    """
    await _finish(
        executor, job_id,
        cancelled_now=was_cancelled,
        succeeded=(exit_code == 0),
        error=error_tail or failure_message,
        container_id=container_id,
        success_fields=success_fields,
    )


async def settle_by_status(
    executor: Any,
    job_id: int,
    *,
    status: str,
    error: str = "",
    container_id: str | None = None,
    success_fields: dict | None = None,
    failure_message: str = "job failed",
) -> None:
    """同上，但判据是 **HTTP 作业的状态字符串**（``succeeded``/``failed``/``cancelled``）。

    为什么单独一个入口而不是让调用方把状态翻译成退出码再走 :func:`settle`：
    TorchKiln 服务给的终态是**已经判定过的结论**（``setup_failed`` /
    ``no_end_event`` / ``killed`` 都已被它归成 ``failed``）。让调用方
    ``0 if status == 'succeeded' else 1`` 会丢掉这个信息——失败原因要原样透传，
    否则用户只会看到「评估失败」而看不到「trainer 构造阶段异常」。
    """
    st = (status or "").strip().lower()
    await _finish(
        executor, job_id,
        cancelled_now=(st == "cancelled"),
        succeeded=(st == "succeeded"),
        error=error or failure_message,
        container_id=container_id,
        success_fields=success_fields,
    )


async def mark_failed(executor: Any, job_id: int, exc: BaseException, *,
                      kind: str) -> None:
    """异常兜底：记 FAILED 并清理本次导出的临时数据（保留日志文件供排查）。"""
    log.error(f"{kind} task {job_id} failed: {exc}")
    await executor._mark_status(job_id, TrainStatus.FAILED,
                                log=str(exc), finished_at=datetime.now())


async def cleanup_registry(executor: Any, job_id: int,
                           container_id: str | None) -> None:
    """``finally`` 里清 registry 与容器。

    放独立函数是因为这段在 eval/predict 里逐字重复，而它**必须**执行——早年的 bug
    就是异常路径上漏了它，导致 ``recover_orphans`` 因注册表残留而永久跳过该行。
    """
    executor._registry.pop(job_id, None)
    if container_id:
        await remove_container(container_id)
