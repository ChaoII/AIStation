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
    find_task_containers,
    follow_container_logs,
    get_container_error_tail,
    pull_image,
    remove_container,
    run_container,
    stop_container,
)
from .model import TrainDeploy, TrainFramework, TrainModel

_deploy_running: dict[int, dict] = {}
# 已请求取消的部署 id -> 请求时间：stop_deployment 后，在途 _execute_deployment
# 仍据此判断"取消"，避免容器被停/移除后误把状态写回 failed。
# 带时间戳的映射（而非无界集合）便于过期清理，防止重启场景下墓碑长期残留
# 压制后续新一次启动的状态写入。
_deploy_cancelled: dict[int, datetime] = {}

# 后台任务持有集合：防止 asyncio.create_task 返回的 Task 在进程退出时被 cancel
# 而留下半成品；任务完成/取消后自动丢弃引用。
_bg_tasks: set[asyncio.Task] = set()


def _spawn(coro) -> asyncio.Task:
    """创建后台任务并持有引用，完成/取消时自动丢弃。"""
    task = asyncio.create_task(coro)
    if task is not None:
        _bg_tasks.add(task)
        task.add_done_callback(_bg_tasks.discard)
    return task


def _cleanup_deploy_half_products(model_dir: str | None, server_dir: str | None) -> None:
    """失败后清理部署的半成品目录（下载的模型权重与服务脚本），保留 deploy.log 供排查。"""
    import shutil
    for d in (model_dir, server_dir):
        if d:
            shutil.rmtree(d, ignore_errors=True)


DOCKER_IMAGE = "ultralytics/ultralytics:latest"
PADDLEX_IMAGE = "paddlex:latest"

DEPLOY_RECOVERY_INTERVAL = 30
# 取消墓碑保留时长：超过后自动失效，避免无限增长
DEPLOY_CANCEL_TTL = 3600


def _mark_deploy_cancelled(deploy_id: int) -> None:
    """记录取消墓碑（带时间戳），并顺带清理过期项。"""
    now = datetime.now()
    expired = [
        k for k, ts in _deploy_cancelled.items()
        if (now - ts).total_seconds() > DEPLOY_CANCEL_TTL
    ]
    for k in expired:
        _deploy_cancelled.pop(k, None)
    _deploy_cancelled[deploy_id] = now


def _is_deploy_cancelled(deploy_id: int) -> bool:
    """是否已请求取消；过期墓碑视为失效并清理。"""
    ts = _deploy_cancelled.get(deploy_id)
    if ts is None:
        return False
    if (datetime.now() - ts).total_seconds() > DEPLOY_CANCEL_TTL:
        _deploy_cancelled.pop(deploy_id, None)
        return False
    return True


def deploy_exit_status(cancel: bool, exit_code: int) -> str | None:
    """容器退出后的部署状态：取消由 stop 处理；否则成功=stopped、失败=failed。"""
    if cancel:
        return None
    return "stopped" if exit_code == 0 else "failed"


def is_port_reusable(status: str) -> bool:
    """已停止/失败/待开始的部署端口可复用；部署中/运行中不可复用。"""
    return status not in ("deploying", "running")


def _is_paddlex_framework(framework: TrainFramework) -> bool:
    """PaddleX 框架（PP-OCRv6 det/rec 训练产物 .pdparams 部署）。"""
    return framework == TrainFramework.PADDLEX


async def resolve_deploy_spec(deploy, model_rec) -> tuple[str, str]:
    """推断部署 OCR 的 (mode, size)：deploy.hyperparams → 训练任务 → 默认。

    部署 hyperparams 未显式给出合法 mode/model_size 时，回溯产出该模型的训练
    任务 hyperparams；仍缺失则回退 ("det", "tiny")。与 eval/predict 的规格推断
    口径一致：model_id 为模型版本 id，与训练任务的 model_repo_id 对应。
    """
    hp = deploy.hyperparams or {}
    # 归一化后再判定：形如 "Small" 的非法值不能靠 or 兜底（其非空会跳过回查）
    mode = str(hp.get("mode", "") or "").lower()
    size = str(hp.get("model_size", "") or "").lower()
    if mode not in ("det", "rec") or size not in ("tiny", "small", "medium"):
        from sqlalchemy import desc, select

        from .model import TrainTask

        async with async_db_session() as db:
            task = (await db.execute(
                select(TrainTask).where(TrainTask.model_repo_id == deploy.model_id)
                .order_by(desc(TrainTask.id)).limit(1)
            )).scalar_one_or_none()
        thp = (task.hyperparams or {}) if task else {}
        mode = mode if mode in ("det", "rec") else str(thp.get("mode", "det")).lower()
        size = size if size in ("tiny", "small", "medium") else str(thp.get("model_size", "tiny")).lower()
    return (
        mode if mode in ("det", "rec") else "det",
        size if size in ("tiny", "small", "medium") else "tiny",
    )


def _generate_server_script(
    api_key: str, device: str, conf: float = 0.25, iou: float = 0.45, imgsz: int = 640
) -> str:
    device_arg = device if device != "cpu" else "cpu"
    return f'''#!/usr/bin/env python3
"""Auto-generated inference server for AIStation model deployment."""
import os, sys, json, time, asyncio, subprocess

# 依赖按需安装：仅在 fastapi 缺失时安装，避免每次启动都 pip install 拖慢健康检查
try:
    import fastapi  # noqa: F401
except ImportError:
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
    results = model(img, device="{device_arg}", conf={conf}, iou={iou}, imgsz={imgsz}, verbose=False)[0]
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


def _generate_paddlex_server_script(
    api_key: str, device: str, mode: str = "det", size: str = "tiny"
) -> str:
    """生成 PaddleX OCR 推理服务脚本（PP-OCRv6 det + rec，.pdparams 权重）。

    运行在 paddlex:latest 镜像（内置 PaddleOCR），加载 /model/det.pdparams +
    /model/rec.pdparams，/predict 返回 [{text, confidence, box}]。
    cfg 由模型规格（``mode``/``size``）驱动，避免 tiny/medium 部署套用 small 架构。
    """
    device_arg = device if device != "cpu" else "cpu"
    if mode not in ("det", "rec"):
        mode = "det"
    if size not in ("tiny", "small", "medium"):
        size = "tiny"
    det_cfg = f"configs/det/PP-OCRv6/PP-OCRv6_{size}_det.yml"
    rec_cfg = f"configs/rec/PP-OCRv6/PP-OCRv6_{size}_rec.yml"
    return r'''#!/usr/bin/env python3
"""Auto-generated PaddleX OCR inference server (PP-OCRv6 det + rec)."""
import os, sys, json, time, io, subprocess

# 依赖按需安装：仅在 fastapi 缺失时安装，避免每次启动都 pip install
try:
    import fastapi  # noqa: F401
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "fastapi", "uvicorn", "python-multipart"], check=True)

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

API_KEY = __API_KEY__
HOST = "0.0.0.0"
PORT = 8000
DEVICE = __DEVICE__


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


DET_CFG = __DET_CFG__
REC_CFG = __REC_CFG__
MODE = __MODE__
SIZE = __SIZE__
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


def _crop_box(img, box):
    """按检测框裁剪文字区域（越界保护），rec 识别应基于裁剪图而非整图。"""
    x, y, w, h = cv2.boundingRect(np.asarray(box, dtype=np.int32))
    ih, iw = img.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(iw, x + w), min(ih, y + h)
    if x2 <= x1 or y2 <= y1:
        # 越界/空裁剪：返回 None 让调用方跳过该框，绝不能回退整图识别
        return None
    return img[y1:y2, x1:x2]


app = FastAPI(title="AIStation PaddleX OCR Inference")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@app.get("/health")
async def health():
    return {"status": "ok", "model": "paddlex-ocr", "mode": MODE, "size": SIZE}


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
        text, conf = "", 0.0
        if rec_model is not None:
            crop = _crop_box(img, box)
            if crop is None:
                continue
            text, conf = _rec_text(crop)
        detections.append({
            "text": text, "confidence": float(conf),
            "box": box.astype(float).tolist(),
        })
    elapsed = round((time.time() - start) * 1000, 1)
    return {"success": True, "detections": detections, "inference_time_ms": elapsed}


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
'''.replace("__API_KEY__", repr(api_key)).replace("__DEVICE__", repr(device_arg)) \
        .replace("__DET_CFG__", repr(det_cfg)).replace("__REC_CFG__", repr(rec_cfg)) \
        .replace("__MODE__", repr(mode)).replace("__SIZE__", repr(size))


async def start_deployment(deploy_id: int):
    # 原子守卫：单条条件 UPDATE 抢占，避免并发 start 的 TOCTOU 重复入队
    async with async_db_session.begin() as db:
        result = await db.execute(
            update(TrainDeploy)
            .where(TrainDeploy.id == deploy_id, TrainDeploy.status.notin_(("deploying", "running")))
            .values(status="deploying", started_at=datetime.now())
        )
        if result.rowcount == 0:
            # 影响 0 行：要么不存在，要么已在部署/运行中
            return
    # 全新启动前清掉该 id 的历史取消墓碑，避免新一次运行被旧记录压制。
    _deploy_cancelled.pop(deploy_id, None)
    _spawn(_execute_deployment(deploy_id))


async def stop_deployment(deploy_id: int):
    """停止部署并停掉真实容器。

    优先内存注册表；后端重启后注册表丢失，则回退到 DB 的 container_id；
    DB 也没有时按 label 查找残留容器。二者皆无则仅落库为 stopped。

    处于 deploying/running 的部署，无论注册表是否存在，都记录取消墓碑，
    以便在途执行器观察到取消、不再拉起新容器。
    """
    entry = _deploy_running.pop(deploy_id, None)
    if entry:
        entry["cancel"] = True
    container_id = entry.get("container_id") if entry else None
    db_status = None
    async with async_db_session() as db:
        row = await db.get(TrainDeploy, deploy_id)
        db_status = row.status if row else None
        if not container_id:
            container_id = row.container_id if row else None
    # 活跃状态一律记录取消（含注册表丢失但 DB 仍在 deploying/running 的场景）
    if db_status in ("deploying", "running"):
        _mark_deploy_cancelled(deploy_id)
    if not container_id:
        cids = find_task_containers("deploy", deploy_id)
        container_id = cids[0] if cids else None
    if container_id:
        await stop_container(container_id)
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                status="stopped", finished_at=datetime.now(), container_id=None
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
    """回收孤儿部署：容器存活 → 重建内存注册表；容器确认丢失 → 标记 failed。

    后端重启后 `_deploy_running` 为空，存活容器需要重建注册表（标记 adopted），
    之后 stop_deployment 才能直接停掉它。adopted 条目没有在途协程负责收尾，
    因此每次周期都要复检容器是否仍在；一旦丢失即释放注册表并把行标记 failed。

    注意：`deploying` 是拉镜像/下载模型等启动中的在途状态，此时 container_id
    可能尚未落库（NULL/旧值），不能据此判定容器丢失；仅当行确为 `running`
    且 container_id 非空、容器又确实不存在时，才标记 failed。
    """
    async with async_db_session() as db:
        rows = (await db.execute(
            select(TrainDeploy).where(TrainDeploy.status.in_(("running", "deploying")))
        )).scalars().all()
    for d in rows:
        entry = _deploy_running.get(d.id)
        # 在途执行器拥有（非 adopted）的部署由其自行维护，恢复逻辑不介入
        # （30s 周期对账可能与启动竞态）
        if entry and not entry.get("adopted"):
            continue
        # _container_exists 仅在确认 NotFound 时返回 False；daemon 不可达返回 True
        # （"无法证明缺失"），此时按存活处理，避免误杀在途部署。
        if await _container_exists(d.container_id):
            # 标记 adopted：该条目由恢复逻辑接管而非执行器，后续周期需持续复检，
            # 容器若消失才能及时回收端口/状态
            _deploy_running[d.id] = {
                "container_id": d.container_id, "cancel": False, "adopted": True
            }
            continue
        # 容器确认丢失：清理已接管的注册表条目（无在途协程会替它收尾）
        if entry:
            _deploy_running.pop(d.id, None)
        # deploying 属于在途启动，跳过；仅确认丢失的 running 行标 failed
        if d.status != "running" or not d.container_id:
            continue
        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainDeploy).where(TrainDeploy.id == d.id).values(
                    status="failed", error_log="部署容器已丢失",
                    finished_at=datetime.now(), container_id=None
                )
            )
        log.info(f"deploy {d.id} marked failed: container lost or session disconnected")


async def start_deploy_recovery() -> None:
    """周期对账部署状态：立即执行一次，之后每 30s 重建注册表/回收孤儿。"""
    while True:
        try:
            await recover_orphan_deploys()
        except Exception as e:
            log.error(f"deploy orphan recovery failed: {e}")
        await asyncio.sleep(DEPLOY_RECOVERY_INTERVAL)


async def _execute_deployment(deploy_id: int):
    container_id = None
    export_dir = None
    model_dir = None
    server_dir = None
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

        is_paddlex = _is_paddlex_framework(deploy.framework)
        image = PADDLEX_IMAGE if is_paddlex else DOCKER_IMAGE

        if is_paddlex:
            # PaddleX 部署必须有显式的 rec 模型：仅挂载 det 权重时推理管线会产出垃圾文本。
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

        if is_paddlex:
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
            mode, size = await resolve_deploy_spec(deploy, model_rec)
            server_script = _generate_paddlex_server_script(
                deploy.api_key, deploy.device, mode=mode, size=size
            )
        else:
            hp = deploy.hyperparams or {}
            server_script = _generate_server_script(
                deploy.api_key, deploy.device,
                conf=hp.get("conf", 0.25), iou=hp.get("iou", 0.45),
                imgsz=hp.get("imgsz", 640),
            )
        server_path = os.path.join(server_dir, "server.py")
        with open(server_path, "w", encoding="utf-8") as f:
            f.write(server_script)

        # Determine port（自动选端口时同时排除 DB 已预留 + Docker 已发布 + socket 已占用）
        host_port = deploy.host_port
        if not host_port:
            async with async_db_session() as db:
                rows = (await db.execute(
                    select(TrainDeploy.host_port).where(
                        TrainDeploy.host_port > 0,
                        TrainDeploy.status.in_(("deploying", "running")),
                    )
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
                labels={"aistation.task_kind": "deploy", "aistation.task_id": str(deploy_id)},
            )

        # 启动/拉镜像/下载模型期间可能已被 stop/delete 取消：不要在取消后拉起新容器
        if _is_deploy_cancelled(deploy_id):
            log.info(f"deploy {deploy_id} cancelled before container launch")
            return

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
        # 先登记注册表，便于 stop_deployment 能命中并停掉容器
        _deploy_running[deploy_id] = {"container_id": container_id, "cancel": False}
        # 拉起容器期间被取消：立即清理，不写 running
        if _is_deploy_cancelled(deploy_id):
            log.info(f"deploy {deploy_id} cancelled during launch, removing container")
            await remove_container(container_id)
            return

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
            cancelled = _is_deploy_cancelled(deploy_id) or bool(
                _deploy_running.get(deploy_id, {}).get("cancel")
            )
            if not cancelled:
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

        cancel = _is_deploy_cancelled(deploy_id) or bool(
            _deploy_running.get(deploy_id, {}).get("cancel")
        )
        status = deploy_exit_status(cancel, exit_code)
        if status == "failed":
            error_msg = (await get_container_error_tail(container_id)).strip()
        if status is not None:
            await remove_container(container_id)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                        status=status, finished_at=datetime.now(),
                        container_id=None, error_log=(error_msg if status == "failed" else None),
                    )
                )

    except Exception as e:
        log.error(f"deploy {deploy_id} failed: {e}")
        # 已请求取消（stop_deployment）时容器被主动移除，wait 可能抛错，不要覆盖为 failed
        if not _is_deploy_cancelled(deploy_id):
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                        status="failed", error_log=str(e), finished_at=datetime.now()
                    )
                )
            # 失败后清理部署半成品（模型权重/服务脚本），保留 deploy.log
            _cleanup_deploy_half_products(model_dir, server_dir)
    finally:
        _deploy_running.pop(deploy_id, None)
        _deploy_cancelled.pop(deploy_id, None)
        if container_id:
            await remove_container(container_id)
