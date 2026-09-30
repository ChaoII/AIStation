import asyncio
import os
import socket
from contextlib import nullcontext
from datetime import datetime

import docker
import httpx
from sqlalchemy import select, update

from app.config.setting import settings
from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import client as docker_client
from .docker_utils import (
    find_task_containers,
    follow_container_logs,
    get_container_error_tail,
    pull_image,
    remove_container,
    run_container,
    stop_container,
)
from .gpu_pool import gpu_lease
from .model import TrainDeploy, TrainModel
from .paths import work_dir
from .retired import _RetiredFramework, ensure_active

_deploy_running: dict[int, dict] = {}
# 已请求取消的部署 id -> 请求时间：stop_deployment 后，在途 _execute_deployment
# 仍据此判断"取消"，避免容器被停/移除后误把状态写回 failed。
# 带时间戳的映射（而非无界集合）便于过期清理，防止重启场景下墓碑长期残留
# 压制后续新一次启动的状态写入。
_deploy_cancelled: dict[int, datetime] = {}

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


def _cleanup_deploy_half_products(model_dir: str | None) -> None:
    """失败后清理部署的半成品目录（下载的模型权重），保留 deploy.log 供排查。

    原来还要清 ``server_dir``（平台侧生成的 server.py），PaddleX / Ultralytics
    退场后不再生成该目录，故这个参数一并去掉。
    """
    import shutil
    if model_dir:
        shutil.rmtree(model_dir, ignore_errors=True)


#: 部署镜像。Ultralytics 与 PaddleX 的部署通路已退场，只剩自研平台。
#: 自研平台的推理镜像（镜像内已装好 torch+CUDA、cv2 与 tkiln CLI）
TORKILN_IMAGE = "torchkiln:0.1.0"

DEPLOY_RECOVERY_INTERVAL = 30
# 取消墓碑保留时长：超过后自动失效，避免无限增长
DEPLOY_CANCEL_TTL = 3600


def _mark_deploy_cancelled(deploy_id: int) -> None:
    """记录取消墓碑（带时间戳），并顺带清理过期项。"""
    now = datetime.now()
    expired = [
        k for k, ts in _deploy_cancelled.items()
        if (now - ts).total_seconds() > DEPLOY_CANCEL_TTL
    ]
    for k in expired:
        _deploy_cancelled.pop(k, None)
    _deploy_cancelled[deploy_id] = now


def _is_deploy_cancelled(deploy_id: int) -> bool:
    """是否已请求取消；过期墓碑视为失效并清理。"""
    ts = _deploy_cancelled.get(deploy_id)
    if ts is None:
        return False
    if (datetime.now() - ts).total_seconds() > DEPLOY_CANCEL_TTL:
        _deploy_cancelled.pop(deploy_id, None)
        return False
    return True


def deploy_exit_status(cancel: bool, exit_code: int) -> str | None:
    """容器退出后的部署状态：取消由 stop 处理；否则成功=stopped、失败=failed。"""
    if cancel:
        return None
    return "stopped" if exit_code == 0 else "failed"


def is_port_reusable(status: str) -> bool:
    """已停止/失败/待开始的部署端口可复用；部署中/运行中不可复用。"""
    return status not in ("deploying", "running")


def _is_torchkiln_framework(framework) -> bool:
    """自研平台（TorchKiln）框架。

    ⚠️ 必须用 ``framework_value`` 归一化：PG 的 ``SAEnum`` 存的是**成员名**
    （``"TORKILN"``），读回来是 str 而非枚举成员，直接 ``== TrainFramework.TORKILN``
    恒为 False —— train/eval 两侧都踩过这个坑，会静默走 ultralytics 分支
    （拉错镜像、把 .pth 改名成 best.pt、用 YOLO API 加载，必然失败）。
    """
    from .framework_utils import framework_value

    return framework_value(framework) == "torchkiln"


async def resolve_deploy_tk_config(model_id: int) -> str | None:
    """取产出该模型的训练任务所用的 **TorchKiln 配置名**。

    部署必须与训练同一套架构：配置错了，权重能加载但前向结构对不上，导出的
    服务会输出无意义的结果（而不是报错），所以只从训练任务反查，不让用户手填。

    ⚠️ ``model_id`` 是**模型版本行 id**，而 ``TrainTask.model_repo_id`` 存的**也
    是版本行 id**（字段名有误导，逐条查过历史任务确认）——两者直接相等即可。
    与 ``resolve_eval_context`` 同一口径。
    """
    from sqlalchemy import desc, select

    from .model import TrainTask

    async with async_db_session() as db:
        task = (await db.execute(
            select(TrainTask).where(TrainTask.model_repo_id == model_id)
            .order_by(desc(TrainTask.id)).limit(1)
        )).scalar_one_or_none()
    if not task:
        return None
    hp = task.hyperparams or {}
    return hp.get("model") or hp.get("tk_config") or None


def _build_tk_serve_cmd(
    *, config: str, weights_name: str, api_key: str, port: int,
    device: str, conf: float | None = None, iou: float | None = None,
) -> list[str]:
    """构建 ``tkiln serve`` 命令。

    与 ultralytics/PaddleX 分支最大的不同：**不生成 server.py**。推理逻辑由
    ``tkiln serve`` 提供（与 ``tkiln predict`` 同一份实现），平台侧若再写一份
    推理脚本，预处理一旦和训练不一致，模型照样能出结果、只是精度悄悄变差。
    """
    cmd = [
        "tkiln", "serve",
        "-c", str(config),
        "--weights", f"/model/{weights_name}",
        "--port", str(port),
        "--device", "cpu" if device == "cpu" else "cuda:0",
    ]
    if api_key:
        cmd += ["--api-key", str(api_key)]
    # conf / iou 走配置覆盖而不是命令行参数：它们是后处理阈值（Global.conf /
    # Global.iou），tkiln 的统一覆盖机制就是 -o，平台侧不另造参数风格。
    opts = []
    if conf is not None:
        opts.append(f"Global.conf={conf}")
    if iou is not None:
        opts.append(f"Global.iou={iou}")
    if opts:
        cmd += ["-o", *opts]
    return cmd


async def start_deployment(deploy_id: int):
    # 原子守卫：单条条件 UPDATE 抢占，避免并发 start 的 TOCTOU 重复入队
    async with async_db_session.begin() as db:
        result = await db.execute(
            update(TrainDeploy)
            .where(TrainDeploy.id == deploy_id, TrainDeploy.status.notin_(("deploying", "running")))
            .values(status="deploying", started_at=datetime.now())
        )
        if result.rowcount == 0:
            # 影响 0 行：要么不存在，要么已在部署/运行中
            return
    # 全新启动前清掉该 id 的历史取消墓碑，避免新一次运行被旧记录压制。
    _deploy_cancelled.pop(deploy_id, None)
    _spawn(_execute_deployment(deploy_id))


async def stop_deployment(deploy_id: int):
    """停止部署并停掉真实容器。

    优先内存注册表；后端重启后注册表丢失，则回退到 DB 的 container_id；
    DB 也没有时按 label 查找残留容器。二者皆无则仅落库为 stopped。

    处于 deploying/running 的部署，无论注册表是否存在，都记录取消墓碑，
    以便在途执行器观察到取消、不再拉起新容器。
    """
    entry = _deploy_running.pop(deploy_id, None)
    if entry:
        entry["cancel"] = True
    container_id = entry.get("container_id") if entry else None
    db_status = None
    async with async_db_session() as db:
        row = await db.get(TrainDeploy, deploy_id)
        db_status = row.status if row else None
        if not container_id:
            container_id = row.container_id if row else None
    # 活跃状态一律记录取消（含注册表丢失但 DB 仍在 deploying/running 的场景）
    if db_status in ("deploying", "running"):
        _mark_deploy_cancelled(deploy_id)
    if not container_id:
        cids = find_task_containers("deploy", deploy_id)
        container_id = cids[0] if cids else None
    if container_id:
        await stop_container(container_id)
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                status="stopped", finished_at=datetime.now(), container_id=None
            )
        )


def _is_host_port_used(port: int) -> bool:
    """探测宿主机端口是否已被占用（127.0.0.1）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


async def _docker_published_host_ports() -> set[int]:
    """收集 Docker 所有容器（含已停止）已发布的宿主机端口，避免端口竞态。"""
    def _sync() -> set[int]:
        used: set[int] = set()
        try:
            for c in docker_client.containers.list(all=True):
                bindings = (c.attrs or {}).get("HostConfig", {}).get("PortBindings") or {}
                for _, host_bindings in bindings.items():
                    for b in host_bindings:
                        try:
                            used.add(int(b["HostPort"]))
                        except (KeyError, TypeError, ValueError):
                            continue
        except Exception as e:
            log.debug(f"cannot list docker published ports: {e}")
        return used

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


def _find_available_port(
    start: int = 9001, end: int = 9999, excluded: set[int] | None = None,
    docker_used: set[int] = frozenset(),
) -> int:
    """在 [start, end] 内寻找可用端口。

    同时排除：调用方传入的已预留端口、Docker 已发布端口、以及本机 socket 已占用端口。
    """
    used = set(excluded or ())
    used |= set(docker_used)
    for port in range(start, end + 1):
        if port in used:
            continue
        if not _is_host_port_used(port):
            return port
    raise Exception(f"no available port found in range {start}-{end}")


def _is_port_conflict_error(exc: Exception) -> bool:
    """判断 Docker APIError 是否为端口被占（TOCTOU 竞态重试的依据）。"""
    msg = str(exc).lower()
    return any(k in msg for k in (
        "port is already allocated",
        "port already allocated",
        "address already in use",
    ))


async def _container_exists(container_id: str | None) -> bool:
    """判断容器是否仍存在于 Docker 中。

    NotFound（容器确实不存在）返回 False；其余异常（daemon 不可达等）视为
    "无法证明容器不存在"，返回 True，避免恢复逻辑把 daemon 故障误判为容器丢失。
    """
    if not container_id:
        return False

    def _sync() -> bool:
        try:
            docker_client.containers.get(container_id)
            return True
        except docker.errors.NotFound:
            return False
        except Exception:
            return True

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


async def _wait_server_healthy(container, host_port: int, timeout: int = 60, interval: float = 2.0) -> str:
    """轮询推理服务 /health 直至就绪。返回空串表示健康，否则返回失败原因。"""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    async with httpx.AsyncClient(timeout=2.0) as client:
        while True:
            try:
                status = await loop.run_in_executor(None, lambda: container.status)
                if status in ("exited", "dead"):
                    return f"container exited with status {status} before health check passed"
            except Exception as e:
                return f"container status check failed: {e}"
            try:
                resp = await client.get(f"http://127.0.0.1:{host_port}/health")
                if resp.status_code == 200:
                    return ""
            except Exception:
                pass
            if loop.time() >= deadline:
                return "deploy health check timeout"
            await asyncio.sleep(interval)


async def recover_orphan_deploys() -> None:
    """回收孤儿部署：容器存活 → 重建内存注册表；容器确认丢失 → 标记 failed。

    后端重启后 `_deploy_running` 为空，存活容器需要重建注册表（标记 adopted），
    之后 stop_deployment 才能直接停掉它。adopted 条目没有在途协程负责收尾，
    因此每次周期都要复检容器是否仍在；一旦丢失即释放注册表并把行标记 failed。

    注意：`deploying` 是拉镜像/下载模型等启动中的在途状态，此时 container_id
    可能尚未落库（NULL/旧值），不能据此判定容器丢失；仅当行确为 `running`
    且 container_id 非空、容器又确实不存在时，才标记 failed。
    """
    async with async_db_session() as db:
        rows = (await db.execute(
            select(TrainDeploy).where(TrainDeploy.status.in_(("running", "deploying")))
        )).scalars().all()
    for d in rows:
        entry = _deploy_running.get(d.id)
        # 在途执行器拥有（非 adopted）的部署由其自行维护，恢复逻辑不介入
        # （30s 周期对账可能与启动竞态）
        if entry and not entry.get("adopted"):
            continue
        # _container_exists 仅在确认 NotFound 时返回 False；daemon 不可达返回 True
        # （"无法证明缺失"），此时按存活处理，避免误杀在途部署。
        if await _container_exists(d.container_id):
            # 标记 adopted：该条目由恢复逻辑接管而非执行器，后续周期需持续复检，
            # 容器若消失才能及时回收端口/状态
            _deploy_running[d.id] = {
                "container_id": d.container_id, "cancel": False, "adopted": True
            }
            continue
        # 容器确认丢失：清理已接管的注册表条目（无在途协程会替它收尾）
        if entry:
            _deploy_running.pop(d.id, None)
        # deploying 属于在途启动，跳过；仅确认丢失的 running 行标 failed
        if d.status != "running" or not d.container_id:
            continue
        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainDeploy).where(TrainDeploy.id == d.id).values(
                    status="failed", error_log="部署容器已丢失",
                    finished_at=datetime.now(), container_id=None
                )
            )
        log.info(f"deploy {d.id} marked failed: container lost or session disconnected")


async def start_deploy_recovery() -> None:
    """周期对账部署状态：立即执行一次，之后每 30s 重建注册表/回收孤儿。"""
    while True:
        try:
            await recover_orphan_deploys()
        except Exception as e:
            log.error(f"deploy orphan recovery failed: {e}")
        await asyncio.sleep(DEPLOY_RECOVERY_INTERVAL)


async def _execute_deployment(deploy_id: int):
    container_id = None
    export_dir = None
    model_dir = None
    try:
        async with async_db_session() as db:
            deploy = await db.get(TrainDeploy, deploy_id)
            if not deploy:
                return
            model_rec = await db.get(TrainModel, deploy.model_id)
            if not model_rec or not model_rec.storage_path:
                async with async_db_session.begin() as d:
                    await d.execute(
                        update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                            status="failed", error_log="model not found or no storage_path",
                            finished_at=datetime.now()
                        )
                    )
                return

        # 框架以**模型记录**为准：create 时若没把 framework 持久化到 deploy 上
        # （历史数据常见），deploy.framework 会是空的，此时按模型推断。
        framework = deploy.framework or getattr(model_rec, "framework", None)
        # Ultralytics / PaddleX 的部署通路已退场：在这里挡住并写明原因。
        # 之前是"非 torchkiln 就走 ultralytics 分支"，那会让历史模型拉错镜像、
        # 把 .pth 改名成 best.pt 再用 YOLO API 加载，失败原因与真实问题毫无关系。
        try:
            ensure_active(framework, action="部署")
        except _RetiredFramework as exc:
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                        status="failed", error_log=str(exc),
                        finished_at=datetime.now()))
            log.warning(f"deploy {deploy_id} 拒绝执行：{exc}")
            return

        image = TORKILN_IMAGE
        is_torchkiln = True

        await pull_image(image)

        export_dir = work_dir("deploy_output", deploy_id)
        model_dir = os.path.join(export_dir, "model")
        os.makedirs(model_dir, exist_ok=True)

        # Download model from RustFS
        from app.utils.s3_client import s3_client
        model_data = s3_client.download_fileobj(model_rec.storage_path)
        model_filename = model_rec.storage_path.rsplit("/", 1)[-1]
        model_local_path = os.path.join(model_dir, model_filename)
        with open(model_local_path, "wb") as f:
            f.write(model_data.read())

        # TorchKiln：权重**保持原名**（best_accuracy.pth）。
        # 刻意不改成 best.pt —— 那个名字只对 ultralytics 的 YOLO(...) 有意义，
        # 改名在这里没有任何收益，只会在排查时让人误以为文件来源不对。

        # 推理服务直接用 `tkiln serve`，平台侧不生成 server.py
        tk_cfg = await resolve_deploy_tk_config(deploy.model_id)
        if not tk_cfg:
            raise Exception(
                "TorchKiln 部署找不到产出该模型的训练任务，无法确定配置名——"
                "配置错了权重能加载但前向结构对不上，会静默输出无意义结果。"
                "请确认该模型版本确实由 TorchKiln 训练产出")
        # -c 只认 configs/ 下的配置路径，借常驻元数据服务把模型名换过去
        from .torchkiln_client import TorchKilnClient

        async with TorchKilnClient() as _tk:
            tk_cfg_path = await _tk.resolve_config_path(tk_cfg)

        # Determine port（自动选端口时同时排除 DB 已预留 + Docker 已发布 + socket 已占用）
        host_port = deploy.host_port
        if not host_port:
            async with async_db_session() as db:
                rows = (await db.execute(
                    select(TrainDeploy.host_port).where(
                        TrainDeploy.host_port > 0,
                        TrainDeploy.status.in_(("deploying", "running")),
                    )
                )).scalars().all()
            reserved = set(rows)
            docker_used = await _docker_published_host_ports()
            host_port = _find_available_port(excluded=reserved, docker_used=docker_used)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(host_port=host_port)
                )

        # TOCTOU 兜底：DB 预留与容器实际绑定之间存在竞态窗口，两个并发部署可能选到同一端口。
        # run_container 抛出端口冲突 APIError 时，换新端口（排除当前端口）重试一次。
        # ⚠️ 顺带解决「部署完全没有 GPU 排队」：它此前直接拿 deploy.device 起容器，
        #   而训练/评估/预测各自有各自的排队，两边互不知情必然抢同一张卡。
        #   这里也向 gpu_pool 租一张够显存的卡，保证**起容器时机器上确实有空闲卡**；
        #   用户显式指定的设备仍然尊重（那是软需求，撞车由日志提示，不静默改掉）。
        want_gpu = None if deploy.device in ("cpu", "", None) else str(deploy.device)
        need_mem_gb = float(((deploy.hyperparams or {}).get("resources") or {}).get(
            "gpu_memory_gb") or settings.TORKILN_GPU_MIN_FREE_GB)
        lease = gpu_lease(deploy_id, need_mem_gb) if want_gpu else nullcontext(None)

        # TorchKiln：命令是 `tkiln serve`，不挂 server_dir、不清 entrypoint
        # （torchkiln 镜像本身没有 ENTRYPOINT，清了反而会让 docker 走 image CMD）。
        # 另外容器内固定用 cuda:0：只暴露被分配的那一张卡，容器内序号恒为 0。
        hp_tk = deploy.hyperparams or {}
        launch_cmd = _build_tk_serve_cmd(
            config=tk_cfg_path,
            weights_name=model_filename,
            api_key=deploy.api_key,
            port=8000,
            device=deploy.device,
            conf=hp_tk.get("conf"),
            iou=hp_tk.get("iou"),
        )
        launch_volumes = {model_dir: {"bind": "/model", "mode": "ro"}}
        log.info(f"deploy {deploy_id} tkiln serve cmd: {' '.join(launch_cmd)}")

        async def _launch(port: int):
            return await run_container(
                image,
                launch_cmd,
                volumes=launch_volumes,
                ports={f"{8000}/tcp": port},
                gpu_id=want_gpu or getattr(alloc, "device_ids", None),
                entrypoint=None,
                shm_size="4g",
                labels={"aistation.task_kind": "deploy", "aistation.task_id": str(deploy_id)},
            )

        # 启动/拉镜像/下载模型期间可能已被 stop/delete 取消：不要在取消后拉起新容器
        if _is_deploy_cancelled(deploy_id):
            log.info(f"deploy {deploy_id} cancelled before container launch")
            return

        try:
            async with lease as alloc:
                if want_gpu and getattr(alloc, "device_ids", "") != want_gpu:
                    log.warning(
                        f"deploy {deploy_id}: 用户指定 GPU {want_gpu}，gpu_pool 分配的是 "
                        f"{getattr(alloc, 'device_ids', '?')}；按用户指定启动——"
                        f"若与其它任务抢卡会 OOM")
                container = await _launch(host_port)
        except docker.errors.APIError as e:
            if not _is_port_conflict_error(e):
                raise
            log.warning(f"deploy {deploy_id} port {host_port} conflict, retrying with a fresh port")
            host_port = _find_available_port(excluded={host_port})
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(host_port=host_port)
                )
            container = await _launch(host_port)
        container_id = container.id
        # 先登记注册表，便于 stop_deployment 能命中并停掉容器
        _deploy_running[deploy_id] = {"container_id": container_id, "cancel": False}
        # 拉起容器期间被取消：立即清理，不写 running
        if _is_deploy_cancelled(deploy_id):
            log.info(f"deploy {deploy_id} cancelled during launch, removing container")
            await remove_container(container_id)
            return

        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                    container_id=container_id, api_url=f"http://127.0.0.1:{host_port}",
                    status="running"
                )
            )

        # 健康探活：等待推理服务就绪；异常则标记 failed 并清理。
        # ⚠️ TorchKiln 的超时必须放宽：容器内 `import torch` 约 23s（本机实测），
        # 再加上按配置构建模型 + 加载权重，60s 卡得很紧——会在服务其实能起来的
        # 情况下被判失败，用户只看到一句 "timeout"，无从判断该等还是该改。
        probe_timeout = 240 if is_torchkiln else 60
        probe_error = await _wait_server_healthy(container, host_port, timeout=probe_timeout)
        if probe_error:
            log.error(f"deploy {deploy_id} health probe failed: {probe_error}")
            await remove_container(container_id)
            cancelled = _is_deploy_cancelled(deploy_id) or bool(
                _deploy_running.get(deploy_id, {}).get("cancel")
            )
            if not cancelled:
                async with async_db_session.begin() as db:
                    await db.execute(
                        update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                            status="failed", error_log=probe_error,
                            finished_at=datetime.now(), container_id=None
                        )
                    )
            return
        log.info(f"deploy {deploy_id} healthy at http://127.0.0.1:{host_port}/health")

        log_queue = await follow_container_logs(container_id)
        log_file = os.path.join(export_dir, "deploy.log")
        with open(log_file, "w", encoding="utf-8") as lf:
            while True:
                line = await log_queue.get()
                if line == "__EOF__":
                    break
                lf.write(line + "\n")
                lf.flush()

        loop = asyncio.get_event_loop()
        exit_code = await loop.run_in_executor(None, lambda: container.wait(timeout=300)["StatusCode"])

        cancel = _is_deploy_cancelled(deploy_id) or bool(
            _deploy_running.get(deploy_id, {}).get("cancel")
        )
        status = deploy_exit_status(cancel, exit_code)
        if status == "failed":
            error_msg = (await get_container_error_tail(container_id)).strip()
        if status is not None:
            await remove_container(container_id)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                        status=status, finished_at=datetime.now(),
                        container_id=None, error_log=(error_msg if status == "failed" else None),
                    )
                )

    except Exception as e:
        log.error(f"deploy {deploy_id} failed: {e}")
        # 已请求取消（stop_deployment）时容器被主动移除，wait 可能抛错，不要覆盖为 failed
        if not _is_deploy_cancelled(deploy_id):
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                        status="failed", error_log=str(e), finished_at=datetime.now()
                    )
                )
            # 失败后清理部署半成品（模型权重/服务脚本），保留 deploy.log
            _cleanup_deploy_half_products(model_dir)
    finally:
        _deploy_running.pop(deploy_id, None)
        _deploy_cancelled.pop(deploy_id, None)
        if container_id:
            await remove_container(container_id)
