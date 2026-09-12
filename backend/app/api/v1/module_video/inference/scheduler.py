import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil
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


# ---------------------------------------------------------------------------
# Worker PID 防重：内存字典在后端重启后会丢失，改用 pidfile 落盘辅助判断，
# 避免对 DB 中仍是 RUNNING 的任务重复拉起 worker（旧 worker 仍在回调）。
# ---------------------------------------------------------------------------
def pid_file(task_id: int) -> Path:
    return CONFIG_DIR / f"infer_{task_id}.pid"


def read_worker_pid(task_id: int) -> int | None:
    try:
        return int(pid_file(task_id).read_text().strip())
    except Exception:
        return None


def is_worker_alive(pid: int | None) -> bool:
    """校验 pid 对应进程是否存活且确为推理 worker。

    用 cmdline 各参数的 basename 精确匹配 ``worker.py``，避免子串误判
    （例如 ``test_inference_worker.py`` 也包含 "worker.py"）。
    """
    if not pid:
        return False
    try:
        p = psutil.Process(pid)
        return any(Path(arg).name == WORKER_SCRIPT.name for arg in p.cmdline())
    except Exception:
        return False


def write_worker_pid(task_id: int, pid: int) -> None:
    try:
        pid_file(task_id).write_text(str(pid))
    except OSError as e:
        logger.warning(f"[推理调度器] 写入 pidfile 失败: task_id={task_id} {e}")


def clear_worker_pid(task_id: int) -> None:
    try:
        pid_file(task_id).unlink()
    except OSError:
        pass


def terminate_stale_worker(task_id: int) -> None:
    """终止 pidfile 记录的存活孤儿 worker 并清理 pidfile（用于后端重启后防重）。"""
    pid = read_worker_pid(task_id)
    if pid and is_worker_alive(pid):
        try:
            p = psutil.Process(pid)
            p.terminate()
            try:
                p.wait(timeout=5)
            except psutil.TimeoutExpired:
                p.kill()
            logger.info(f"[推理调度器] 已终止残留 worker: task_id={task_id} pid={pid}")
        except psutil.Error:
            pass
    clear_worker_pid(task_id)


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

    # 告警去重间隔与类别名：与边缘 Agent 配置（orchestrator）保持同源
    interval_seconds = int(
        merged_params.get("alarm_interval_sec")
        or merged_runtime.get("alarm_interval_sec")
        or 30
    )
    class_names = merged_params.get("labels") or []

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
        "schedule_json": task.schedule_json,
        "class_names": class_names,
        "callback_url": (
            f"http://127.0.0.1:{settings.SERVER_PORT}"
            f"{settings.ROOT_PATH}/video/algorithm/detection/callback"
        ),
        "callback_token": settings.INFERENCE_CALLBACK_TOKEN,
        "fps_target": 5,
        "interval_seconds": interval_seconds,
        "snapshot_dir": str(settings.DETECTIONS_DIR),
    }


async def start_inference(task_id: int) -> dict:
    # 仅当 worker 使用后端同一解释器时才做进程内校验；
    # 若配置了独立 worker 解释器（可能自带 modeldeploy），后端解释器并不权威。
    if not settings.INFERENCE_WORKER_PYTHON:
        from app.api.v1.module_video.inference.registry import ensure_inference_backend
        ensure_inference_backend()
    else:
        logger.info(
            "[推理调度器] 已配置 INFERENCE_WORKER_PYTHON，跳过后端进程内推理后端校验"
        )

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

    # 后端重启后内存注册表已丢失：若 pidfile 记录的旧 worker 仍存活，先终止，
    # 避免对同一任务重复拉起导致重复回调/告警。
    terminate_stale_worker(task_id)

    config = _build_task_config(task_model, camera, algorithm)
    config_path = CONFIG_DIR / f"infer_{task_id}_{int(time.time())}.json"
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2))

    proc = await asyncio.create_subprocess_exec(
        _get_worker_python(), "-u", str(WORKER_SCRIPT),
        "--config", str(config_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )

    # 持续排空 stderr，避免管道缓冲填满导致 worker 阻塞
    async def _drain_stderr(p: asyncio.subprocess.Process):
        try:
            while True:
                line = await p.stderr.readline()
                if not line:
                    break
                try:
                    logger.info(f"[推理Worker {task_id}] {line.decode('utf-8', errors='replace').rstrip()}")
                except Exception:
                    pass
        except Exception:
            pass

    asyncio.create_task(_drain_stderr(proc))

    _running_inferences[task_id] = {
        "proc": proc,
        "config_path": str(config_path),
        "start_time": datetime.now(),
        "algorithm_task_id": task_id,
        "camera_id": task_model.camera_id,
        "camera_name": camera.name or "",
    }
    write_worker_pid(task_id, proc.pid)

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
        clear_worker_pid(task_id)
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

    clear_worker_pid(task_id)

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
        clear_worker_pid(task_id)
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
