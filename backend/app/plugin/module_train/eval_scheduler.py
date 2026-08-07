import asyncio
import json
import os
import re
import tempfile
from datetime import datetime

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import get_container_error_tail, pull_image, remove_container, run_container
from .model import TrainEval, TrainFramework, TrainModel, TrainStatus
from .task_executor import TaskExecutor
from .ws import broadcast_eval_log

DOCKER_IMAGE = "ultralytics/ultralytics:latest"

# PaddleX OCR 独立 eval 脚本（挂载容器 /scripts/paddlex_eval.py，det/rec 通用）。
# 加载 best.pdparams + Eval dataset，跑 program.eval，输出 EVAL_METRIC_JSON。
_PADDLEX_EVAL_SCRIPT = r'''
import sys, os, json
__dir__ = os.path.dirname(os.path.abspath(__file__))
_POCR_DIR = "/paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR"
sys.path.append(__dir__)
sys.path.insert(0, _POCR_DIR)
sys.path.insert(0, os.path.abspath(os.path.join(_POCR_DIR, "..")))

import paddle
from ppocr.data import build_dataloader
from ppocr.modeling.architectures import build_model
from ppocr.postprocess import build_post_process
from ppocr.metrics import build_metric
from ppocr.utils.save_load import load_model
import tools.program as program

config, device, logger, vdl_writer = program.preprocess(is_train=False)
model = build_model(config["Architecture"])
load_model(config, model, model_type=config["Architecture"]["model_type"])
valid_dataloader = build_dataloader(config, "Eval", device, logger)
post_process_class = build_post_process(config["PostProcess"], config["Global"])
eval_class = build_metric(config["Metric"])
metric = program.eval(
    model, valid_dataloader, post_process_class, eval_class,
    model_type=config["Architecture"]["model_type"],
)
print("EVAL_METRIC_JSON " + json.dumps(metric, ensure_ascii=False), flush=True)
'''


async def start_evaluation_scheduler():
    await EvalExecutor.start_recovery_loop()


async def start_evaluation(eval_id: int):
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainEval).where(TrainEval.id == eval_id).values(
                status=TrainStatus.RUNNING, started_at=datetime.now(), progress=10
            )
        )
    asyncio.create_task(EvalExecutor.run(eval_id))


async def stop_evaluation(eval_id: int):
    await EvalExecutor.stop(eval_id)


class EvalExecutor(TaskExecutor):
    name = "eval"
    status_enum = TrainStatus
    model_class = TrainEval
    _concurrency = 1

    @classmethod
    async def _execute(cls, eval_id: int):
        container_id = None
        try:
            async with async_db_session() as db:
                eval_rec = await db.get(TrainEval, eval_id)
                if not eval_rec:
                    return

            # 有效框架：create_eval 未持久化 framework 时，从模型版本推断
            framework = eval_rec.framework or TrainFramework.ULTRALYTICS
            async with async_db_session() as db:
                model_row = await db.get(TrainModel, eval_rec.model_id)
                if model_row and model_row.framework:
                    framework = model_row.framework

            docker_image = DOCKER_IMAGE

            export_dir = os.path.join(tempfile.gettempdir(), "eval_output", str(eval_id))
            data_dir = os.path.join(export_dir, "data")
            model_dir = os.path.join(export_dir, "model")
            os.makedirs(data_dir, exist_ok=True)
            os.makedirs(model_dir, exist_ok=True)

            # Export evaluation dataset
            from .exporter import prepare_training_data_for_task
            await broadcast_eval_log(eval_id, "[eval] exporting dataset...")
            eval_ocr_rec = (framework == TrainFramework.PADDLEX
                            and str((eval_rec.hyperparams or {}).get("mode", "det")).lower() == "rec")
            await prepare_training_data_for_task(
                eval_rec.eval_dataset_id, eval_id, framework.value, data_dir,
                ocr_rec=eval_ocr_rec,
            )

            # Download model file from RustFS（统一解析：/export/ 导出产物自动回溯原始 best.pt）
            from .service import TrainService
            # model_id 是版本行 id（model_repo_id 是仓库 id），不可用仓库 id 冒充版本 id
            storage_path = await TrainService._resolve_model_storage(eval_rec.model_id)

            await broadcast_eval_log(eval_id, f"[eval] downloading model {storage_path}...")
            from app.utils.s3_client import s3_client
            model_data = s3_client.download_fileobj(storage_path)
            model_filename = storage_path.rsplit("/", 1)[-1]
            model_local_path = os.path.join(model_dir, model_filename)
            with open(model_local_path, "wb") as f:
                f.write(model_data.read())

            # Build command by framework
            hp = eval_rec.hyperparams or {}
            imgsz = hp.get("imgsz", 640)
            batch = hp.get("batch", 16)
            conf = hp.get("conf", 0.001)
            iou = hp.get("iou", 0.6)
            device = hp.get("device", "0")

            if framework == TrainFramework.PADDLEX:
                # PaddleX OCR eval：容器内脚本加载 best.pdparams 跑 program.eval（det/rec）
                mode = str(hp.get("mode", "det")).lower()
                size = str(hp.get("model_size", "tiny"))
                if size not in ("tiny", "small", "medium"):
                    size = "tiny"
                cfg = (
                    f"configs/det/PP-OCRv6/PP-OCRv6_{size}_det.yml"
                    if mode == "det" else f"configs/rec/PP-OCRv6/PP-OCRv6_{size}_rec.yml"
                )
                eval_script = os.path.join(export_dir, "paddlex_eval.py")
                with open(eval_script, "w", encoding="utf-8") as f:
                    f.write(_PADDLEX_EVAL_SCRIPT)
                docker_image = "paddlex:latest"
                inner = (
                    f"cd /paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR && "
                    f"PYTHONPATH=/paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR "
                    f"python /scripts/paddlex_eval.py -c {cfg} -o "
                    f"Global.pretrained_model=/model/{model_filename} "
                    f"Global.save_model_dir=/output "
                    f"Eval.dataset.data_dir=/data/{mode}/dataset "
                    f"'Eval.dataset.label_file_list=[\"/data/{mode}/dataset/val.txt\"]' "
                    f"Eval.loader.num_workers=0"
                )
                cmd = ["bash", "-c", inner]
            else:
                cmd = [
                    "yolo", "val",
                    f"model=/model/{model_filename}",
                    "data=/data/dataset.yaml",
                    f"imgsz={imgsz}",
                    f"batch={batch}",
                    f"conf={conf}",
                    f"iou={iou}",
                ]

            await broadcast_eval_log(eval_id, f"[eval] pulling image {docker_image}...")
            await pull_image(docker_image)
            volumes = {
                data_dir: {"bind": "/data", "mode": "rw"},
                model_dir: {"bind": "/model", "mode": "ro"},
            }
            if framework == TrainFramework.PADDLEX:
                volumes[export_dir] = {"bind": "/scripts", "mode": "ro"}
                volumes[os.path.join(export_dir, "output")] = {"bind": "/output", "mode": "rw"}
                os.makedirs(os.path.join(export_dir, "output"), exist_ok=True)
            container = await run_container(
                docker_image, cmd,
                volumes=volumes,
                gpu_id=device,
                shm_size="4g" if framework == TrainFramework.PADDLEX else None,
            )
            container_id = container.id
            entry = cls._registry.get(eval_id) or {}
            entry.update({"container_id": container_id})
            cls._registry[eval_id] = entry

            metrics: dict = {}

            def _parse_paddlex_metrics(line: str) -> dict | None:
                """解析 PaddleX eval 脚本输出的 EVAL_METRIC_JSON 行。"""
                if "EVAL_METRIC_JSON" in line:
                    try:
                        data = json.loads(line.split("EVAL_METRIC_JSON", 1)[1].strip())
                        metrics.update(data)
                        return dict(metrics)
                    except Exception:
                        return None
                return None

            def _parse_val_metrics(line: str) -> dict | None:
                """解析 YOLO val 输出：all 汇总行与 per-class 行（累积到 metrics）。"""
                if re.match(r"^\s+all\s+", line):
                    parts = line.strip().split()
                    if len(parts) >= 7:
                        metrics.update({
                            "precision": float(parts[3]) if parts[3] else 0,
                            "recall": float(parts[4]) if parts[4] else 0,
                            "map50": float(parts[5]) if parts[5] else 0,
                            "map5095": float(parts[6]) if parts[6] else 0,
                        })
                        return dict(metrics)
                m = re.match(r"^\s+(\d+)\s+", line)
                if m:
                    parts = line.strip().split()
                    if len(parts) >= 7:
                        cls_id = int(parts[0])
                        metrics.setdefault("classes", {})[str(cls_id)] = {
                            "precision": float(parts[3]) if parts[3] else 0,
                            "recall": float(parts[4]) if parts[4] else 0,
                            "map50": float(parts[5]) if parts[5] else 0,
                            "map5095": float(parts[6]) if parts[6] else 0,
                        }
                        return dict(metrics)
                return None

            await cls.follow_logs(
                container_id,
                os.path.join(export_dir, "eval.log"),
                lambda line: broadcast_eval_log(eval_id, line),
                _parse_paddlex_metrics if framework == TrainFramework.PADDLEX else _parse_val_metrics,
            )
            exit_code = await cls._get_exit_code(container)

            current_metrics = metrics or None

            if cls._registry.get(eval_id, {}).get("cancel"):
                await remove_container(container_id)
                await cls._mark_status(eval_id, TrainStatus.CANCELLED, finished_at=datetime.now(), progress=100)
            elif exit_code == 0:
                await remove_container(container_id)
                await cls._mark_status(eval_id, TrainStatus.SUCCESS,
                                       metrics=current_metrics,
                                       metrics_log=[current_metrics] if current_metrics else None,
                                       best_metrics=current_metrics,
                                       last_metrics=current_metrics,
                                       finished_at=datetime.now(),
                                       progress=100)
            else:
                error_msg = (await get_container_error_tail(container_id)).strip()
                await remove_container(container_id)
                await cls._mark_status(eval_id, TrainStatus.FAILED,
                                       log=error_msg or "eval failed",
                                       error_log=error_msg or "eval failed",
                                       finished_at=datetime.now(), progress=100)

        except Exception as e:
            log.error(f"eval task {eval_id} failed: {e}")
            await cls._mark_status(eval_id, TrainStatus.FAILED, log=str(e), finished_at=datetime.now())
        finally:
            cls._registry.pop(eval_id, None)
            if container_id:
                await remove_container(container_id)
