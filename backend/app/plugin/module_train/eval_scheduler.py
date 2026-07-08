import asyncio
import os
import re
import tempfile
from datetime import datetime

from sqlalchemy import select, update

from app.core.database import async_db_session
from app.core.logger import log

from .model import TrainEval, TrainStatus, TrainModel
from .docker_utils import pull_image, run_container, follow_container_logs, remove_container
from .ws import broadcast_eval_log

_eval_running: dict[int, dict] = {}
_eval_scheduler_task: asyncio.Task | None = None

DOCKER_IMAGE = "ultralytics/ultralytics:latest"


async def start_evaluation_scheduler():
    global _eval_scheduler_task
    if _eval_scheduler_task is None or _eval_scheduler_task.done():
        _eval_scheduler_task = asyncio.create_task(_eval_scheduler_loop())
        log.info("eval scheduler started")


async def _eval_scheduler_loop():
    while True:
        try:
            async with async_db_session() as db:
                running = await db.execute(
                    select(TrainEval).where(TrainEval.status == TrainStatus.RUNNING)
                )
                for e in running.scalars().all():
                    if e.id not in _eval_running and e.started_at:
                        elapsed = (datetime.now() - e.started_at).total_seconds()
                        if elapsed > 1800:
                            async with async_db_session.begin() as db2:
                                await db2.execute(
                                    update(TrainEval).where(TrainEval.id == e.id).values(
                                        status=TrainStatus.FAILED,
                                        log="评估会话已断开（后端重启或容器丢失）",
                                        finished_at=datetime.now()
                                    )
                                )
        except Exception as e:
            log.error(f"eval scheduler error: {e}")
        await asyncio.sleep(30)


async def start_evaluation(eval_id: int):
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainEval).where(TrainEval.id == eval_id).values(
                status=TrainStatus.RUNNING, started_at=datetime.now()
            )
        )
    asyncio.create_task(_execute_evaluation(eval_id))


async def stop_evaluation(eval_id: int):
    entry = _eval_running.get(eval_id)
    if entry:
        entry["cancel"] = True
        from .docker_utils import stop_container
        await stop_container(entry["container_id"])


async def _execute_evaluation(eval_id: int):
    container_id = None
    try:
        async with async_db_session() as db:
            eval_rec = await db.get(TrainEval, eval_id)
            if not eval_rec:
                return

        await broadcast_eval_log(eval_id, f"[eval] pulling image {DOCKER_IMAGE}...")
        await pull_image(DOCKER_IMAGE)

        export_dir = os.path.join(tempfile.gettempdir(), "eval_output", str(eval_id))
        data_dir = os.path.join(export_dir, "data")
        model_dir = os.path.join(export_dir, "model")
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(model_dir, exist_ok=True)

        # Export evaluation dataset
        from .exporter import prepare_training_data_for_task
        await broadcast_eval_log(eval_id, "[eval] exporting dataset...")
        await prepare_training_data_for_task(eval_rec.eval_dataset_id, eval_id, "ultralytics", data_dir)

        # Download model file from RustFS
        async with async_db_session() as db:
            model_rec = await db.get(TrainModel, eval_rec.model_id or eval_rec.model_repo_id)
            if not model_rec or not model_rec.storage_path:
                raise Exception("model not found or no storage_path")

        await broadcast_eval_log(eval_id, f"[eval] downloading model {model_rec.storage_path}...")
        from app.utils.s3_client import s3_client
        model_data = s3_client.download_fileobj(model_rec.storage_path)
        model_filename = model_rec.storage_path.rsplit("/", 1)[-1]
        model_local_path = os.path.join(model_dir, model_filename)
        with open(model_local_path, "wb") as f:
            f.write(model_data.read())

        # Build command
        hp = eval_rec.hyperparams or {}
        imgsz = hp.get("imgsz", 640)
        batch = hp.get("batch", 16)
        conf = hp.get("conf", 0.001)
        iou = hp.get("iou", 0.6)
        device = hp.get("device", "0")

        cmd = [
            "yolo", "val",
            f"model=/model/{model_filename}",
            "data=/data/dataset.yaml",
            f"imgsz={imgsz}",
            f"batch={batch}",
            f"conf={conf}",
            f"iou={iou}",
        ]

        container = await run_container(
            DOCKER_IMAGE, cmd,
            volumes={
                data_dir: {"bind": "/data", "mode": "rw"},
                model_dir: {"bind": "/model", "mode": "ro"},
            },
            gpu_id=device,
        )
        container_id = container.id
        _eval_running[eval_id] = {"container_id": container_id, "cancel": False}

        log_queue = await follow_container_logs(container_id)
        log_file = os.path.join(export_dir, "eval.log")

        metrics: dict = {}
        with open(log_file, "w", encoding="utf-8") as lf:
            while True:
                line = await log_queue.get()
                if line == "__EOF__":
                    break
                lf.write(line + "\n")
                lf.flush()
                await broadcast_eval_log(eval_id, line)

                # Parse YOLO val metrics: "all" line
                if re.match(r"^\s+all\s+", line):
                    parts = line.strip().split()
                    if len(parts) >= 7:
                        metrics = {
                            "precision": float(parts[3]) if parts[3] else 0,
                            "recall": float(parts[4]) if parts[4] else 0,
                            "map50": float(parts[5]) if parts[5] else 0,
                            "map5095": float(parts[6]) if parts[6] else 0,
                        }

                # Parse per-class metrics
                m = re.match(r"^\s+(\d+)\s+", line)
                if m:
                    parts = line.strip().split()
                    if len(parts) >= 7:
                        cls_id = int(parts[0])
                        if "classes" not in metrics:
                            metrics["classes"] = {}
                        metrics["classes"][str(cls_id)] = {
                            "precision": float(parts[3]) if parts[3] else 0,
                            "recall": float(parts[4]) if parts[4] else 0,
                            "map50": float(parts[5]) if parts[5] else 0,
                            "map5095": float(parts[6]) if parts[6] else 0,
                        }

        loop = asyncio.get_event_loop()
        exit_code = await loop.run_in_executor(None, lambda: container.wait(timeout=600)["StatusCode"])

        if _eval_running.get(eval_id, {}).get("cancel"):
            await remove_container(container_id)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainEval).where(TrainEval.id == eval_id).values(
                        status=TrainStatus.CANCELLED, finished_at=datetime.now()
                    )
                )
        elif exit_code == 0:
            await remove_container(container_id)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainEval).where(TrainEval.id == eval_id).values(
                        status=TrainStatus.SUCCESS,
                        metrics=metrics or None,
                        finished_at=datetime.now(),
                    )
                )
        else:
            error_msg = ""
            try:
                err_logs = container.logs(stdout=False, stderr=True, tail=50).decode("utf-8", errors="replace")
                if err_logs:
                    error_msg = err_logs.strip()
            except Exception:
                pass
            await remove_container(container_id)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainEval).where(TrainEval.id == eval_id).values(
                        status=TrainStatus.FAILED, log=error_msg or "eval failed",
                        finished_at=datetime.now(),
                    )
                )

    except Exception as e:
        log.error(f"eval task {eval_id} failed: {e}")
        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainEval).where(TrainEval.id == eval_id).values(
                    status=TrainStatus.FAILED, log=str(e), finished_at=datetime.now()
                )
            )
    finally:
        _eval_running.pop(eval_id, None)
        if container_id:
            await remove_container(container_id)
