"""TorchKiln 训练执行器。

与 ultralytics / PaddleX 执行器的**根本区别**
--------------------------------------------
后两者由本项目自己 ``run_container`` 起容器、自己 tail 日志、再用正则从日志里抠指标。
这个执行器什么都不做——只把声明式 ``JobSpec`` 交给 TorchKiln 服务，然后消费它推回来的流：

  日志流 -> 广播到前端 WebSocket（**仅排查用，不解析指标**）
  指标流 -> 原样落 ``TrainTask.metrics_log`` + 广播给前端 SSE 订阅者

好处：
  - **超参零映射**：点分键直通 ``-o Key.Sub=value``，加模型不用改本项目
  - **指标走契约**：来自 ``metrics.jsonl``，不再受日志格式/stdout 缓冲影响
  - **单一排队点**：GPU 排队与容器生命周期在服务端，本项目不抢 GPU 信号量
    （两边都排队 = 双队列 + 队头阻塞）

⚠️ 两条通道是互补而非重复：指标/日志用 SSE（实时、可断点续传），
**状态机用轮询**（``GET /jobs/{id}`` 永远可查，SSE 断线不影响状态收敛）。
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import posixpath
import time
import traceback
from datetime import datetime

from sqlalchemy import update

from app.config.setting import settings
from app.core.database import async_db_session
from app.plugin.module_train.framework_utils import framework_value
from app.plugin.module_train.model import TrainStatus, TrainTask
from app.plugin.module_train.task_executor import TaskExecutor
from app.plugin.module_train.torchkiln_client import (
    EVENT_BEST,
    EVENT_END,
    EVENT_EVAL,
    EVENT_STEP,
    TorchKilnClient,
    TorchKilnError,
    TorchKilnUnavailable,
    build_job_spec,
    probe_service,
)

from . import gpu_pool
from .docker_utils import get_container_labels, run_container, stop_container
from .paths import work_dir

log = logging.getLogger(__name__)

#: job 容器内的路径约定。宿主工作目录被挂到这里，所以 TorchKiln 侧的一切
#: 路径都必须是**容器内**路径——传宿主路径会在容器里 open 失败。
_CONTAINER_WORKSPACE = "/workspace"
_CONTAINER_DATA_DIR = "/workspace/data"
#: 镜像内 TorchKiln 代码的位置，与 TorchKiln 的 service/docker-run.sh 保持一致
_CONTAINER_REPO_ROOT = "/opt/torchkiln"

#: 服务状态 -> 本项目 TrainStatus。queued 也算 RUNNING（业务上已"开始"）
_STATUS_MAP = {
    "queued": TrainStatus.RUNNING,
    "running": TrainStatus.RUNNING,
    "succeeded": TrainStatus.SUCCESS,
    "failed": TrainStatus.FAILED,
    "cancelled": TrainStatus.CANCELLED,
}

#: 作业 id 存在 hyperparams 的这个键下（``__`` 前缀，用户表单不会渲染）
JOB_ID_KEY = "__tk_job_id"

#: 排队超过这么久就在日志里补一句"排了多久 + 前面有几个人在等"
_QUEUE_HINT_AFTER = 10.0

#: 指标落库批量阈值：step 级指标很密，逐条 UPDATE 会把 Postgres 打满
_FLUSH_EVERY = 40
_FLUSH_SECONDS = 3.0
#: metrics_log 行数上限，超出保留末尾（不限制会涨到几十 MB）
_MAX_METRIC_ROWS = 5000

#: 指标流订阅者（前端 SSE 端点）。key = task_id
_metric_subscribers: dict[int, list[asyncio.Queue]] = {}


# ---------------------------------------------------------------- 订阅（SSE 扇出）
def subscribe_metrics(task_id: int) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=4096)
    _metric_subscribers.setdefault(task_id, []).append(q)
    return q


def unsubscribe_metrics(task_id: int, q: asyncio.Queue) -> None:
    lst = _metric_subscribers.get(task_id)
    if lst and q in lst:
        lst.remove(q)
        if not lst:
            _metric_subscribers.pop(task_id, None)


def publish_metric(task_id: int, event: dict) -> None:
    for q in list(_metric_subscribers.get(task_id, ())):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            try:
                q.get_nowait()   # 丢最旧，给新数据腾位置
                q.put_nowait(event)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass


# ---------------------------------------------------------------- 持久化
def get_job_id(hyperparams: dict | None) -> str | None:
    return (hyperparams or {}).get(JOB_ID_KEY)


async def set_job_id(task_id: int, job_id: str) -> None:
    """把作业 id 持久化，供服务/本项目重启后重新接管。"""
    async with async_db_session.begin() as db:
        row = await db.get(TrainTask, task_id)
        if row is None:
            return
        hp = dict(row.hyperparams or {})
        hp[JOB_ID_KEY] = job_id
        row.hyperparams = hp


async def load_metrics_rows(task_id: int) -> list[dict]:
    async with async_db_session() as db:
        task = await db.get(TrainTask, task_id)
        return list(task.metrics_log or []) if task else []


async def save_metrics(task_id: int, rows: list[dict]) -> None:
    """整体覆盖写 ``metrics_log``。

    指标流是**单写者**，所以覆盖写比 UPDATE 安全（避免读-改-写竞态）。
    """
    payload = rows[-_MAX_METRIC_ROWS:] if len(rows) > _MAX_METRIC_ROWS else rows
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainTask).where(TrainTask.id == task_id)
            .values(metrics_log=payload)
        )


async def broadcast_line(task_id: int, line: str) -> None:
    """把一行日志广播到前端 WebSocket（复用训练日志通道）。"""
    from app.plugin.module_train.ws import broadcast_log

    try:
        await broadcast_log(task_id, line)
    except Exception as e:  # noqa: BLE001
        log.debug("广播日志失败 task={}: {}", task_id, e)


# ---------------------------------------------------------------- 执行器
class TorchKilnExecutor(TaskExecutor):
    """TorchKiln 训练执行器（HTTP 客户端形态）。"""

    name = "torchkiln_train"
    task_kind = "train"
    status_enum = TrainStatus
    model_class = TrainTask
    #: 真正的 GPU 排队由 :mod:`gpu_pool` 负责（Redis 原子分配 + NVML 空闲判定），
    #: 这里只需要一个足够大的上限防止 asyncio 任务无限堆积——**不能沿用原来的 8**：
    #: 那个值的理由是「排队交给常驻服务」，而现在常驻服务已经不存在了。
    #: 取 16 是因为通常只有 1~2 张卡，多出来的任务会停在 pool 里等卡，
    #: 而不是在信号量上排队（那样它们连数据都还没导出，白占磁盘 IO）。
    _concurrency = 16

    @classmethod
    async def reattach(cls, task_id: int, container_id: str | None = None) -> None:
        """后端重启后重新连上仍在运行的 job 容器。

        基类的实现是「重新 tail 容器日志」，那是 ultralytics / PaddleX 的一次性
        训练命令模型；TorchKiln 容器里跑的是 HTTP 服务，所以要**从容器 label 里
        读回宿主端口**再连上去。端口取不到就只能放弃——不能瞎猜一个端口连过去。
        """
        if not container_id:
            return
        labels = get_container_labels(container_id)
        port = (labels.get("aistation.tk_port") or "").strip()
        if not port:
            log.warning(
                f"[torchkiln] 任务 {task_id} 的容器 {container_id[:12]} 没有端口 label，"
                f"无法重连（该容器可能不是本执行器起的）")
            return
        try:
            port_i = int(port)
        except ValueError:
            log.warning(f"[torchkiln] 任务 {task_id} 的容器端口 label 非法: {port!r}")
            return

        async with async_db_session() as db:
            task = await db.get(TrainTask, task_id)
            job_id = get_job_id(task.hyperparams) if task else None
        if not job_id:
            log.warning(f"[torchkiln] 任务 {task_id} 没有 job_id，无法重连")
            return

        base_url = f"http://127.0.0.1:{port_i}"
        log.warning(f"[torchkiln] 任务 {task_id} 重连 {base_url}（作业 {job_id}）")
        await broadcast_line(task_id, f"[torchkiln] 后端重启，正在重连 job 容器 {base_url}")
        async with TorchKilnClient(base_url=base_url) as client:
            await cls._pump(client, task_id, job_id)

    @classmethod
    def _recover_row_applies(cls, row) -> bool:
        return framework_value(getattr(row, "framework", None)) == "torchkiln"

    # ------------------------------------------------------------ 组装
    @staticmethod
    def _model_name(task) -> str:
        hp = task.hyperparams or {}
        name = hp.get("model") or hp.get("model_name")
        if not name:
            raise ValueError("hyperparams.model 未指定 TorchKiln 模型名")
        return str(name)

    @staticmethod
    async def _task_type(task) -> str:
        """训练任务的**标注任务类型**（``AnnotationType`` 裸值），不是模型 task。

        必须与三处保持一致：ultralytics 路径的 ``scheduler._resolve_task_type``、
        前端 ``TK_SUPPORTED_TASK_TYPES`` 过滤的字段、本类 ``SUPPORTED_TASK_TYPES``
        的语义说明——它们说的都是「标注任务类型」。这里直接复用前者，避免两套
        实现各自漂移。

        ⚠️ 曾经读 ``hyperparams.task_type``，而该字段由前端按**模型** task 填写
        （``task/index.vue`` 的 ``tkModelInfo.task``），于是同一批任务既「选得了
        却提交不了」、又「提交得了却导出空标签」：

          - 模型 ``task=classify`` / ``task=obb`` 不在白名单 -> 后端拒提交，
            而导出器其实早就支持旋转框 9 字段角点；
          - 模型 ``task=segment`` 恰好在白名单，却把 ``export_framework`` 拼成
            ``yolo-segment``，格式器只认 ``segmentation``/``seg`` ->
            **标签文件全空，训练照常跑完但学的是空数据集**；
          - OCR 模型 yml 的 ``task`` 字段为空 -> 退化成 ``detection`` ->
            ``ocr_rec`` 恒 False -> **rec 按 det 的清单导出，数据语义错**。

        标注任务 id 缺失时回退 ``detection``（与 scheduler 同语义）。
        """
        from app.plugin.module_train.scheduler import _resolve_task_type

        return (await _resolve_task_type(task)).lower()

    @staticmethod
    async def _dataset_params(task_type: str, hp: dict,
                              annotation_task_id: int | None) -> dict:
        """由**实际数据**推出必须下发给 TorchKiln 的数据集级超参。

        目前只有关键点任务的 ``Train.dataset.kpt_shape`` 需要推导。

        ⚠️ 不下发会「静默丢标签」而不是报错：``PoseDataset._load`` 里
        ``if len(p) < 5 + nk * kpt_dim: continue``——配置模板里的 kpt_shape
        若与本数据集的关键点数不一致（模板按 COCO 的 17 点、数据实际 4 点），
        每一行标注都会被整条跳过，训练照常跑完但学到的是空数据集。
        """
        params: dict = {}
        if task_type not in ("keypoint", "pose") or not annotation_task_id:
            return params

        n_kpt = 0
        try:
            from sqlalchemy import select

            from app.api.v1.module_annotation.annotation.model import (
                AnnotationRecordModel,
            )
            async with async_db_session() as db:
                result = await db.execute(
                    select(AnnotationRecordModel.annotations)
                    .where(AnnotationRecordModel.annotation_task_id == annotation_task_id)
                )
                for (anns,) in result.all():
                    for ann in anns or []:
                        if isinstance(ann, dict) and isinstance(ann.get("keypoints"), list):
                            n_kpt = max(n_kpt, len(ann["keypoints"]))
        except Exception as e:  # noqa: BLE001
            log.warning("[torchkiln] 推导 kpt_shape 失败，沿用配置模板值: {}", e)
            return params

        if n_kpt:
            # 3 = (x, y, visibility)，与本项目导出的 kx ky kv 三元组对齐
            params["Train.dataset.kpt_shape"] = [n_kpt, 3]
            log.info("[torchkiln] 注入 Train.dataset.kpt_shape={}", params["Train.dataset.kpt_shape"])
        return params

    @classmethod
    def _build_spec(cls, task, data_dir: str, params: dict | None = None) -> dict:
        """``TrainTask.hyperparams`` -> 服务端 ``JobSpec``（声明式）。

        约定的 ``hyperparams`` 结构::

            {
              "model": "yolov8n-det",            # 必填，TorchKiln 的 Global.model_name
              "task_type": "detection",           # 仅影响数据导出格式
              "params": {"Global.epoch_num": 100},  # 点分键，原样透传给 -o
              "seed": 1024,
              "resources": {"gpu_memory_gb": 12, "shm_size": "4g"},
              "train_ratio": 0.8
            }
        """
        hp = task.hyperparams or {}
        # ⚠️ 这里**只给 data_dir**。train.txt / val.txt 由导出器产出，导出前还不存在，
        #    探测必然落空；由 ``_attach_dataset_lists`` 在导出之后补挂（见其注释）。
        dataset = {"data_dir": data_dir}
        resources = dict(hp.get("resources") or {})
        resources.setdefault("gpu", 1)
        # DataLoader worker>0 时不给 shm 会 BUS error
        resources.setdefault("shm_size", "4g")
        labels = {"aistation_task_id": str(task.id), "aistation_task_name": str(task.name or "")}
        if task.annotation_task_id:
            labels["annotation_task_id"] = str(task.annotation_task_id)
        return build_job_spec(
            model_name=cls._model_name(task),
            # 用户填的超参在前，推导出的数据集级超参在后：让推导值能覆盖模板默认值，
            # 同时用户显式填过同一个键时应当以用户为准。
            params={**(hp.get("params") or {}), **(params or {})},
            dataset=dataset,
            resources=resources,
            seed=hp.get("seed"),
            labels=labels,
        )

    @staticmethod
    def _attach_dataset_lists(spec: dict, host_data_dir: str,
                              container_data_dir: str) -> dict:
        """把导出后的 ``train.txt`` / ``val.txt`` 挂进 spec 的 dataset 段。

        ⚠️ **必须在数据导出之后调用**。这两个文件是导出器产出的，导出前探测
        必然落空，于是 ``dataset`` 里没有 ``train_list``/``val_list``，TorchKiln
        的 runner 就不会注入 ``Train.dataset.label_file_list``，会退回用模型配置
        模板里的路径（如镜像内的 ``datasets/det_demo/train.txt``）→ 首次训练必然
        FileNotFoundError。此前的写法正是把探测放在导出之前，踩的就是这个坑。

        只挂「确实存在」的文件。

        ⚠️ 注意「不注入」的**真实后果**：TorchKiln 的 runner 只在 ``ds.val_list``
        非空时才覆盖 ``Eval.dataset.label_file_list``（service/runner.py）。所以
        「不注入」等于**退回模型配置模板里的值**（通常是镜像内 demo 数据的
        ``val.txt``）—— 找不到就 FileNotFoundError，找得到就拿 demo 数据当验证集，
        指标是假的。本方法只解决「别指向别的数据集」，**不能**用它来「跳过验证集」。

        真正的保障在导出侧：两个 split 都要有图才会写两份清单。而
        ``_export_yolo`` 的 ``split_idx = max(1, int(n * ratio))`` 在 n>=2 时必然给
        val 留出至少 1 张，**只有 n==1（数据集仅 1 张标注图）才会缺 val.txt**，
        属已知边界，此时训练会退回模板验证集。

        **存在性在宿主目录探测、路径给容器内路径**：文件实际写在宿主上，但
        TorchKiln 是在容器里读的，拿宿主路径去 ``open`` 必然 FileNotFoundError。
        拼接必须用 ``posixpath``——宿主是 Windows，``os.path.join`` 产出反斜杠，
        到容器里就不是合法路径了。
        """
        dataset = dict(spec.get("dataset") or {})
        dataset["data_dir"] = container_data_dir
        for key, fname in (("train_list", "train.txt"), ("val_list", "val.txt")):
            if os.path.isfile(os.path.join(host_data_dir, fname)):
                dataset[key] = posixpath.join(container_data_dir, fname)
        spec["dataset"] = dataset
        return spec

    @classmethod
    async def _start_job_container(cls, alloc, host_workspace: str, task_id: int):
        """起这个任务专属的 TorchKiln job 容器。

        与 ultralytics / PaddleX 的容器模式一致（每任务一容器），区别是**容器里
        跑的是完整的 TorchKiln 服务**而不是一次性训练命令——于是 HTTP 契约、
        指标事件、状态机全都原样保留，只把「常驻服务」换成了「一任务一服务」。

        三个容易踩的点：

        1. ``TKILN_DATA_ROOT`` 必须指向**挂载点**。服务默认往容器内目录写
           ``metrics.jsonl`` 和权重，不挂出来的话容器一销毁产物就没了——而且
           任务还会显示成功，事后才发现没产物。
        2. 端口映射到 ``alloc.port``，本项目再用 ``alloc.base_url`` 连它。
        3. ``shm_size``：DataLoader worker>0 时不给 shm 会 BUS error。
        """
        # volumes 的值必须是 {"bind": ..., "mode": ...}，不能写成裸字符串——
        # Docker SDK 会对 str 调 .get() 而炸（与 paddlex_executor 同一写法）
        volumes = {host_workspace: {"bind": _CONTAINER_WORKSPACE, "mode": "rw"}}
        env = {
            "TKILN_DATA_ROOT": _CONTAINER_WORKSPACE,
            "TKILN_REPO_ROOT": _CONTAINER_REPO_ROOT,
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
            labels={"aistation.task_kind": "train",
                    "aistation.task_id": str(task_id),
                    "aistation.tk_port": str(alloc.port)},
            shm_size="8g",
        )

    # ------------------------------------------------------------ 指标换算
    @staticmethod
    def _row_from_event(ev: dict) -> dict | None:
        """``metrics.jsonl`` 事件 -> ``metrics_log`` 行。

        ⚠️ **必须把 ``seq`` 写进行里**。前端刷新页面时用
        ``maxSeqOf(task.metrics_log)`` 恢复 SSE 断点续传的位置
        （``/train/task/{id}/metrics/stream?offset=<lastSeq>``）；
        落库行里没有 seq 时它恒为 -1，重连就会从头重发整段指标——
        轻则重复行把曲线画粗，重则把已画的点挤掉。
        """
        etype = ev.get("type")
        seq = ev.get("seq")
        # TorchKiln 的事件带 `epoch_num`（总轮次），但**必须改写成本项目约定的 `total_epochs`**：
        # 前端「Epoch N/M」卡片与进度条按 `total_epochs`（PaddleX 叫 `total`）取分母。
        # 之前没透传，导致完成态永远显示成「50/?」。
        total_epochs = ev.get("epoch_num")
        if etype == EVENT_STEP:
            row = {
                "_kind": EVENT_STEP,
                "seq": seq,
                "epoch": ev.get("epoch"),
                "global_step": ev.get("global_step"),
                "loss": ev.get("loss"),
                "lr": ev.get("lr"),
                "ips": ev.get("ips"),
                "mem_reserved": ev.get("mem_reserved"),
            }
            if isinstance(total_epochs, int):
                row["total_epochs"] = total_epochs
            for k, v in (ev.get("comps") or {}).items():
                if isinstance(v, (int, float)):
                    row[k] = v
            return row
        if etype in (EVENT_EVAL, EVENT_BEST):
            row = {"_kind": etype, "seq": seq, "best": etype == EVENT_BEST or None}
            row["epoch"] = ev.get("epoch")
            row["global_step"] = ev.get("global_step")
            row["main_indicator"] = ev.get("main_indicator")
            row["main_indicator_mode"] = ev.get("main_indicator_mode")
            row["main_value"] = ev.get("main_value")
            if isinstance(total_epochs, int):
                row["total_epochs"] = total_epochs
            if ev.get("fps") is not None:
                row["fps"] = ev["fps"]
            # metrics 子对象摊平，前端按 {epoch, 指标名: 值} 取值
            for k, v in (ev.get("metrics") or {}).items():
                if isinstance(v, (int, float)):
                    row[k] = v
            return row
        if etype == EVENT_END:
            row = {
                "_kind": EVENT_END,
                "seq": seq,
                "exit_reason": ev.get("exit_reason"),
                "epoch": ev.get("epoch"),
                "main_indicator": ev.get("main_indicator"),
                "main_value": ev.get("main_value"),
                "duration_sec": ev.get("duration_sec"),
            }
            if isinstance(total_epochs, int):
                row["total_epochs"] = total_epochs
            return row
        return None

    @staticmethod
    def _summarize(rows: list[dict]) -> tuple[dict | None, dict | None]:
        """挑 best / last。

        主指标**从事件里读**（TorchKiln 的 ``main_indicator`` 随任务变：
        mAP50-95 / acc / hmean / RMSE…），不再像以前那样为每个框架维护一张
        硬编码映射表——这正是接自研平台的收益。
        """
        main_indicator = None
        mode = "max"
        for r in rows:
            if r.get("main_indicator"):
                main_indicator = r["main_indicator"]
                mode = str(r.get("main_indicator_mode") or "max").lower()
                break
        evals = [r for r in rows if r.get("_kind") == EVENT_EVAL and r.get("epoch")]
        if not evals:
            return None, (rows[-1] if rows else None)

        def score(r: dict):
            if main_indicator and isinstance(r.get(main_indicator), (int, float)):
                return float(r[main_indicator])
            v = r.get("main_value")
            return float(v) if isinstance(v, (int, float)) else None

        scored = [(s, r) for s, r in ((score(r), r) for r in evals) if s is not None]
        if not scored:
            return None, evals[-1]
        best = (min if mode == "min" else max)(scored, key=lambda x: x[0])[1]
        return best, evals[-1]

    # ------------------------------------------------------------ 主流程
    @classmethod
    async def _execute(cls, task_id: int):
        if not settings.TORKILN_ENABLED:
            await cls._mark_status(
                task_id, TrainStatus.FAILED, progress=0,
                error_log="TorchKiln 接入已关闭（setting.TORKILN_ENABLED=False）",
                finished_at=datetime.now())
            return

        export_dir = work_dir("train_output", task_id)
        # 宿主上真正写数据的目录；容器里它对应 /workspace/data
        host_data_dir = os.path.join(export_dir, "data")
        try:
            async with async_db_session() as db:
                task = await db.get(TrainTask, task_id)
                if not task:
                    return
                hp = dict(task.hyperparams or {})
                dataset_id = task.dataset_id
                annotation_task_id = task.annotation_task_id
                existing_job = get_job_id(hp)
                # 取标注任务类型（不是模型 task）——它同时决定白名单、导出格式
                # 分派与 OCR 的 det/rec，详见 _task_type 的说明。
                task_type = await cls._task_type(task)
                # OCR 的 det / rec 决定导出的是「四点 JSON」还是「整图文本」，
                # 从模型名末段推导（PP-OCRv6_tiny_det → det，…_rec → rec）。
                model_name = cls._model_name(task)
                ocr_rec = task_type == "ocr" and model_name.lower().rstrip("-_").endswith("rec")
                params = await cls._dataset_params(task_type, hp, annotation_task_id)
                # ⚠️ spec 里的路径是**容器内**路径：TorchKiln 在容器里读数据
                spec = cls._build_spec(task, _CONTAINER_DATA_DIR, params=params)
                train_ratio = float(hp.get("train_ratio", 0.8))

            cls._check_task_type(task_type)

            # 接管已有作业时不必重新导出（那个作业的数据就是这份）
            if not existing_job:
                await cls._export_training_data(
                    task_id, host_data_dir, dataset_id=dataset_id,
                    annotation_task_id=annotation_task_id,
                    train_ratio=train_ratio, task_type=task_type, ocr_rec=ocr_rec)
                spec = cls._attach_dataset_lists(spec, host_data_dir, _CONTAINER_DATA_DIR)

            # 先导出再排队：反过来的话，等 GPU 的任务会一边排队一边白占一张卡
            need_mem_gb = float((hp.get("resources") or {}).get("gpu_memory_gb")
                                or settings.TORKILN_GPU_MIN_FREE_GB)
            waiting_since = time.monotonic()
            await broadcast_line(
                task_id,
                f"[torchkiln] 等待可用显存 ≥ {need_mem_gb:.1f}GB 的 GPU 与空闲端口…")
            alloc = await gpu_pool.acquire(task_id, need_gpu=1, need_mem_gb=need_mem_gb)
            if alloc is None:
                await cls._mark_status(
                    task_id, TrainStatus.FAILED,
                    error_log="拿不到空闲 GPU 或可用端口（详见后端日志中 gpu_pool 的占用明细）",
                    finished_at=datetime.now())
                return
            waited = time.monotonic() - waiting_since
            if waited >= _QUEUE_HINT_AFTER:
                # 说清楚"等多久、为什么等"：只说"等待可用 GPU"的话，用户无法判断
                # 是该继续等还是这台机器根本跑不动这个任务。
                ahead = await gpu_pool.busy_task_count()
                await broadcast_line(
                    task_id,
                    f"[torchkiln] 已排队 {waited:.0f}s，当前有 {ahead} 个任务占用 GPU"
                    f"（本次需要 {need_mem_gb:.1f}GB 可用显存）")
            # 拿到资源才算"开始"：在此之前一直是 PENDING（排队中）。
            # ⚠️ 此前**从不**置 RUNNING，于是整个训练过程在列表页都显示"排队中"，
            # 进度条与运行中态（v-if status==='running'）永远不出现——用户看到的
            # 与实际完全对不上。RUNNING 语义 = 已分配到资源、正在执行。
            if task.status != TrainStatus.RUNNING:
                await cls._mark_status(
                    task_id, TrainStatus.RUNNING,
                    started_at=task.started_at or datetime.now())

            container = None
            try:
                gpu_desc = (f"GPU {','.join(str(i) for i in alloc.gpu_indices)}"
                            if alloc.gpu_indices else "未指定 GPU")
                await broadcast_line(
                    task_id,
                    f"[torchkiln] 分配到端口 {alloc.port} / {gpu_desc}，启动 job 容器…")
                container = await cls._start_job_container(alloc, export_dir, task_id)
                # 容器 running ≠ 服务可用：容器内冷启动要 import torch（本机实测
                # 23.4 秒），这段时间端口还没监听，提交作业只会拿到连接拒绝。
                await gpu_pool.wait_service_ready(alloc.port)
                await broadcast_line(task_id, "[torchkiln] job 容器就绪")

                async with TorchKilnClient(base_url=alloc.base_url) as client:
                    job_id = await cls._ensure_job(
                        client, task_id, spec, existing_job=existing_job)
                    await cls._pump(client, task_id, job_id)

            finally:
                # 无论成败都要收摊：容器停掉、GPU 与端口归还，否则单卡机器会被
                # 一次失败的任务永久占死。
                if container is not None:
                    with contextlib.suppress(Exception):
                        await stop_container(container.id)
                await gpu_pool.release(task_id)

        except TorchKilnUnavailable as e:
            # 服务不可达：保持 RUNNING 等 recover_orphans 重试，**不误判失败**
            log.warning("[torchkiln] 服务不可达，任务 {} 保持运行态待重试: {}", task_id, e)
            await broadcast_line(task_id, f"[torchkiln] 服务不可达，稍后重试: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            # 记录完整堆栈：只留 str(e) 会丢掉"哪个文件哪一行调用出错"，
            # 排查时只能靠猜（本项目就曾因此被 task_type 形参问题绕了很久）
            log.exception("[torchkiln] task {} failed", task_id)
            await cls._mark_status(
                task_id, TrainStatus.FAILED,
                error_log=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                finished_at=datetime.now())

    @classmethod
    async def _export_training_data(cls, task_id: int, host_data_dir: str, *,
                                   dataset_id: int,
                                   annotation_task_id: int | None,
                                   train_ratio: float, task_type: str,
                                   ocr_rec: bool) -> None:
        """把标注数据导出到**宿主**目录（容器里挂成 /workspace/data）。"""
        await broadcast_line(task_id, f"[torchkiln] 准备训练数据 -> {host_data_dir}")
        from app.plugin.module_train.exporter import YOLO_LAYOUT, prepare_training_data_for_task

        # 数据布局与 YOLO 一致：images/<split> + labels/<split>；
        # torchkiln_index=True 额外生成 TorchKiln 需要的 train.txt / val.txt 索引。
        # ⚠️ task_type 走 framework 前缀（``yolo-<type>``）——这是 _export_core 既有的
        #    约定（``framework.startswith("yolo-")`` 时用它推导任务类型），
        #    prepare_training_data_for_task 没有 task_type 形参。
        # 用 YOLO_LAYOUT 常量而非裸 "ultralytics"：那个值是**目录布局标识符**，
        # 不是已退场的训练框架名，写成常量免得被误读成"还在用 ultralytics"。
        export_framework = (f"yolo-{task_type}"
                            if task_type not in ("detection", "detect") else YOLO_LAYOUT)
        await prepare_training_data_for_task(
            dataset_id, task_id, export_framework, host_data_dir,
            annotation_task_id=annotation_task_id,
            train_ratio=train_ratio,
            ocr_rec=ocr_rec,
            torchkiln_index=True,
        )

    @classmethod
    def _check_task_type(cls, task_type: str) -> None:
        """白名单校验。**必须在导出之前**——不然会为一个注定被拒的任务
        白导出一遍数据、还占着 IO。"""
        if task_type in cls.SUPPORTED_TASK_TYPES:
            return
        raise ValueError(
            f"标注任务类型 {task_type!r} 暂不支持 TorchKiln 训练"
            f"（已支持：{', '.join(sorted(cls.SUPPORTED_TASK_TYPES))}）"
        )

    #: 本平台**标注任务类型**（``AnnotationType`` 裸值）中，TorchKiln 已实现读取器、
    #: 且本项目导出格式能对齐的子集。**成员与前端 ``TK_SUPPORTED_TASK_TYPES`` 逐一对应**
    #: （那边按标注任务类型过滤下拉，这边兜底拦截），取值来源见 ``_task_type``。
    #: 其余类型（全景分割 / 音视频事件 / 时序事件 / 文本 NER / 折线）要么
    #: TorchKiln 侧根本没有对应 task，要么语义对不上，一律在提交前拦下。
    #: 直接调 API 绕过前端时仍会得到明确报错，而不是训出一堆空标签。
    SUPPORTED_TASK_TYPES = frozenset({
        "detection",
        "rotated_detection",
        "segmentation",
        "semantic_segmentation",
        "keypoint",
        "classification",
        "ocr",
        # 视频帧级检测：exporter._export_video_detection 已按帧抽帧并复用检测
        # 格式器，且它在 framework 分派**之前**命中（按标注任务类型），故放行。
        "video_detection",
        # 3D：导出为「相机系 -> LiDAR 系」的 7-dof（cls x y z l w h yaw），
        # 对应 TorchKiln 的 `mono3d` 任务（det3d 的图像分支）。
        # ⚠️ 只有带 `box3d` 米制参数的标注才会被导出；只有 2D 投影的会跳过并记日志——
        #    绝不拿归一化的 cx/cy/w/h 顶替，那会被当米制解析、不报错但数据全错。
        "cuboid",
    })

    @classmethod
    async def _ensure_job(cls, client, task_id: int, spec: dict,
                          existing_job: str | None) -> str:
        """拿到一个作业 id：优先接管已有作业，否则提交新作业。

        数据导出与白名单校验都不在这里——分别在 ``_execute`` 里更早做完，
        免得为一个注定被拒、或注定要重跑的任务白导一遍数据。
        """
        if existing_job:
            try:
                info = await client.get_job(existing_job)
            except TorchKilnError as e:
                await broadcast_line(
                    task_id, f"[torchkiln] 原作业 {existing_job} 不可达（{e}），改为新建")
            else:
                await broadcast_line(
                    task_id,
                    f"[torchkiln] 接管已有作业 {existing_job}（状态 {info.get('status')}）")
                return existing_job

        await broadcast_line(task_id, f"[torchkiln] 提交作业（模型 {spec['model_name']}）")
        created = await client.submit_job(
            spec, idempotency_key=f"aistation-train-{task_id}")
        job_id = created["job_id"]
        await set_job_id(task_id, job_id)
        await broadcast_line(
            task_id, f"[torchkiln] 作业已受理 {job_id}"
                     f"（幂等命中={created.get('idempotent_hit')}）")
        return job_id

    @classmethod
    async def _pump(cls, client, task_id: int, job_id: str):
        """启动两条流，等终态，收敛本项目状态。"""
        # 接管场景先把历史指标补齐，避免曲线从零开始
        rows: list[dict] = list(await load_metrics_rows(task_id))
        last_seq = -1
        for ev in await client.metrics(job_id, offset=-1, limit=20000):
            if isinstance(ev.get("seq"), int):
                last_seq = max(last_seq, ev["seq"])
            row = cls._row_from_event(ev)
            if row:
                rows.append(row)
        if rows:
            await save_metrics(task_id, rows)

        metrics_task = asyncio.ensure_future(
            cls._consume_metrics(client, task_id, job_id, last_seq, rows))
        logs_task = asyncio.ensure_future(cls._consume_logs(client, task_id, job_id))
        try:
            final = await cls._await_terminal(client, task_id, job_id)
        finally:
            for t in (metrics_task, logs_task):
                t.cancel()
            await asyncio.gather(metrics_task, logs_task, return_exceptions=True)

        # 收尾再拉一次，确保 end 事件入库（流可能刚好被取消在前一条）
        final_rows = list(await load_metrics_rows(task_id))
        if not any(r.get("_kind") == EVENT_END for r in final_rows):
            for ev in await client.metrics(job_id, offset=-1, limit=20000):
                row = cls._row_from_event(ev)
                if row:
                    final_rows.append(row)
            if final_rows:
                await save_metrics(task_id, final_rows)

        best, last = cls._summarize(final_rows)
        status = _STATUS_MAP.get(str(final.get("status")), TrainStatus.FAILED)
        reason = final.get("exit_reason")
        err = final.get("error")
        if status == TrainStatus.FAILED and not err:
            err = f"TorchKiln 作业失败（exit_reason={reason}）"

        # 训练成功后把最优权重复制进 RustFS 并建模型版本——这是打通
        # 「评估 / 预测 / 导出 / 部署」的前提：那些链路都按 model_id 取权重，
        # 没有版本它们全都无从下手。
        model_repo_id = None
        if status == TrainStatus.SUCCESS:
            from app.plugin.module_train.exporter import export_model

            export_dir = work_dir("train_output", task_id)
            try:
                model_info = await export_model(
                    task_id, "torchkiln", export_dir, best_metrics=best)
                model_repo_id = model_info.get("repo_id")
                if not model_info.get("storage_path"):
                    await broadcast_line(
                        task_id, "[torchkiln] 未能取得权重，本次不创建模型版本"
                        "（评估/预测/导出将不可用）")
                else:
                    await broadcast_line(
                        task_id, f"[torchkiln] 权重已入库，模型版本 id={model_repo_id}")
            except Exception as e:  # noqa: BLE001
                # 取权重失败**不能**把训练判成失败——训练本身已成功，
                # 只是没能建版本；否则用户会白跑一遍训练。
                log.error("[torchkiln] 权重入库失败: {}", e)
                await broadcast_line(task_id, f"[torchkiln] 权重入库失败: {e}")

        await cls._mark_status(
            task_id, status,
            model_repo_id=model_repo_id,
            metrics_log=final_rows or None,
            best_metrics=best or None,
            last_metrics=last or None,
            progress=100,
            error_log=err if status == TrainStatus.FAILED else None,
            finished_at=datetime.now(),
        )

    # ------------------------------------------------------------ 两条流
    @classmethod
    async def _consume_logs(cls, client, task_id: int, job_id: str):
        try:
            async for line in client.stream_logs(job_id, tail=200):
                await broadcast_line(task_id, line)
        except asyncio.CancelledError:
            raise
        except TorchKilnError as e:
            log.warning("[torchkiln] 日志流中断: {}", e)
            await broadcast_line(task_id, f"[torchkiln] 日志流中断: {e}")

    @staticmethod
    def _flush_interval(row_count: int) -> float:
        """按已积累的行数决定落库间隔（秒）。

        指标是**整列覆盖写**，所以「写入速率 × 单次体积」才是真正的压力来源。
        固定间隔下，行数越多单次越贵，总吞吐随训练推进而线性上升——长训练到几千行
        时每次 flush 都是几 MB。这里让间隔随行数线性放大，把单次写入速率维持在
        近似常数：行数翻倍、间隔翻倍。

        下限 ``_FLUSH_SECONDS``（别太频繁，否则小数据集反而延迟落库），
        上限 30 秒（再慢前端刷新就明显滞后于 SSE；SSE 是实时的，落库只影响
        刷新页面后的回看）。
        """
        if row_count <= 1000:
            return _FLUSH_SECONDS
        return min(_FLUSH_SECONDS * (row_count / 1000.0), 30.0)

    @classmethod
    async def _consume_metrics(cls, client, task_id: int, job_id: str,
                               last_seq: int, rows: list[dict]):
        pending = 0
        loop = asyncio.get_event_loop()
        last_flush = loop.time()
        try:
            async for ev in client.stream_metrics(job_id, offset=last_seq):
                if ev.get("__end__"):
                    break
                seq = ev.get("seq")
                if isinstance(seq, int):
                    if seq <= last_seq:
                        continue
                    last_seq = seq
                publish_metric(task_id, ev)
                row = cls._row_from_event(ev)
                if row:
                    rows.append(row)
                    pending += 1
                now = loop.time()
                # ⚠️ 落库是**整列覆盖写**（save_metrics）：每写一次都要把整个
                #    metrics_log 序列化并推送。固定 3 秒一次 flush，在几千行时
                #    等于「每 3 秒重写几 MB JSONB」，Postgres TOAST 直接吃满。
                #    按行数自适应退避，把写入速率压到大致恒定的字节量。
                if (pending >= _FLUSH_EVERY
                        or (now - last_flush) >= cls._flush_interval(len(rows))):
                    await save_metrics(task_id, rows)
                    pending = 0
                    last_flush = now
        except asyncio.CancelledError:
            raise
        except TorchKilnError as e:
            log.warning("[torchkiln] 指标流中断: {}", e)
        finally:
            try:
                if rows:
                    await save_metrics(task_id, rows)
            except Exception as e:  # noqa: BLE001
                log.warning("[torchkiln] 指标落库失败: {}", e)

    @classmethod
    async def _await_terminal(cls, client, task_id: int, job_id: str,
                              poll_seconds: float = 5.0) -> dict:
        """轮询到终态（取消请求也在这里被翻译成服务端的 cancel）。"""
        while True:
            if cls._registry.get(task_id, {}).get("cancel"):
                await broadcast_line(task_id, "[torchkiln] 收到停止请求，转发取消")
                try:
                    return await client.cancel_job(job_id)
                except TorchKilnError as e:
                    log.warning("[torchkiln] 取消失败: {}", e)
                    return {"status": "cancelled", "exit_reason": "cancelled"}
            info = await client.get_job(job_id)
            status = str(info.get("status"))
            if status in ("succeeded", "failed", "cancelled"):
                return info
            await asyncio.sleep(poll_seconds)


# ---------------------------------------------------------------- 对外辅助
async def service_status() -> dict:
    """训练服务可用性（前端"训练"页展示，避免点了开始才报错）。"""
    return await probe_service()


def executor_info() -> dict:
    return {
        "executor": TorchKilnExecutor.name,
        "url": settings.TORKILN_SERVICE_URL,
        "enabled": bool(settings.TORKILN_ENABLED),
        "has_token": bool(settings.TORKILN_SERVICE_TOKEN),
    }
