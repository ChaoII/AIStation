import asyncio
import os
import zipfile
from datetime import datetime

from sqlalchemy import update

from app.config.setting import settings
from app.core.database import async_db_session
from app.core.logger import log

from .concurrency import get_train_semaphore
from .docker_utils import get_container_error_tail, pull_image, remove_container, run_container
from .gpu_pool import gpu_lease
from .model import TrainFramework, TrainModel, TrainPredict, TrainStatus
from .paths import work_dir
from .retired import ensure_active
from .task_executor import TaskExecutor
from .ws import broadcast_predict_log

#: 自研平台的推理镜像（镜像内已装好 torch+CUDA 与 tkiln CLI）
DOCKER_IMAGE = "torchkiln:0.1.0"

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


def predict_gpu_id(device) -> str | None:
    """GPU 设备 id；cpu/空 → None（不请求 GPU）。"""
    if device is None:
        return None
    d = str(device).strip().lower()
    if d in ("", "cpu"):
        return None
    return str(device)


def build_predict_cmd(framework: str, model_filename: str, hp: dict) -> list[str]:
    """构建 ``tkiln predict`` 命令。

    只剩自研平台一条通路（Ultralytics / PaddleX 已退场，由 ``ensure_active``
    在入口挡住）。保留 ``framework`` 形参是为了让调用点不必为退场再改一轮签名，
    这里的断言顺带把"传了已退场框架"这类错误在开发期就暴露出来。
    """
    from .framework_utils import framework_value

    fw = framework_value(framework)
    if fw != "torchkiln":
        raise ValueError(
            f"build_predict_cmd 只支持 torchkiln，收到 {fw!r}（已退场框架）")

    conf = hp.get("conf", 0.25)
    iou = hp.get("iou", 0.45)
    imgsz = hp.get("imgsz", 640)
    device = hp.get("device", "0")
    # 配置由训练任务带下来（model 名）
    model_cfg = hp.get("tk_config") or hp.get("model") or ""
    if not model_cfg:
        # 兜底：用训练任务的 hyperparams.model（调用方应透传）
        model_cfg = hp.get("tk_model") or ""
    opts = [
        f"Global.pretrained_model=/model/{model_filename}",
        "Global.save_model_dir=/output",
        f"Global.imgsz={imgsz}",
        f"Global.conf={conf}",
        f"Global.iou={iou}",
        f"Global.device={device}",
        "Global.infer_dir=/data",
    ]
    return ["tkiln", "predict", "-c", str(model_cfg), "-o"] + opts


async def resolve_predict_tk_config(model_id: int) -> str | None:
    """反查产出该模型版本的**训练任务**，取其 TorchKiln 配置名。

    预测必须用与训练一致的配置（架构/imgsz/后处理都对不上就没有可比性），
    所以这里不猜、不让用户手填——直接回到训练任务要。
    """
    from sqlalchemy import desc, select

    from .framework_utils import framework_value
    from .model import TrainModel, TrainTask

    async with async_db_session() as db:
        model_row = await db.get(TrainModel, model_id)
        repo_id = model_row.repo_id if model_row else None
        if not repo_id:
            return None
        task = (await db.execute(
            select(TrainTask).where(TrainTask.model_repo_id == repo_id)
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
        container_id = None
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

            docker_image = DOCKER_IMAGE

            export_dir = work_dir("predict_output", predict_id)
            source_dir = os.path.join(export_dir, "source")
            output_dir = os.path.join(export_dir, "output")
            model_dir = os.path.join(export_dir, "model")
            os.makedirs(source_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(model_dir, exist_ok=True)

            # 超参需在数据导出前取得，供 mode/device 使用
            hp = pred.hyperparams or {}
            device = hp.get("device", "0")

            # Prepare source images
            from app.utils.s3_client import s3_client
            if pred.source_type == "dataset":
                await broadcast_predict_log(predict_id, "[predict] exporting dataset images...")
                from .exporter import prepare_training_data_for_task
                await prepare_training_data_for_task(
                    pred.source_dataset_id, predict_id, framework.value, source_dir
                )
                # Remove label files and yaml, keep only images
                for root, _, files in os.walk(source_dir):
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
                    except Exception as e:
                        log.warning(f"skip image {img_key}: {e}")

            # Download model（统一解析：/export/ 导出产物自动回溯原始 best.pt）
            from .service import TrainService
            # model_id 是版本行 id（model_repo_id 是仓库 id），不可用仓库 id 冒充版本 id
            storage_path = await TrainService._resolve_model_storage(pred.model_id)

            await broadcast_predict_log(predict_id, f"[predict] downloading model {storage_path}...")
            model_data = s3_client.download_fileobj(storage_path)
            model_filename = storage_path.rsplit("/", 1)[-1]
            model_local_path = os.path.join(model_dir, model_filename)
            with open(model_local_path, "wb") as f:
                f.write(model_data.read())

            # 自研平台的推理镜像（镜像内已装好 torch+CUDA 与 tkiln CLI）
            docker_image = hp.get("docker_image") or "torchkiln:0.1.0"

            # 配置名回查训练任务：预测必须与训练用同一套配置
            tk_cfg = hp.get("tk_config") or await resolve_predict_tk_config(pred.model_id)
            if not tk_cfg:
                raise Exception(
                    "TorchKiln 预测找不到产出该模型的训练任务，无法确定配置名")
            # ⚠️ 上面拿到的是**模型名**（如 yolo11-seg），而 `tkiln predict -c`
            # 只认 configs/ 下的**配置路径**。借常驻元数据服务换一次，否则容器里
            # 会报「省略 <task> 时必须用 -c <config> 指定配置」。
            from .torchkiln_client import TorchKilnClient
            async with TorchKilnClient() as _tk:
                tk_cfg = await _tk.resolve_config_path(tk_cfg)
            hp = {**hp, "tk_config": tk_cfg, "model": tk_cfg}

            cmd = build_predict_cmd(framework.value, model_filename, hp)

            await broadcast_predict_log(predict_id, f"[predict] pulling image {docker_image}...")
            await pull_image(docker_image)
            # 全局 GPU 并发上限：与训练/评估共享同一信号量，避免同一张卡被并发抢占。
            # ⚠️ 信号量**只认本进程里排队的任务**，看不见别的框架、更看不见平台外
            #   占着卡的人——而训练走的是 gpu_pool（Redis + NVML）。两套排队互不知情
            #   必然撞卡，所以这里在信号量之后**再**向 gpu_pool 租一张够显存的卡。
            need_mem_gb = float((hp.get("resources") or {}).get("gpu_memory_gb")
                                or settings.TORKILN_GPU_MIN_FREE_GB)
            async with get_train_semaphore(), gpu_lease(predict_id, need_mem_gb) as lease:
                # 等待期间可能被取消：启动容器前再检查一次
                if cls._registry.get(predict_id, {}).get("cancel"):
                    return
                container = await run_container(
                    docker_image, cmd,
                    volumes={
                        source_dir: {"bind": "/data", "mode": "ro"},
                        model_dir: {"bind": "/model", "mode": "ro"},
                        output_dir: {"bind": "/output", "mode": "rw"},
                    },
                    gpu_id=lease.device_ids or predict_gpu_id(device),
                    shm_size="4g",
                    labels={"aistation.task_kind": cls.task_kind, "aistation.task_id": str(predict_id)},
                )
                container_id = container.id
                entry = cls._registry.get(predict_id) or {}
                entry.update({"container_id": container_id})
                cls._registry[predict_id] = entry

                await cls.follow_logs(
                    container_id,
                    os.path.join(export_dir, "predict.log"),
                    lambda line: broadcast_predict_log(predict_id, line),
                )
                exit_code = await cls._get_exit_code(container)

            result_images = []
            result_zip_path = None

            if cls._registry.get(predict_id, {}).get("cancel"):
                await remove_container(container_id)
                await cls._mark_status(predict_id, TrainStatus.CANCELLED, finished_at=datetime.now(), progress=100)
            elif exit_code == 0:
                await remove_container(container_id)

                # Collect result images from output dir.
                # tkiln predict 把可视化结果写在 save_model_dir 下的常见子目录里；
                # 逐个找，找到就用该子目录作为打包的相对根（这样 zip 里不带多层前缀）。
                # ⚠️ 原来的实现是「找到文件后反而只去看 exp/」，结果落在 vis/ 或
                # output/ 时会把已找到的文件丢掉、只认 exp/——那是条会静默返回空
                # 结果的路径。现在改成记住实际命中的那个子目录。
                results_base = output_dir
                result_files = []
                for sub in ("output", "results", "vis", "exp"):
                    base = os.path.join(output_dir, sub)
                    if not os.path.isdir(base):
                        continue
                    found = [os.path.join(base, f) for f in sorted(os.listdir(base))
                             if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp"))]
                    if found:
                        results_base, result_files = base, found
                        break
                if not result_files:
                    result_files = [
                        os.path.join(output_dir, f) for f in sorted(os.listdir(output_dir))
                        if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp"))
                    ]

                if result_files:
                    for img_path in result_files:
                        f = os.path.basename(img_path)
                        rustfs_key = f"train/predict/{predict_id}/{f}"
                        with open(img_path, "rb") as img_f:
                            s3_client.upload_fileobj(img_f, rustfs_key)
                        result_images.append(rustfs_key)

                    # Create ZIP
                    zip_path = os.path.join(export_dir, "results.zip")
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        for fp in result_files:
                            zf.write(fp, os.path.relpath(fp, results_base))
                    zip_rustfs_key = f"train/predict/{predict_id}/results.zip"
                    with open(zip_path, "rb") as zf:
                        s3_client.upload_fileobj(zf, zip_rustfs_key)
                    result_zip_path = zip_rustfs_key

                await cls._mark_status(predict_id, TrainStatus.SUCCESS,
                                       result_images=result_images or None,
                                       result_zip_path=result_zip_path,
                                       finished_at=datetime.now(),
                                       progress=100)
            else:
                error_msg = (await get_container_error_tail(container_id)).strip()
                await remove_container(container_id)
                await cls._mark_status(predict_id, TrainStatus.FAILED,
                                       log=error_msg or "predict failed",
                                       finished_at=datetime.now(), progress=100)

        except Exception as e:
            log.error(f"predict task {predict_id} failed: {e}")
            await cls._mark_status(predict_id, TrainStatus.FAILED, log=str(e), finished_at=datetime.now())
            # 失败后清理本次导出的临时输出目录（保留日志文件供排查）
            _cleanup_export_dir(export_dir)
        finally:
            cls._registry.pop(predict_id, None)
            if container_id:
                await remove_container(container_id)
