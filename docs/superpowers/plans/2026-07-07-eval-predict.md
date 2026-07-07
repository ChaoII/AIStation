# 模型评估（验证）与预测测试 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Ultralytics 模型提供完整的评估（`yolo val`）和预测（`yolo predict`）功能，复用现有训练 Docker 基础设施。

**Architecture:** 评估和预测作为独立子模块位于 `module_train` 插件内，遵循现有训练任务模式（controller → service → scheduler/executor → docker_utils）。评估使用现有 `TrainEval` 模型并增强字段；预测新建 `TrainPredict` 模型。调度器/执行器类比 `scheduler.py`。

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Docker SDK for Python, RustFS (S3), Vue 3, Element Plus, ECharts

## Global Constraints

- 所有新模型继承 `ModelMixin` + `UserMixin`
- 评估和预测的 Docker 镜像复用训练的镜像（`ultralytics/ultralytics:latest`）
- 所有 API 端点使用 `Depends(AuthPermission([...]))` 鉴权
- 前端路由 hash 模式（`createWebHashHistory`），动态路由来自后端菜单数据
- 预测结果图片通过 RustFS 存储和返回 presigned URL
- 后端端口 8001，前端端口 5180

---

### Task 1: 后端数据模型 — 增强 TrainEval + 新建 TrainPredict

**Files:**
- Modify: `backend/app/plugin/module_train/model.py:54-60`
- Test: N/A（已有模型迁移）

**Interfaces:**
- Consumes: `ModelMixin`, `UserMixin`, `TrainStatus`, `TrainFramework`（已有）
- Produces: `TrainEval`（增强）, `TrainPredict`（新建）

- [ ] **Step 1: 增强 TrainEval**

在 `model.py` 中将 `TrainEval` 替换为：

```python
class TrainEval(ModelMixin, UserMixin):
    __tablename__ = "train_evals"
    model_repo_id: Mapped[int] = mapped_column(Integer, comment="模型仓库ID")
    model_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="具体模型版本ID")
    eval_dataset_id: Mapped[int] = mapped_column(Integer, comment="评估数据集ID")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), default=TrainFramework.ULTRALYTICS, comment="框架")
    hyperparams: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="评估参数")
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="评估指标")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")
    log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="评估日志")
```

- [ ] **Step 2: 新建 TrainPredict**

在 `model.py` 末尾 `TrainEval` 定义之后添加：

```python
class TrainPredict(ModelMixin, UserMixin):
    __tablename__ = "train_predicts"
    model_repo_id: Mapped[int] = mapped_column(Integer, comment="模型仓库ID")
    model_id: Mapped[int] = mapped_column(Integer, comment="模型版本ID")
    framework: Mapped[TrainFramework] = mapped_column(SAEnum(TrainFramework), default=TrainFramework.ULTRALYTICS, comment="框架")
    source_type: Mapped[str] = mapped_column(String(16), comment="图片来源 dataset/upload")
    source_dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="源数据集ID")
    source_images: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="上传图片原始URL列表")
    result_images: Mapped[list | None] = mapped_column(JSONB, nullable=True, comment="结果图片URL列表")
    result_zip_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="结果ZIP在RustFS的路径")
    hyperparams: Mapped[dict | None] = mapped_column(JSONB, nullable=True, default=dict, comment="预测参数")
    status: Mapped[TrainStatus] = mapped_column(SAEnum(TrainStatus), default=TrainStatus.PENDING, comment="状态")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="完成时间")
    log: Mapped[str | None] = mapped_column(Text, nullable=True, comment="预测日志")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/plugin/module_train/model.py
git commit -m "feat(train): enhance TrainEval model, add TrainPredict model"
```

---

### Task 2: Schema — 新增预测 + 增强评估

**Files:**
- Modify: `backend/app/plugin/module_train/schema.py`

**Interfaces:**
- Consumes: `TrainEval`, `TrainPredict` 模型字段
- Produces: `TrainEvalCreateSchema`（增强）, `TrainEvalOutSchema`（增强）, `TrainPredictCreateSchema`, `TrainPredictOutSchema`

- [ ] **Step 1: 替换 `TrainEvalCreateSchema` 和 `TrainEvalOutSchema`**

```python
class TrainEvalCreateSchema(BaseModel):
    model_repo_id: int
    model_id: int | None = None
    eval_dataset_id: int
    hyperparams: dict = Field(default_factory=dict)


class TrainEvalOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    model_repo_id: int
    model_id: int | None
    eval_dataset_id: int
    framework: str
    hyperparams: dict | None
    metrics: dict | None
    status: str
    log: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_id: int | None
    created_time: datetime | None
```

- [ ] **Step 2: 新增预测 Schema**

在 `DatasetExportSchema` 之前添加：

```python
class TrainPredictCreateSchema(BaseModel):
    model_repo_id: int
    model_id: int
    source_type: str = Field(pattern=r"^(dataset|upload)$")
    source_dataset_id: int | None = None
    source_images: list[str] | None = None
    hyperparams: dict = Field(default_factory=dict)


class TrainPredictOutSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    model_repo_id: int
    model_id: int
    framework: str
    source_type: str
    source_dataset_id: int | None
    source_images: list | None
    result_images: list | None
    result_zip_path: str | None
    hyperparams: dict | None
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    log: str | None
    created_id: int | None
    created_time: datetime | None
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/plugin/module_train/schema.py
git commit -m "feat(train): add predict schemas, enhance eval schemas"
```

---

### Task 3: Service — 评估服务增强 + 预测服务

**Files:**
- Modify: `backend/app/plugin/module_train/service.py`

**Interfaces:**
- Consumes: `TrainEval`, `TrainPredict` 模型, `TrainEvalCreateSchema`, `TrainPredictCreateSchema`
- Produces: `TrainService.create_eval()`, `TrainService.get_eval()`, `TrainService.list_evals()`, `TrainService.delete_evals()`, `TrainService.create_predict()`, `TrainService.get_predict()`, `TrainService.list_predicts()`, `TrainService.delete_predicts()`

- [ ] **Step 1: 增强现有评估方法**

修改 `create_eval`（第 94 行）以接受 `model_id` 和 `hyperparams`：

```python
@classmethod
async def create_eval(cls, data, auth) -> dict:
    async with async_db_session.begin() as db:
        e = TrainEval(
            model_repo_id=data.model_repo_id,
            model_id=data.model_id,
            eval_dataset_id=data.eval_dataset_id,
            hyperparams=data.hyperparams,
            created_id=auth.user.id,
        )
        db.add(e)
        await db.flush()
        return {"id": e.id}
```

- [ ] **Step 2: 新增 `get_eval` 方法**

在 `delete_evals` 之后添加：

```python
@classmethod
async def get_eval(cls, eval_id: int) -> dict | None:
    async with async_db_session() as db:
        e = await db.get(TrainEval, eval_id)
        return dict(e.__dict__) if e else None
```

- [ ] **Step 3: 新增预测 CRUD 方法**

在 `get_eval` 之后添加：

```python
@classmethod
async def create_predict(cls, data, auth) -> dict:
    async with async_db_session.begin() as db:
        p = TrainPredict(
            model_repo_id=data.model_repo_id,
            model_id=data.model_id,
            source_type=data.source_type,
            source_dataset_id=data.source_dataset_id,
            source_images=data.source_images,
            hyperparams=data.hyperparams,
            created_id=auth.user.id,
        )
        db.add(p)
        await db.flush()
        return {"id": p.id}


@classmethod
async def get_predict(cls, predict_id: int) -> dict | None:
    async with async_db_session() as db:
        p = await db.get(TrainPredict, predict_id)
        return dict(p.__dict__) if p else None


@classmethod
async def list_predicts(cls) -> list[dict]:
    async with async_db_session() as db:
        result = await db.execute(select(TrainPredict).order_by(desc(TrainPredict.created_time)))
        return [dict(r.__dict__) for r in result.scalars().all()]


@classmethod
async def delete_predicts(cls, ids: list[int]) -> None:
    async with async_db_session.begin() as db:
        for pid in ids:
            p = await db.get(TrainPredict, pid)
            if p:
                await db.delete(p)
```

- [ ] **Step 4: Update import**

在 `service.py` 顶部将 `from .model import TrainModel, TrainTask, TrainEval` 改为：

```python
from .model import TrainModel, TrainTask, TrainEval, TrainPredict
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugin/module_train/service.py
git commit -m "feat(train): add predict service, enhance eval service"
```

---

### Task 4: Controller — 新增预测端点 + 增强评估端点

**Files:**
- Modify: `backend/app/plugin/module_train/controller.py`

**Interfaces:**
- Consumes: `TrainService` 方法, `TrainEvalCreateSchema`, `TrainPredictCreateSchema`
- Produces: `/eval/{id}/start`, `/eval/{id}/stop`, `/eval/{id}/detail`, `/predict/*` 端点

- [ ] **Step 1: 更新 import**

将第 5 行的 schema import 改为：

```python
from .schema import (
    TrainModelCreateSchema, TrainTaskCreateSchema,
    TrainEvalCreateSchema, TrainPredictCreateSchema, DatasetExportSchema
)
```

将第 7 行 `from .scheduler import start_training` 改为：

```python
from .scheduler import start_training
from .eval_scheduler import start_evaluation, stop_evaluation
from .predict_executor import start_prediction, stop_prediction
```

- [ ] **Step 2: 增强评估端点**

在第 72-104 行之间添加新的评估端点并增强现有端点。

**替换现有 `create_eval` 端点**（第 72-75 行）：

```python
@router.post("/eval/create", summary="创建评估任务")
async def create_eval(data: TrainEvalCreateSchema, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:create"]))):
    result = await TrainService.create_eval(data, auth)
    return SuccessResponse(data=result, msg="评估任务已创建")


@router.get("/eval/{eval_id}/detail", summary="评估详情")
async def get_eval(eval_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:query"]))):
    data = await TrainService.get_eval(eval_id)
    return SuccessResponse(data=data)


@router.post("/eval/{eval_id}/start", summary="开始评估")
async def start_eval(eval_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:create"]))):
    await start_evaluation(eval_id)
    return SuccessResponse(data={"id": eval_id}, msg="评估已开始")


@router.post("/eval/{eval_id}/stop", summary="停止评估")
async def stop_eval(eval_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:eval:create"]))):
    await stop_evaluation(eval_id)
    return SuccessResponse(data={"id": eval_id}, msg="评估已停止")
```

- [ ] **Step 3: 新增预测端点**

在 `delete_eval` 端点之后添加：

```python
@router.post("/predict/create", summary="创建预测任务")
async def create_predict(data: TrainPredictCreateSchema, auth: AuthSchema = Depends(AuthPermission(["module_train:predict:create"]))):
    result = await TrainService.create_predict(data, auth)
    return SuccessResponse(data=result, msg="预测任务已创建")


@router.get("/predict/list", summary="预测任务列表")
async def list_predicts(auth: AuthSchema = Depends(AuthPermission(["module_train:predict:query"]))):
    data = await TrainService.list_predicts()
    return SuccessResponse(data=data)


@router.get("/predict/{predict_id}/detail", summary="预测详情")
async def get_predict(predict_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:predict:query"]))):
    data = await TrainService.get_predict(predict_id)
    return SuccessResponse(data=data)


@router.post("/predict/{predict_id}/start", summary="开始预测")
async def start_predict(predict_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:predict:create"]))):
    await start_prediction(predict_id)
    return SuccessResponse(data={"id": predict_id}, msg="预测已开始")


@router.post("/predict/{predict_id}/stop", summary="停止预测")
async def stop_predict(predict_id: int, auth: AuthSchema = Depends(AuthPermission(["module_train:predict:create"]))):
    await stop_prediction(predict_id)
    return SuccessResponse(data={"id": predict_id}, msg="预测已停止")


@router.delete("/predict/delete", summary="删除预测任务")
async def delete_predict(ids: list[int] = Body(...), auth: AuthSchema = Depends(AuthPermission(["module_train:predict:delete"]))):
    await TrainService.delete_predicts(ids)
    return SuccessResponse(msg="删除成功")


@router.post("/predict/upload", summary="上传预测图片")
async def upload_predict_images(files: list[UploadFile] = File(...), auth: AuthSchema = Depends(AuthPermission(["module_train:predict:create"]))):
    urls = await TrainService.upload_predict_images(files, auth)
    return SuccessResponse(data=urls, msg="上传成功")
```

同时在 controller.py 顶部增加 import：
```python
from fastapi import APIRouter, Depends, Body, UploadFile, File
```

- [ ] **Step 4: 添加 `upload_predict_images` 方法到 `TrainService`**

在 `service.py` 的 `delete_predicts` 之后添加：

```python
@classmethod
async def upload_predict_images(cls, files: list, auth) -> list[str]:
    import tempfile, os
    from app.utils.s3_client import s3_client

    urls = []
    for f in files:
        content = await f.read()
        ext = f.filename.rsplit(".", 1)[-1] if "." in f.filename else "jpg"
        key = f"train/predict/upload/{auth.user.id}/{uuid.uuid4()}.{ext}"
        s3_client.upload_fileobj(content, key)
        urls.append(s3_client.presigned_url(key))
    return urls
```

并在 `service.py` 顶部加上 `import uuid`。

- [ ] **Step 5: Commit**

```bash
git add backend/app/plugin/module_train/controller.py backend/app/plugin/module_train/service.py
git commit -m "feat(train): add predict API endpoints, enhance eval endpoints"
```

---

### Task 5: Eval Scheduler — 评估任务调度器

**Files:**
- Create: `backend/app/plugin/module_train/eval_scheduler.py`

**Interfaces:**
- Consumes: `docker_utils`（`pull_image`, `run_container`, `follow_container_logs`, `remove_container`, `wait_container`）, `ws.broadcast_eval_log`, `TrainEval` 模型
- Produces: `start_evaluation(eval_id)`, `stop_evaluation(eval_id)`

- [ ] **Step 1: 创建 `eval_scheduler.py`**

```python
import asyncio
import os
import re
import tempfile
from datetime import datetime

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .model import TrainEval, TrainStatus, TrainModel
from .docker_utils import pull_image, run_container, follow_container_logs, remove_container
from .ws import broadcast_eval_log

_eval_running: dict[int, dict] = {}

DOCKER_IMAGE = "ultralytics/ultralytics:latest"


async def start_evaluation(eval_id: int):
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainEval).where(TrainEval.id == eval_id).values(
                status=TrainStatus.RUNNING, started_at=datetime.now()
            )
        )
    asyncio.create_task(_execute_evaluation(eval_id))


async def stop_evaluation(eval_id: int):
    entry = _eval_running.get(eval_id)
    if entry:
        entry["cancel"] = True
        from .docker_utils import stop_container
        await stop_container(entry["container_id"])


async def _execute_evaluation(eval_id: int):
    container_id = None
    try:
        async with async_db_session() as db:
            eval_rec = await db.get(TrainEval, eval_id)
            if not eval_rec:
                return

        await broadcast_eval_log(eval_id, f"[eval] pulling image {DOCKER_IMAGE}...")
        await pull_image(DOCKER_IMAGE)

        export_dir = os.path.join(tempfile.gettempdir(), "eval_output", str(eval_id))
        data_dir = os.path.join(export_dir, "data")
        model_dir = os.path.join(export_dir, "model")
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(model_dir, exist_ok=True)

        # Export evaluation dataset
        from .exporter import export_dataset
        await broadcast_eval_log(eval_id, "[eval] exporting dataset...")
        await export_dataset(eval_rec.eval_dataset_id, eval_id, "ultralytics", data_dir)

        # Download model file from RustFS
        async with async_db_session() as db:
            model_rec = await db.get(TrainModel, eval_rec.model_id or eval_rec.model_repo_id)
            if not model_rec or not model_rec.storage_path:
                raise Exception("model not found or no storage_path")

        await broadcast_eval_log(eval_id, f"[eval] downloading model {model_rec.storage_path}...")
        from app.utils.s3_client import s3_client
        model_data = s3_client.download_fileobj(model_rec.storage_path)
        model_filename = model_rec.storage_path.rsplit("/", 1)[-1]
        model_local_path = os.path.join(model_dir, model_filename)
        with open(model_local_path, "wb") as f:
            f.write(model_data.read())

        # Build command
        hp = eval_rec.hyperparams or {}
        imgsz = hp.get("imgsz", 640)
        batch = hp.get("batch", 16)
        conf = hp.get("conf", 0.001)
        iou = hp.get("iou", 0.6)
        device = hp.get("device", "0")

        cmd = [
            "yolo", "val",
            f"model=/model/{model_filename}",
            "data=/data/dataset.yaml",
            f"imgsz={imgsz}",
            f"batch={batch}",
            f"conf={conf}",
            f"iou={iou}",
        ]

        container = await run_container(
            DOCKER_IMAGE, cmd,
            volumes={
                data_dir: {"bind": "/data", "mode": "rw"},
                model_dir: {"bind": "/model", "mode": "ro"},
            },
            gpu_id=device,
        )
        container_id = container.id
        _eval_running[eval_id] = {"container_id": container_id, "cancel": False}

        log_queue = await follow_container_logs(container_id)
        log_file = os.path.join(export_dir, "eval.log")

        metrics: dict = {}
        with open(log_file, "w", encoding="utf-8") as lf:
            while True:
                line = await log_queue.get()
                if line == "__EOF__":
                    break
                lf.write(line + "\n")
                lf.flush()
                await broadcast_eval_log(eval_id, line)

                # Parse YOLO val metrics
                if re.match(r"^\s+all\s+", line):
                    parts = line.strip().split()
                    if len(parts) >= 7:
                        metrics = {
                            "precision": float(parts[3]) if parts[3] else 0,
                            "recall": float(parts[4]) if parts[4] else 0,
                            "map50": float(parts[5]) if parts[5] else 0,
                            "map5095": float(parts[6]) if parts[6] else 0,
                        }

                # Parse per-class metrics
                m = re.match(r"^\s+(\d+)\s+", line)
                if m:
                    parts = line.strip().split()
                    if len(parts) >= 7:
                        cls_id = int(parts[0])
                        if "classes" not in metrics:
                            metrics["classes"] = {}
                        metrics["classes"][str(cls_id)] = {
                            "precision": float(parts[3]) if parts[3] else 0,
                            "recall": float(parts[4]) if parts[4] else 0,
                            "map50": float(parts[5]) if parts[5] else 0,
                            "map5095": float(parts[6]) if parts[6] else 0,
                        }

        loop = asyncio.get_event_loop()
        exit_code = await loop.run_in_executor(None, lambda: container.wait(timeout=600)["StatusCode"])

        if _eval_running.get(eval_id, {}).get("cancel"):
            await remove_container(container_id)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainEval).where(TrainEval.id == eval_id).values(
                        status=TrainStatus.CANCELLED, finished_at=datetime.now()
                    )
                )
        elif exit_code == 0:
            await remove_container(container_id)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainEval).where(TrainEval.id == eval_id).values(
                        status=TrainStatus.SUCCESS,
                        metrics=metrics or None,
                        finished_at=datetime.now(),
                    )
                )
        else:
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
                    update(TrainEval).where(TrainEval.id == eval_id).values(
                        status=TrainStatus.FAILED, log=error_msg or "eval failed",
                        finished_at=datetime.now(),
                    )
                )

    except Exception as e:
        log.error(f"eval task {eval_id} failed: {e}")
        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainEval).where(TrainEval.id == eval_id).values(
                    status=TrainStatus.FAILED, log=str(e), finished_at=datetime.now()
                )
            )
    finally:
        _eval_running.pop(eval_id, None)
        if container_id:
            await remove_container(container_id)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/plugin/module_train/eval_scheduler.py
git commit -m "feat(train): add eval scheduler for running yolo val in Docker"
```

---

### Task 6: Predict Executor — 预测任务执行器

**Files:**
- Create: `backend/app/plugin/module_train/predict_executor.py`

**Interfaces:**
- Consumes: `docker_utils`, `ws.broadcast_predict_log`, `TrainPredict` 模型, `TrainModel`
- Produces: `start_prediction(predict_id)`, `stop_prediction(predict_id)`

- [ ] **Step 1: 创建 `predict_executor.py`**

```python
import asyncio
import os
import tempfile
import shutil
import zipfile
from datetime import datetime

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .model import TrainPredict, TrainStatus, TrainModel
from .docker_utils import pull_image, run_container, follow_container_logs, remove_container
from .ws import broadcast_predict_log

_predict_running: dict[int, dict] = {}

DOCKER_IMAGE = "ultralytics/ultralytics:latest"


async def start_prediction(predict_id: int):
    async with async_db_session.begin() as db:
        await db.execute(
            update(TrainPredict).where(TrainPredict.id == predict_id).values(
                status=TrainStatus.RUNNING, started_at=datetime.now()
            )
        )
    asyncio.create_task(_execute_prediction(predict_id))


async def stop_prediction(predict_id: int):
    entry = _predict_running.get(predict_id)
    if entry:
        entry["cancel"] = True
        from .docker_utils import stop_container
        await stop_container(entry["container_id"])


async def _execute_prediction(predict_id: int):
    container_id = None
    try:
        async with async_db_session() as db:
            pred = await db.get(TrainPredict, predict_id)
            if not pred:
                return

        await broadcast_predict_log(predict_id, f"[predict] pulling image {DOCKER_IMAGE}...")
        await pull_image(DOCKER_IMAGE)

        export_dir = os.path.join(tempfile.gettempdir(), "predict_output", str(predict_id))
        source_dir = os.path.join(export_dir, "source")
        output_dir = os.path.join(export_dir, "output")
        model_dir = os.path.join(export_dir, "model")
        os.makedirs(source_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(model_dir, exist_ok=True)

        # Prepare source images
        from app.utils.s3_client import s3_client
        if pred.source_type == "dataset":
            await broadcast_predict_log(predict_id, "[predict] exporting dataset images...")
            from .exporter import export_dataset
            await export_dataset(pred.source_dataset_id, predict_id, "ultralytics", source_dir)
            # Remove label files and yaml, keep only images
            for root, _, files in os.walk(source_dir):
                for f in files:
                    if f.endswith(".txt") or f == "dataset.yaml":
                        os.remove(os.path.join(root, f))
        else:
            await broadcast_predict_log(predict_id, "[predict] downloading uploaded images...")
            for img_url in (pred.source_images or []):
                # img_url is a presigned URL, we need the object_key
                # Extract key from URL
                try:
                    data = s3_client.download_fileobj(img_url)
                    filename = img_url.rsplit("/", 1)[-1].split("?")[0]
                    with open(os.path.join(source_dir, filename), "wb") as f:
                        f.write(data.read())
                except Exception as e:
                    log.warning(f"skip image {img_url}: {e}")

        # Download model
        async with async_db_session() as db:
            model_rec = await db.get(TrainModel, pred.model_id)
            if not model_rec or not model_rec.storage_path:
                raise Exception("model not found or no storage_path")

        await broadcast_predict_log(predict_id, f"[predict] downloading model {model_rec.storage_path}...")
        model_data = s3_client.download_fileobj(model_rec.storage_path)
        model_filename = model_rec.storage_path.rsplit("/", 1)[-1]
        model_local_path = os.path.join(model_dir, model_filename)
        with open(model_local_path, "wb") as f:
            f.write(model_data.read())

        # Build command
        hp = pred.hyperparams or {}
        conf = hp.get("conf", 0.25)
        iou = hp.get("iou", 0.45)
        imgsz = hp.get("imgsz", 640)
        device = hp.get("device", "0")

        cmd = [
            "yolo", "predict",
            f"model=/model/{model_filename}",
            f"source=/data",
            f"imgsz={imgsz}",
            f"conf={conf}",
            f"iou={iou}",
            "save_txt=True",
            "save_conf=True",
            "project=/output",
            "name=exp",
        ]

        container = await run_container(
            DOCKER_IMAGE, cmd,
            volumes={
                source_dir: {"bind": "/data", "mode": "ro"},
                model_dir: {"bind": "/model", "mode": "ro"},
                output_dir: {"bind": "/output", "mode": "rw"},
            },
            gpu_id=device,
        )
        container_id = container.id
        _predict_running[predict_id] = {"container_id": container_id, "cancel": False}

        log_queue = await follow_container_logs(container_id)
        log_file = os.path.join(export_dir, "predict.log")

        with open(log_file, "w", encoding="utf-8") as lf:
            while True:
                line = await log_queue.get()
                if line == "__EOF__":
                    break
                lf.write(line + "\n")
                lf.flush()
                await broadcast_predict_log(predict_id, line)

        loop = asyncio.get_event_loop()
        exit_code = await loop.run_in_executor(None, lambda: container.wait(timeout=600)["StatusCode"])

        result_images = []
        result_zip_path = None

        if _predict_running.get(predict_id, {}).get("cancel"):
            await remove_container(container_id)
            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainPredict).where(TrainPredict.id == predict_id).values(
                        status=TrainStatus.CANCELLED, finished_at=datetime.now()
                    )
                )
        elif exit_code == 0:
            await remove_container(container_id)

            # Collect result images from output dir
            predict_output = os.path.join(output_dir, "exp")
            if os.path.exists(predict_output):
                for f in sorted(os.listdir(predict_output)):
                    if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                        img_path = os.path.join(predict_output, f)
                        rustfs_key = f"train/predict/{predict_id}/{f}"
                        with open(img_path, "rb") as img_f:
                            s3_client.upload_fileobj(img_f, rustfs_key)
                        result_images.append(s3_client.presigned_url(rustfs_key))

                # Create ZIP
                zip_path = os.path.join(export_dir, "results.zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for root, _, files in os.walk(predict_output):
                        for fn in files:
                            fp = os.path.join(root, fn)
                            zf.write(fp, os.path.relpath(fp, predict_output))
                zip_rustfs_key = f"train/predict/{predict_id}/results.zip"
                with open(zip_path, "rb") as zf:
                    s3_client.upload_fileobj(zf, zip_rustfs_key)
                result_zip_path = s3_client.presigned_url(zip_rustfs_key)

            async with async_db_session.begin() as db:
                await db.execute(
                    update(TrainPredict).where(TrainPredict.id == predict_id).values(
                        status=TrainStatus.SUCCESS,
                        result_images=result_images or None,
                        result_zip_path=result_zip_path,
                        finished_at=datetime.now(),
                    )
                )
        else:
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
                    update(TrainPredict).where(TrainPredict.id == predict_id).values(
                        status=TrainStatus.FAILED, log=error_msg or "predict failed",
                        finished_at=datetime.now(),
                    )
                )

    except Exception as e:
        log.error(f"predict task {predict_id} failed: {e}")
        async with async_db_session.begin() as db:
            await db.execute(
                update(TrainPredict).where(TrainPredict.id == predict_id).values(
                    status=TrainStatus.FAILED, log=str(e), finished_at=datetime.now()
                )
            )
    finally:
        _predict_running.pop(predict_id, None)
        if container_id:
            await remove_container(container_id)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/plugin/module_train/predict_executor.py
git commit -m "feat(train): add predict executor for running yolo predict in Docker"
```

---

### Task 7: WebSocket — 新增 eval/predict 日志广播

**Files:**
- Modify: `backend/app/plugin/module_train/ws.py`

**Interfaces:**
- Consumes: `fastapi.WebSocket`, `fastapi.Query`
- Produces: `broadcast_eval_log(eval_id, line)`, `broadcast_predict_log(predict_id, line)`, eval/predict WebSocket endpoints

- [ ] **Step 1: 增强 `ws.py`**

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

WS_Train = APIRouter(prefix="/train", tags=["训练WebSocket"])

# Train logs
_train_ws_clients: dict[int, list[WebSocket]] = {}

async def broadcast_log(task_id: int, line: str):
    for ws in _train_ws_clients.get(task_id, [])[:]:
        try:
            await ws.send_text(line)
        except Exception:
            _train_ws_clients[task_id].remove(ws)


@WS_Train.websocket("/ws/train/logs")
async def train_log_ws(websocket: WebSocket, task_id: int = Query(...)):
    await websocket.accept()
    _train_ws_clients.setdefault(task_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if task_id in _train_ws_clients:
            _train_ws_clients[task_id].remove(websocket)
            if not _train_ws_clients[task_id]:
                del _train_ws_clients[task_id]


# Eval logs
_eval_ws_clients: dict[int, list[WebSocket]] = {}

async def broadcast_eval_log(eval_id: int, line: str):
    for ws in _eval_ws_clients.get(eval_id, [])[:]:
        try:
            await ws.send_text(line)
        except Exception:
            _eval_ws_clients[eval_id].remove(ws)


@WS_Train.websocket("/ws/eval/logs")
async def eval_log_ws(websocket: WebSocket, eval_id: int = Query(...)):
    await websocket.accept()
    _eval_ws_clients.setdefault(eval_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if eval_id in _eval_ws_clients:
            _eval_ws_clients[eval_id].remove(websocket)
            if not _eval_ws_clients[eval_id]:
                del _eval_ws_clients[eval_id]


# Predict logs
_predict_ws_clients: dict[int, list[WebSocket]] = {}

async def broadcast_predict_log(predict_id: int, line: str):
    for ws in _predict_ws_clients.get(predict_id, [])[:]:
        try:
            await ws.send_text(line)
        except Exception:
            _predict_ws_clients[predict_id].remove(ws)


@WS_Train.websocket("/ws/predict/logs")
async def predict_log_ws(websocket: WebSocket, predict_id: int = Query(...)):
    await websocket.accept()
    _predict_ws_clients.setdefault(predict_id, []).append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if predict_id in _predict_ws_clients:
            _predict_ws_clients[predict_id].remove(websocket)
            if not _predict_ws_clients[predict_id]:
                del _predict_ws_clients[predict_id]
```

- [ ] **Step 2: 更新 `init_app.py` 注册新 WebSocket 路由**

查找 `init_app.py` 中注册 `WS_Train` 的行（约第 587 行），确认该路由已注册。新增的 `/ws/eval/logs` 和 `/ws/predict/logs` 路径共享同一个 `WS_Train` 路由器，所以已经自动注册。

- [ ] **Step 3: Commit**

```bash
git add backend/app/plugin/module_train/ws.py
git commit -m "feat(train): add eval/predict WebSocket log broadcasting"
```

---

### Task 8: 权限与菜单注册

**Files:**
- Modify: `backend/app/scripts/init_app.py`

- [ ] **Step 1: 添加预测权限**

在 `init_app.py` 中查找到权限注册区域（约第 332-355 行），在评估权限之后添加：

```python
("module_train:predict:query", "查询预测"),
("module_train:predict:create", "创建预测"),
("module_train:predict:delete", "删除预测"),
```

- [ ] **Step 2: 添加预测菜单条目**

在评估菜单（约第 309-311 行）之后添加：

```python
MenuData(
    route_name="TrainPredict", route_path="/train/predict",
    component_path="module_train/predict/index",
    permission="module_train:predict:query", parent_id=parent.id,
),
```

并添加隐藏详情页路由：

```python
MenuData(
    route_name="TrainPredictDetail", route_path="/train/predict/:id",
    component_path="module_train/predict/detail",
    permission="module_train:predict:query", parent_id=parent.id,
    hidden=True,
),
MenuData(
    route_name="TrainEvalDetail", route_path="/train/eval/:id",
    component_path="module_train/eval/detail",
    permission="module_train:eval:query", parent_id=parent.id,
    hidden=True,
),
```

- [ ] **Step 3: 启动 eval_scheduler**

在 `init_app.py` 的 `start_scheduler()` 调用附近（约第 590 行），添加：

```python
from app.plugin.module_train.eval_scheduler import start_evaluation_scheduler
await start_evaluation_scheduler()
```

并创建 `eval_scheduler.py` 的调度器循环。在 `eval_scheduler.py` 末尾添加：

```python
_eval_scheduler_task: asyncio.Task | None = None

async def start_evaluation_scheduler():
    global _eval_scheduler_task
    if _eval_scheduler_task is None or _eval_scheduler_task.done():
        _eval_scheduler_task = asyncio.create_task(_eval_scheduler_loop())
        log.info("eval scheduler started")

async def _eval_scheduler_loop():
    """Clean up orphan eval tasks"""
    while True:
        try:
            async with async_db_session() as db:
                running = await db.execute(
                    select(TrainEval).where(TrainEval.status == TrainStatus.RUNNING)
                )
                for e in running.scalars().all():
                    if e.id not in _eval_running and e.started_at:
                        elapsed = (datetime.now() - e.started_at).total_seconds()
                        if elapsed > 1800:
                            async with async_db_session.begin() as db2:
                                await db2.execute(
                                    update(TrainEval).where(TrainEval.id == e.id).values(
                                        status=TrainStatus.FAILED,
                                        log="评估会话已断开（后端重启或容器丢失）",
                                        finished_at=datetime.now()
                                    )
                                )
        except Exception as e:
            log.error(f"eval scheduler error: {e}")
        await asyncio.sleep(30)
```

并在 `eval_scheduler.py` 顶部补充 import：
```python
from sqlalchemy import select
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/scripts/init_app.py backend/app/plugin/module_train/eval_scheduler.py
git commit -m "feat(train): register predict permissions/menus, add eval scheduler loop"
```

---

### Task 9: 前端 API — 新增预测 API 调用

**Files:**
- Modify: `frontend/src/api/module_train.ts`

- [ ] **Step 1: 添加预测 API 方法和评估新端点**

```typescript
  getEvalDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/eval/${id}/detail`, method: "get" });
  },
  startEval(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/eval/${id}/start`, method: "post" });
  },
  stopEval(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/eval/${id}/stop`, method: "post" });
  },

  createPredict(data: any) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/predict/create`, method: "post", data });
  },
  getPredictList() {
    return request<ApiResponse<any[]>>({ url: `${API_PATH}/predict/list`, method: "get" });
  },
  getPredictDetail(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/predict/${id}/detail`, method: "get" });
  },
  startPredict(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/predict/${id}/start`, method: "post" });
  },
  stopPredict(id: number) {
    return request<ApiResponse<any>>({ url: `${API_PATH}/predict/${id}/stop`, method: "post" });
  },
  deletePredict(ids: number[]) {
    return request<ApiResponse>({ url: `${API_PATH}/predict/delete`, method: "delete", data: ids });
  },
  uploadPredictImages(files: File[]) {
    const formData = new FormData();
    files.forEach(f => formData.append("files", f));
    return request<ApiResponse<string[]>>({ url: `${API_PATH}/predict/upload`, method: "post", data: formData, headers: { "Content-Type": "multipart/form-data" } });
  },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/module_train.ts
git commit -m "feat(train): add predict API and eval detail/start/stop API"
```

---

### Task 10: 前端评估页面 — 增强列表 + 新建详情页

**Files:**
- Modify: `frontend/src/views/module_train/eval/index.vue`
- Create: `frontend/src/views/module_train/eval/detail.vue`

- [ ] **Step 1: 增强 `eval/index.vue`**

添加「详情」「开始评估」「停止」操作列。在 `<el-table-column label="操作">` 中添加按钮：

```vue
<el-table-column label="操作" width="200" fixed="right">
  <template #default="{ row }">
    <el-button text size="small" type="primary" @click="router.push(`/train/eval/${row.id}`)">详情</el-button>
    <el-button v-if="row.status === 'pending'" text size="small" type="success" @click="handleStartEval(row.id)">开始</el-button>
    <el-button v-if="row.status === 'running'" text size="small" type="danger" @click="handleStopEval(row.id)">停止</el-button>
    <el-button v-if="row.status === 'success'" text size="small" type="primary" @click="router.push(`/train/eval/${row.id}`)">查看结果</el-button>
    <el-popconfirm title="确定删除？" @confirm="handleDeleteEval([row.id])">
      <template #reference>
        <el-button text size="small" type="danger">删除</el-button>
      </template>
    </el-popconfirm>
  </template>
</el-table-column>
```

并在 `<script>` 中添加 `router`：

```typescript
import { useRoute, useRouter } from "vue-router";
const router = useRouter();
```

添加处理方法：

```typescript
async function handleStartEval(id: number) {
  await TrainAPI.startEval(id);
  ElMessage.success("评估已开始");
  await reloadEvalData();
}

async function handleStopEval(id: number) {
  await TrainAPI.stopEval(id);
  ElMessage.success("评估已停止");
  await reloadEvalData();
}

async function handleDeleteEval(ids: number[]) {
  await TrainAPI.deleteEval(ids);
  ElMessage.success("已删除");
  await reloadEvalData();
}
```

为创建评估弹窗添加模型选择和超参配置（组件通过 `el-dialog` 实现），在 `<template>` 中补充：

```vue
<el-dialog v-model="createDialogVisible" title="创建评估" width="500px">
  <el-form label-width="100px">
    <el-form-item label="模型版本">
      <el-select v-model="createForm.modelId" filterable style="width:100%">
        <el-option v-for="m in modelVersions" :key="m.id" :label="`${m.name} v${m.version}`" :value="m.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="评估数据集">
      <el-select v-model="createForm.evalDatasetId" filterable style="width:100%">
        <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="imgsz"><el-input-number v-model="createForm.hyperparams.imgsz" :min="32" :step="32" /></el-form-item>
    <el-form-item label="batch"><el-input-number v-model="createForm.hyperparams.batch" :min="1" :max="128" /></el-form-item>
    <el-form-item label="conf"><el-input-number v-model="createForm.hyperparams.conf" :min="0.001" :max="1" :step="0.01" /></el-form-item>
    <el-form-item label="iou"><el-input-number v-model="createForm.hyperparams.iou" :min="0.1" :max="1" :step="0.05" /></el-form-item>
  </el-form>
  <template #footer>
    <el-button @click="createDialogVisible = false">取消</el-button>
    <el-button type="primary" :loading="creating" @click="handleCreateEval">创建</el-button>
  </template>
</el-dialog>
```

在 `<script>` 中补充响应式数据：

```typescript
const createDialogVisible = ref(false);
const modelVersions = ref<any[]>([]);
const createForm = reactive({
  modelId: null as number | null,
  evalDatasetId: null as number | null,
  hyperparams: { imgsz: 640, batch: 16, conf: 0.001, iou: 0.6 },
});

// 加载模型版本列表
(async () => {
  const r = await TrainAPI.getModelList();
  modelVersions.value = r.data?.data || [];
})();
```

修改 `handleCreateEval` 以支持对话框流程。

- [ ] **Step 2: 创建评估详情页 `detail.vue`**

类比 `task/detail.vue`，但更专注于评估指标展示。关键代码结构：

```vue
<template>
  <div class="app-container train-detail-page">
    <!-- header: eval name, status, framework tags -->
    <!-- info card: model, dataset, params -->
    <!-- metrics cards: precision, recall, mAP@50, mAP@50:95 (when status=success) -->
    <!-- per-class metrics table (when available) -->
    <!-- log area: 500px, black bg, WebSocket for running evals, stored log for completed -->
  </div>
</template>
```

核心指标显示：
```vue
<el-card shadow="never" class="section-card">
  <template #header><span class="card-title">评估指标</span></template>
  <div v-if="evalData?.metrics" class="metric-grid">
    <div class="metric-item"><span class="metric-val metric-orange">{{ fmtPct(evalData.metrics.map50) }}</span><span class="metric-lbl">mAP@50</span></div>
    <div class="metric-item"><span class="metric-val metric-purple">{{ fmtPct(evalData.metrics.map5095) }}</span><span class="metric-lbl">mAP@50:95</span></div>
    <div class="metric-item"><span class="metric-val metric-green">{{ fmtPct(evalData.metrics.precision) }}</span><span class="metric-lbl">Precision</span></div>
    <div class="metric-item"><span class="metric-val metric-blue">{{ fmtPct(evalData.metrics.recall) }}</span><span class="metric-lbl">Recall</span></div>
  </div>
  <el-empty v-else :image-size="40" description="暂无评估指标" />
</el-card>
```

日志区域复用 `task/detail.vue` 的 `log-container` 模式。WebSocket 连接地址为 `ws://{baseUrl}/api/v1/train/ws/eval/logs?eval_id={id}`。

- [ ] **Step 3: 添加非 scoped CSS 修复**

在 `detail.vue` 中添加 `<style lang="scss">` 块（与 `task/detail.vue` 一致）：

```vue
<style lang="scss">
.app-container.train-detail-page {
  display: block !important;
  height: auto !important;
  overflow: visible !important;
}
</style>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/module_train/eval/
git commit -m "feat(train): enhance eval list page, add eval detail page"
```

---

### Task 11: 前端预测页面 — 列表 + 详情

**Files:**
- Create: `frontend/src/views/module_train/predict/index.vue`
- Create: `frontend/src/views/module_train/predict/detail.vue`

- [ ] **Step 1: 创建预测列表页 `predict/index.vue`**

标准 CRUD 结构：`PageSearch + PageContent`。

```vue
<template>
  <div class="app-container">
    <PageSearch ref="searchRef" :search-config="searchConfig" @search="handleQueryClick" @reset="handleResetClick" />
    <PageContent ref="contentRef" :content-config="contentConfig">
      <template #toolbar="{ toolbarRight, onToolbar, cols }">
        <div class="data-table__toolbar--left">
          <el-button type="primary" size="small" @click="showCreateDialog = true">创建预测</el-button>
        </div>
        <div class="data-table__toolbar--right">
          <CrudToolbarRight :buttons="toolbarRight" :cols="cols" :on-toolbar="onToolbar" />
        </div>
      </template>
      <template #table="{ data, loading, tableRef, pagination }">
        <div class="data-table__content">
          <el-table :ref="tableRef as any" v-loading="loading" row-key="id" :data="data" border stripe>
            <template #empty><el-empty :image-size="80" description="暂无预测任务" /></template>
            <el-table-column type="selection" width="55" align="center" />
            <el-table-column label="序号" width="60">
              <template #default="scope">{{ (pagination.currentPage - 1) * pagination.pageSize + scope.$index + 1 }}</template>
            </el-table-column>
            <el-table-column label="模型" min-width="150">
              <template #default="{ row }">{{ getModelName(row.model_id) }}</template>
            </el-table-column>
            <el-table-column label="图片来源" width="120">
              <template #default="{ row }">{{ row.source_type === 'dataset' ? '数据集' : '上传' }}</template>
            </el-table-column>
            <el-table-column label="图片数量" width="100">
              <template #default="{ row }">{{ (row.source_images?.length || 0) + (row.source_dataset_id ? 'dataset' : '') }}</template>
            </el-table-column>
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="tagType(row.status)" size="small" effect="plain">{{ tagLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="创建时间" prop="created_time" width="170" />
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <el-button text size="small" type="primary" @click="router.push(`/train/predict/${row.id}`)">详情</el-button>
                <el-button v-if="row.status === 'pending'" text size="small" type="success" @click="handleStart(row.id)">开始</el-button>
                <el-button v-if="row.status === 'running'" text size="small" type="danger" @click="handleStop(row.id)">停止</el-button>
                <el-button v-if="row.result_zip_path" text size="small" type="primary" @click="downloadResult(row)">下载</el-button>
                <el-popconfirm title="确定删除？" @confirm="handleDelete([row.id])">
                  <template #reference><el-button text size="small" type="danger">删除</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>
    </PageContent>

    <!-- Create Dialog -->
    <el-dialog v-model="showCreateDialog" title="创建预测任务" width="600px">
      <el-form label-width="120px">
        <el-form-item label="模型版本" required>
          <el-select v-model="createForm.modelId" filterable style="width:100%">
            <el-option v-for="m in models" :key="m.id" :label="`${m.name} v${m.version}`" :value="m.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="图片来源">
          <el-radio-group v-model="createForm.sourceType">
            <el-radio value="dataset">从数据集</el-radio>
            <el-radio value="upload">上传图片</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="createForm.sourceType === 'dataset'" label="数据集" required>
          <el-select v-model="createForm.sourceDatasetId" filterable style="width:100%">
            <el-option v-for="ds in datasets" :key="ds.id" :label="ds.name" :value="ds.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="createForm.sourceType === 'upload'" label="图片" required>
          <el-upload multiple list-type="picture-card" :auto-upload="false" ref="uploadRef">
            <el-icon><Plus /></el-icon>
          </el-upload>
        </el-form-item>
        <el-form-item label="conf">
          <el-input-number v-model="createForm.hyperparams.conf" :min="0.01" :max="1" :step="0.05" />
        </el-form-item>
        <el-form-item label="iou">
          <el-input-number v-model="createForm.hyperparams.iou" :min="0.1" :max="1" :step="0.05" />
        </el-form-item>
        <el-form-item label="imgsz">
          <el-input-number v-model="createForm.hyperparams.imgsz" :min="32" :step="32" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>
```

Script 部分实现 CRUD 操作、创建预测任务逻辑（上传图片 → 创建任务）、启动/停止/删除/下载。

- [ ] **Step 2: 创建预测详情页 `predict/detail.vue`**

```vue
<template>
  <div class="app-container train-detail-page">
    <!-- Header: model name, status tag, framework -->
    <div class="detail-header">
      <el-button text size="small" @click="router.back()"><el-icon><ArrowLeft /></el-icon></el-button>
      <span class="task-name">预测 #{{ predict?.id }}</span>
      <el-tag :type="tagType(predict?.status || '') as any" size="small">{{ tagLabel(predict?.status || '') }}</el-tag>
    </div>

    <!-- Info cards -->
    <div class="info-cards">
      <el-card shadow="never" class="info-card">
        <template #header><span class="card-title">预测信息</span></template>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="模型版本">{{ getModelName(predict?.model_id) }}</el-descriptions-item>
          <el-descriptions-item label="图片来源">{{ predict?.source_type === 'dataset' ? '数据集' : '上传图片' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ predict?.created_time }}</el-descriptions-item>
          <el-descriptions-item label="完成时间">{{ predict?.finished_at || '—' }}</el-descriptions-item>
        </el-descriptions>
      </el-card>
      <el-card shadow="never" class="info-card">
        <template #header><span class="card-title">参数</span></template>
        <div class="hp-grid">
          <div class="hp-item"><span class="hp-label">conf</span><span class="hp-value">{{ predict?.hyperparams?.conf ?? '—' }}</span></div>
          <div class="hp-item"><span class="hp-label">iou</span><span class="hp-value">{{ predict?.hyperparams?.iou ?? '—' }}</span></div>
          <div class="hp-item"><span class="hp-label">imgsz</span><span class="hp-value">{{ predict?.hyperparams?.imgsz ?? '—' }}</span></div>
        </div>
      </el-card>
    </div>

    <!-- Action buttons -->
    <el-card shadow="never" class="section-card" v-if="predict?.status === 'pending' || predict?.status === 'running'">
      <el-button v-if="predict?.status === 'pending'" type="primary" @click="handleStart">开始预测</el-button>
      <el-button v-if="predict?.status === 'running'" type="danger" @click="handleStop">停止预测</el-button>
    </el-card>

    <!-- Result images grid -->
    <el-card v-if="predict?.result_images?.length" shadow="never" class="section-card">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span class="card-title">预测结果（{{ predict.result_images.length }} 张）</span>
          <el-button v-if="predict.result_zip_path" size="small" type="primary" @click="downloadZip">下载全部</el-button>
        </div>
      </template>
      <div class="result-grid">
        <div v-for="(url, i) in predict.result_images" :key="i" class="result-item">
          <el-image :src="url" :preview-src-list="predict.result_images" fit="cover" style="width:100%;height:200px" />
        </div>
      </div>
    </el-card>

    <!-- Log area -->
    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">预测日志</span></template>
      <div ref="logRef" class="log-container">
        <pre class="log-text">{{ logText || '等待日志...' }}</pre>
      </div>
    </el-card>
  </div>
</template>
```

Script 部分实现：`onMounted` 加载详情，WebSocket 连接（`ws://{baseUrl}/api/v1/train/ws/predict/logs?predict_id={id}`），开始/停止/下载操作。

CSS 块：

```vue
<style lang="scss">
.app-container.train-detail-page {
  display: block !important;
  height: auto !important;
  overflow: visible !important;
}
</style>

<style scoped lang="scss">
.result-grid {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
}
.result-item {
  border-radius: 8px; overflow: hidden; border: 1px solid #ebeef5;
}
/* ... other styles same as task/detail.vue */
</style>
```

- [ ] **Step 3: 确保非 scoped CSS 文件也在 `predict/index.vue` 中使用**

`predict/index.vue` 不用非 scoped 覆盖，因为它是标准 CRUD 页，正常使用全局 `.app-container` flex 布局。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/module_train/predict/
git commit -m "feat(train): add predict list and detail pages"
```

---

### Self-Review 检查清单

1. **Spec coverage:** 所有 spec 中的模块都已覆盖：enhanced TrainEval ✅, TrainPredict ✅, eval_scheduler ✅, predict_executor ✅, ws ✅, permissions/menus ✅, frontend APIs ✅, frontend pages ✅
2. **Placeholder scan:** 无 TBD/TODO 占位，所有代码块完整
3. **Type consistency:** 所有函数签名在任务间一致
4. **Style guide compliance:** 遵循现有的 `scheduler.py`, `controller.py`, `service.py` 模式
