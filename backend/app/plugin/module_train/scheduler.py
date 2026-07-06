import asyncio
import os
import tempfile
from datetime import datetime

from sqlalchemy import select, update

from app.core.database import async_db_session
from app.core.logger import log

from .model import TrainTask, TrainStatus, TrainFramework
from .docker_utils import run_container, stop_container, pull_image, follow_container_logs
from .controller import broadcast_log

_running_tasks: dict[int, dict] = {}
_scheduler_task: asyncio.Task | None = None
MAX_CONCURRENT = 1


async def start_scheduler():
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())
        log.info("train scheduler started")


async def _scheduler_loop():
    while True:
        try:
            async with async_db_session() as db:
                result = await db.execute(
                    select(TrainTask).where(TrainTask.status == TrainStatus.PENDING)
                    .order_by(TrainTask.created_time.asc()).limit(MAX_CONCURRENT)
                )
                pending = result.scalars().all()

            for task in pending:
                asyncio.create_task(_execute_training(task.id))
                async with async_db_session.begin() as db:
                    await db.execute(
                        update(TrainTask).where(TrainTask.id == task.id).values(status=TrainStatus.RUNNING)
                    )
        except Exception as e:
            log.error(f"train scheduler error: {e}")

        await asyncio.sleep(1)


async def _build_export_dir(task_id: int) -> str:
    export_dir = os.path.join(tempfile.gettempdir(), "train_output", str(task_id))
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def _build_ultralytics_cmd(hp: dict, data_dir: str, export_dir: str) -> list[str]:
    epochs = hp.get("epochs", 100)
    batch = hp.get("batch", 16)
    lr = hp.get("lr", 0.01)
    model_name = hp.get("model", "yolo11n.pt")
    return ["yolo", "train", f"model={model_name}", "data=/data/dataset.yaml",
            f"epochs={epochs}", f"batch={batch}", f"lr0={lr}", "project=/output", "name=exp"]


def _build_paddlex_cmd(hp: dict, data_dir: str, export_dir: str) -> list[str]:
    epochs = hp.get("epochs", 100)
    batch = hp.get("batch", 16)
    lr = hp.get("lr", 0.01)
    model_name = hp.get("model", "PP-YOLOE")
    return ["paddlex", "--model", model_name, "--data", "/data",
            "--epochs", str(epochs), "--batch", str(batch), "--lr", str(lr),
            "--output", "/output"]


async def _execute_training(task_id: int):
    try:
        async with async_db_session() as db:
            task = await db.get(TrainTask, task_id)
            if not task:
                return

        await broadcast_log(task_id, f"[scheduler] pulling image {task.docker_image}...")
        await pull_image(task.docker_image)

        export_dir = await _build_export_dir(task_id)
        data_dir = os.path.join(export_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        from .exporter import export_dataset
        await export_dataset(task.dataset_id, task.id, task.framework, data_dir)

        if task.framework == TrainFramework.ULTRALYTICS:
            cmd = _build_ultralytics_cmd(task.hyperparams, data_dir, export_dir)
        else:
            cmd = _build_paddlex_cmd(task.hyperparams, data_dir, export_dir)

        container = await run_container(
            task.docker_image, cmd,
            volumes={data_dir: {"bind": "/data", "mode": "rw"},
                     export_dir: {"bind": "/output", "mode": "rw"}},
            gpu_id=task.hyperparams.get("gpu_id", "0"),
        )

        _running_tasks[task_id] = {"container_id": container.id, "cancel": False}

        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainTask).where(TrainTask.id == task_id).values(
                    status=TrainStatus.RUNNING, started_at=datetime.now()
                )
            )

        log_queue = await follow_container_logs(container.id)
        while True:
            line = await log_queue.get()
            if line == "__EOF__":
                break
            await broadcast_log(task_id, line)

        container.reload()
        exit_code = container.attrs["State"]["ExitCode"]

        if _running_tasks.get(task_id, {}).get("cancel"):
            status = TrainStatus.CANCELLED
        elif exit_code == 0:
            status = TrainStatus.SUCCESS
            from .exporter import export_model
            model_info = await export_model(task_id, task.framework, export_dir)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainTask).where(TrainTask.id == task_id).values(
                        model_repo_id=model_info.get("repo_id"), status=status,
                        progress=100, finished_at=datetime.now()
                    )
                )
        else:
            status = TrainStatus.FAILED
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainTask).where(TrainTask.id == task_id).values(
                        status=status, finished_at=datetime.now()
                    )
                )

        _running_tasks.pop(task_id, None)

    except Exception as e:
        log.error(f"training task {task_id} failed: {e}")
        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainTask).where(TrainTask.id == task_id).values(
                    status=TrainStatus.FAILED, error_log=str(e), finished_at=datetime.now()
                )
            )
        _running_tasks.pop(task_id, None)


async def stop_training(task_id: int) -> None:
    entry = _running_tasks.get(task_id)
    if entry:
        entry["cancel"] = True
        await stop_container(entry["container_id"])
