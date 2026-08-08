import asyncio
import os
import tempfile
import zipfile
from datetime import datetime

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import get_container_error_tail, pull_image, remove_container, run_container
from .model import TrainFramework, TrainModel, TrainPredict, TrainStatus
from .task_executor import TaskExecutor
from .ws import broadcast_predict_log

DOCKER_IMAGE = "ultralytics/ultralytics:latest"


async def start_prediction_scheduler():
    """PredictExecutor 孤儿恢复循环（此前缺失，Task 4 修复）。"""
    await PredictExecutor.start_recovery_loop()


async def start_prediction(predict_id: int):
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainPredict).where(TrainPredict.id == predict_id).values(
                status=TrainStatus.RUNNING, started_at=datetime.now(), progress=10
            )
        )
    asyncio.create_task(PredictExecutor.run(predict_id))


async def stop_prediction(predict_id: int):
    await PredictExecutor.stop(predict_id)


class PredictExecutor(TaskExecutor):
    name = "predict"
    status_enum = TrainStatus
    model_class = TrainPredict
    _concurrency = 1

    @classmethod
    async def _execute(cls, predict_id: int):
        container_id = None
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

            # Prepare source images
            from app.utils.s3_client import s3_client
            if pred.source_type == "dataset":
                await broadcast_predict_log(predict_id, "[predict] exporting dataset images...")
                from .exporter import prepare_training_data_for_task
                await prepare_training_data_for_task(pred.source_dataset_id, predict_id, framework.value, source_dir)
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
            hp = pred.hyperparams or {}
            conf = hp.get("conf", 0.25)
            iou = hp.get("iou", 0.45)
            imgsz = hp.get("imgsz", 640)
            device = hp.get("device", "0")

            if framework == TrainFramework.PADDLEX:
                # PaddleX OCR 推理：infer_det / infer_rec（用训练产物 .pdparams）
                mode = str(hp.get("mode", "det")).lower()
                if mode == "rec":
                    cfg = "configs/rec/PP-OCRv6/PP-OCRv6_{}_rec.yml".format(hp.get("model_size", "tiny"))
                    infer = "tools/infer_rec.py"
                else:
                    cfg = "configs/det/PP-OCRv6/PP-OCRv6_{}_det.yml".format(hp.get("model_size", "tiny"))
                    infer = "tools/infer_det.py"
                docker_image = "paddlex:latest"
                inner = (
                    f"cd /paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR && "
                    f"python {infer} -c {cfg} "
                    f"-o Global.infer_img=/data "
                    f"-o Global.pretrained_model=/model/{model_filename} "
                    f"-o Global.save_res_path=/output/results.txt "
                    f"-o Global.use_gpu=true "
                    f"-o Global.output_dir=/output"
                )
                cmd = ["bash", "-c", inner]
            else:
                cmd = [
                    "yolo", "predict",
                    f"model=/model/{model_filename}",
                    "source=/data",
                    f"imgsz={imgsz}",
                    f"conf={conf}",
                    f"iou={iou}",
                    "save_txt=True",
                    "save_conf=True",
                    "project=/output",
                    "name=exp",
                ]

            await broadcast_predict_log(predict_id, f"[predict] pulling image {docker_image}...")
            await pull_image(docker_image)
            container = await run_container(
                docker_image, cmd,
                volumes={
                    source_dir: {"bind": "/data", "mode": "ro"},
                    model_dir: {"bind": "/model", "mode": "ro"},
                    output_dir: {"bind": "/output", "mode": "rw"},
                },
                gpu_id=device,
                shm_size="4g" if framework == TrainFramework.PADDLEX else None,
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
                        result_images.append(s3_client.presigned_url(rustfs_key))

                    # Create ZIP
                    zip_path = os.path.join(export_dir, "results.zip")
                    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                        for fp in result_files:
                            zf.write(fp, os.path.relpath(fp, results_base))
                    zip_rustfs_key = f"train/predict/{predict_id}/results.zip"
                    with open(zip_path, "rb") as zf:
                        s3_client.upload_fileobj(zf, zip_rustfs_key)
                    result_zip_path = s3_client.presigned_url(zip_rustfs_key)

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
        finally:
            cls._registry.pop(predict_id, None)
            if container_id:
                await remove_container(container_id)
