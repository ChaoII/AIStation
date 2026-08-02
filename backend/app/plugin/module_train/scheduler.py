import asyncio
import os
import re
import tempfile
from datetime import datetime

import requests
from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import get_container_error_tail, pull_image, remove_container, run_container
from .model import TrainFramework, TrainStatus, TrainTask
from .task_executor import TaskExecutor
from .ws import broadcast_log

_scheduler_task: asyncio.Task | None = None

MODELS_CACHE_DIR = os.path.join(tempfile.gettempdir(), "train_output", ".models_cache").replace("\\", "/")
_MODEL_DOWNLOAD_BASE = "https://github.com/ultralytics/assets/releases/latest/download"
_MODEL_MIRROR = os.environ.get("MODEL_MIRROR", "")  # e.g. https://ghproxy.com/


def _send_notify(user_id: int, title: str, content: str | None, type_: str, module: str, module_id: int | None):
    """Fire-and-forget notification; non-blocking on best-effort basis."""
    try:
        import asyncio

        from app.api.v1.module_system.notification.service import NotificationService
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
    """维护循环：触发定时训练 + 周期孤儿恢复（交由 TrainExecutor.recover_orphans）。"""
    while True:
        try:
            # Check for due training schedules
            try:
                from .schedule_model import TrainScheduleModel
                from .schedule_service import ScheduleService
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

            # Periodic orphan recovery (base executor owns registry/DB state)
            await TrainExecutor.recover_orphans()
        except Exception as e:
            log.error(f"train scheduler error: {e}")
        await asyncio.sleep(30)


async def _build_export_dir(task_id: int) -> str:
    export_dir = os.path.join(tempfile.gettempdir(), "train_output", str(task_id))
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


# hp dict key → (yolo CLI flag, 默认值, 校验lambda)。仅当 key 在 hp 且值非 None 时拼入命令。
_ULTRALYTICS_HP: dict[str, tuple[str, object, object | None]] = {
    "model":        ("model", "yolo11n.pt", None),
    "epochs":       ("epochs", 100, lambda v: 1 <= int(v) <= 1000),
    "batch":        ("batch", 16, lambda v: 1 <= int(v) <= 512),
    "imgsz":        ("imgsz", 640, lambda v: 32 <= int(v) <= 4096),
    "lr0":          ("lr0", 0.01, lambda v: float(v) > 0),
    "lrf":          ("lrf", 0.01, lambda v: 0 <= float(v) <= 1),
    "momentum":     ("momentum", 0.937, lambda v: 0 <= float(v) <= 1),
    "weight_decay": ("weight_decay", 0.0005, lambda v: float(v) >= 0),
    "optimizer":    ("optimizer", "AdamW", lambda v: v in ("AdamW", "SGD", "Adam", "Adamax", "NAdam")),
    "patience":     ("patience", 100, lambda v: int(v) >= 0),
    "workers":      ("workers", 8, lambda v: 0 <= int(v) <= 32),
    "device":       ("device", "0", None),
    "seed":         ("seed", 0, None),
    "hsv_h":        ("hsv_h", 0.015, lambda v: 0 <= float(v) <= 1),
    "hsv_s":        ("hsv_s", 0.7, lambda v: 0 <= float(v) <= 1),
    "hsv_v":        ("hsv_v", 0.4, lambda v: 0 <= float(v) <= 1),
    "fliplr":       ("fliplr", 0.5, lambda v: 0 <= float(v) <= 1),
    "flipud":       ("flipud", 0.0, lambda v: 0 <= float(v) <= 1),
    "mosaic":       ("mosaic", 1.0, lambda v: 0 <= float(v) <= 1),
    "mixup":        ("mixup", 0.0, lambda v: 0 <= float(v) <= 1),
    "multi_label":  ("multi_label", False, None),
}


def _build_ultralytics_cmd(hp: dict, data_dir: str, export_dir: str, task_type: str = "detection") -> list[str]:
    model_name = hp.get("model") or "yolo11n.pt"
    # Auto-select OBB model for rotated_detection tasks
    if task_type == "rotated_detection" and "-obb" not in model_name:
        base = model_name.replace(".pt", "")
        model_name = f"{base}-obb.pt"
    cmd = ["yolo", "train", f"model=/models/{model_name}", "data=/data/dataset.yaml",
           "project=/output", "name=exp"]
    for key, (flag, _default, validator) in _ULTRALYTICS_HP.items():
        if key == "model":
            continue
        if key not in hp or hp[key] is None:
            continue
        val = hp[key]
        if validator is not None:
            try:
                if not validator(val):
                    log.warning(f"[yolo] skipping invalid hyperparam {key}={val}")
                    continue
            except (TypeError, ValueError):
                log.warning(f"[yolo] skipping invalid hyperparam {key}={val}")
                continue
        if isinstance(val, bool):
            cmd.append(f"{flag}={str(val)}")
        else:
            cmd.append(f"{flag}={val}")
    return cmd


def _build_paddlex_cmd(hp: dict, data_dir: str, export_dir: str) -> list[str]:
    # TODO(paddlex): verify CLI flags against paddlecloud/paddlex:3.0 — the following command shapes are best-effort
    epochs = hp.get("epochs", 100)
    batch = hp.get("batch", 16)
    lr = hp.get("lr", 0.01)
    model_name = hp.get("model", "PP-YOLOE")
    return ["paddlex", "--train", "--model", model_name, "--data", "/data",
            "--epochs", str(epochs), "--batch", str(batch), "--lr", str(lr),
            "--output", "/output"]


async def _build_cmd(task, data_dir: str, export_dir: str) -> list[str]:
    """按框架构建训练命令（复用原 _build_ultralytics_cmd/_build_paddlex_cmd）。"""
    if task.framework == TrainFramework.ULTRALYTICS:
        task_type = "detection"
        if task.annotation_task_id:
            from app.api.v1.module_annotation.task.model import AnnotationTaskModel
            async with async_db_session() as db:
                ann_task = await db.get(AnnotationTaskModel, task.annotation_task_id)
                if ann_task:
                    task_type = ann_task.task_type
        return _build_ultralytics_cmd(task.hyperparams, data_dir, export_dir, task_type)
    return _build_paddlex_cmd(task.hyperparams, data_dir, export_dir)


def _parse_epoch(line: str) -> dict | None:
    """解析 YOLO 训练输出行：epoch 行或最终 all 汇总行。"""
    m = re.search(r"^\s*(\d+)/(\d+)\s+", line)
    if m:
        parts = line.strip().split()
        met = {"epoch": int(m.group(1)), "total_epochs": int(m.group(2))}
        for i, p in enumerate(parts):
            if re.match(r"^[\d.]+[GM]$", p):
                if i + 1 < len(parts):
                    try:
                        met["box_loss"] = float(parts[i + 1])
                    except ValueError:
                        pass
                if i + 2 < len(parts):
                    try:
                        met["cls_loss"] = float(parts[i + 2])
                    except ValueError:
                        pass
                if i + 3 < len(parts):
                    try:
                        met["dfl_loss"] = float(parts[i + 3])
                    except ValueError:
                        pass
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


def _compute_best(metrics_log: list[dict]) -> dict | None:
    """从每轮指标中选出 map50 最优的一轮；无 map50 时取含最多数值字段的一轮，再退最后一轮。"""
    if not metrics_log:
        return None
    valid = [m for m in metrics_log if m and m.get("map50") is not None]
    if valid:
        return max(valid, key=lambda m: m["map50"])
    # 兜底：若全无 map50，取含最多数值字段的一轮
    ranked = sorted(
        metrics_log,
        key=lambda m: sum(1 for k in ("precision", "recall", "map50", "map5095") if m and m.get(k) is not None),
        reverse=True,
    )
    best = ranked[0] if ranked else None
    return best if best else metrics_log[-1]


class TrainExecutor(TaskExecutor):
    name = "train"
    status_enum = TrainStatus
    model_class = TrainTask
    _concurrency = 1

    @classmethod
    async def _execute(cls, task_id: int):
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

            cmd = await _build_cmd(task, data_dir, export_dir)

            # Pre-download model weights so container doesn't fetch from internet
            if task.framework == TrainFramework.ULTRALYTICS:
                model_arg = next((a for a in cmd if a.startswith("model=")), "model=yolo11n.pt")
                model_name = model_arg.split("=", 1)[1].removeprefix("/models/")
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
            entry = cls._registry.get(task_id) or {}
            entry.update({"container_id": container_id})
            cls._registry[task_id] = entry

            metrics_log = await cls.follow_logs(
                container_id,
                os.path.join(export_dir, "train.log"),
                lambda line: broadcast_log(task_id, line),
                _parse_epoch,
            )

            # Merge trailing "all" summary (epoch == -1) into last real epoch to restore old metrics shape
            if metrics_log and metrics_log[-1].get("epoch") == -1:
                summary = metrics_log.pop()
                for m in metrics_log[::-1]:
                    if m.get("epoch", -1) > 0:
                        for k, v in summary.items():
                            if k != "epoch":
                                m[k] = v
                        break
            exit_code = await cls._get_exit_code(container)

            if cls._registry.get(task_id, {}).get("cancel"):
                await remove_container(container_id)
                await cls._mark_status(task_id, TrainStatus.CANCELLED, finished_at=datetime.now())
            elif exit_code == 0:
                await remove_container(container_id)
                from .exporter import export_model
                best_metrics = _compute_best(metrics_log)
                last_metrics = metrics_log[-1] if metrics_log else None
                model_info = await export_model(task_id, task.framework, export_dir, best_metrics=best_metrics)
                await cls._mark_status(task_id, TrainStatus.SUCCESS,
                                       model_repo_id=model_info.get("repo_id"),
                                       progress=100, finished_at=datetime.now(),
                                       metrics_log=metrics_log or None,
                                       best_metrics=best_metrics,
                                       last_metrics=last_metrics)
                if getattr(task, "created_id", None):
                    _send_notify(task.created_id, f"训练完成: {task.name}",
                                 "任务已成功完成，模型已保存", "training_complete", "train", task_id)
            else:
                error_msg = (await get_container_error_tail(container_id)).strip()
                await remove_container(container_id)
                await cls._mark_status(task_id, TrainStatus.FAILED,
                                       error_log=error_msg or "training failed",
                                       finished_at=datetime.now(),
                                       metrics_log=metrics_log or None,
                                       best_metrics=_compute_best(metrics_log),
                                       last_metrics=metrics_log[-1] if metrics_log else None)
                if getattr(task, "created_id", None):
                    _send_notify(task.created_id, f"训练失败: {task.name}",
                                 error_msg or "训练异常退出", "training_failed", "train", task_id)
        except Exception as e:
            log.error(f"training task {task_id} failed: {e}")
            await cls._mark_status(task_id, TrainStatus.FAILED,
                                   error_log=str(e), finished_at=datetime.now())
        finally:
            cls._registry.pop(task_id, None)
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
    asyncio.create_task(TrainExecutor.run(task_id))


async def stop_training(task_id: int) -> None:
    await TrainExecutor.stop(task_id)
