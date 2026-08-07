import asyncio
import os
import socket
import tempfile
from datetime import datetime

import docker
import httpx
from sqlalchemy import select, update

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import client as docker_client
from .docker_utils import (
    follow_container_logs,
    get_container_error_tail,
    pull_image,
    remove_container,
    run_container,
)
from .model import TrainDeploy, TrainFramework, TrainModel

_deploy_running: dict[int, dict] = {}

DOCKER_IMAGE = "ultralytics/ultralytics:latest"
OCR_IMAGE = "aistation-ocr:latest"
PADDLEX_IMAGE = "paddlex:latest"
OCR_FRAMEWORKS = (TrainFramework.PYTORCH_OCR_DET, TrainFramework.PYTORCH_OCR_REC)


def _is_ocr_framework(framework: TrainFramework) -> bool:
    """判断部署框架是否需要 pytorch OCR server（det/rec 双模型推理）。"""
    return framework in OCR_FRAMEWORKS


def _is_paddlex_framework(framework: TrainFramework) -> bool:
    """PaddleX 框架（PP-OCRv6 det/rec 训练产物 .pdparams 部署）。"""
    return framework == TrainFramework.PADDLEX


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


def _generate_ocr_server_script(api_key: str, device: str) -> str:
    """生成 OCR 推理服务脚本：加载 det+rec `.pt`，/predict 返回 [{text, confidence, box}]。

    运行在 aistation-ocr 镜像中（WORKDIR=/workspace，含 pytorch_ocr 包），
    通过 sys.path.insert 引入 pytorch_ocr.inference.ocr_pipeline.OCRPipeline。
    rec.pt 可选：未挂载时 rec_state 传 None（骨架阶段允许 det 单模型）。
    """
    device_arg = device if device != "cpu" else "cpu"
    return f'''#!/usr/bin/env python3
"""Auto-generated OCR inference server for AIStation model deployment (det + rec)."""
import os, sys, json, time, asyncio, subprocess

# Ensure dependencies
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                "fastapi", "uvicorn", "python-multipart"], check=True)

import numpy as np
import cv2
from fastapi import FastAPI, File, UploadFile, HTTPException, Security
from fastapi.security import APIKeyHeader
import uvicorn

import torch
import sys as _sys
sys.path.insert(0, "/workspace")
from pytorch_ocr.inference.ocr_pipeline import OCRPipeline

MODEL_PATH = "/model/det.pt"
REC_MODEL_PATH = "/model/rec.pt"
API_KEY = "{api_key}"
HOST = "0.0.0.0"
PORT = 8000

print(f"[deploy] loading OCR models...", flush=True)
det_state = torch.load(MODEL_PATH, map_location="cpu")
rec_state = torch.load(REC_MODEL_PATH, map_location="cpu") if os.path.exists(REC_MODEL_PATH) else None
pipe = OCRPipeline(
    det_state=det_state,
    rec_state=rec_state,
    config={{"device": "{device_arg}"}},
)
print(f"[deploy] OCR models loaded", flush=True)

app = FastAPI(title="AIStation OCR Inference")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

@app.get("/health")
async def health():
    return {{"status": "ok", "model": "ocr"}}

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
    detections = pipe(img)
    elapsed = round((time.time() - start) * 1000, 1)
    return {{
        "success": True,
        "detections": detections,
        "inference_time_ms": elapsed,
    }}

if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
'''


def _generate_paddlex_server_script(api_key: str, device: str) -> str:
    """生成 PaddleX OCR 推理服务脚本（PP-OCRv6 det + rec，.pdparams 权重）。

    运行在 paddlex:latest 镜像（内置 PaddleOCR），加载 /model/det.pdparams +
    /model/rec.pdparams，/predict 返回 [{text, confidence, box}]。
    """
    device_arg = device if device != "cpu" else "cpu"
    return r'''#!/usr/bin/env python3
"""Auto-generated PaddleX OCR inference server (PP-OCRv6 det + rec)."""
import os, sys, json, time, io

_POCR_DIR = "/paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR"
sys.path.insert(0, _POCR_DIR)
sys.path.insert(0, os.path.join(_POCR_DIR, ".."))
os.chdir(_POCR_DIR)
os.environ["FLAGS_allocator_strategy"] = "auto_growth"

import numpy as np
import cv2
import paddle
from fastapi import FastAPI, File, UploadFile, HTTPException, Security
from fastapi.security import APIKeyHeader
import uvicorn

from ppocr.data import create_operators, transform
from ppocr.modeling.architectures import build_model
from ppocr.postprocess import build_post_process
from ppocr.utils.save_load import load_model
import tools.program as program

API_KEY = "__API_KEY__"
HOST = "0.0.0.0"
PORT = 8000
DEVICE = "__DEVICE__"


def _load_pipeline(cfg_name, weights_path):
    """构建 PP-OCRv6 推理管线（det 或 rec）。"""
    sys.argv = ["infer", "-c", cfg_name, "-o",
                "Global.pretrained_model=" + weights_path,
                "Global.use_gpu=" + str(DEVICE != "cpu")]
    config, _device, logger, _vdl = program.preprocess(is_train=False)
    post_process_class = build_post_process(config["PostProcess"], config["Global"])
    # rec MultiHead 需要 out_channels_list（从字符集算输出通道，对齐官方 tools/eval.py）
    if config["Architecture"].get("Head", {}).get("name") == "MultiHead":
        char_num = len(getattr(post_process_class, "character"))
        out_channels_list = {
            "CTCLabelDecode": char_num,
            "SARLabelDecode": char_num + 2,
            "NRTRLabelDecode": char_num + 3,
        }
        config["Architecture"]["Head"]["out_channels_list"] = out_channels_list
    model = build_model(config["Architecture"])
    load_model(config, model)
    model.eval()
    transforms = []
    for op in config["Eval"]["dataset"]["transforms"]:
        op_name = list(op)[0]
        if "Label" in op_name:
            continue
        elif op_name == "KeepKeys":
            op[op_name]["keep_keys"] = ["image", "shape"]
        transforms.append(op)
    ops = create_operators(transforms, config["Global"])
    return model, post_process_class, ops


DET_CFG = "configs/det/PP-OCRv6/PP-OCRv6_small_det.yml"
REC_CFG = "configs/rec/PP-OCRv6/PP-OCRv6_small_rec.yml"
DET_PATH = "/model/det.pdparams"
REC_PATH = "/model/rec.pdparams"

print("[deploy] loading PaddleX det model...", flush=True)
det_model, det_post, det_ops = _load_pipeline(DET_CFG, DET_PATH)
rec_model, rec_post, rec_ops = None, None, None
if os.path.exists(REC_PATH):
    print("[deploy] loading PaddleX rec model...", flush=True)
    rec_model, rec_post, rec_ops = _load_pipeline(REC_CFG, REC_PATH)
print("[deploy] PaddleX OCR models loaded", flush=True)


def _det_boxes(img):
    data = {"image": cv2.imencode(".jpg", img)[1].tobytes()}
    batch = transform(data, det_ops)
    images = np.expand_dims(batch[0], axis=0)
    shape_list = np.expand_dims(batch[1], axis=0)
    preds = det_model(paddle.to_tensor(images))
    res = det_post(preds, shape_list)
    # PP-OCRv6 DetPostProcess 输出 res[0]["points"] = list[ndarray(N,2)]
    boxes = res[0]["points"]
    return [np.array(b, dtype=np.float32) for b in boxes]


def _rec_text(crop):
    if rec_model is None:
        return "", 0.0
    data = {"image": cv2.imencode(".jpg", crop)[1].tobytes()}
    batch = transform(data, rec_ops)
    images = np.expand_dims(batch[0], axis=0)
    preds = rec_model(paddle.to_tensor(images))
    res = rec_post(preds)
    return res[0]["text"], res[0]["score"]


app = FastAPI(title="AIStation PaddleX OCR Inference")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@app.get("/health")
async def health():
    return {"status": "ok", "model": "paddlex-ocr"}


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
    detections = []
    boxes = _det_boxes(img)
    for box in boxes:
        text, conf = _rec_text(img)
        detections.append({
            "text": text, "confidence": float(conf),
            "box": box.astype(float).tolist(),
        })
    elapsed = round((time.time() - start) * 1000, 1)
    return {"success": True, "detections": detections, "inference_time_ms": elapsed}


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
'''.replace("__API_KEY__", repr(api_key)).replace("__DEVICE__", repr(device_arg))


async def start_deployment(deploy_id: int):
    async with async_db_session.begin() as db:
        row = await db.get(TrainDeploy, deploy_id)
        if not row or row.status in ("deploying", "running"):
            return
        await db.execute(
            update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                status="deploying", started_at=datetime.now()
            )
        )
    asyncio.create_task(_execute_deployment(deploy_id))


async def stop_deployment(deploy_id: int):
    entry = _deploy_running.get(deploy_id)
    if entry:
        entry["cancel"] = True
        if entry.get("container_id"):
            from .docker_utils import stop_container
            await stop_container(entry["container_id"])
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                status="stopped", finished_at=datetime.now()
            )
        )


def _is_host_port_used(port: int) -> bool:
    """探测宿主机端口是否已被占用（127.0.0.1）。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


async def _docker_published_host_ports() -> set[int]:
    """收集 Docker 所有容器（含已停止）已发布的宿主机端口，避免端口竞态。"""
    def _sync() -> set[int]:
        used: set[int] = set()
        try:
            for c in docker_client.containers.list(all=True):
                bindings = (c.attrs or {}).get("HostConfig", {}).get("PortBindings") or {}
                for _, host_bindings in bindings.items():
                    for b in host_bindings:
                        try:
                            used.add(int(b["HostPort"]))
                        except (KeyError, TypeError, ValueError):
                            continue
        except Exception as e:
            log.debug(f"cannot list docker published ports: {e}")
        return used

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


def _find_available_port(
    start: int = 9001, end: int = 9999, excluded: set[int] | None = None,
    docker_used: set[int] = frozenset(),
) -> int:
    """在 [start, end] 内寻找可用端口。

    同时排除：调用方传入的已预留端口、Docker 已发布端口、以及本机 socket 已占用端口。
    """
    used = set(excluded or ())
    used |= set(docker_used)
    for port in range(start, end + 1):
        if port in used:
            continue
        if not _is_host_port_used(port):
            return port
    raise Exception(f"no available port found in range {start}-{end}")


def _is_port_conflict_error(exc: Exception) -> bool:
    """判断 Docker APIError 是否为端口被占（TOCTOU 竞态重试的依据）。"""
    msg = str(exc).lower()
    return any(k in msg for k in (
        "port is already allocated",
        "port already allocated",
        "address already in use",
    ))


async def _container_exists(container_id: str | None) -> bool:
    """判断容器是否仍存在于 Docker 中。

    NotFound（容器确实不存在）返回 False；其余异常（daemon 不可达等）视为
    "无法证明容器不存在"，返回 True，避免恢复逻辑把 daemon 故障误判为容器丢失。
    """
    if not container_id:
        return False

    def _sync() -> bool:
        try:
            docker_client.containers.get(container_id)
            return True
        except docker.errors.NotFound:
            return False
        except Exception:
            return True

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync)


async def _wait_server_healthy(container, host_port: int, timeout: int = 60, interval: float = 2.0) -> str:
    """轮询推理服务 /health 直至就绪。返回空串表示健康，否则返回失败原因。"""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    async with httpx.AsyncClient(timeout=2.0) as client:
        while True:
            try:
                status = await loop.run_in_executor(None, lambda: container.status)
                if status in ("exited", "dead"):
                    return f"container exited with status {status} before health check passed"
            except Exception as e:
                return f"container status check failed: {e}"
            try:
                resp = await client.get(f"http://127.0.0.1:{host_port}/health")
                if resp.status_code == 200:
                    return ""
            except Exception:
                pass
            if loop.time() >= deadline:
                return "deploy health check timeout"
            await asyncio.sleep(interval)


async def recover_orphan_deploys() -> None:
    """回收孤儿部署：running/deploying 但容器不存在的部署 → 标记 failed。

    后端重启后，在途部署的容器丢失或从未存在（部署中崩溃），状态会永久卡在
    running/deploying，需要一次性回收。
    """
    async with async_db_session() as db:
        rows = (await db.execute(
            select(TrainDeploy).where(TrainDeploy.status.in_(("running", "deploying")))
        )).scalars().all()
    for d in rows:
        # 仅当容器被确认不存在（NotFound）才回收；daemon 不可达时 _container_exists 返回
        # True（"无法证明缺失"），跳过以免误杀在途部署。
        if await _container_exists(d.container_id):
            continue
        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainDeploy).where(TrainDeploy.id == d.id).values(
                    status="failed", error_log="deploy 会话已断开（容器丢失）",
                    finished_at=datetime.now(), container_id=None
                )
            )
        log.info(f"deploy {d.id} marked failed: container lost or session disconnected")


async def start_deploy_recovery() -> None:
    try:
        await recover_orphan_deploys()
    except Exception as e:
        log.error(f"deploy orphan recovery failed: {e}")


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

        if deploy.framework == TrainFramework.PYTORCH_OCR_REC:
            # 双模型（det + rec）关联尚未实现：rec 权重需先有 det 模型才能组成完整 OCR 链路，
            # 单独部署 rec 模型会产出语义错误（det.pt 被加载进 det 网络）。暂不支持。
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                        status="failed",
                        error_log="rec 部署需要 det+rec 双模型关联，暂不支持",
                        finished_at=datetime.now(),
                    )
                )
            return

        is_ocr = _is_ocr_framework(deploy.framework)
        is_paddlex = _is_paddlex_framework(deploy.framework)
        image = PADDLEX_IMAGE if is_paddlex else (OCR_IMAGE if is_ocr else DOCKER_IMAGE)

        if is_ocr or is_paddlex:
            # OCR/PaddleX 部署必须有显式的 rec 模型：仅挂载 det 权重时推理管线会产出垃圾文本。
            # rec_model_path 缺失 → 拒绝部署。
            rec_model_path = (deploy.hyperparams or {}).get("rec_model_path")
            if not rec_model_path:
                async with async_db_session.begin() as db:
                    await db.execute(
                        update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                            status="failed",
                            error_log="OCR 部署需要提供 rec_model_path",
                            finished_at=datetime.now(),
                        )
                    )
                return

        await pull_image(image)

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

        if is_ocr:
            # OCR：det 训练产物统一命名 det.pt；rec 模型按 hyperparams.rec_model_path 下载为 rec.pt
            det_pt_path = os.path.join(model_dir, "det.pt")
            if model_local_path != det_pt_path:
                import shutil
                shutil.copy2(model_local_path, det_pt_path)
            rec_data = s3_client.download_fileobj(rec_model_path)
            rec_local_path = os.path.join(model_dir, "rec.pt")
            with open(rec_local_path, "wb") as f:
                f.write(rec_data.read())
        elif is_paddlex:
            # PaddleX：det 产物统一命名 det.pdparams；rec 为 rec.pdparams
            det_pd_path = os.path.join(model_dir, "det.pdparams")
            if model_local_path != det_pd_path:
                import shutil
                shutil.copy2(model_local_path, det_pd_path)
            rec_data = s3_client.download_fileobj(rec_model_path)
            rec_local_path = os.path.join(model_dir, "rec.pdparams")
            with open(rec_local_path, "wb") as f:
                f.write(rec_data.read())
        else:
            # Ensure file is named best.pt inside model mount
            best_pt_path = os.path.join(model_dir, "best.pt")
            if model_local_path != best_pt_path:
                import shutil
                shutil.copy2(model_local_path, best_pt_path)

        # Write inference server script
        if is_paddlex:
            server_script = _generate_paddlex_server_script(deploy.api_key, deploy.device)
        elif is_ocr:
            server_script = _generate_ocr_server_script(deploy.api_key, deploy.device)
        else:
            server_script = _generate_server_script(deploy.api_key, deploy.device)
        server_path = os.path.join(server_dir, "server.py")
        with open(server_path, "w", encoding="utf-8") as f:
            f.write(server_script)

        # Determine port（自动选端口时同时排除 DB 已预留 + Docker 已发布 + socket 已占用）
        host_port = deploy.host_port
        if not host_port:
            async with async_db_session() as db:
                rows = (await db.execute(
                    select(TrainDeploy.host_port).where(TrainDeploy.host_port > 0)
                )).scalars().all()
            reserved = set(rows)
            docker_used = await _docker_published_host_ports()
            host_port = _find_available_port(excluded=reserved, docker_used=docker_used)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(host_port=host_port)
                )

        # TOCTOU 兜底：DB 预留与容器实际绑定之间存在竞态窗口，两个并发部署可能选到同一端口。
        # run_container 抛出端口冲突 APIError 时，换新端口（排除当前端口）重试一次。
        async def _launch(port: int):
            return await run_container(
                image,
                ["python3", "/server/server.py"],
                volumes={
                    model_dir: {"bind": "/model", "mode": "ro"},
                    server_dir: {"bind": "/server", "mode": "ro"},
                },
                ports={f"{8000}/tcp": port},
                gpu_id=deploy.device if deploy.device != "cpu" else None,
                entrypoint="",
                shm_size="4g" if is_paddlex else None,
            )

        try:
            container = await _launch(host_port)
        except docker.errors.APIError as e:
            if not _is_port_conflict_error(e):
                raise
            log.warning(f"deploy {deploy_id} port {host_port} conflict, retrying with a fresh port")
            host_port = _find_available_port(excluded={host_port})
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(host_port=host_port)
                )
            container = await _launch(host_port)
        container_id = container.id
        _deploy_running[deploy_id] = {"container_id": container_id, "cancel": False}

        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                    container_id=container_id, api_url=f"http://127.0.0.1:{host_port}",
                    status="running"
                )
            )

        # 健康探活：等待推理服务就绪（最多 60s）；异常则标记 failed 并清理
        probe_error = await _wait_server_healthy(container, host_port)
        if probe_error:
            log.error(f"deploy {deploy_id} health probe failed: {probe_error}")
            await remove_container(container_id)
            if not _deploy_running.get(deploy_id, {}).get("cancel"):
                async with async_db_session.begin() as db:
                    await db.execute(
                        update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                            status="failed", error_log=probe_error,
                            finished_at=datetime.now(), container_id=None
                        )
                    )
            return
        log.info(f"deploy {deploy_id} healthy at http://127.0.0.1:{host_port}/health")

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
            error_msg = (await get_container_error_tail(container_id)).strip()
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
