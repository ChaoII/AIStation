import asyncio
import contextlib
import os
from datetime import datetime

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from . import gpu_pool
from . import tk_job_container as tkjc
from .docker_utils import stop_container
from .exporter import YOLO_LAYOUT, _write_torchkiln_index, prepare_eval_data_for_task
from .framework_utils import framework_value
from .job_runner import JobCancelled, cleanup_registry, gpu_slot, mark_failed, settle_by_status
from .model import TrainEval, TrainFramework, TrainModel, TrainStatus
from .paths import work_dir
from .retired import ensure_active
from .service import TrainService
from .task_executor import TaskExecutor
from .torchkiln_client import TorchKilnClient
from .ws import broadcast_eval_log

#: 自研平台的评估镜像（保留为兜底；实际用 settings.TORKILN_JOB_IMAGE）
DOCKER_IMAGE = "torchkiln:0.1.0"

#: 评估作业的 TorchKiln job_id 存在 hyperparams 里的键。
#: 与训练用同一个键名（``__tk_job_id``）——它们是同一种东西：一个 TorchKiln
#: 作业的引用。用两个键名会让「按 job_id 恢复」的逻辑要判断两次。
JOB_ID_KEY = "__tk_job_id"

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


async def start_evaluation_scheduler():
    await EvalExecutor.start_recovery_loop()


async def start_evaluation(eval_id: int):
    # 原子守卫：单条条件 UPDATE 抢占，避免并发 start 的 TOCTOU 重复入队
    async with async_db_session.begin() as db:
        result = await db.execute(
            update(TrainEval)
            .where(TrainEval.id == eval_id, TrainEval.status != TrainStatus.RUNNING)
            .values(
                status=TrainStatus.RUNNING, started_at=datetime.now(), progress=10,
                metrics=None, metrics_log=None, best_metrics=None, last_metrics=None,
                log=None, error_log=None, finished_at=None,
            )
        )
        if result.rowcount == 0:
            # 影响 0 行：要么不存在，要么已在运行
            row = await db.get(TrainEval, eval_id)
            if row:
                raise Exception("评估任务正在运行，请勿重复启动")
            raise Exception(f"评估任务 {eval_id} 不存在")
    _spawn(EvalExecutor.run(eval_id))


async def resolve_eval_context(model_id: int) -> tuple[int | None, str, str]:
    """从产出该模型的训练任务推断 ``(annotation_task_id, tk_config_name, _)``。

    评估必须传 ``annotation_task_id`` 给导出，否则任务类型默认 detection，
    分类/分割评估会导出错误格式；配置名也须与被评模型一致而非沿用 eval 超参。
    无匹配训练任务时回退 ``(None, "", "tiny")``。

    ⚠️ 两处 id 语义，历史上都踩过：

    1. ``model_id`` 是**版本行 id**，不是仓库 id。
    2. ``TrainTask.model_repo_id`` 这个字段名有误导——实测**它存的也是版本行
       id**（产出模型行的主键），不是仓库 id。逐条查过历史任务：torchkiln /
       ultralytics 的任务都是如此。

    所以匹配要**先按版本行 id 查**；为兼容万一真存了仓库 id 的老数据，查不到
    时再按 ``TrainModel.repo_id`` 兜一次。此前这里拿仓库 id 去比
    ``model_repo_id``，**永远匹配不到**，于是恒走回退：``annotation_task_id``
    丢成 None（分类/分割评估导出成 detection 格式）、配置名丢成空。
    """
    from sqlalchemy import desc, select

    from .model import TrainTask

    async with async_db_session() as db:
        model_row = await db.get(TrainModel, model_id)
        task = None
        if model_row:
            task = (await db.execute(
                select(TrainTask).where(TrainTask.model_repo_id == model_id)
                .order_by(desc(TrainTask.id)).limit(1)
            )).scalar_one_or_none()
        if task is None and model_row and model_row.repo_id:
            # 兜底：万一这行的 model_repo_id 真的存的是仓库 id
            task = (await db.execute(
                select(TrainTask).where(TrainTask.model_repo_id == model_row.repo_id)
                .order_by(desc(TrainTask.id)).limit(1)
            )).scalar_one_or_none()
    if not task:
        log.warning(
            f"评估上下文：模型版本 {model_id} 找不到产出它的训练任务，"
            f"回退 annotation_task_id=None——若被评模型不是 detection，"
            f"导出的标签格式会与训练时不一致")
        return (None, "", "tiny")
    hp = task.hyperparams or {}
    mode = str(hp.get("mode", "det")).lower()
    size = str(hp.get("model_size", "tiny"))
    if framework_value(getattr(task, "framework", None)) == "torchkiln":
        # TorchKiln 的"规格"就是配置名（configs/... 的 model_name），直接回传
        return (task.annotation_task_id, str(hp.get("model") or ""), "tiny")
    return (
        task.annotation_task_id,
        mode if mode in ("det", "rec") else "det",
        size if size in ("tiny", "small", "medium") else "tiny",
    )


def build_eval_spec(
    config_path: str,
    weights_path: str,
    data_dir: str,
    val_list: str,
    params: dict | None = None,
    resources: dict | None = None,
) -> dict:
    """组装 TorchKiln 评估作业的 ``JobSpec``。

    ⚠️ ``data_dir`` / ``val_list`` / ``weights_path`` 都必须是**容器内**路径
    （作业进程看不到宿主机）。这里由调用方用
    :func:`tk_job_container.container_path` 换算。

    ⚠️ 只放**用户可调**的超参进 ``params``：``Global.save_model_dir`` 与
    ``Global.metrics_sink`` 由 TorchKiln 服务强制注入，这里传了也会被覆盖。
    """
    spec: dict = {
        "spec_version": "1.0",
        "framework": "torchkiln",
        "kind": "eval",
        "config_path": config_path,
        "weights_path": weights_path,
        "params": dict(params or {}),
        # 只给 val_list；服务端会把它同时注入 Train/Eval 两个 dataset
        # （build_trainer 构造期会打开这两个文件，少一个就 setup 失败）
        "dataset": {"data_dir": data_dir, "val_list": val_list},
    }
    if resources:
        spec["resources"] = resources
    return spec


async def stop_evaluation(eval_id: int):
    await EvalExecutor.stop(eval_id)


class EvalExecutor(TaskExecutor):
    name = "eval"
    task_kind = "eval"
    status_enum = TrainStatus
    model_class = TrainEval
    _concurrency = 1

    @classmethod
    async def _execute(cls, eval_id: int):
        """跑一次评估：起 job 容器 -> HTTP 提交作业 -> 消费指标契约 -> 收尾。

        与训练同形。**指标来自 ``metrics.jsonl`` 契约**（经 ``/metrics`` 读取），
        不再解析容器日志——原先那套「``EVAL_METRIC_JSON`` 标记行 + 两个兜底正则」
        在日志格式变动时会静默失效（指标变空却不报错），而正则里的
        ``main indicator (...)`` 模式一旦上游改了措辞就是**静默返回空**。
        """
        container = None
        data_dir = None
        try:
            async with async_db_session() as db:
                eval_rec = await db.get(TrainEval, eval_id)
                if not eval_rec:
                    return

            # 有效框架：create_eval 未持久化 framework 时，从模型版本推断
            framework = eval_rec.framework or TrainFramework.TORKILN
            async with async_db_session() as db:
                model_row = await db.get(TrainModel, eval_rec.model_id)
                if model_row and model_row.framework:
                    framework = model_row.framework

            # ⚠️ 必须用 framework_value 归一化：PG 的 SAEnum 存的是**成员名**
            # （"TORKILN"），读回来是 str 而非枚举成员，直接 `== TrainFramework.X`
            # 恒为 False 会静默走错分支（train 侧已踩过这个坑）。
            fw = framework_value(framework)
            # Ultralytics / PaddleX 的评估通路已退场：在这里挡住并说明原因，
            # 而不是继续往下走——否则会拉错镜像、用 YOLO val 去评估 OCR 权重，
            # 报出与真实原因无关的错。
            ensure_active(fw, action="评估")

            export_dir = work_dir("eval_output", eval_id)
            data_dir = os.path.join(export_dir, "data")
            model_dir = os.path.join(export_dir, "model")
            os.makedirs(data_dir, exist_ok=True)
            os.makedirs(model_dir, exist_ok=True)

            # ---- 导出评估数据集（全量、确定性；任务类型/配置从产出模型推断）----
            await broadcast_eval_log(eval_id, "[eval] exporting dataset...")
            ann_task_id, tk_cfg_name, _tk_size = await resolve_eval_context(eval_rec.model_id)
            # TorchKiln 读 data_dir + label_file_list（train.txt/val.txt 索引），
            # 图片/标签布局与 YOLO 一致，故复用 YOLO 布局导出并补索引。
            # 传 YOLO_LAYOUT 而不是裸 "ultralytics"：后者是布局标识符，不是框架名。
            await prepare_eval_data_for_task(
                eval_rec.eval_dataset_id, eval_id, YOLO_LAYOUT, data_dir,
                annotation_task_id=ann_task_id,
            )
            _write_torchkiln_index(data_dir)

            # ---- 取权重（统一解析：/export/ 导出产物自动回溯原始 best.pt）----
            # model_id 是版本行 id（model_repo_id 是仓库 id），不可用仓库 id 冒充版本 id
            storage_path = await TrainService._resolve_model_storage(eval_rec.model_id)
            await broadcast_eval_log(eval_id, f"[eval] downloading model {storage_path}...")
            from app.utils.s3_client import s3_client

            model_data = s3_client.download_fileobj(storage_path)
            model_filename = storage_path.rsplit("/", 1)[-1]
            model_local_path = os.path.join(model_dir, model_filename)
            with open(model_local_path, "wb") as f:
                f.write(model_data.read())

            # ---- 配置名 -> 配置路径 ----
            # ⚠️ 拿到的是**模型名**（如 yolo11-seg），而 ``-c`` 只认 configs/ 下的
            # 配置路径。原样传会在容器里报「省略 <task> 时必须用 -c <config> 指定
            # 配置」。借常驻元数据服务把模型名换成配置路径。
            if not tk_cfg_name:
                raise Exception(
                    "TorchKiln 评估找不到产出该模型的训练任务，无法确定配置名；"
                    "请确认该模型版本确实由 TorchKiln 训练产出")
            async with TorchKilnClient() as _tk:
                tk_cfg = await _tk.resolve_config_path(tk_cfg_name)

            hp = eval_rec.hyperparams or {}
            spec = build_eval_spec(
                config_path=tk_cfg,
                weights_path=tkjc.container_path("model", model_filename),
                data_dir=tkjc.container_path("data"),
                val_list=tkjc.container_path("data", "val.txt"),
                params={
                    # 后处理阈值与输入尺寸：这些确实是评估侧可调的
                    "Global.conf": float(hp.get("conf", 0.001)),
                    "Global.iou": float(hp.get("iou", 0.6)),
                    "Global.imgsz": int(hp.get("imgsz", 640)),
                    "Global.batch": int(hp.get("batch", 16)),
                    # ⚠️ num_workers=0：评估是一次性短作业，多进程 DataLoader 的
                    # 启动开销可能超过评估本身；训练侧才值得付这个代价。
                    "Eval.loader.num_workers": 0,
                },
                resources={"gpu": 1,
                           "gpu_memory_gb": (hp.get("resources") or {}).get(
                               "gpu_memory_gb")},
            )

            # ---- 起 job 容器 -> 提交作业 -> 消费指标 ----
            async with gpu_slot(cls, eval_id, hp) as lease:
                container = await tkjc.start_job_container(
                    lease, export_dir, task_kind=cls.task_kind, task_id=eval_id)
                entry = cls._registry.get(eval_id) or {}
                entry.update({"container_id": container.id})
                cls._registry[eval_id] = entry

                await tkjc.wait_ready(lease, broadcast=lambda ln: broadcast_eval_log(eval_id, ln))

                async with TorchKilnClient(base_url=lease.base_url) as client:
                    job_id = await cls._submit(client, eval_id, spec, hp)
                    logs_task = await tkjc.stream_logs(
                        client, job_id, "eval",
                        lambda ln: broadcast_eval_log(eval_id, ln))
                    try:
                        final = await tkjc.await_terminal(
                            client, job_id, "eval",
                            is_cancelled=lambda: bool(
                                cls._registry.get(eval_id, {}).get("cancel")),
                            broadcast=lambda ln: broadcast_eval_log(eval_id, ln))
                    finally:
                        logs_task.cancel()
                        await asyncio.gather(logs_task, return_exceptions=True)

                    metrics = await cls._read_metrics(client, job_id)

            status = str(final.get("status"))
            err = final.get("error") or ""
            if status != "succeeded" and not err:
                err = (f"TorchKiln 评估作业失败"
                       f"（exit_reason={final.get('exit_reason')}, "
                       f"exit_code={final.get('exit_code')}）")

            await settle_by_status(
                cls, eval_id,
                status=status, error=err,
                success_fields={
                    "metrics": metrics or None,
                    "metrics_log": [metrics] if metrics else None,
                    "best_metrics": metrics or None,
                    "last_metrics": metrics or None,
                },
                failure_message="eval failed",
            )

        except JobCancelled:
            # 等待 GPU 期间被取消：容器从未起来，不能记失败也不能走收尾。
            # 状态留给 stop_evaluation 置 CANCELLED。
            log.info(f"[eval] 任务 {eval_id} 在等待 GPU 期间被取消，未启动容器")
            return

        except Exception as e:
            await mark_failed(cls, eval_id, e, kind="eval")
            # 失败后清理本次导出的 data 半成品目录（保留日志文件供排查）
            if data_dir:
                import shutil

                shutil.rmtree(data_dir, ignore_errors=True)
        finally:
            # 无论成败都要收摊：容器停掉、GPU 与端口归还，否则单卡机器会被
            # 一次失败的任务永久占死。
            if container is not None:
                with contextlib.suppress(Exception):
                    await stop_container(container.id)
            await gpu_pool.release(eval_id)
            await cleanup_registry(cls, eval_id, None)

    @classmethod
    async def _submit(cls, client: TorchKilnClient, eval_id: int,
                      spec: dict, hp: dict) -> str:
        """提交评估作业。已有 job_id 则**接管**而不是重复排队。

        幂等键按评估 id 生成，所以超时重试 / 服务重启后重提都落到同一个作业上，
        不会重复烧卡。
        """
        created = await client.submit_eval_job(
            spec, idempotency_key=f"aistation-eval-{eval_id}")
        job_id = created["job_id"]
        await cls._remember_job_id(eval_id, job_id)
        await broadcast_eval_log(
            eval_id, f"[eval] 作业已受理 {job_id}（幂等命中="
                     f"{created.get('idempotent_hit')}）")
        return job_id

    @classmethod
    async def _remember_job_id(cls, eval_id: int, job_id: str) -> None:
        """把 job_id 记进 hyperparams。

        有了它，进程重启后 ``recover_orphans`` 能重新接上而不是从头再跑一遍评估。
        存在 hyperparams 而不是新增列：这是**作业引用**，不是评估的业务属性，
        没必要占一列（训练侧也是这么做的）。
        """
        try:
            async with async_db_session.begin() as db:
                row = await db.get(TrainEval, eval_id)
                if row is None:
                    return
                hp = dict(row.hyperparams or {})
                hp[JOB_ID_KEY] = job_id
                row.hyperparams = hp
        except Exception as e:  # noqa: BLE001
            # 记不住只影响重启后的接管，不该让评估本身失败
            log.warning(f"[eval] 任务 {eval_id} 的 job_id 记录失败: {e}")

    @classmethod
    async def _read_metrics(cls, client: TorchKilnClient, job_id: str) -> dict | None:
        """从指标契约读评估结果。

        契约（``tools/eval.py`` 写）：一条 ``eval`` 事件（含全量指标 + 主指标），
        外加一条 ``end`` 事件。

        ⚠️ **不能只看 exit_code**。服务会把「进程退出但没 end 事件」判成
        ``no_end_event / failed``，而 exit_code 此时可能是 0——只看退出码就会
        把「评估压根没跑起来」当成成功、指标为空。
        """
        events = await client.metrics(job_id, offset=-1, limit=1000, kind="eval")
        out: dict = {}
        for ev in events:
            if ev.get("type") != "eval":
                continue
            # eval 事件的 metrics 是全量子指标，主指标单列
            for k, v in (ev.get("metrics") or {}).items():
                out[k] = v
            for k in ("main_indicator", "main_value", "fps"):
                if ev.get(k) is not None:
                    out[k] = ev[k]
        return out or None
