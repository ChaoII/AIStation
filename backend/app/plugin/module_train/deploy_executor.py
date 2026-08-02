import asyncio
import os
import tempfile
from datetime import datetime

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import follow_container_logs, pull_image, remove_container, run_container
from .model import TrainDeploy, TrainModel

_deploy_running: dict[int, dict] = {}

DOCKER_IMAGE = "ultralytics/ultralytics:latest"


def _generate_server_script(api_key: str, device: str) -> str:
    device_arg = device if device != "cpu" else "cpu"
    return f'''#!/usr/bin/env python3
"""Auto-generated inference server for AIStation model deployment."""
import os, sys, json, time, asyncio, subprocess

# Ensure dependencies
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "fastapi", "uvicorn", "python-multipart"], check=True)

import numpy as np
import cv2
from fastapi import FastAPI, File, UploadFile, HTTPException, Security
from fastapi.security import APIKeyHeader
import uvicorn
from ultralytics import YOLO

MODEL_PATH = "/model/best.pt"
API_KEY = "{api_key}"
HOST = "0.0.0.0"
PORT = 8000

print(f"[deploy] loading model from {{MODEL_PATH}}...", flush=True)
model = YOLO(MODEL_PATH)
print(f"[deploy] model loaded: {{model.names}}", flush=True)

app = FastAPI(title="AIStation Model Inference")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

@app.get("/health")
async def health():
    return {{"status": "ok", "model_name": model.model_name}}

@app.post("/predict")
async def predict(file: UploadFile = File(...), api_key: str = Security(api_key_header)):
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    start = time.time()
    contents = await file.read()
    img_array = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image")
    results = model(img, device="{device_arg}", verbose=False)[0]
    elapsed = round((time.time() - start) * 1000, 1)
    detections = []
    if results.boxes is not None:
        for box in results.boxes:
            cls_id = int(box.cls[0])
            detections.append({{
                "class": results.names[cls_id],
                "confidence": float(box.conf[0]),
                "bbox": box.xyxy[0].tolist(),
            }})
    return {{
        "success": True,
        "detections": detections,
        "image_width": int(results.orig_shape[1]) if results.orig_shape else 0,
        "image_height": int(results.orig_shape[0]) if results.orig_shape else 0,
        "inference_time_ms": elapsed,
    }}

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
'''


async def start_deployment(deploy_id: int):
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                status="deploying", started_at=datetime.now()
            )
        )
    asyncio.create_task(_execute_deployment(deploy_id))


async def stop_deployment(deploy_id: int):
    entry = _deploy_running.get(deploy_id)
    if entry and entry.get("container_id"):
        from .docker_utils import stop_container
        await stop_container(entry["container_id"])
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                status="stopped", finished_at=datetime.now()
            )
        )


def _find_available_port(start: int = 9001, end: int = 9999) -> int:
    import socket
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise Exception("no available port found in range 9001-9999")


async def _execute_deployment(deploy_id: int):
    container_id = None
    export_dir = None
    try:
        async with async_db_session() as db:
            deploy = await db.get(TrainDeploy, deploy_id)
            if not deploy:
                return
            model_rec = await db.get(TrainModel, deploy.model_id)
            if not model_rec or not model_rec.storage_path:
                async with async_db_session.begin() as d:
                    await d.execute(
                        update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                            status="failed", error_log="model not found or no storage_path",
                            finished_at=datetime.now()
                        )
                    )
                return

        await pull_image(DOCKER_IMAGE)

        export_dir = os.path.join(tempfile.gettempdir(), "deploy_output", str(deploy_id))
        model_dir = os.path.join(export_dir, "model")
        server_dir = os.path.join(export_dir, "server")
        os.makedirs(model_dir, exist_ok=True)
        os.makedirs(server_dir, exist_ok=True)

        # Download model from RustFS
        from app.utils.s3_client import s3_client
        model_data = s3_client.download_fileobj(model_rec.storage_path)
        model_filename = model_rec.storage_path.rsplit("/", 1)[-1]
        model_local_path = os.path.join(model_dir, model_filename)
        with open(model_local_path, "wb") as f:
            f.write(model_data.read())

        # Ensure file is named best.pt inside model mount
        best_pt_path = os.path.join(model_dir, "best.pt")
        if model_local_path != best_pt_path:
            import shutil
            shutil.copy2(model_local_path, best_pt_path)

        # Write inference server script
        server_script = _generate_server_script(deploy.api_key, deploy.device)
        server_path = os.path.join(server_dir, "server.py")
        with open(server_path, "w", encoding="utf-8") as f:
            f.write(server_script)

        # Determine port
        host_port = deploy.host_port or _find_available_port()
        if not deploy.host_port:
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(host_port=host_port)
                )

        ports = {f"{8000}/tcp": host_port}

        container = await run_container(
            DOCKER_IMAGE,
            ["python3", "/server/server.py"],
            volumes={
                model_dir: {"bind": "/model", "mode": "ro"},
                server_dir: {"bind": "/server", "mode": "ro"},
            },
            ports=ports,
            gpu_id=deploy.device if deploy.device != "cpu" else None,
            entrypoint="",
        )
        container_id = container.id
        _deploy_running[deploy_id] = {"container_id": container_id, "cancel": False}

        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                    container_id=container_id, api_url=f"http://127.0.0.1:{host_port}",
                    status="running"
                )
            )

        log_queue = await follow_container_logs(container_id)
        log_file = os.path.join(export_dir, "deploy.log")
        with open(log_file, "w", encoding="utf-8") as lf:
            while True:
                line = await log_queue.get()
                if line == "__EOF__":
                    break
                lf.write(line + "\n")
                lf.flush()

        loop = asyncio.get_event_loop()
        exit_code = await loop.run_in_executor(None, lambda: container.wait(timeout=300)["StatusCode"])

        if _deploy_running.get(deploy_id, {}).get("cancel"):
            pass  # already handled by stop_deployment
        elif exit_code != 0:
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
                    update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                        status="failed", error_log=error_msg or "deploy failed",
                        finished_at=datetime.now(), container_id=None
                    )
                )

    except Exception as e:
        log.error(f"deploy {deploy_id} failed: {e}")
        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                    status="failed", error_log=str(e), finished_at=datetime.now()
                )
            )
    finally:
        _deploy_running.pop(deploy_id, None)
        if container_id:
            await remove_container(container_id)
