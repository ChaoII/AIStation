import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.api.v1.module_video.algorithm.model import AlgorithmTaskModel
from app.api.v1.module_video.camera.model import CameraModel
from app.config.setting import settings
from app.core.database import async_db_session
from app.core.logger import logger

_running_inferences: dict[int, dict] = {}
# Key: algorithm_task_id
# Value:
#   "proc": asyncio.subprocess.Process
#   "config_path": str
#   "start_time": datetime
#   "algorithm_task_id": int
#   "camera_id": int
#   "camera_name": str

CONFIG_DIR = Path(settings.INFERENCE_CONFIG_DIR)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

WORKER_SCRIPT = Path(__file__).parent / "worker.py"
SCHEDULER_INTERVAL = settings.INFERENCE_SCHEDULER_INTERVAL
WARMUP_DELAY = settings.INFERENCE_WARMUP_DELAY

_inference_task: asyncio.Task | None = None


def _get_worker_python() -> str:
    return settings.INFERENCE_WORKER_PYTHON or sys.executable


def _build_task_config(task: AlgorithmTaskModel, camera: CameraModel, algorithm) -> dict:
    stream_type = task.stream_type or "SUB"
    if stream_type == "MAIN":
        stream_url = (camera.rtsp_url_main or "").strip()
    else:
        stream_url = (camera.rtsp_url_sub or "").strip()

    if not stream_url and camera.stream_id:
        stream_url = f"{settings.ZLM_BASE_URL}/live/{camera.stream_id}.live.flv"

    runtime_config = algorithm.runtime_config or {}
    preset_params = algorithm.preset_params or {}
    runtime_overrides = task.runtime_overrides or {}
    params_overrides = task.params_overrides or {}

    merged_runtime = {**runtime_config, **runtime_overrides}
    merged_params = {**preset_params, **params_overrides}

    return {
        "task_id": task.id,
        "camera_id": task.camera_id,
        "algorithm_type": algorithm.algorithm_type,
        "stream_url": stream_url,
        "model_path": algorithm.model_path or "",
        "runtime_config": merged_runtime,
        "preset_params": merged_params,
        "detect_region": task.detect_region,
        "sensitivity": task.sensitivity or 50,
        "callback_url": (
            f"http://127.0.0.1:{settings.SERVER_PORT}"
            f"{settings.ROOT_PATH}/algorithm/detection/callback"
        ),
        "callback_token": settings.INFERENCE_CALLBACK_TOKEN,
        "fps_target": 5,
        "alarm_interval": 30,
        "snapshot_dir": str(settings.DETECTIONS_DIR),
    }


async def start_inference(task_id: int) -> dict:
    if task_id in _running_inferences:
        info = _running_inferences[task_id]
        proc = info["proc"]
        if proc.returncode is None:
            return {"task_id": task_id, "status": "RUNNING", "pid": proc.pid, "message": "已在运行中"}

    async with async_db_session() as session:
        stmt = (
            select(AlgorithmTaskModel)
            .where(AlgorithmTaskModel.id == task_id, AlgorithmTaskModel.is_deleted.is_(False))
        )
        result = await session.execute(stmt)
        task_model = result.scalar_one_or_none()
        if not task_model:
            raise LookupError(f"算法任务不存在: {task_id}")

        camera = task_model.camera
        algorithm = task_model.algorithm
        if not camera:
            raise ValueError("任务未关联摄像头")
        if not algorithm:
            raise ValueError("任务未关联算法")

    config = _build_task_config(task_model, camera, algorithm)
    config_path = CONFIG_DIR / f"infer_{task_id}_{int(time.time())}.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2))

    proc = await asyncio.create_subprocess_exec(
        _get_worker_python(), "-u", str(WORKER_SCRIPT),
        "--config", str(config_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    _running_inferences[task_id] = {
        "proc": proc,
        "config_path": str(config_path),
        "start_time": datetime.now(),
        "algorithm_task_id": task_id,
        "camera_id": task_model.camera_id,
        "camera_name": camera.name or "",
    }

    async with async_db_session.begin() as session:
        stmt = select(AlgorithmTaskModel).where(AlgorithmTaskModel.id == task_id)
        result = await session.execute(stmt)
        t = result.scalar_one_or_none()
        if t:
            t.status = "RUNNING"

    logger.info(f"[推理调度器] 启动推理: task_id={task_id} camera={camera.name} pid={proc.pid}")
    return {"task_id": task_id, "status": "RUNNING", "pid": proc.pid, "message": "推理任务已启动"}


async def stop_inference(task_id: int) -> dict:
    info = _running_inferences.pop(task_id, None)
    if not info:
        async with async_db_session.begin() as session:
            stmt = select(AlgorithmTaskModel).where(AlgorithmTaskModel.id == task_id)
            result = await session.execute(stmt)
            t = result.scalar_one_or_none()
            if t:
                t.status = "STOPPED"
        return {"task_id": task_id, "status": "STOPPED", "message": "未在运行中"}

    proc = info["proc"]
    config_path = info.get("config_path")

    if proc.returncode is None:
        try:
            proc.send_signal(signal.SIGTERM)
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

    if config_path:
        try:
            os.unlink(config_path)
        except OSError:
            pass

    async with async_db_session.begin() as session:
        stmt = select(AlgorithmTaskModel).where(AlgorithmTaskModel.id == task_id)
        result = await session.execute(stmt)
        t = result.scalar_one_or_none()
        if t:
            t.status = "STOPPED"

    logger.info(f"[推理调度器] 停止推理: task_id={task_id}")
    return {"task_id": task_id, "status": "STOPPED"}


async def get_inference_status(task_id: int) -> dict:
    info = _running_inferences.get(task_id)
    if not info:
        return {"task_id": task_id, "status": "STOPPED", "pid": None, "uptime_seconds": 0}

    proc = info["proc"]
    if proc.returncode is not None:
        return {"task_id": task_id, "status": "ERROR", "pid": proc.pid, "uptime_seconds": 0}

    uptime = (datetime.now() - info["start_time"]).total_seconds()
    return {
        "task_id": task_id,
        "status": "RUNNING",
        "pid": proc.pid,
        "camera_name": info.get("camera_name", ""),
        "uptime_seconds": round(uptime, 1),
    }


async def check_inference_health():
    dead = []
    for task_id, info in list(_running_inferences.items()):
        proc = info["proc"]
        if proc.returncode is not None:
            logger.warning(f"[推理调度器] Worker 意外退出: task_id={task_id} rc={proc.returncode}")
            dead.append(task_id)

    for task_id in dead:
        info = _running_inferences.pop(task_id, None)
        if info and info.get("config_path"):
            try:
                os.unlink(info["config_path"])
            except OSError:
                pass
        try:
            async with async_db_session.begin() as session:
                stmt = select(AlgorithmTaskModel).where(AlgorithmTaskModel.id == task_id)
                result = await session.execute(stmt)
                t = result.scalar_one_or_none()
                if t and t.status == "RUNNING":
                    t.status = "ERROR"
        except Exception as e:
            logger.error(f"[推理调度器] 更新错误状态失败: task_id={task_id} {e}")


async def inference_scheduler_loop():
    global _inference_task
    _inference_task = asyncio.current_task()
    await asyncio.sleep(WARMUP_DELAY)
    logger.info(f"[推理调度器] 启动，检查间隔 {SCHEDULER_INTERVAL}s")

    while True:
        try:
            async with async_db_session() as session:
                stmt = select(AlgorithmTaskModel).where(
                    AlgorithmTaskModel.status == "RUNNING",
                    AlgorithmTaskModel.is_deleted.is_(False),
                )
                result = await session.execute(stmt)
                db_tasks = {t.id: t for t in result.scalars().all()}

            for tid in db_tasks:
                if tid not in _running_inferences:
                    try:
                        await start_inference(tid)
                    except Exception as e:
                        logger.error(f"[推理调度器] 自动启动失败: task_id={tid} {e}")

            for tid in list(_running_inferences.keys()):
                if tid not in db_tasks:
                    try:
                        await stop_inference(tid)
                    except Exception as e:
                        logger.error(f"[推理调度器] 自动停止失败: task_id={tid} {e}")

            await check_inference_health()

        except Exception as e:
            logger.error(f"[推理调度器] 调度循环异常: {e}")

        await asyncio.sleep(SCHEDULER_INTERVAL)


async def start_inference_scheduler():
    await inference_scheduler_loop()


async def stop_inference_scheduler():
    global _inference_task
    if _inference_task:
        _inference_task.cancel()
        _inference_task = None

    for task_id in list(_running_inferences.keys()):
        try:
            await stop_inference(task_id)
        except Exception as e:
            logger.error(f"[推理调度器] 停止进程失败: task_id={task_id} {e}")

    logger.info("[推理调度器] 已停止")
