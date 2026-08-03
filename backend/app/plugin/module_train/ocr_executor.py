"""OCR det 训练执行器：复用 TaskExecutor，跑 aistation-ocr 容器。"""
import os
import tempfile
from datetime import datetime

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import pull_image, remove_container, run_container
from .model import TrainStatus, TrainTask
from .scheduler import _build_cmd
from .task_executor import TaskExecutor
from .ws import broadcast_log


class OCRDetExecutor(TaskExecutor):
    name = "ocr_det"
    status_enum = TrainStatus
    model_class = TrainTask
    _concurrency = 1
    DOCKER_IMAGE = "aistation-ocr:latest"

    @classmethod
    async def _execute(cls, task_id: int):
        container_id = None
        try:
            async with async_db_session() as db:
                task = await db.get(TrainTask, task_id)
                if not task:
                    return

            await broadcast_log(task_id, f"[ocr] pulling image {cls.DOCKER_IMAGE}...")
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
                gpu_id=task.hyperparams.get("gpu_id", "0"),
            )
            container_id = container.id
            entry = cls._registry.get(task_id) or {}
            entry.update({"container_id": container_id})
            cls._registry[task_id] = entry

            await cls.follow_logs(
                container_id,
                os.path.join(export_dir, "train.log"),
                lambda line: broadcast_log(task_id, line),
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
                    await cls._mark_status(
                        task_id, TrainStatus.SUCCESS,
                        model_repo_id=model_info.get("repo_id"),
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
            log.error(f"ocr task {task_id} failed: {e}")
            await cls._mark_status(task_id, TrainStatus.FAILED,
                                   error_log=str(e), finished_at=datetime.now())
        finally:
            cls._registry.pop(task_id, None)
            if container_id:
                await remove_container(container_id)
