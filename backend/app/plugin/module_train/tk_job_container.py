"""「每任务一容器跑 TorchKiln 服务」——训练与评估共用的容器启动与作业消费。

为什么抽出来
------------
训练早就是「起 job 容器 -> HTTP POST 作业 -> SSE 取指标」，评估原先还在
「起一次性容器跑 ``tkiln val`` CLI」。两者的容器配置几乎一样：同一个镜像、
同样把宿主工作目录挂到 ``/workspace``、同样映射端口、同样需要 shm、
同样要等 ``import torch`` 冷启动（本机实测 **23.4 秒**）。

差异只有两处：容器标签里的 ``task_kind``，以及消费端各自的广播函数。

⚠️ 容器里跑的是**完整的 TorchKiln 服务**而不是一次性命令——这样 HTTP 契约、
指标事件、终态判定全都原样保留，只把「常驻服务」换成了「一任务一服务」。
这条设计是评估能改走 HTTP 通路的前提。
"""

from __future__ import annotations

import asyncio

from app.config.setting import settings
from app.core.logger import log

from .docker_utils import run_container
from .gpu_pool import wait_service_ready
from .torchkiln_client import TorchKilnClient, TorchKilnError

#: 宿主工作目录在容器内的挂载点。数据/权重/产物都在它下面。
CONTAINER_WORKSPACE = "/workspace"
#: 容器内 TorchKiln 代码根；作业命令行里的 ``-c configs/...`` 相对它解析。
CONTAINER_REPO_ROOT = "/opt/torchkiln"


async def start_job_container(alloc, host_workspace: str, *,
                              task_kind: str, task_id: int,
                              shm_size: str = "8g"):
    """起一个专属的 TorchKiln job 容器。

    三个容易踩的点：

    1. ``TKILN_DATA_ROOT`` 必须指向**挂载点**。服务默认往容器内目录写
       ``metrics.jsonl`` 与权重，不挂出来的话容器一销毁产物就没了——而且
       任务还会显示成功，事后才发现没产物。
    2. 端口映射到 ``alloc.port``，调用方再用 ``alloc.base_url`` 连它。
    3. ``shm_size``：DataLoader worker>0 时不给 shm 会 BUS error。
    """
    # volumes 的值必须是 {"bind": ..., "mode": ...}，不能写成裸字符串——
    # Docker SDK 会对 str 调 .get() 而炸
    volumes = {host_workspace: {"bind": CONTAINER_WORKSPACE, "mode": "rw"}}
    env = {
        "TKILN_DATA_ROOT": CONTAINER_WORKSPACE,
        "TKILN_REPO_ROOT": CONTAINER_REPO_ROOT,
        "TKILN_SERVICE_TOKEN": settings.TORKILN_SERVICE_TOKEN,
        "TKILN_MAX_CONCURRENT": "1",
        "TKILN_POLL_INTERVAL": "1.0",
    }
    # device_ids 用**序号**而非 UUID：容器只暴露被选中的卡，容器内序号恒为 0
    device_ids = ",".join(str(i) for i in alloc.gpu_indices) or "0"
    # ⚠️ Docker SDK 的 ports 语义是「**key=容器内端口，value=宿主机端口**」
    # （文档写的是 "ports to bind inside the container"，很容易读反）。
    # 写反的话 Docker 会去绑**宿主机**的 8000，直接撞上已在运行的常驻服务。
    return await run_container(
        image=settings.TORKILN_JOB_IMAGE,
        cmd=["python", "-m", "uvicorn", "service.main:app",
             "--host", "0.0.0.0", "--port", str(settings.TORKILN_JOB_CONTAINER_PORT)],
        volumes=volumes,
        gpu_id=device_ids,
        env=env,
        ports={f"{int(settings.TORKILN_JOB_CONTAINER_PORT)}/tcp": int(alloc.port)},
        # label 让 recover_orphans / find_task_containers 能重新找到它
        labels={"aistation.task_kind": task_kind,
                "aistation.task_id": str(task_id),
                "aistation.tk_port": str(alloc.port)},
        shm_size=shm_size,
    )


async def wait_ready(alloc, *, broadcast=None) -> None:
    """等容器内服务真的在监听。

    容器 running ≠ 服务可用：容器内冷启动要 ``import torch``，这段时间里
    端口还没监听，此时提交作业只会拿到连接拒绝。
    """
    if broadcast is not None:
        await broadcast("[torchkiln] 等待 job 容器内服务就绪…")
    await wait_service_ready(alloc.port)


async def stream_logs(client: TorchKilnClient, job_id: str, kind: str,
                      broadcast, *, tail: int = 200) -> asyncio.Task:
    """把作业日志转发到广播函数（后台任务）。"""
    return asyncio.ensure_future(_consume_logs(client, job_id, kind, broadcast, tail))


async def _consume_logs(client, job_id, kind, broadcast, tail):
    try:
        async for line in client.stream_logs(job_id, tail=tail, kind=kind):
            await broadcast(line)
    except (TorchKilnError, asyncio.CancelledError):
        raise
    except Exception as e:  # noqa: BLE001
        # 日志流失败不该让作业被判失败——指标与终态才是判据
        log.warning("[torchkiln] 日志流中断（作业本身不受影响）: {}", e)


async def await_terminal(client: TorchKilnClient, job_id: str, kind: str,
                         *, is_cancelled, broadcast, poll_seconds: float = 5.0) -> dict:
    """轮询到终态；把本地取消请求翻译成服务端的 cancel。

    返回作业信息 dict（含 ``status`` / ``exit_reason`` / ``error``）。
    """
    while True:
        if is_cancelled():
            await broadcast("[torchkiln] 收到停止请求，转发取消")
            try:
                return await client.cancel_job(job_id, kind=kind)
            except TorchKilnError as e:
                log.warning("[torchkiln] 取消失败: {}", e)
                return {"status": "cancelled", "exit_reason": "cancelled"}
        info = await client.get_job(job_id, kind=kind)
        if str(info.get("status")) in ("succeeded", "failed", "cancelled"):
            return info
        await asyncio.sleep(poll_seconds)


def container_path(*parts: str) -> str:
    """把宿主相对路径拼成容器内**POSIX** 绝对路径。

    两个容易踩的点：

    1. ⚠️ **必须用 ``/`` 而不是 ``os.path.join``**。本项目跑在 Windows 上而容器是
       Linux，``os.path.join("/workspace", "data")`` 得到 ``/workspace\\data``——
       它在宿主上看着完全正常，传进容器就找不到文件了。这类错没有任何本地信号，
       只会在容器里报「找不到文件」，而错误信息里那个反斜杠极易被忽略。
    2. 刻意只接受**相对**片段并逐段拼：直接 ``CONTAINER_WORKSPACE + "/" + p``
       时，一个以 ``/`` 开头的 ``p`` 会拼出 ``/workspace//abs/path``，
       看着像对的，实际指向了挂载点之外。
    """
    segs = [s.strip("/\\") for s in parts]
    out = CONTAINER_WORKSPACE
    for seg in segs:
        if seg:
            out = out + "/" + seg
    return out
