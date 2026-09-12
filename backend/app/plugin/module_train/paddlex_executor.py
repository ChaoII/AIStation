"""PaddleX OCR 训练执行器：复用 TaskExecutor，跑 paddlex 容器 tools/train.py（PP-OCRv6 det/rec）。

镜像：paddlex:latest（内置 PaddleOCR 插件，官方 train.py）。
数据：/data/det 或 /data/rec（exporter 生成的 PaddleX 格式）
输出：/output/det 或 /output/rec（best_accuracy.pdparams）
预训练：/pretrained/det.pdparams 或 /pretrained/rec.pdparams（官方 PP-OCRv6 权重）
"""
import os
import re
import tempfile
from datetime import datetime

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import pull_image, remove_container, run_container
from .framework_utils import framework_value
from .model import TrainStatus, TrainTask
from .scheduler import _build_cmd
from .task_executor import TaskExecutor
from .ws import broadcast_log


class PaddleXOCRExecutor(TaskExecutor):
    """PaddleX PP-OCRv6 det/rec 训练执行器。

    det / rec 由 task.hyperparams.mode 区分（'det' / 'rec'），数据导出与命令构建
    均按 mode 分支（scheduler._build_paddlex_ocr_cmd + exporter._export_paddle_ocr）。
    """
    name = "paddlex_ocr_train"
    task_kind = "train"
    status_enum = TrainStatus
    model_class = TrainTask
    _concurrency = 1
    DOCKER_IMAGE = "paddlex:latest"

    @staticmethod
    def _mode(task) -> str:
        hp = task.hyperparams or {}
        mode = str(hp.get("mode", "det")).lower()
        return mode if mode in ("det", "rec") else "det"

    @classmethod
    async def recover_orphans(cls) -> None:
        """只回收 PADDLEX 训练任务（避免与其他执行器重复处理）。

        det/rec 执行器共享检查：任一 PaddleXOCR* 的 registry 中有该任务即视为存活。
        """
        async with async_db_session() as db:
            from sqlalchemy import select, update

            rows = (await db.execute(select(TrainTask).where(
                TrainTask.status == TrainStatus.RUNNING
            ))).scalars().all()
            all_registries = {}
            for sub in cls.__mro__:
                reg = getattr(sub, "_registry", None)
                if isinstance(reg, dict):
                    all_registries.update(reg)
            for r in rows:
                if framework_value(getattr(r, "framework", None)) != "paddlex":
                    continue
                if r.id in all_registries:
                    continue
                if r.started_at and (datetime.now() - r.started_at).total_seconds() > cls._orphan_timeout_sec:
                    async with async_db_session.begin() as db2:
                        await db2.execute(
                            update(TrainTask).where(TrainTask.id == r.id).values(
                                status=TrainStatus.FAILED,
                                error_log="任务会话已断开（后端重启或容器丢失）",
                                finished_at=datetime.now(),
                            )
                        )

    @staticmethod
    def _parse_epoch(line: str) -> dict | None:
        """解析 PaddleOCR 训练日志：epoch: [n/total] ... / best metric。"""
        m = re.search(r"epoch:\s*\[(\d+)/(\d+)\]", line)
        if m:
            cur = int(m.group(1))
            total = int(m.group(2))
            out = {"epoch": cur, "total": total}
            # acc / hmean 指标
            am = re.search(r"acc:\s*([\d.]+)", line)
            if am:
                out["acc"] = float(am.group(1))
            hm = re.search(r"loss:\s*([\d.]+)", line)
            if hm:
                out["loss"] = float(hm.group(1))
            return out
        bm = re.search(r"best metric,.*hmean:\s*([\d.]+)", line)
        if bm:
            return {"hmean": float(bm.group(1)), "best": True}
        ba = re.search(r"best metric,.*acc:\s*([\d.]+)", line)
        if ba:
            return {"acc": float(ba.group(1)), "best": True}
        return None

    @classmethod
    async def _execute(cls, task_id: int):
        container_id = None
        try:
            async with async_db_session() as db:
                task = await db.get(TrainTask, task_id)
                if not task:
                    return
                mode = cls._mode(task)

            await broadcast_log(task_id, f"[{cls.name}] pulling image {cls.DOCKER_IMAGE}...")
            await pull_image(cls.DOCKER_IMAGE)

            export_dir = os.path.join(tempfile.gettempdir(), "train_output", str(task_id))
            data_dir = os.path.join(export_dir, "data")
            os.makedirs(data_dir, exist_ok=True)

            from .exporter import prepare_training_data_for_task
            hp = task.hyperparams or {}
            await prepare_training_data_for_task(
                task.dataset_id, task.id, task.framework, data_dir,
                annotation_task_id=task.annotation_task_id,
                train_ratio=float(hp.get("train_ratio", 0.8)),
                ocr_rec=(mode == "rec"),
            )

            cmd = await _build_cmd(task, data_dir, export_dir)

            volumes = {
                data_dir: {"bind": "/data", "mode": "rw"},
                export_dir: {"bind": "/output", "mode": "rw"},
            }
            # 官方预训练权重：det/rec 各规格 .pdparams（pretrained=true 时下载到 pretrained_host）
            pretrained_host = os.path.join(export_dir, "pretrained")
            os.makedirs(pretrained_host, exist_ok=True)
            volumes[pretrained_host] = {"bind": "/pretrained", "mode": "rw"}
            use_pretrained = bool((task.hyperparams or {}).get("pretrained", False))
            if use_pretrained:
                size = str((task.hyperparams or {}).get("model_size", "tiny"))
                if size not in ("tiny", "small", "medium"):
                    size = "tiny"
                url = (
                    f"https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/"
                    f"PP-OCRv6_{size}_{mode}_pretrained.pdparams"
                )
                wpath = os.path.join(pretrained_host, f"{mode}.pdparams")
                if not os.path.exists(wpath):
                    await broadcast_log(task_id, f"[{cls.name}] downloading pretrained {url}")
                    import requests
                    resp = requests.get(url, timeout=300)
                    if resp.status_code == 200:
                        with open(wpath, "wb") as f:
                            f.write(resp.content)
                    else:
                        await broadcast_log(task_id, "[paddlex] pretrained download failed, train from scratch")
                        use_pretrained = False
                if not use_pretrained:
                    hp = dict(task.hyperparams or {})
                    hp["pretrained"] = False
                    task.hyperparams = hp

            container = await run_container(
                cls.DOCKER_IMAGE, cmd,
                volumes=volumes,
                gpu_id=task.hyperparams.get("device") or task.hyperparams.get("gpu_id") or "0",
                shm_size="4g",
                labels={"aistation.task_kind": cls.task_kind, "aistation.task_id": str(task_id)},
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
                from .exporter import export_model
                model_info = await export_model(task_id, task.framework, export_dir)
                if model_info.get("storage_path"):
                    # 从 metrics_log 提取 best（hmean/acc）与最新指标
                    best = {}
                    latest = {}
                    epoch_records = [m for m in metrics_log if m.get("epoch") and not m.get("best")]
                    if epoch_records:
                        latest = epoch_records[-1]
                    best_records = [m for m in metrics_log if m.get("best")]
                    if best_records:
                        best = best_records[-1]
                    else:
                        best = latest
                    await cls._mark_status(
                        task_id, TrainStatus.SUCCESS,
                        model_repo_id=model_info.get("repo_id"),
                        metrics_log=metrics_log or None,
                        best_metrics=best or None,
                        last_metrics=latest or None,
                        progress=100, finished_at=datetime.now(),
                    )
                else:
                    await cls._mark_status(task_id, TrainStatus.FAILED,
                                           error_log="no .pdparams found in output",
                                           finished_at=datetime.now())
            else:
                await remove_container(container_id)
                await cls._mark_status(task_id, TrainStatus.FAILED,
                                       error_log="paddlex training failed",
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


class PaddleXOCRDetExecutor(PaddleXOCRExecutor):
    name = "paddlex_ocr_det"


class PaddleXOCRRecExecutor(PaddleXOCRExecutor):
    name = "paddlex_ocr_rec"
