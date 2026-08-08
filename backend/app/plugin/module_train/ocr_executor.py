"""OCR 训练执行器：复用 TaskExecutor，跑 aistation-ocr 容器 train-det/train-rec。"""
import os
import re
import tempfile
from datetime import datetime

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import pull_image, remove_container, run_container
from .model import TrainStatus, TrainTask
from .scheduler import _build_cmd
from .task_executor import TaskExecutor
from .ws import broadcast_log


class OCRTrainExecutor(TaskExecutor):
    """OCR det/rec 训练共用执行器。

    子命令 train-det / train-rec 由 _build_cmd 按 task.framework 分支，数据导出同样
    由 prepare_training_data_for_task 按 framework 走 _export_core 的 det/rec 分支，
    故 det 与 rec 执行流程完全一致，仅 name 不同。
    """
    name = "ocr_train"
    status_enum = TrainStatus
    model_class = TrainTask
    _concurrency = 1
    DOCKER_IMAGE = "aistation-ocr:latest"

    @staticmethod
    def _parse_epoch(line: str) -> dict | None:
        """解析 pytorch-ocr 训练日志：epoch: [n/total] 进度 + eval hmean/char_acc。"""
        m = re.search(r"epoch:\s*\[(\d+)/(\d+)\]", line)
        if m:
            return {"epoch": int(m.group(1)), "total": int(m.group(2))}
        hm = re.search(r"eval hmean\s+([\d.]+)", line)
        if hm:
            return {"hmean": float(hm.group(1)), "best": True}
        ca = re.search(r"eval char_acc\s+([\d.]+)", line)
        if ca:
            return {"char_acc": float(ca.group(1)), "best": True}
        return None

    @classmethod
    async def _execute(cls, task_id: int):
        container_id = None
        try:
            async with async_db_session() as db:
                task = await db.get(TrainTask, task_id)
                if not task:
                    return

            await broadcast_log(task_id, f"[{cls.name}] pulling image {cls.DOCKER_IMAGE}...")
            await pull_image(cls.DOCKER_IMAGE)

            export_dir = os.path.join(tempfile.gettempdir(), "train_output", str(task_id))
            data_dir = os.path.join(export_dir, "data")
            os.makedirs(data_dir, exist_ok=True)

            from .exporter import prepare_training_data_for_task
            await prepare_training_data_for_task(
                task.dataset_id, task.id, task.framework, data_dir,
                annotation_task_id=task.annotation_task_id,
            )

            cmd = await _build_cmd(task, data_dir, export_dir)

            container = await run_container(
                cls.DOCKER_IMAGE, cmd,
                volumes={data_dir: {"bind": "/data", "mode": "rw"},
                         export_dir: {"bind": "/output", "mode": "rw"}},
                gpu_id=task.hyperparams.get("device") or task.hyperparams.get("gpu_id") or "0",
            )
            container_id = container.id
            entry = cls._registry.get(task_id) or {}
            entry.update({"container_id": container_id})
            cls._registry[task_id] = entry

            metrics_log = await cls.follow_logs(
                container_id,
                os.path.join(export_dir, "train.log"),
                lambda line: broadcast_log(task_id, line),
                parse_fn=cls._parse_epoch,
            )
            exit_code = await cls._get_exit_code(container)

            if cls._registry.get(task_id, {}).get("cancel"):
                await remove_container(container_id)
                await cls._mark_status(task_id, TrainStatus.CANCELLED, finished_at=datetime.now())
            elif exit_code == 0:
                await remove_container(container_id)
                # 收集 best.pt
                best_path = os.path.join(export_dir, "best.pt")
                if os.path.exists(best_path):
                    from .exporter import export_model
                    model_info = await export_model(task_id, task.framework, export_dir)
                    best = next((m for m in metrics_log if m.get("best")), None) or None
                    await cls._mark_status(
                        task_id, TrainStatus.SUCCESS,
                        model_repo_id=model_info.get("repo_id"),
                        metrics_log=metrics_log or None,
                        best_metrics=best,
                        last_metrics=best,
                        progress=100, finished_at=datetime.now(),
                    )
                else:
                    await cls._mark_status(task_id, TrainStatus.FAILED,
                                           error_log="best.pt not found in output",
                                           finished_at=datetime.now())
            else:
                await remove_container(container_id)
                await cls._mark_status(task_id, TrainStatus.FAILED,
                                       error_log="ocr training failed",
                                       finished_at=datetime.now())
        except Exception as e:
            log.error(f"[{cls.name}] task {task_id} failed: {e}")
            cancelled = cls._registry.get(task_id, {}).get("cancel", False)
            await cls._mark_status(
                task_id,
                TrainStatus.CANCELLED if cancelled else TrainStatus.FAILED,
                error_log=str(e), finished_at=datetime.now(),
            )
        finally:
            cls._registry.pop(task_id, None)
            if container_id:
                await remove_container(container_id)


class OCRDetExecutor(OCRTrainExecutor):
    name = "ocr_det"
