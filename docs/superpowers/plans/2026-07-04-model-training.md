# Model Training Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an industrial-grade model training pipeline as a plugin module, supporting PaddleX and Ultralytics frameworks via Docker, with model repository (versioned), real-time log streaming, evaluation, and deployment to existing inference pipeline.

**Architecture:** Plugin module (`module_train`) with async subprocess-based scheduler, Docker SDK for container lifecycle, WebSocket for log streaming, PostgreSQL + RustFS for artifact storage. Reuses existing inference scheduler pattern.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, PostgreSQL, Redis, Docker SDK (`docker-py`), WebSocket, Vue 3 + Element Plus + TypeScript

---

## File Structure

### Backend (new plugin)
```
backend/app/plugin/module_train/
  plugin.toml
  __init__.py
  model.py              # train_models, train_tasks, train_evals tables
  schema.py             # Pydantic request/response schemas
  controller.py         # REST endpoints
  service.py            # Business logic
  docker_utils.py       # Docker image/container management
  scheduler.py          # Async training task scheduler
  exporter.py           # Dataset format exporter (YOLO / PaddleX)
```

### Frontend (new pages)
```
frontend/src/views/module_train/
  repo/index.vue        # Model repository with version management
  task/index.vue        # Training task list + create dialog
  task/detail.vue       # Training detail (real-time logs)
  eval/index.vue        # Model evaluation

frontend/src/api/
  module_train.ts       # API client
```

### Backend (modified)
```
backend/app/scripts/init_app.py  # Menu registration (seeds)
```

### Database migration
- New: `train_models`, `train_tasks`, `train_evals` tables

---

## Global Constraints

- All SQLAlchemy models inherit `ModelMixin` + `UserMixin` for audit fields
- All REST endpoints use `Depends(AuthPermission([...]))` for auth
- Response format: `SuccessResponse(data=..., msg=...)` / `ErrorResponse(msg=...)`
- Frontend router is hash-based; dynamic routes from backend menu data
- Frontend API functions follow naming convention: `getXxxList`, `getXxxDetail`, `createXxx`, `updateXxx`, `deleteXxx`
- Docker SDK: use `docker-py` (`docker` package)
- WebSocket target URL: `ws://host/api/v1/ws/train/logs?task_id={id}`
- Menu parent: `Annotation` with route_path `/annotation`

---

### Task 1: Backend Plugin Scaffold + Data Models

**Files:**
- Create: `backend/app/plugin/module_train/plugin.toml`
- Create: `backend/app/plugin/module_train/__init__.py`
- Create: `backend/app/plugin/module_train/model.py`
- Create: `backend/app/plugin/module_train/schema.py`
- Create: `backend/app/alembic/versions/xxxx_train_models.py`

**Interfaces:**
- Consumes: `ModelMixin`, `UserMixin` from `app.core.base_model`
- Consumes: `async_db_session` from `app.core.database`
- Produces: `TrainModel`, `TrainTask`, `TrainEval` SQLAlchemy models
- Produces: `TrainModelSchema`, `TrainTaskCreateSchema`, `TrainTaskOutSchema`, `TrainEvalCreateSchema`, `TrainEvalOutSchema` Pydantic schemas

- [ ] **Step 1: Create `plugin.toml`**

```toml
name = "train"
title = "模型训练子系统"
tags = ["train", "paddlex", "ultralytics"]
```

- [ ] **Step 2: Create `__init__.py`** (empty, marks directory as Python package)

- [ ] **Step 3: Create `model.py` with three tables**

```python
import enum
from sqlalchemy import String, Integer, Float, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.base_model import ModelMixin, UserMixin


class TrainStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrainFramework(str, enum.Enum):
    PADDLEX = "paddlex"
    ULTRALYTICS = "ultralytics"


class TrainModel(ModelMixin, UserMixin):
    __tablename__ = "train_models"
    name: Mapped[str] = mapped_column(String(128), comment="模型名称")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), comment="训练框架")
    version: Mapped[str] = mapped_column(String(32), comment="语义版本号")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="RustFS 存储路径")
    format: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="导出格式 ONNX/Paddle/TorchScript")
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="评估指标")
    annotation_dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="来源数据集ID")
    status: Mapped[str] = mapped_column(String(16), default="draft", comment="draft/released/archived")


class TrainTask(ModelMixin, UserMixin):
    __tablename__ = "train_tasks"
    name: Mapped[str] = mapped_column(String(128), comment="任务名称")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), comment="训练框架")
    dataset_id: Mapped[int] = mapped_column(Integer, comment="数据集ID")
    model_repo_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="产出模型ID")
    base_model_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="基础模型ID")
    docker_image: Mapped[str] = mapped_column(String(256), comment="Docker 镜像")
    hyperparams: Mapped[dict] = mapped_column(JSONB, default=dict, comment="超参数")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="进度0-100")
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误日志")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")


class TrainEval(ModelMixin, UserMixin):
    __tablename__ = "train_evals"
    model_repo_id: Mapped[int] = mapped_column(Integer, comment="模型版本ID")
    eval_dataset_id: Mapped[int] = mapped_column(Integer, comment="评估数据集ID")
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="评估指标")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="评估日志")
```

- [ ] **Step 4: Create `schema.py`**

```python
from datetime import datetime
from pydantic import BaseModel, Field

class TrainModelCreateSchema(BaseModel):
    name: str = Field(max_length=128)
    framework: str
    annotation_dataset_id: int | None = None

class TrainModelOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    framework: str
    version: str
    storage_path: str | None
    format: str | None
    metrics: dict | None
    status: str
    annotation_dataset_id: int | None
    created_id: int | None
    created_time: datetime | None

class TrainTaskCreateSchema(BaseModel):
    name: str = Field(max_length=128)
    framework: str
    dataset_id: int
    base_model_id: int | None = None
    hyperparams: dict = Field(default_factory=dict)

class TrainTaskOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    framework: str
    dataset_id: int
    model_repo_id: int | None
    docker_image: str
    hyperparams: dict
    status: str
    progress: int
    error_log: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_id: int | None
    created_time: datetime | None

class TrainEvalCreateSchema(BaseModel):
    model_repo_id: int
    eval_dataset_id: int

class TrainEvalOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    model_repo_id: int
    eval_dataset_id: int
    metrics: dict | None
    status: str
    log: str | None
    created_time: datetime | None
```

- [ ] **Step 5: Create Alembic migration** (auto-generate with `uv run main.py revision --env=dev`)

- [ ] **Step 6: Run migration**

```bash
uv run main.py upgrade --env=dev
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/plugin/module_train/ backend/app/alembic/versions/
git commit -m "feat(train): add plugin scaffold and data models"
```

---

### Task 2: Backend API Endpoints

**Files:**
- Create: `backend/app/plugin/module_train/controller.py`
- Create: `backend/app/plugin/module_train/service.py`

**Interfaces:**
- Consumes: `TrainModel`, `TrainTask`, `TrainEval` from `model.py`
- Consumes: `TrainTaskCreateSchema`, `TrainTaskOutSchema`, `TrainModelOutSchema`, `TrainEvalCreateSchema`, `TrainEvalOutSchema` from `schema.py`
- Consumes: `async_db_session`, `AuthPermission`, `AuthSchema`, `SuccessResponse`
- Produces: REST endpoints documented below

- [ ] **Step 1: Create `controller.py`**

```python
from fastapi import APIRouter, Depends
from app.common.response import SuccessResponse
from app.core.dependencies import AuthPermission
from app.api.v1.module_system.auth.schema import AuthSchema
from .schema import TrainTaskCreateSchema, TrainEvalCreateSchema
from .service import TrainService

router = APIRouter(prefix="/train", tags=["模型训练"])


@router.get("/model/list", summary="模型仓库列表")
async def list_models(auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"]))):
    data = await TrainService.list_models()
    return SuccessResponse(data=data)


@router.get("/model/detail/{model_id}", summary="模型详情")
async def get_model(model_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:model:query"]))):
    data = await TrainService.get_model(model_id)
    return SuccessResponse(data=data)


@router.post("/model/create", summary="创建模型记录")
async def create_model(data: TrainModelCreateSchema, auth: AuthSchema = Depends(AuthPermission(["module_train:model:create"]))):
    result = await TrainService.create_model(data, auth)
    return SuccessResponse(data=result)


@router.post("/task/create", summary="创建训练任务")
async def create_task(data: TrainTaskCreateSchema, auth: AuthSchema = Depends(AuthPermission(["module_train:task:create"]))):
    result = await TrainService.create_task(data, auth)
    return SuccessResponse(data=result, msg="训练任务已创建")


@router.get("/task/list", summary="训练任务列表")
async def list_tasks(auth: AuthSchema = Depends(AuthPermission(["module_train:task:query"]))):
    data = await TrainService.list_tasks()
    return SuccessResponse(data=data)


@router.get("/task/{task_id}/detail", summary="训练任务详情")
async def get_task(task_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:task:query"]))):
    data = await TrainService.get_task(task_id)
    return SuccessResponse(data=data)


@router.post("/task/{task_id}/stop", summary="停止训练")
async def stop_task(task_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:task:update"]))):
    result = await TrainService.stop_task(task_id)
    return SuccessResponse(data=result, msg="训练已停止")


@router.post("/eval/create", summary="创建评估任务")
async def create_eval(data: TrainEvalCreateSchema, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:create"]))):
    result = await TrainService.create_eval(data, auth)
    return SuccessResponse(data=result, msg="评估任务已创建")


@router.get("/eval/list", summary="评估记录列表")
async def list_evals(model_repo_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:query"]))):
    data = await TrainService.list_evals(model_repo_id)
    return SuccessResponse(data=data)
```

- [ ] **Step 2: Create `service.py`**

```python
from sqlalchemy import select, desc
from app.core.database import async_db_session
from .model import TrainModel, TrainTask, TrainEval


class TrainService:

    @classmethod
    async def list_models(cls) -> list[dict]:
        async with async_db_session() as db:
            result = await db.execute(select(TrainModel).order_by(desc(TrainModel.created_time)))
            return [r._asdict() for r in result.scalars().all()]

    @classmethod
    async def get_model(cls, model_id: int) -> dict | None:
        async with async_db_session() as db:
            m = await db.get(TrainModel, model_id)
            return m._asdict() if m else None

    @classmethod
    async def create_model(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            # 计算版本号
            existing = await db.execute(
                select(TrainModel).where(TrainModel.name == data.name).order_by(desc(TrainModel.id)).limit(1)
            )
            last = existing.scalar_one_or_none()
            next_ver = 1
            if last and last.version:
                try:
                    next_ver = int(last.version.replace("v", "")) + 1
                except ValueError:
                    next_ver = 1
            version = f"v{next_ver}"
            m = TrainModel(
                name=data.name, framework=data.framework,
                version=version, annotation_dataset_id=data.annotation_dataset_id,
                created_id=auth.user.id,
            )
            db.add(m)
            await db.flush()
            return {"id": m.id, "version": version}

    @classmethod
    async def list_tasks(cls) -> list[dict]:
        async with async_db_session() as db:
            result = await db.execute(select(TrainTask).order_by(desc(TrainTask.created_time)))
            return [dict(r.__dict__) for r in result.scalars().all()]

    @classmethod
    async def get_task(cls, task_id: int) -> dict | None:
        async with async_db_session() as db:
            t = await db.get(TrainTask, task_id)
            return dict(t.__dict__) if t else None

    @classmethod
    async def create_task(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            image = "paddlecloud/paddlex:3.0" if data.framework == "paddlex" else "ultralytics/ultralytics:latest"
            t = TrainTask(
                name=data.name, framework=data.framework, dataset_id=data.dataset_id,
                base_model_id=data.base_model_id, docker_image=image,
                hyperparams=data.hyperparams, created_id=auth.user.id,
            )
            db.add(t)
            await db.flush()
            return {"id": t.id}

    @classmethod
    async def stop_task(cls, task_id: int) -> dict:
        from .scheduler import stop_training
        await stop_training(task_id)
        return {"id": task_id}

    @classmethod
    async def create_eval(cls, data, auth) -> dict:
        async with async_db_session.begin() as db:
            e = TrainEval(model_repo_id=data.model_repo_id, eval_dataset_id=data.eval_dataset_id, created_id=auth.user.id)
            db.add(e)
            await db.flush()
            return {"id": e.id}

    @classmethod
    async def list_evals(cls, model_repo_id: int) -> list[dict]:
        async with async_db_session() as db:
            result = await db.execute(
                select(TrainEval).where(TrainEval.model_repo_id == model_repo_id).order_by(desc(TrainEval.created_time))
            )
            return [dict(r.__dict__) for r in result.scalars().all()]
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/plugin/module_train/controller.py backend/app/plugin/module_train/service.py
git commit -m "feat(train): add REST API endpoints and service layer"
```

---

### Task 3: Backend Docker Utilities

**Files:**
- Create: `backend/app/plugin/module_train/docker_utils.py`

**Interfaces:**
- Produces: `pull_image(image: str)`, `run_container(image, cmd, volumes, gpu_id, env) -> Container`, `stop_container(container_id)`, `get_container_logs(container_id) -> AsyncIterator[str]`

- [ ] **Step 1: Create `docker_utils.py`**

```python
import asyncio
import json
import docker
from docker.errors import DockerException, ImageNotFound

client = docker.from_env()


async def pull_image(image: str) -> None:
    """异步拉取 Docker 镜像（线程池包装，避免阻塞事件循环）"""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, client.images.pull, image)


def _pull_sync(image: str) -> None:
    client.images.pull(image)


def _run_container(image: str, cmd: list[str], volumes: dict, gpu_id: str, env: dict) -> docker.models.containers.Container:
    device_requests = []
    if gpu_id:
        device_requests = [docker.types.DeviceRequest(device_ids=[gpu_id], capabilities=[["gpu"]])]
    return client.containers.run(
        image, cmd,
        volumes=volumes,
        environment=env,
        device_requests=device_requests,
        detach=True,
        remove=False,
        stderr=True,
    )


async def run_container(image: str, cmd: list[str], volumes: dict, gpu_id: str = "0", env: dict | None = None) -> docker.models.containers.Container:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _run_container, image, cmd, volumes, gpu_id, env or {})


def _stop_container(container_id: str) -> None:
    try:
        c = client.containers.get(container_id)
        c.stop(timeout=10)
        c.remove()
    except docker.errors.NotFound:
        pass


async def stop_container(container_id: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _stop_container, container_id)


async def follow_container_logs(container_id: str) -> "asyncio.Queue[str]":
    """异步逐行读取容器日志，返回 asyncio.Queue"""
    queue: asyncio.Queue = asyncio.Queue()
    container = client.containers.get(container_id)
    loop = asyncio.get_event_loop()

    def _stream():
        for line in container.logs(stream=True, follow=True, timestamps=False):
            loop.call_soon_threadsafe(queue.put_nowait, line.decode("utf-8", errors="replace").rstrip("\n"))
        loop.call_soon_threadsafe(queue.put_nowait, "__EOF__")

    thread = loop.run_in_executor(None, _stream)
    return queue
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/plugin/module_train/docker_utils.py
git commit -m "feat(train): add Docker utilities for container lifecycle"
```

---

### Task 4: Backend Training Scheduler

**Files:**
- Create: `backend/app/plugin/module_train/scheduler.py`

**Interfaces:**
- Consumes: `TrainTask`, `TrainTask.status` from `model.py`
- Consumes: `run_container`, `stop_container`, `pull_image`, `follow_container_logs` from `docker_utils.py`
- Consumes: `async_db_session`
- Produces: `start_training(task_id)`, `stop_training(task_id)`, `start_scheduler()`, `_running_tasks: dict`
- Produces: WebSocket log broadcasting (via `ws.py`)

- [ ] **Step 1: Create `scheduler.py`**

```python
import asyncio
import json
import os
import tempfile
from datetime import datetime

from sqlalchemy import select, update

from app.core.database import async_db_session
from app.core.logger import log

from .model import TrainTask, TrainStatus, TrainFramework
from .docker_utils import run_container, stop_container, pull_image, follow_container_logs
from .ws import broadcast_log

_running_tasks: dict[int, dict] = {}
_scheduler_task: asyncio.Task | None = None
MAX_CONCURRENT = 1


async def start_scheduler():
    """启动调度器后台任务"""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())
        log.info("train scheduler started")


async def _scheduler_loop():
    while True:
        try:
            async with async_db_session() as db:
                result = await db.execute(
                    select(TrainTask).where(TrainTask.status == TrainStatus.PENDING)
                    .order_by(TrainTask.created_time.asc()).limit(MAX_CONCURRENT)
                )
                pending = result.scalars().all()

            for task in pending:
                asyncio.create_task(_execute_training(task.id))
                async with async_db_session.begin() as db:
                    await db.execute(
                        update(TrainTask).where(TrainTask.id == task.id).values(status=TrainStatus.RUNNING)
                    )
        except Exception as e:
            log.error(f"train scheduler error: {e}")

        await asyncio.sleep(1)


async def _build_export_dir(task_id: int) -> str:
    """创建训练输出目录"""
    export_dir = os.path.join(tempfile.gettempdir(), "train_output", str(task_id))
    os.makedirs(export_dir, exist_ok=True)
    return export_dir


def _build_ultralytics_cmd(hp: dict, data_dir: str, export_dir: str) -> list[str]:
    epochs = hp.get("epochs", 100)
    batch = hp.get("batch", 16)
    lr = hp.get("lr", 0.01)
    model_name = hp.get("model", "yolo11n.pt")
    return ["yolo", "train", f"model={model_name}", f"data={data_dir}/dataset.yaml",
            f"epochs={epochs}", f"batch={batch}", f"lr0={lr}", f"project={export_dir}", "name=exp"]


def _build_paddlex_cmd(hp: dict, data_dir: str, export_dir: str) -> list[str]:
    epochs = hp.get("epochs", 100)
    batch = hp.get("batch", 16)
    lr = hp.get("lr", 0.01)
    model_name = hp.get("model", "PP-YOLOE")
    return ["paddlex", "--model", model_name, "--data", data_dir,
            "--epochs", str(epochs), "--batch", str(batch), "--lr", str(lr),
            "--output", export_dir]


async def _execute_training(task_id: int):
    try:
        async with async_db_session() as db:
            task = await db.get(TrainTask, task_id)
            if not task:
                return

        # 1. 拉取镜像（首次）
        await pull_image(task.docker_image)

        # 2. 导出数据集
        export_dir = await _build_export_dir(task_id)
        data_dir = os.path.join(export_dir, "data")
        os.makedirs(data_dir, exist_ok=True)

        from .exporter import export_dataset
        await export_dataset(task.dataset_id, task.framework, data_dir)

        # 3. 构建命令
        if task.framework == TrainFramework.ULTRALYTICS:
            cmd = _build_ultralytics_cmd(task.hyperparams, data_dir, export_dir)
        else:
            cmd = _build_paddlex_cmd(task.hyperparams, data_dir, export_dir)

        # 4. 启动容器
        container = await run_container(
            task.docker_image, cmd,
            volumes={data_dir: {"bind": data_dir, "mode": "rw"},
                     export_dir: {"bind": export_dir, "mode": "rw"}},
            gpu_id=task.hyperparams.get("gpu_id", "0"),
        )

        _running_tasks[task_id] = {"container_id": container.id, "cancel": False}

        # 5. 更新状态
        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainTask).where(TrainTask.id == task_id).values(
                    status=TrainStatus.RUNNING, started_at=datetime.now()
                )
            )

        # 6. 流式读取日志并广播
        log_queue = await follow_container_logs(container.id)
        while True:
            line = await log_queue.get()
            if line == "__EOF__":
                break
            await broadcast_log(task_id, line)

        # 7. 容器退出，检查状态
        container.reload()
        exit_code = container.attrs["State"]["ExitCode"]

        if _running_tasks.get(task_id, {}).get("cancel"):
            status = TrainStatus.CANCELLED
        elif exit_code == 0:
            status = TrainStatus.SUCCESS
            # 导出模型
            from .exporter import export_model
            model_info = await export_model(task_id, task.framework, export_dir)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainTask).where(TrainTask.id == task_id).values(
                        model_repo_id=model_info.get("repo_id"), status=status,
                        progress=100, finished_at=datetime.now()
                    )
                )
        else:
            status = TrainStatus.FAILED
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainTask).where(TrainTask.id == task_id).values(
                        status=status, finished_at=datetime.now()
                    )
                )

        _running_tasks.pop(task_id, None)

    except Exception as e:
        log.error(f"training task {task_id} failed: {e}")
        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainTask).where(TrainTask.id == task_id).values(
                    status=TrainStatus.FAILED, error_log=str(e), finished_at=datetime.now()
                )
            )
        _running_tasks.pop(task_id, None)


async def stop_training(task_id: int) -> None:
    entry = _running_tasks.get(task_id)
    if entry:
        entry["cancel"] = True
        await stop_container(entry["container_id"])
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/plugin/module_train/scheduler.py
git commit -m "feat(train): add async training scheduler with Docker lifecycle"
```

---

### Task 5: Backend WebSocket Log Streaming

**Files:**
- Modify: `backend/app/plugin/module_train/controller.py` (add WebSocket endpoint)

**Interfaces:**
- Produces: `broadcast_log(task_id, line)`, `register_ws(task_id, websocket)`, `unregister_ws(task_id, websocket)`
- Endpoint: `GET /ws/train/logs?task_id={id}` (WebSocket upgrade, on same router as REST)

- [ ] **Step 1: Add WebSocket to `controller.py`**

```python
# At top of file, add:
from fastapi import WebSocket, WebSocketDisconnect, Query
from typing import Dict

_ws_clients: Dict[int, list[WebSocket]] = {}

async def broadcast_log(task_id: int, line: str):
    for ws in _ws_clients.get(task_id, [])[:]:
        try:
            await ws.send_text(line)
        except Exception:
            _ws_clients[task_id].remove(ws)


@router.websocket("/ws/train/logs")
async def train_log_ws(websocket: WebSocket, task_id: int = Query(...)):
    await websocket.accept()
    _ws_clients.setdefault(task_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if task_id in _ws_clients:
            _ws_clients[task_id].remove(websocket)
            if not _ws_clients[task_id]:
                del _ws_clients[task_id]
```

Remove `ws.py` — all logic is in `controller.py`.

- [ ] **Step 2: Update `scheduler.py` import**

```python
# Change from:
# from .ws import broadcast_log
# To:
from .controller import broadcast_log
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/plugin/module_train/controller.py
git rm backend/app/plugin/module_train/ws.py
git commit -m "feat(train): add WebSocket log streaming on controller router"
```

---

### Task 6: Backend Dataset Exporter

**Files:**
- Create: `backend/app/plugin/module_train/exporter.py`

**Interfaces:**
- Produces: `export_dataset(dataset_id, framework, output_dir)` — exports annotations to YOLO/PaddleX format
- Produces: `export_model(task_id, framework, output_dir) -> dict` — copies trained weights, uploads to RustFS, creates TrainModel record

- [ ] **Step 1: Create `exporter.py`**

```python
import os
import json
import shutil
from sqlalchemy import select
from app.core.database import async_db_session
from app.api.v1.module_annotation.dataset.model import AnnotationImageModel
from app.api.v1.module_annotation.annotation.model import AnnotationRecordModel


async def export_dataset(dataset_id: int, framework: str, output_dir: str) -> None:
    """将标注数据集导出为指定框架格式"""
    async with async_db_session() as db:
        result = await db.execute(
            select(AnnotationImageModel).where(AnnotationImageModel.dataset_id == dataset_id)
        )
        images = result.scalars().all()

        if framework == "ultralytics":
            _export_yolo(images, output_dir)
        else:
            _export_paddlex(images, output_dir)


def _export_yolo(images: list, output_dir: str) -> None:
    """YOLO 格式: images/ + labels/ 目录"""
    img_dir = os.path.join(output_dir, "images")
    label_dir = os.path.join(output_dir, "labels")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(label_dir, exist_ok=True)
    classes = set()

    for img in images:
        anns = img.get("annotations", [])
        label_path = os.path.join(label_dir, img.filename.rsplit(".", 1)[0] + ".txt")
        lines = []
        for ann in anns:
            cls_id = ann.get("class_id", 0)
            classes.add(cls_id)
            if ann.get("type") == "AxisAlignedBox":
                x1, y1, x2, y2 = ann["x1"], ann["y1"], ann["x2"], ann["y2"]
                xc = (x1 + x2) / 2
                yc = (y1 + y2) / 2
                w = x2 - x1
                h = y2 - y1
                lines.append(f"{cls_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}")
        if lines:
            with open(label_path, "w") as f:
                f.write("\n".join(lines))

    # 生成 dataset.yaml
    yaml_path = os.path.join(output_dir, "dataset.yaml")
    with open(yaml_path, "w") as f:
        f.write(f"path: {output_dir}\n")
        f.write("train: images\n")
        f.write("val: images\n")
        f.write(f"nc: {len(classes)}\n")
        f.write(f"names: {json.dumps(list(classes))}\n")


def _export_paddlex(images: list, output_dir: str) -> None:
    """PaddleX 格式"""
    # 简化实现：复制图片 + 生成标注 JSON
    img_dir = os.path.join(output_dir, "images")
    os.makedirs(img_dir, exist_ok=True)
    # 实际项目中需要按 PaddleX 标准格式组织


async def export_model(task_id: int, framework: str, export_dir: str) -> dict:
    """导出训练产物到 RustFS 并创建模型记录"""
    from app.core.database import async_db_session
    from .model import TrainModel, TrainTask

    # 查找最佳模型权重
    best_path = None
    for root, _, files in os.walk(export_dir):
        for f in files:
            if framework == "ultralytics" and f.endswith(".pt"):
                best_path = os.path.join(root, f)
            elif framework == "paddlex" and f.endswith(".pdparams"):
                best_path = os.path.join(root, f)

    storage_path = ""
    if best_path:
        # 上传到 RustFS
        rustfs_path = f"train/models/task_{task_id}/{os.path.basename(best_path)}"
        with open(best_path, "rb") as f:
            from app.utils.s3_client import s3_client
            s3_client.upload_fileobj(f, rustfs_path)
        storage_path = rustfs_path

    async with async_db_session.begin() as db:
        task = await db.get(TrainTask, task_id)
        if not task:
            return {"repo_id": None, "storage_path": storage_path}

        # 创建或更新模型记录
        existing = await db.execute(
            select(TrainModel).where(TrainModel.name == task.name).order_by(TrainModel.id.desc()).limit(1)
        )
        last = existing.scalar_one_or_none()
        next_ver = 1
        if last and last.version:
            try:
                next_ver = int(last.version.replace("v", "")) + 1
            except ValueError:
                next_ver = 1

        model_rec = TrainModel(
            name=task.name, framework=task.framework,
            version=f"v{next_ver}", storage_path=storage_path,
            annotation_dataset_id=task.dataset_id,
            created_id=task.created_id,
        )
        db.add(model_rec)
        await db.flush()

        task.model_repo_id = model_rec.id

    return {"repo_id": model_rec.id, "storage_path": storage_path}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/plugin/module_train/exporter.py
git commit -m "feat(train): add dataset exporter and model export"
```

---

### Task 7: Frontend API Client

**Files:**
- Create: `frontend/src/api/module_train.ts`

- [ ] **Step 1: Create `module_train.ts`**

```typescript
import request from "@/utils/request";

const API_PATH = "/train";

export const TrainAPI = {
  // Models
  getModelList() {
    return request<ApiResponse<any[]>>({ url: `${API_PATH}/model/list`, method: "get" });
  },
  getModelDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/model/detail/${id}`, method: "get" });
  },
  createModel(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/model/create`, method: "post", data });
  },

  // Tasks
  createTask(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/create`, method: "post", data });
  },
  getTaskList() {
    return request<ApiResponse<any[]>>({ url: `${API_PATH}/task/list`, method: "get" });
  },
  getTaskDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/${id}/detail`, method: "get" });
  },
  stopTask(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/task/${id}/stop`, method: "post" });
  },

  // Eval
  createEval(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/eval/create`, method: "post", data });
  },
  getEvalList(modelRepoId: number) {
    return request<ApiResponse<any[]>>({ url: `${API_PATH}/eval/list`, method: "get", params: { model_repo_id: modelRepoId } });
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/module_train.ts
git commit -m "feat(train): add frontend API client"
```

---

### Task 8: Frontend Model Repository Page

**Files:**
- Create: `frontend/src/views/module_train/repo/index.vue`

- [ ] **Step 1: Create `repo/index.vue`**

```vue
<template>
  <div class="app-container">
    <PageSearch ... />
    <PageContent ... />
  </div>
</template>

<script setup lang="ts">
// 模型仓库列表 + 展开版本对比
// 列: 模型名 | 框架 | 最新版本 | 最新指标(mAP) | 操作(训练/评估/部署)
// 操作: 部署 → 注册到 video_algorithms 表
</script>
```

(Full implementation follows standard CRUD pattern matching existing pages like `module_annotation/task/index.vue`.)

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/module_train/repo/index.vue
git commit -m "feat(train): add model repository page"
```

---

### Task 9: Frontend Training Task Pages

**Files:**
- Create: `frontend/src/views/module_train/task/index.vue`
- Create: `frontend/src/views/module_train/task/detail.vue`

- [ ] **Step 1: Create `task/index.vue`** — list page + create dialog

```vue
<template>
  <div class="app-container">
    <el-button @click="showCreate = true">新建训练</el-button>
    <el-table :data="tasks">
      <el-table-column prop="name" label="任务名" />
      <el-table-column prop="framework" label="框架" />
      <el-table-column prop="status" label="状态" />
      <el-table-column prop="progress" label="进度" />
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button v-if="row.status === 'running'" @click="stopTask(row.id)">停止</el-button>
          <el-button @click="$router.push(`/train/task/${row.id}`)">详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新建弹窗 -->
    <el-dialog v-model="showCreate" title="新建训练任务">
      <el-form>
        <el-form-item label="任务名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="数据集">
          <el-select v-model="form.dataset_id">
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="框架">
          <el-radio-group v-model="form.framework">
            <el-radio value="paddlex">PaddleX</el-radio>
            <el-radio value="ultralytics">Ultralytics</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="超参数">
          <el-input v-model="form.hyperparams" type="textarea" :rows="6" placeholder="JSON 格式" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreate = false">取消</el-button>
        <el-button type="primary" @click="handleCreate">开始训练</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { TrainAPI } from "@/api/module_train";
import { ElMessage } from "element-plus";

const tasks = ref<any[]>([]);
const datasets = ref<any[]>([]);
const showCreate = ref(false);
const form = ref({ name: "", dataset_id: null, framework: "ultralytics", hyperparams: "{}" });

onMounted(async () => {
  tasks.value = (await TrainAPI.getTaskList()).data?.data || [];
  const ds = await import("@/api/module_annotation").then(m => m.AnnotationAPI.getDatasetList({ page_no: 1, page_size: 999 }));
  datasets.value = ds.data?.data?.items || [];
});

async function handleCreate() {
  const hp = JSON.parse(form.value.hyperparams || "{}");
  await TrainAPI.createTask({ ...form.value, hyperparams: hp });
  showCreate.value = false;
  ElMessage.success("训练任务已创建");
  tasks.value = (await TrainAPI.getTaskList()).data?.data || [];
}

async function stopTask(id: number) {
  await TrainAPI.stopTask(id);
  ElMessage.success("训练已停止");
}
</script>
```

- [ ] **Step 2: Create `task/detail.vue`**

```vue
<template>
  <div class="app-container">
    <el-card>
      <template #header>
        <span>{{ task?.name }}</span>
        <el-tag :type="statusTag" size="small" style="margin-left:8px">{{ task?.status }}</el-tag>
      </template>
      <div class="log-container" ref="logRef">
        <pre class="log-text">{{ logText }}</pre>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from "vue";
import { useRoute } from "vue-router";
import { TrainAPI } from "@/api/module_train";

const route = useRoute();
const task = ref<any>(null);
const logText = ref("");
const logRef = ref<HTMLElement | null>(null);
let ws: WebSocket | null = null;

const statusTag = computed(() => ({
  pending: "info", running: "warning", success: "success",
  failed: "danger", cancelled: "info",
}[task.value?.status] || "info"));

onMounted(async () => {
  const id = Number(route.params.id);
  task.value = (await TrainAPI.getTaskDetail(id)).data?.data;

  // 连接 WebSocket 日志
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/api/v1/ws/train/logs?task_id=${id}`);
  ws.onmessage = (e) => {
    logText.value += e.data + "\n";
    if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight;
  };
  ws.onclose = () => { /* 自动重连逻辑可由业务决定 */ };
});

onBeforeUnmount(() => { ws?.close(); });
</script>

<style scoped>
.log-container { height: 600px; overflow-y: auto; background: #1e1e1e; border-radius: 6px; padding: 16px; }
.log-text { font-family: "Cascadia Code", "Fira Code", monospace; font-size: 13px; line-height: 1.5; color: #d4d4d4; white-space: pre-wrap; word-break: break-all; }
</style>
```

- [ ] **Step 3: Add route for detail page** (in frontend router or menu data)

Add a hidden menu route in `init_app.py`:
```python
MenuModel(
    name="训练详情", type=2, icon=None, order=99,
    route_name="TrainTaskDetail", route_path="/train/task/:id",
    component_path="module_train/task/detail",
    permission="module_train:task:query", parent_id=train_parent.id,
    status="0", is_deleted=False, title="训练详情", hidden=True,
)
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/module_train/task/
git commit -m "feat(train): add training task list and detail pages"
```

---

### Task 10: Frontend Model Evaluation Page

**Files:**
- Create: `frontend/src/views/module_train/eval/index.vue`

- [ ] **Step 1: Create page**

(Standard CRUD page: select model version → select eval dataset → create eval → show metrics table.)

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/module_train/eval/index.vue
git commit -m "feat(train): add model evaluation page"
```

---

### Task 11: Menu Registration and Permissions

**Files:**
- Modify: `backend/app/scripts/init_app.py`

- [ ] **Step 1: Add menu seed data**

In `_ensure_annotation_menus()` function, add training module menus under the Annotation parent:
- 模型训练 (parent, icon="el-icon-Aim", order=4)
  - 模型仓库
  - 训练任务
  - 模型评估

- [ ] **Step 2: Add button permissions**

```python
button_perms = [
    ("module_train:model:query", "查询模型", ...),
    ("module_train:model:create", "创建模型", ...),
    ("module_train:task:query", "查询任务", ...),
    ("module_train:task:create", "创建任务", ...),
    ("module_train:task:update", "更新任务", ...),
    ("module_train:eval:query", "查询评估", ...),
    ("module_train:eval:create", "创建评估", ...),
]
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/scripts/init_app.py
git commit -m "feat(train): add menu and permission registration"
```
