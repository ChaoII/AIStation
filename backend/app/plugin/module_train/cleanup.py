"""定时清理临时训练产物目录。"""
import asyncio
import os
import shutil
import tempfile
import time

from app.core.database import async_db_session
from app.core.logger import log

from .model import TrainDeploy, TrainEval, TrainPredict, TrainStatus, TrainTask


async def _running_ids() -> dict[str, set[int]]:
    """查询各任务表当前处于运行中的 id 集合，用于跳过对应输出目录。

    ``子目录名 -> 运行中 id 集合``：cleanup 只跳过仍被 RUNNING 任务占用的
    输出前缀目录，避免误删运行中任务的临时产物。查询失败时返回空集合，
    回退到纯 mtime 逻辑（保守兜底）。
    """
    from sqlalchemy import select

    ids: dict[str, set[int]] = {
        "train_output": set(),
        "eval_output": set(),
        "predict_output": set(),
        "deploy_output": set(),
    }
    try:
        async with async_db_session() as db:
            ids["train_output"].update((await db.execute(
                select(TrainTask.id).where(TrainTask.status == TrainStatus.RUNNING)
            )).scalars().all())
            ids["eval_output"].update((await db.execute(
                select(TrainEval.id).where(TrainEval.status == TrainStatus.RUNNING)
            )).scalars().all())
            ids["predict_output"].update((await db.execute(
                select(TrainPredict.id).where(TrainPredict.status == TrainStatus.RUNNING)
            )).scalars().all())
            ids["deploy_output"].update((await db.execute(
                select(TrainDeploy.id).where(TrainDeploy.status.in_(("deploying", "running")))
            )).scalars().all())
    except Exception as e:
        log.warning(f"cleanup 查询运行中任务失败，回退纯 mtime 逻辑: {e}")
    return ids


async def cleanup_loop(keep_days: int = 7, interval_sec: int = 3600):
    while True:
        try:
            base = tempfile.gettempdir()
            running = await _running_ids()
            for sub in ("train_output", "eval_output", "predict_output", "deploy_output", "model_export", "dataset_export", "model_export_logs"):
                d = os.path.join(base, sub)
                if not os.path.isdir(d):
                    continue
                cutoff = time.time() - keep_days * 86400
                running_set = running.get(sub, set()) or set()
                for entry in os.listdir(d):
                    p = os.path.join(d, entry)
                    # 跳过仍在运行的任务输出目录，避免误删
                    try:
                        if entry.isdigit() and int(entry) in running_set:
                            continue
                    except ValueError:
                        pass
                    try:
                        if os.path.getmtime(p) < cutoff:
                            if os.path.isdir(p):
                                shutil.rmtree(p, ignore_errors=True)
                            else:
                                os.remove(p)
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(interval_sec)
