import asyncio
import os
import tempfile
import zipfile
from datetime import datetime

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .concurrency import get_train_semaphore
from .docker_utils import get_container_error_tail, pull_image, remove_container, run_container
from .model import TrainFramework, TrainModel, TrainPredict, TrainStatus
from .task_executor import TaskExecutor
from .ws import broadcast_predict_log

DOCKER_IMAGE = "ultralytics/ultralytics:latest"

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
    """按框架构建预测命令。"""
    conf = hp.get("conf", 0.25)
    iou = hp.get("iou", 0.45)
    imgsz = hp.get("imgsz", 640)
    device = hp.get("device", "0")
    if str(framework).lower() == "paddlex":
        mode = str(hp.get("mode", "det")).lower()
        size = hp.get("model_size", "tiny")
        if size not in ("tiny", "small", "medium"):
            size = "tiny"
        if mode == "rec":
            cfg = f"configs/rec/PP-OCRv6/PP-OCRv6_{size}_rec.yml"
            infer = "tools/infer_rec.py"
        else:
            cfg = f"configs/det/PP-OCRv6/PP-OCRv6_{size}_det.yml"
            infer = "tools/infer_det.py"
        use_gpu = "true" if predict_gpu_id(device) is not None else "false"
        opts = [
            "Global.infer_img=/data",
            f"Global.pretrained_model=/model/{model_filename}",
            "Global.save_res_path=/output/results.txt",
            f"Global.use_gpu={use_gpu}",
            "Global.output_dir=/output",
        ]
        inner = (
            "cd /paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR && "
            f"python {infer} -c {cfg} -o " + " ".join(opts)
        )
        return ["bash", "-c", inner]
    return [
        "yolo", "predict",
        f"model=/model/{model_filename}",
        "source=/data",
        f"imgsz={imgsz}",
        f"conf={conf}",
        f"iou={iou}",
        f"device={device}",
        "save_txt=True", "save_conf=True",
        "project=/output", "name=exp",
    ]


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
            framework = pred.framework or TrainFramework.ULTRALYTICS
            async with async_db_session() as db:
                model_row = await db.get(TrainModel, pred.model_id)
                if model_row and model_row.framework:
                    framework = model_row.framework

            docker_image = DOCKER_IMAGE

            export_dir = os.path.join(tempfile.gettempdir(), "predict_output", str(predict_id))
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
                ocr_rec = (framework == TrainFramework.PADDLEX and str(hp.get("mode", "det")).lower() == "rec")
                await prepare_training_data_for_task(
                    pred.source_dataset_id, predict_id, framework.value, source_dir, ocr_rec=ocr_rec
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

            # Build command by framework
            if framework == TrainFramework.PADDLEX:
                docker_image = "paddlex:latest"

            cmd = build_predict_cmd(framework.value, model_filename, hp)

            await broadcast_predict_log(predict_id, f"[predict] pulling image {docker_image}...")
            await pull_image(docker_image)
            # 全局 GPU 并发上限：与训练/评估共享同一信号量，避免同一张卡被并发抢占
            async with get_train_semaphore():
                # 等待信号量期间可能被取消：启动容器前再检查一次
                if cls._registry.get(predict_id, {}).get("cancel"):
                    return
                container = await run_container(
                    docker_image, cmd,
                    volumes={
                        source_dir: {"bind": "/data", "mode": "ro"},
                        model_dir: {"bind": "/model", "mode": "ro"},
                        output_dir: {"bind": "/output", "mode": "rw"},
                    },
                    gpu_id=predict_gpu_id(device),
                    shm_size="4g" if framework == TrainFramework.PADDLEX else None,
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

                # Collect result images from output dir
                if framework == TrainFramework.PADDLEX:
                    # infer_det/infer_rec 输出 det_results/*.jpg（或直接 output/）
                    results_base = output_dir
                    result_files = []
                    for base in (os.path.join(output_dir, "det_results"), output_dir):
                        if os.path.isdir(base):
                            result_files.extend(
                                os.path.join(base, f) for f in sorted(os.listdir(base))
                                if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp"))
                            )
                else:
                    results_base = os.path.join(output_dir, "exp")
                    result_files = [
                        os.path.join(results_base, f) for f in sorted(os.listdir(results_base))
                        if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp"))
                    ] if os.path.isdir(results_base) else []

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
