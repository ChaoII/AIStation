import asyncio
import contextlib
import os
import zipfile
from datetime import datetime

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from . import gpu_pool
from . import tk_job_container as tkjc
from .docker_utils import stop_container
from .job_runner import (
    JobCancelled,
    cleanup_registry,
    gpu_slot,
    mark_failed,
    settle_by_status,
)
from .model import TrainFramework, TrainModel, TrainPredict, TrainStatus
from .paths import work_dir
from .retired import ensure_active
from .task_executor import TaskExecutor
from .torchkiln_client import TorchKilnClient
from .ws import broadcast_predict_log

#: 自研平台的推理镜像（保留为兜底；实际用 settings.TORKILN_JOB_IMAGE）
DOCKER_IMAGE = "torchkiln:0.1.0"

#: 预测作业的 TorchKiln job_id 存在 hyperparams 里的键。
#: 与训练/评估用**同一个**键名（``__tk_job_id``）：它们指的是同一种东西——
#: 一个 TorchKiln 作业的引用。用两个键名会让「按 job_id 恢复」的逻辑要判断两次。
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


def _cleanup_export_dir(export_dir: str | None) -> None:
    """失败后清理本次导出的临时输出目录（保留日志文件供排查）。"""
    if not export_dir:
        return
    import shutil
    shutil.rmtree(export_dir, ignore_errors=True)


def build_predict_spec(
    config_path: str,
    weights_path: str,
    input_dir: str,
    params: dict | None = None,
    resources: dict | None = None,
) -> dict:
    """组装 TorchKiln 预测作业的 ``JobSpec``。

    ⚠️ 三个路径都必须是**容器内**路径（作业进程看不到宿主机），由调用方用
    :func:`tk_job_container.container_path` 换算。

    ⚠️ 用 ``input_dir`` 而不是 ``dataset.data_dir``：预测不吃 YOLO 清单，
    它要的是**一个装满图片的目录**。放混的话 TorchKiln 会去找 val.txt 然后
    报「找不到清单」——与真实原因（这里根本没清单）无关的错误信息。
    """
    spec: dict = {
        "spec_version": "1.0",
        "framework": "torchkiln",
        "kind": "predict",
        "config_path": config_path,
        "weights_path": weights_path,
        "input_dir": input_dir,
        "params": dict(params or {}),
    }
    if resources:
        spec["resources"] = resources
    return spec


def collect_result_images(output_dir: str) -> list[tuple[str, str]]:
    """收集容器输出目录下的结果图，返回 ``[(相对路径, 绝对路径)]``，按相对路径排序。

    契约：``tkiln predict`` 收到目录输入时，按输入的**相对路径**把每张图的可视化
    结果写到 ``--output`` 下，只把扩展名统一成 ``.jpg``。所以这里**递归**扫。

    两处曾各踩一个坑，都是「同名互相覆盖 / 静默丢结果」这一类：

    1. 原来只扫 ``output``/``results``/``vis``/``exp`` 四个固定子目录加顶层，
       而实际布局是 ``images/train``、``images/val`` —— 扫不到，结果恒为空；
       更早还有一个「找到文件后反而只去看 ``exp/``」的写法，同样静默返回空。
       那套猜测是为 Ultralytics/PaddleX 准备的，两者已退场，留着只会让人以为
       还有别的输出布局要兼容。
    2. RustFS key 曾用 ``basename``：``images/train/a.jpg`` 与 ``images/val/a.jpg``
       同名，后者会静默覆盖前者，表现为「结果数对不上」。

    返回相对路径（``/`` 分隔）正是为了让调用方能把它当唯一标识用。
    """
    found: list[tuple[str, str]] = []
    for root, dirs, files in os.walk(output_dir):
        dirs.sort()
        for name in sorted(files):
            if not name.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                continue
            abspath = os.path.join(root, name)
            rel = os.path.relpath(abspath, output_dir).replace(os.sep, "/")
            found.append((rel, abspath))
    found.sort(key=lambda it: it[0])
    return found


async def resolve_predict_tk_config(model_id: int) -> str | None:
    """反查产出该模型版本的**训练任务**，取其 TorchKiln 配置名。

    预测必须用与训练一致的配置（架构/imgsz/后处理都对不上就没有可比性），
    所以这里不猜、不让用户手填——直接回到训练任务要。

    ⚠️ 两处 id 语义，历史上都踩过（与 ``eval_scheduler.resolve_eval_context``
    同一个坑，那边早已修好、这边一直漏着）：

    1. ``model_id`` 是**版本行 id**，不是仓库 id。
    2. ``TrainTask.model_repo_id`` 字段名有误导——实测**它存的也是版本行 id**
       （产出模型行的主键），不是仓库 id。逐条查过历史任务：torchkiln /
       ultralytics 的任务都是如此。

    原实现拿 ``TrainModel.repo_id``（仓库 id）去比 ``model_repo_id``，**永远匹配
    不到** → 恒返回 None → 预测恒失败于「找不到产出该模型的训练任务」。这条链路
    自接入 TorchKiln 起就没跑通过；此前没有 e2e 覆盖预测，所以一直没暴露。

    匹配**先按版本行 id 查**；为兼容万一真存了仓库 id 的老数据，查不到时再按
    ``TrainModel.repo_id`` 兜一次。
    """
    from sqlalchemy import desc, select

    from .framework_utils import framework_value
    from .model import TrainModel, TrainTask

    async with async_db_session() as db:
        model_row = await db.get(TrainModel, model_id)
        if not model_row:
            return None
        task = (await db.execute(
            select(TrainTask).where(TrainTask.model_repo_id == model_id)
            .order_by(desc(TrainTask.id)).limit(1)
        )).scalar_one_or_none()
        if not task and model_row.repo_id:
            # 兜底：万一某些老数据真的存了仓库 id
            task = (await db.execute(
                select(TrainTask).where(TrainTask.model_repo_id == model_row.repo_id)
                .order_by(desc(TrainTask.id)).limit(1)
            )).scalar_one_or_none()
    if not task:
        return None
    if framework_value(getattr(task, "framework", None)) != "torchkiln":
        return None
    return str((task.hyperparams or {}).get("model") or "") or None


async def start_prediction_scheduler():
    """PredictExecutor 孤儿恢复循环（此前缺失，Task 4 修复）。"""
    await PredictExecutor.start_recovery_loop()


async def start_prediction(predict_id: int):
    # 原子守卫：单条条件 UPDATE 抢占，避免并发 start 的 TOCTOU 重复入队
    async with async_db_session.begin() as db:
        result = await db.execute(
            update(TrainPredict)
            .where(TrainPredict.id == predict_id, TrainPredict.status != TrainStatus.RUNNING)
            .values(status=TrainStatus.RUNNING, started_at=datetime.now(), progress=10)
        )
        if result.rowcount == 0:
            # 影响 0 行：要么不存在，要么已在运行
            row = await db.get(TrainPredict, predict_id)
            if row:
                raise Exception("预测任务正在运行，请勿重复启动")
            raise Exception(f"预测任务 {predict_id} 不存在")
    _spawn(PredictExecutor.run(predict_id))


async def stop_prediction(predict_id: int):
    await PredictExecutor.stop(predict_id)


class PredictExecutor(TaskExecutor):
    name = "predict"
    task_kind = "predict"
    status_enum = TrainStatus
    model_class = TrainPredict
    _concurrency = 1

    @classmethod
    async def _execute(cls, predict_id: int):
        """跑一次预测：起 job 容器 -> HTTP 提交作业 -> 收集结果图 -> 收尾。

        与训练、评估同形。三条链路共用 TorchKiln 的作业契约，所以排队、幂等、
        日志、终态判定、产物发现全都不需要各自实现一遍——此前预测是唯一还留在
        「起一次性容器跑 CLI」上的链路，结果它的结果收集逻辑曾与评估漂移过
        （「找到文件后反而只去看 exp/」），且静默返回空。

        结果图的落点变了：不再是容器内 ``/output`` 再拷回来，而是直接写在
        **作业的 output_dir**（服务把 ``TKILN_DATA_ROOT`` 指到挂载点），
        宿主上直接可读——少一次容器内外拷贝。
        """
        container = None
        export_dir = None
        try:
            async with async_db_session() as db:
                pred = await db.get(TrainPredict, predict_id)
                if not pred:
                    return

            # 有效框架：create_predict 未持久化 framework 时，从模型版本推断
            framework = pred.framework or TrainFramework.TORKILN
            async with async_db_session() as db:
                model_row = await db.get(TrainModel, pred.model_id)
                if model_row and model_row.framework:
                    framework = model_row.framework

            # Ultralytics / PaddleX 的推理通路已退场：在这里挡住并说明原因，
            # 而不是继续往下走——否则会拉错镜像、把 .pth 当 best.pt 加载，
            # 报出与真实原因毫无关系的错。
            ensure_active(framework, action="预测")

            export_dir = work_dir("predict_output", predict_id)
            source_dir = os.path.join(export_dir, "source")
            model_dir = os.path.join(export_dir, "model")
            os.makedirs(source_dir, exist_ok=True)
            os.makedirs(model_dir, exist_ok=True)

            # 超参需在数据导出前取得，供 spec 组装使用
            hp = pred.hyperparams or {}

            # ---- 准备待推理图片 ----
            from app.utils.s3_client import s3_client

            if pred.source_type == "dataset":
                await broadcast_predict_log(predict_id, "[predict] exporting dataset images...")
                from .exporter import YOLO_LAYOUT, prepare_training_data_for_task
                # ⚠️ 必须传 **YOLO_LAYOUT**（目录布局名），不能传 framework.value。
                #    两者恰好都是 "ultralytics" 的时候看不出问题，但 TorchKiln 下
                #    framework.value 是 "torchkiln"，而 _export_core 只按**布局名**
                #    分发，于是直接抛「不支持的导出框架: torchkiln」——预测链路
                #    从接入 TorchKiln 起就一直是坏的，只是此前没有 e2e 覆盖到它。
                #    eval_scheduler 早就用的是 YOLO_LAYOUT，两边不一致才拖到现在。
                await prepare_training_data_for_task(
                    pred.source_dataset_id, predict_id, YOLO_LAYOUT, source_dir
                )
                # Remove label files and yaml, keep only images
                for root, _dirs, files in os.walk(source_dir):
                    for f in files:
                        if f.endswith(".txt") or f == "dataset.yaml":
                            os.remove(os.path.join(root, f))
            else:
                await broadcast_predict_log(predict_id, "[predict] downloading uploaded images...")
                for img_key in (pred.source_images or []):
                    try:
                        data = s3_client.download_fileobj(img_key)
                        filename = img_key.rsplit("/", 1)[-1]
                        with open(os.path.join(source_dir, filename), "wb") as f:
                            f.write(data.read())
                    except Exception as e:  # noqa: BLE001
                        log.warning(f"skip image {img_key}: {e}")

            # ---- 取权重（统一解析：/export/ 导出产物自动回溯原始 best.pt）----
            from .service import TrainService

            # model_id 是版本行 id（model_repo_id 是仓库 id），不可用仓库 id 冒充版本 id
            storage_path = await TrainService._resolve_model_storage(pred.model_id)
            await broadcast_predict_log(
                predict_id, f"[predict] downloading model {storage_path}...")
            model_data = s3_client.download_fileobj(storage_path)
            model_filename = storage_path.rsplit("/", 1)[-1]
            model_local_path = os.path.join(model_dir, model_filename)
            with open(model_local_path, "wb") as f:
                f.write(model_data.read())

            # ---- 配置名回查训练任务：预测必须与训练用同一套配置 ----
            tk_cfg = hp.get("tk_config") or await resolve_predict_tk_config(pred.model_id)
            if not tk_cfg:
                raise Exception(
                    "TorchKiln 预测找不到产出该模型的训练任务，无法确定配置名")
            # ⚠️ 拿到的是**模型名**（如 yolo11-seg），而作业的 ``config_path`` 只认
            # configs/ 下的**配置路径**。借常驻元数据服务换一次。
            async with TorchKilnClient() as _tk:
                tk_cfg_path = await _tk.resolve_config_path(tk_cfg)

            spec = build_predict_spec(
                config_path=tk_cfg_path,
                weights_path=tkjc.container_path("model", model_filename),
                input_dir=tkjc.container_path("source"),
                params={
                    "Global.conf": float(hp.get("conf", 0.25)),
                    "Global.iou": float(hp.get("iou", 0.45)),
                    "Global.imgsz": int(hp.get("imgsz", 640)),
                },
                resources={"gpu": 1,
                           "gpu_memory_gb": (hp.get("resources") or {}).get(
                               "gpu_memory_gb")},
            )

            # ---- 起 job 容器 -> 提交作业 -> 等终态 ----
            async with gpu_slot(cls, predict_id, hp) as lease:
                container = await tkjc.start_job_container(
                    lease, export_dir, task_kind=cls.task_kind, task_id=predict_id)
                entry = cls._registry.get(predict_id) or {}
                entry.update({"container_id": container.id})
                cls._registry[predict_id] = entry

                await tkjc.wait_ready(
                    lease, broadcast=lambda ln: broadcast_predict_log(predict_id, ln))

                async with TorchKilnClient(base_url=lease.base_url) as client:
                    # 提交作业**之前**确认镜像里的代码身份——
                    # 否则缺端点会表现为 404、缺方法会表现为 AttributeError，
                    # 而后者往往在结果图都写完之后才炸（need_kinds=('predict',)）。
                    await tkjc.assert_image_current(
                        client, need_kinds=("predict",),
                        expect_revision=None)  # 默认自动读本地 HEAD
                    job_id = await cls._submit(client, predict_id, spec)
                    logs_task = await tkjc.stream_logs(
                        client, job_id, "predict",
                        lambda ln: broadcast_predict_log(predict_id, ln))
                    try:
                        final = await tkjc.await_terminal(
                            client, job_id, "predict",
                            is_cancelled=lambda: bool(
                                cls._registry.get(predict_id, {}).get("cancel")),
                            broadcast=lambda ln: broadcast_predict_log(predict_id, ln))
                    finally:
                        logs_task.cancel()
                        await asyncio.gather(logs_task, return_exceptions=True)

                    metrics = await cls._read_metrics(client, job_id)
                    info = await client.get_job(job_id, kind="predict")
                    # 作业的 output_dir 在宿主上就是 <export_dir>/jobs/<job_id>
                    job_dir = os.path.join(
                        export_dir, "jobs", job_id)
                    results_dir = os.path.join(job_dir, "predict_results")

            status = str(final.get("status"))
            err = final.get("error") or (info.get("error") if info else "") or ""
            if status != "succeeded" and not err:
                err = (f"TorchKiln 预测作业失败"
                       f"（exit_reason={final.get('exit_reason')}, "
                       f"exit_code={final.get('exit_code')}）")

            # ---- 收集结果图 -> 上传 RustFS -> 打包 ----
            # 只在成功且未取消时收集：否则会白白把一批图传上对象存储，
            # 而状态最终会被写成 CANCELLED/FAILED。
            was_cancelled = bool(cls._registry.get(predict_id, {}).get("cancel"))
            result_images: list[str] = []
            result_zip_path = None
            if status == "succeeded" and not was_cancelled:
                result_files = collect_result_images(results_dir)
                if result_files:
                    for rel, img_path in result_files:
                        rustfs_key = f"train/predict/{predict_id}/{rel}"
                        with open(img_path, "rb") as img_f:
                            s3_client.upload_fileobj(img_f, rustfs_key)
                        result_images.append(rustfs_key)

                    # 打包（相对 results_dir 保留层级，便于对照输入图定位）
                    zip_path = os.path.join(export_dir, "results.zip")
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        for rel, fp in result_files:
                            zf.write(fp, rel)
                    zip_rustfs_key = f"train/predict/{predict_id}/results.zip"
                    with open(zip_path, "rb") as zf:
                        s3_client.upload_fileobj(zf, zip_rustfs_key)
                    result_zip_path = zip_rustfs_key

                if metrics:
                    await broadcast_predict_log(
                        predict_id,
                        f"[predict] 完成：{metrics.get('images_done')}/"
                        f"{metrics.get('images_total')} 张，"
                        f"耗时 {metrics.get('elapsed_sec')}s，"
                        f"输出 {metrics.get('output_dir')}")

            # ⚠️ success_fields 里**只能有 TrainPredict 真实存在的列**。
            #   它没有 metrics / metrics_log / last_metrics（那是训练与评估的列），
            #   写进去会让 ``_mark_status`` 抛 ``Unconsumed column names`` ——
            #   而那发生在**收尾**阶段，结果是「结果图都齐了、任务却判失败」。
            #   预测的指标摘要改为写进日志（上面已广播）。
            await settle_by_status(
                cls, predict_id,
                status=status, error=err,
                success_fields={
                    "result_images": result_images or None,
                    "result_zip_path": result_zip_path,
                },
                failure_message="predict failed",
            )

        except JobCancelled:
            # 等待 GPU 期间被取消：容器从未起来，不能记失败也不能走收尾。
            # 状态留给 stop_prediction 置 CANCELLED。
            log.info(f"[predict] 任务 {predict_id} 在等待 GPU 期间被取消，未启动容器")
            return

        except Exception as e:
            await mark_failed(cls, predict_id, e, kind="predict")
            # 失败后清理本次导出的临时输出目录（保留日志文件供排查）
            _cleanup_export_dir(export_dir)
        finally:
            # 无论成败都要收摊：容器停掉、GPU 与端口归还，否则单卡机器会被
            # 一次失败的任务永久占死。
            if container is not None:
                with contextlib.suppress(Exception):
                    await stop_container(container.id)
            await gpu_pool.release(predict_id)
            await cleanup_registry(cls, predict_id, None)

    @classmethod
    async def _submit(cls, client: TorchKilnClient, predict_id: int, spec: dict) -> str:
        """提交预测作业。幂等键按预测 id 生成，重试/重启不会重复排队。"""
        created = await client.submit_predict_job(
            spec, idempotency_key=f"aistation-predict-{predict_id}")
        job_id = created["job_id"]
        await cls._remember_job_id(predict_id, job_id)
        await broadcast_predict_log(
            predict_id, f"[predict] 作业已受理 {job_id}（幂等命中="
                        f"{created.get('idempotent_hit')}）")
        return job_id

    @classmethod
    async def _remember_job_id(cls, predict_id: int, job_id: str) -> None:
        """把 job_id 记进 hyperparams，供重启后接管而不是重跑。

        与训练/评估用同一个键名 ``__tk_job_id``：它们指的是同一种东西
        （一个 TorchKiln 作业的引用）。用两个键名会让「按 job_id 恢复」的
        逻辑要判断两次。
        """
        try:
            async with async_db_session.begin() as db:
                row = await db.get(TrainPredict, predict_id)
                if row is None:
                    return
                h = dict(row.hyperparams or {})
                h[JOB_ID_KEY] = job_id
                row.hyperparams = h
        except Exception as e:  # noqa: BLE001
            # 记不住只影响重启后的接管，不该让预测本身失败
            log.warning(f"[predict] 任务 {predict_id} 的 job_id 记录失败: {e}")

    @classmethod
    async def _read_metrics(cls, client: TorchKilnClient, job_id: str) -> dict | None:
        """从指标契约读预测结果。

        契约（``tools/infer/predict_yolo.py`` 写）：一条 ``predict`` 事件
        （总张数 / 成功张数 / 耗时 / 输出目录），外加一条 ``end``。

        ⚠️ 这里**没有**精度指标——预测没有 ground truth。TorchKiln 那边刻意
        只报计数与耗时，所以这一段也不会出现 mAP 字段；哪天出现了，说明
        有人往契约里塞了编造的数据。
        """
        events = await client.metrics(job_id, offset=-1, limit=1000, kind="predict")
        out: dict = {}
        for ev in events:
            if ev.get("type") != "predict":
                continue
            for k in ("images_total", "images_done", "elapsed_sec", "output_dir"):
                if ev.get(k) is not None:
                    out[k] = ev[k]
        return out or None
