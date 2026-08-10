### Task 4: 统一执行器基类 — 并发 + 孤儿恢复 + 容器生命周期

**Files:**
- Create: `backend/app/plugin/module_train/task_executor.py`
- Modify: `backend/app/plugin/module_train/scheduler.py`
- Modify: `backend/app/plugin/module_train/eval_scheduler.py`
- Modify: `backend/app/plugin/module_train/predict_executor.py`
- Test: `backend/tests/test_task_executor.py`（新建）

**Interfaces:**
- Consumes: `docker_utils`（`run_container`/`follow_container_logs`/`remove_container`）, `ws` 广播函数
- Produces:
  - `class TaskExecutor` — 抽象基类
    - `registry: dict[str, dict[int, dict]]`（内存执行中任务表）
    - `semaphore: asyncio.Semaphore`（每框架独立）
    - `async run(task_id)` — 入口：acquire → 状态 RUNNING → `_execute` → 释放
    - `async stop(task_id)` — 标记 cancel + 停容器 + DB 状态
    - `async _execute(task_id)` — 子类实现
    - `async _mark_running/_mark_success/_mark_failed/_mark_cancelled(db, task_id, **fields)`
    - `async _follow_and_broadcast(container_id, log_file, broadcast_fn, parse_fn)` — 统一日志管道
    - `async recover_orphans()` — 类方法：DB 中 RUNNING 且不在 registry → 按超时标记 FAILED
    - `start_orphan_recovery_loop()` — 类方法：30s 循环

- [ ] **Step 1: 写失败测试 — 基类并发与注册表隔离**

`backend/tests/test_task_executor.py`（纯同步，不触发 DB/容器）：

```python
"""TaskExecutor 基类测试：并发信号量与注册表隔离。"""
import pytest

from app.plugin.module_train.task_executor import TaskExecutor


class TrainExecutorStub(TaskExecutor):
    name = "train"


class EvalExecutorStub(TaskExecutor):
    name = "eval"


def test_semaphore_is_class_shared_and_initialized():
    t1, t2 = TrainExecutorStub(), TrainExecutorStub()
    assert t1._get_semaphore() is t2._get_semaphore()


def test_registry_is_per_executor_class():
    t = TrainExecutorStub()
    e = EvalExecutorStub()
    t._registry[1] = {"container_id": "abc"}
    assert 1 not in e._registry
    assert 1 in t._registry
```

> 说明：基类将 `_registry`/`_semaphore` 定义为**类属性**（每个子类独立副本），`_get_semaphore()` 为类方法惰性初始化。子类只需定义 `name`、`model_class`、`status_enum` 并实现 `_execute`。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && uv run pytest tests/test_task_executor.py -v`
Expected: FAIL（`task_executor` 模块不存在）

- [ ] **Step 3: 实现 `task_executor.py` 基类**

```python
"""统一任务执行器基类：并发控制、孤儿恢复、容器生命周期、日志管道。"""
import asyncio
import os
from abc import ABC, abstractmethod
from datetime import datetime

from sqlalchemy import update

from app.core.database import async_db_session
from app.core.logger import log

from .docker_utils import follow_container_logs, remove_container, stop_container


class TaskExecutor(ABC):
    """抽象基类。子类：TrainExecutor / EvalExecutor / PredictExecutor。

    每个子类通过 __init_subclass__ 维护独立 registry 与信号量。
    并发上限由 _concurrency 控制。
    """
    name: str = "task"
    status_enum = None  # TrainStatus 等
    model_class = None  # TrainTask / TrainEval / TrainPredict
    _concurrency: int = 1
    _registry: dict[int, dict] = {}
    _semaphore: asyncio.Semaphore | None = None
    _recovery_task: asyncio.Task | None = None
    _orphan_timeout_sec: float = 1800.0

    def __init_subclass__(cls, **kwargs):
        """每个子类获得独立的 registry / semaphore / recovery task。"""
        super().__init_subclass__(**kwargs)
        cls._registry = {}
        cls._semaphore = None
        cls._recovery_task = None

    @classmethod
    def _get_semaphore(cls) -> asyncio.Semaphore:
        if cls._semaphore is None:
            cls._semaphore = asyncio.Semaphore(cls._concurrency)
        return cls._semaphore

    @classmethod
    async def run(cls, task_id: int) -> None:
        sem = cls._get_semaphore()
        async with sem:
            await cls._execute_with_state(task_id)

    @classmethod
    async def _execute_with_state(cls, task_id: int):
        try:
            await cls._mark_status(task_id, "running", started_at=datetime.now())
            await cls._execute(task_id)
        except Exception as e:
            log.error(f"[{cls.name}] task {task_id} failed: {e}")
            await cls._mark_status(task_id, "failed", error_log=str(e), finished_at=datetime.now())
        finally:
            cls._registry.pop(task_id, None)

    @classmethod
    @abstractmethod
    async def _execute(cls, task_id: int) -> None:
        """子类实现：pull image → 导出数据 → run container → 收集产物 → 标记状态。"""

    @classmethod
    async def _mark_status(cls, task_id: int, status: str, **fields) -> None:
        values = {"status": status, **fields}
        async with async_db_session.begin() as db:
            await db.execute(update(cls.model_class).where(cls.model_class.id == task_id).values(**values))

    @classmethod
    async def stop(cls, task_id: int) -> None:
        entry = cls._registry.get(task_id)
        if entry and entry.get("container_id"):
            entry["cancel"] = True
            await stop_container(entry["container_id"])
        async with async_db_session.begin() as db:
            await db.execute(
                update(cls.model_class)
                .where(cls.model_class.id == task_id, cls.model_class.status == cls.status_enum.RUNNING)
                .values(status=cls.status_enum.CANCELLED, finished_at=datetime.now())
            )

    @classmethod
    async def follow_logs(cls, container_id: str, log_file: str, broadcast_fn, parse_fn=None):
        """统一日志管道：写文件 + 广播 + 可选指标解析。返回 (metrics_log, exit_code)。"""
        import asyncio as _asyncio
        metrics_log: list = []
        log_queue = await follow_container_logs(container_id)
        with open(log_file, "w", encoding="utf-8") as lf:
            while True:
                line = await log_queue.get()
                if line == "__EOF__":
                    break
                lf.write(line + "\n")
                lf.flush()
                if broadcast_fn:
                    try:
                        await broadcast_fn(line)
                    except Exception:
                        pass
                if parse_fn:
                    parsed = parse_fn(line)
                    if parsed:
                        metrics_log.append(parsed)
        return metrics_log

    @classmethod
    async def _get_exit_code(cls, container):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: container.wait(timeout=600)["StatusCode"])

    @classmethod
    async def recover_orphans(cls) -> None:
        """DB 中 RUNNING 但不在 registry 的任务，超时则标记 FAILED。"""
        async with async_db_session() as db:
            from sqlalchemy import select
            rows = (await db.execute(select(cls.model_class).where(
                cls.model_class.status == cls.status_enum.RUNNING
            ))).scalars().all()
            for r in rows:
                if r.id in cls._registry:
                    continue
                if r.started_at and (datetime.now() - r.started_at).total_seconds() > cls._orphan_timeout_sec:
                    async with async_db_session.begin() as db2:
                        await db2.execute(
                            update(cls.model_class).where(cls.model_class.id == r.id).values(
                                status=cls.status_enum.FAILED,
                                error_log="任务会话已断开（后端重启或容器丢失）",
                                finished_at=datetime.now(),
                            )
                        )

    @classmethod
    async def start_recovery_loop(cls) -> None:
        if cls._recovery_task is None or cls._recovery_task.done():
            cls._recovery_task = asyncio.create_task(cls._recovery_loop())

    @classmethod
    async def _recovery_loop(cls) -> None:
        while True:
            try:
                await cls.recover_orphans()
            except Exception as e:
                log.error(f"[{cls.name}] recovery error: {e}")
            await asyncio.sleep(30)
```

- [ ] **Step 4: 定义子类并接入 init_app**

在 `scheduler.py` 定义 `TrainExecutor`（将原 `_execute_training` 主体迁入 `_execute`，删除原 `_running_tasks`/`MAX_CONCURRENT`/孤儿逻辑，交由基类）：

```python
class TrainExecutor(TaskExecutor):
    name = "train"
    status_enum = TrainStatus
    model_class = TrainTask
    _concurrency = 1

    @classmethod
    async def _execute(cls, task_id: int):
        container_id = None
        try:
            # ---- 以下为原 scheduler._execute_training 主体，原样迁移 ----
            async with async_db_session() as db:
                task = await db.get(TrainTask, task_id)
                if not task:
                    return
            await broadcast_log(task_id, f"[scheduler] pulling image {task.docker_image}...")
            await pull_image(task.docker_image)
            export_dir = await _build_export_dir(task_id)
            data_dir = os.path.join(export_dir, "data")
            os.makedirs(data_dir, exist_ok=True)
            from .exporter import prepare_training_data_for_task
            await prepare_training_data_for_task(
                task.dataset_id, task.id, task.framework, data_dir,
                annotation_task_id=task.annotation_task_id,
                train_ratio=task.hyperparams.get("train_ratio", 0.8),
            )
            cmd = _build_cmd(task)  # 复用现有 _build_ultralytics_cmd/_build_paddlex_cmd
            os.makedirs(MODELS_CACHE_DIR, exist_ok=True)
            container = await run_container(
                task.docker_image, cmd,
                volumes={data_dir: {"bind": "/data", "mode": "rw"},
                         export_dir: {"bind": "/output", "mode": "rw"},
                         MODELS_CACHE_DIR: {"bind": "/models", "mode": "ro"}},
                gpu_id=task.hyperparams.get("gpu_id", "0"),
            )
            container_id = container.id
            cls._registry[task_id] = {"container_id": container_id, "cancel": False}

            metrics_log = await cls.follow_logs(
                container_id,
                os.path.join(export_dir, "train.log"),
                lambda line: broadcast_log(task_id, line),
                _parse_epoch,
            )
            exit_code = await cls._get_exit_code(container)

            if cls._registry.get(task_id, {}).get("cancel"):
                await remove_container(container_id)
                await cls._mark_status(task_id, TrainStatus.CANCELLED, finished_at=datetime.now())
            elif exit_code == 0:
                await remove_container(container_id)
                from .exporter import export_model
                model_info = await export_model(task_id, task.framework, export_dir)
                await cls._mark_status(task_id, TrainStatus.SUCCESS,
                                       model_repo_id=model_info.get("repo_id"),
                                       progress=100, finished_at=datetime.now(),
                                       metrics_log=metrics_log or None,
                                       best_metrics=cls._compute_best(metrics_log),
                                       last_metrics=metrics_log[-1] if metrics_log else None)
                if getattr(task, "created_id", None):
                    _send_notify(task.created_id, f"训练完成: {task.name}",
                                 "任务已成功完成，模型已保存", "training_complete", "train", task_id)
            else:
                await remove_container(container_id)
                await cls._mark_status(task_id, TrainStatus.FAILED,
                                       error_log="training failed", finished_at=datetime.now())
        except Exception as e:
            log.error(f"training task {task_id} failed: {e}")
            await cls._mark_status(task_id, TrainStatus.FAILED,
                                   error_log=str(e), finished_at=datetime.now())
        finally:
            cls._registry.pop(task_id, None)
            if container_id:
                await remove_container(container_id)
```

> `_build_cmd` 与 `_compute_best` 由实现者从现有 `_build_ultralytics_cmd`/`_build_paddlex_cmd` 与 best_metrics 逻辑提取为模块函数。

在 `eval_scheduler.py` 定义 `EvalExecutor`：

```python
class EvalExecutor(TaskExecutor):
    name = "eval"
    status_enum = TrainStatus
    model_class = TrainEval
    _concurrency = 1

    @classmethod
    async def _execute(cls, eval_id: int):
        # 原 eval_scheduler._execute_evaluation 主体迁移，
        # 模型路径解析改用 TrainService._resolve_model_storage（Task 5 提供）。
        # 日志管道改用 cls.follow_logs；状态更新改用 cls._mark_status；
        # registry 用 cls._registry；container 生命周期沿用 docker_utils。
        raise NotImplementedError  # 由实现者按上述指引填充
```

> 注意：`EvalExecutor._execute` 中不能写 `raise NotImplementedError` 后交付——实现者须完整迁移原 `_execute_evaluation` 逻辑（Task 4 Step 4 为骨架指引，完整实现在执行时按原文件内容迁移）。若实现者选择在 Task 4 一次性完成三个子类完整迁移，可跳过本骨架的占位符。

在 `predict_executor.py` 定义 `PredictExecutor`：

```python
class PredictExecutor(TaskExecutor):
    name = "predict"
    status_enum = TrainStatus
    model_class = TrainPredict
    _concurrency = 1

    @classmethod
    async def _execute(cls, predict_id: int):
        # 原 predict_executor._execute_prediction 主体迁移，
        # 模型路径解析改用 TrainService._resolve_model_storage（Task 5 提供）。
        # 本类新增孤儿恢复（此前缺失），由基类 start_recovery_loop 统一提供。
        raise NotImplementedError  # 由实现者按上述指引填充
```

> **重要**：Task 4 Step 4 的两个 `raise NotImplementedError` 是骨架指引，**不允许交付到最终代码**。实现者应在该 Step 内完成三个子类的完整 `_execute` 迁移（复制原 executor 文件逻辑 + 替换 registry/状态/日志调用点），并运行 `uv run ruff check` 确保无 `NotImplementedError` 残留。若任务过大，可拆分为 Task 4a/4b/4c 各自完成一个子类迁移并单独提交。

`init_app.py:535-541` 改为三个子类的恢复循环：

```python
from app.plugin.module_train.scheduler import TrainExecutor
from app.plugin.module_train.eval_scheduler import EvalExecutor
from app.plugin.module_train.predict_executor import PredictExecutor

asyncio.create_task(TrainExecutor.start_recovery_loop())
asyncio.create_task(EvalExecutor.start_recovery_loop())
asyncio.create_task(PredictExecutor.start_recovery_loop())
```

> 注：`PredictExecutor` 此前无孤儿恢复循环——Task 4 修复此缺陷。原 `start_scheduler`/`start_evaluation_scheduler` 的调度循环（定时训练触发、孤儿清理）合并进各自 executor 的 recovery loop。

- [ ] **Step 5: 运行测试验证基类**

Run: `cd backend && uv run pytest tests/test_task_executor.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_train/task_executor.py backend/app/plugin/module_train/scheduler.py backend/app/plugin/module_train/eval_scheduler.py backend/app/plugin/module_train/predict_executor.py backend/app/scripts/init_app.py backend/tests/test_task_executor.py
git commit -m "feat(train): unified TaskExecutor base with concurrency and orphan recovery"
```

---


