import asyncio
import os
import tempfile
from datetime import datetime

import requests
from sqlalchemy import select, update

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import (
    follow_container_logs,
    pull_image,
    remove_container,
    run_container,
    stop_container,
)
from .model import TrainFramework, TrainStatus, TrainTask
from .ws import broadcast_log

_running_tasks: dict[int, dict] = {}
_scheduler_task: asyncio.Task | None = None
MAX_CONCURRENT = 1

MODELS_CACHE_DIR = os.path.join(tempfile.gettempdir(), "train_output", ".models_cache").replace("\\", "/")
_MODEL_DOWNLOAD_BASE = "https://github.com/ultralytics/assets/releases/latest/download"
_MODEL_MIRROR = os.environ.get("MODEL_MIRROR", "")  # e.g. https://ghproxy.com/


def _send_notify(user_id: int, title: str, content: str | None, type_: str, module: str, module_id: int | None):
    """Fire-and-forget notification; non-blocking on best-effort basis."""
    try:
        from app.api.v1.module_system.notification.service import NotificationService
        import asyncio
        asyncio.ensure_future(NotificationService.create_notification(
            user_id=user_id, title=title, content=content,
            type=type_, module=module, module_id=module_id,
        ))
    except Exception:
        pass


def _ensure_model_file(model_name: str) -> str:
    name = model_name if model_name.endswith(".pt") else f"{model_name}.pt"
    dst = os.path.join(MODELS_CACHE_DIR, name)
    if os.path.isfile(dst) and os.path.getsize(dst) > 5000000:
        return dst
    os.makedirs(MODELS_CACHE_DIR, exist_ok=True)
    url = f"{_MODEL_DOWNLOAD_BASE}/{name}"
    if _MODEL_MIRROR:
        url = _MODEL_MIRROR.rstrip("/") + "/" + url
    tmp = dst + ".part"
    log.info(f"downloading model {name} ...")
    try:
        r = requests.get(url, stream=True, timeout=(10, 120))
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
        if downloaded < 5000000:
            raise Exception(f"download too small: {downloaded} bytes")
        os.replace(tmp, dst)
        log.info(f"model {name} downloaded ({downloaded} bytes)")
    except Exception as e:
        log.error(f"failed to download model {name}: {e}")
        if os.path.isfile(tmp):
            os.remove(tmp)
    return dst


async def start_scheduler():
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())
        log.info("train scheduler started")


async def _scheduler_loop():
    """维护循环：清理孤儿任务 + 触发定时训练"""
    while True:
        try:
            # Check for due training schedules
            try:
                from .schedule_service import ScheduleService
                from .schedule_model import TrainScheduleModel
                due = await ScheduleService.get_due_schedules()
                for s in due:
                    try:
                        from .service import TrainService
                        # Create a mock auth object - schedules run as superuser
                        class _ScheduleAuth:
                            class user:
                                id = s.created_id or 1
                        hp = s.hyperparams or {}
                        task_data = type("data", (), {
                            "name": f"[定时] {s.name}",
                            "dataset_id": s.dataset_id,
                            "annotation_task_id": s.annotation_task_id,
                            "framework": s.framework,
                            "hyperparams": hp,
                        })()
                        result = await TrainService.create_task(task_data, _ScheduleAuth())
                        new_id = result.get("id")
                        if new_id:
                            await start_training(new_id)
                        async with async_db_session.begin() as db:
                            await db.execute(
                                update(TrainScheduleModel).where(TrainScheduleModel.id == s.id).values(
                                    last_run_at=datetime.now(), last_task_id=new_id
                                )
                            )
                        log.info(f"scheduled training triggered: schedule={s.id} task={new_id}")
                    except Exception as e:
                        log.error(f"scheduled training failed for schedule {s.id}: {e}")
            except Exception as e:
                log.error(f"schedule check error: {e}")

            # Orphan task cleanup
            async with async_db_session() as db:
                running = await db.execute(
                    select(TrainTask).where(TrainTask.status == TrainStatus.RUNNING)
                )
                for t in running.scalars().all():
                    if t.id not in _running_tasks and t.started_at:
                        elapsed = (datetime.now() - t.started_at).total_seconds()
                        if elapsed > 1800:
                            async with async_db_session.begin() as db2:
                                await db2.execute(
                                    update(TrainTask).where(TrainTask.id == t.id).values(
                                        status=TrainStatus.FAILED,
                                        error_log="训练会话已断开（后端重启或容器丢失）",
                                        finished_at=datetime.now()
                                    )
                                )
        except Exception as e:
            log.error(f"train scheduler error: {e}")
        await asyncio.sleep(30)


async def _build_export_dir(task_id: int) -> str:
    export_dir = os.path.join(tempfile.gettempdir(), "train_output", str(task_id))
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def _build_ultralytics_cmd(hp: dict, data_dir: str, export_dir: str, task_type: str = "detection") -> list[str]:
    epochs = hp.get("epochs", 100)
    batch = hp.get("batch", 16)
    lr = hp.get("lr", 0.01)
    model_name = hp.get("model", "yolo11n.pt")
    # Auto-select OBB model for rotated_detection tasks
    if task_type == "rotated_detection" and "-obb" not in model_name:
        base = model_name.replace(".pt", "")
        model_name = f"{base}-obb.pt"
    return ["yolo", "train", f"model=/models/{model_name}", "data=/data/dataset.yaml",
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
    container_id = None
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

        from .exporter import prepare_training_data_for_task
        data_train_ratio = task.hyperparams.get("train_ratio", 0.8)
        await prepare_training_data_for_task(task.dataset_id, task.id, task.framework, data_dir, annotation_task_id=task.annotation_task_id, train_ratio=data_train_ratio)

        if task.framework == TrainFramework.ULTRALYTICS:
            # Determine task_type for model selection (OBB models need -obb suffix)
            task_type = "detection"
            if task.annotation_task_id:
                from app.api.v1.module_annotation.task.model import AnnotationTaskModel
                async with async_db_session() as db:
                    ann_task = await db.get(AnnotationTaskModel, task.annotation_task_id)
                    if ann_task:
                        task_type = ann_task.task_type
            cmd = _build_ultralytics_cmd(task.hyperparams, data_dir, export_dir, task_type)
        else:
            cmd = _build_paddlex_cmd(task.hyperparams, data_dir, export_dir)

        # Pre-download model weights so container doesn't fetch from internet
        if task.framework == TrainFramework.ULTRALYTICS:
            model_arg = next((a for a in cmd if a.startswith("model=")), "model=yolo11n.pt")
            model_name = model_arg.split("=", 1)[1].lstrip("/models/")
            _ensure_model_file(model_name)

        os.makedirs(MODELS_CACHE_DIR, exist_ok=True)
        container = await run_container(
            task.docker_image, cmd,
            volumes={data_dir: {"bind": "/data", "mode": "rw"},
                     export_dir: {"bind": "/output", "mode": "rw"},
                     MODELS_CACHE_DIR: {"bind": "/models", "mode": "ro"}},
            gpu_id=task.hyperparams.get("gpu_id", "0"),
        )
        container_id = container.id
        _running_tasks[task_id] = {"container_id": container_id, "cancel": False}

        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainTask).where(TrainTask.id == task_id).values(
                    status=TrainStatus.RUNNING, started_at=datetime.now()
                )
            )

        log_queue = await follow_container_logs(container_id)
        log_file = os.path.join(export_dir, "train.log")
        import re

        def _parse_epoch(line: str) -> dict | None:
            m = re.search(r"^\s*(\d+)/(\d+)\s+", line)
            if m:
                parts = line.strip().split()
                met = {"epoch": int(m.group(1)), "total_epochs": int(m.group(2))}
                for i, p in enumerate(parts):
                    if re.match(r"^[\d.]+[GM]$", p):
                        if i + 1 < len(parts):
                            try: met["box_loss"] = float(parts[i + 1])
                            except ValueError: pass
                        if i + 2 < len(parts):
                            try: met["cls_loss"] = float(parts[i + 2])
                            except ValueError: pass
                        if i + 3 < len(parts):
                            try: met["dfl_loss"] = float(parts[i + 3])
                            except ValueError: pass
                        break
                return met
            if re.match(r"^\s+all\s+", line):
                parts = line.strip().split()
                if len(parts) >= 7:
                    return {"epoch": -1,
                            "precision": float(parts[3]) if parts[3] else 0,
                            "recall": float(parts[4]) if parts[4] else 0,
                            "map50": float(parts[5]) if parts[5] else 0,
                            "map5095": float(parts[6]) if parts[6] else 0}
            return None

        metrics_log: list[dict] = []
        cur_epoch: dict | None = None

        with open(log_file, "w", encoding="utf-8") as lf:
            while True:
                line = await log_queue.get()
                if line == "__EOF__":
                    break
                lf.write(line + "\n")
                lf.flush()
                await broadcast_log(task_id, line)

                parsed = _parse_epoch(line)
                if parsed:
                    if parsed.get("epoch") == -1:
                        if cur_epoch is not None:
                            cur_epoch.update(parsed)
                    else:
                        if cur_epoch is not None and cur_epoch.get("epoch", 0) > 0:
                            metrics_log.append(dict(cur_epoch))
                        cur_epoch = parsed
                        pct = int(parsed["epoch"] / parsed.get("total_epochs", 100) * 100)
                        try:
                            async with async_db_session.begin() as db:
                                await db.execute(
                                    update(TrainTask).where(TrainTask.id == task_id).values(progress=pct)
                                )
                        except Exception as e:
                            log.error(f"progress update failed: {e}")

        if cur_epoch is not None and cur_epoch.get("epoch", 0) > 0:
            metrics_log.append(dict(cur_epoch))

        best_metrics = None
        last_metrics = None
        if metrics_log:
            last_metrics = metrics_log[-1]
            valid = [m for m in metrics_log if m.get("map50") is not None]
            best_metrics = max(valid, key=lambda m: m["map50"]) if valid else last_metrics

        loop = asyncio.get_event_loop()
        exit_code = await loop.run_in_executor(None, lambda: container.wait(timeout=600)["StatusCode"])

        if _running_tasks.get(task_id, {}).get("cancel"):
            await remove_container(container_id)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainTask).where(TrainTask.id == task_id).values(
                        status=TrainStatus.CANCELLED, finished_at=datetime.now()
                    )
                )
        elif exit_code == 0:
            await remove_container(container_id)
            from .exporter import export_model
            model_info = await export_model(task_id, task.framework, export_dir)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainTask).where(TrainTask.id == task_id).values(
                        model_repo_id=model_info.get("repo_id"), status=TrainStatus.SUCCESS,
                        progress=100, finished_at=datetime.now(),
                        metrics_log=metrics_log or None,
                        best_metrics=best_metrics, last_metrics=last_metrics,
                    )
                )
            if hasattr(task, "created_id") and task.created_id:
                _send_notify(task.created_id, f"训练完成: {task.name}", f"任务已成功完成，模型已保存", "training_complete", "train", task_id)
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
                    update(TrainTask).where(TrainTask.id == task_id).values(
                        status=TrainStatus.FAILED, error_log=error_msg or "training failed",
                        finished_at=datetime.now(),
                        metrics_log=metrics_log or None,
                        best_metrics=best_metrics, last_metrics=last_metrics,
                    )
                )
            if hasattr(task, "created_id") and task.created_id:
                _send_notify(task.created_id, f"训练失败: {task.name}", error_msg or "训练异常退出", "training_failed", "train", task_id)

    except Exception as e:
        log.error(f"training task {task_id} failed: {e}")
        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainTask).where(TrainTask.id == task_id).values(
                    status=TrainStatus.FAILED, error_log=str(e), finished_at=datetime.now()
                )
            )
    finally:
        _running_tasks.pop(task_id, None)
        if container_id:
            await remove_container(container_id)


async def start_training(task_id: int):
    async with async_db_session.begin() as db:
        task = await db.get(TrainTask, task_id)
        if not task:
            raise Exception(f"训练任务 {task_id} 不存在")

        # If annotation_task_id is set, verify the annotation task is completed (live check)
        if task.annotation_task_id:
            from app.api.v1.module_annotation.task.model import AnnotationTaskModel
            from app.api.v1.module_annotation.task.service import TaskService
            ann_task = await db.get(AnnotationTaskModel, task.annotation_task_id)
            if ann_task:
                try:
                    prog = await TaskService._calc_progress(db, ann_task.id, ann_task.dataset_id)
                except Exception:
                    prog = {"status": "pending"}
                if prog.get("status") != "completed":
                    raise Exception(
                        f"标注任务「{ann_task.name}」尚未完成"
                    )

        await db.execute(
            update(TrainTask).where(TrainTask.id == task_id).values(
                status=TrainStatus.RUNNING, started_at=datetime.now(),
                progress=0, error_log=None,
                metrics_log=None, best_metrics=None, last_metrics=None,
                finished_at=None,
            )
        )
    asyncio.create_task(_execute_training(task_id))


async def stop_training(task_id: int) -> None:
    entry = _running_tasks.get(task_id)
    if entry:
        entry["cancel"] = True
        await stop_container(entry["container_id"])
    # Always update DB status, even if _running_tasks entry is gone
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainTask).where(TrainTask.id == task_id, TrainTask.status == TrainStatus.RUNNING).values(
                status=TrainStatus.CANCELLED, finished_at=datetime.now()
            )
        )
