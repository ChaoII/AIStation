# Phase 2A：训练调度与执行器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 修复定时训练必失败与 `schedule/list` 500；给容器打 label 并按 label 停容器；删除运行中任务先停容器；`start` 状态守卫防止重复启动；重启恢复不再误标失败（存活容器判定）；`base_model_id` 接线；训练并发上限。

**Architecture:** 后端 `app/plugin/module_train/`：把定时任务的 mock 数据抽成纯函数便于测试；`docker_utils` 支持 label 与按 label 查容器；`TaskExecutor` 用 label 做恢复/停止；`TrainService.delete_tasks` 先停运行中任务。

**Tech Stack:** FastAPI + SQLAlchemy + Docker SDK + pytest（SQLite，测试中不实际跑容器，monkeypatch docker 调用）。

## Global Constraints

- 后端命令 `D:\AIStation\backend`（`uv run pytest` / `uv run ruff check`，只判断新增问题）。中文注释。不新增依赖。
- 提交风格 `fix(train): 中文描述`；只 `git add` 本任务文件；ruff `fix=true` 时还原无关改动。
- 测试不得真实启动容器：一律 monkeypatch `docker_utils`/`scheduler` 的容器调用。
- 现有 `recover_orphans` 已用 `framework_value` 正确区分 PaddleX（Phase 0A 修复），勿回退。

---

### Task 1: 定时训练修复 + schedule 序列化

**背景:** `scheduler.py:94-100` 的 mock 任务缺 `base_model_id`，而 `service.create_task`（`service.py:328`）读取 `data.base_model_id` → `AttributeError`，定时训练每条计划必失败并被 outer except 吞掉、`last_run_at` 不推进（30s 反复重试）。`schedule_service.list_schedules:18` 用 `dict(r.__dict__)` 含 `_sa_instance_state`，`jsonable_encoder` 序列化 500。

**Files:**
- Modify: `backend/app/plugin/module_train/scheduler.py`
- Modify: `backend/app/plugin/module_train/schedule_service.py`
- Test: `backend/tests/test_train_schedule.py`

**Interfaces:**
- Produces: `build_scheduled_task_data(schedule) -> SimpleNamespace`（含 `name/dataset_id/annotation_task_id/framework/hyperparams/base_model_id`）。
- Produces: `_schedule_to_dict(row) -> dict`（仅列 columns，可 JSON 序列化）。

- [ ] **Step 1: Write the failing test**

```python
"""定时训练数据构造与 schedule 序列化测试。"""
import json
from types import SimpleNamespace

from app.plugin.module_train.model import TrainFramework
from app.plugin.module_train.schedule_model import TrainScheduleModel
from app.plugin.module_train.schedule_service import _schedule_to_dict
from app.plugin.module_train.scheduler import build_scheduled_task_data


def test_build_scheduled_task_data_has_required_attrs():
    s = SimpleNamespace(
        name="x", dataset_id=1, annotation_task_id=2,
        framework=TrainFramework.ULTRALYTICS, hyperparams={},
    )
    data = build_scheduled_task_data(s)
    for attr in ("name", "dataset_id", "annotation_task_id", "framework", "hyperparams", "base_model_id"):
        assert hasattr(data, attr), attr


def test_schedule_to_dict_is_json_serializable():
    s = TrainScheduleModel(name="n", dataset_id=1, framework="ultralytics",
                           hyperparams={}, cron_expr="0 2 * * 0")
    d = _schedule_to_dict(s)
    json.dumps(d)  # 不得抛异常
    assert "_sa_instance_state" not in d
    assert d["name"] == "n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_train_schedule.py -q`
Expected: FAIL（`build_scheduled_task_data` / `_schedule_to_dict` 不存在）。

- [ ] **Step 3: Write minimal implementation**

`scheduler.py` 新增纯函数并替换 mock：

```python
def build_scheduled_task_data(schedule) -> SimpleNamespace:
    """把计划行转成 create_task 所需的数据对象（签名与 TrainService.create_task 一致）。"""
    from types import SimpleNamespace
    return SimpleNamespace(
        name=f"[定时] {schedule.name}",
        dataset_id=schedule.dataset_id,
        annotation_task_id=getattr(schedule, "annotation_task_id", None),
        framework=schedule.framework,
        hyperparams=getattr(schedule, "hyperparams", None) or {},
        base_model_id=getattr(schedule, "base_model_id", None),
    )
```

在 `_scheduler_loop` 中把 `task_data = type("data", (), {...})()` 替换为 `task_data = build_scheduled_task_data(s)`。并把 `last_run_at` 更新移到"创建成功后立即、且失败也推进"：

```python
                    try:
                        task_data = build_scheduled_task_data(s)
                        result = await TrainService.create_task(task_data, _ScheduleAuth())
                        new_id = result.get("id")
                        if new_id:
                            await start_training(new_id)
                    except Exception as e:
                        new_id = None
                        log.error(f"scheduled training failed for schedule {s.id}: {e}")
                    finally:
                        async with async_db_session.begin() as db:
                            await db.execute(
                                update(TrainScheduleModel).where(TrainScheduleModel.id == s.id).values(
                                    last_run_at=datetime.now(), last_task_id=new_id
                                )
                            )
```

（删除原先成功的更新块，避免重复。）

`schedule_service.py` 新增：

```python
def _schedule_to_dict(row) -> dict:
    """仅导出列，避免 dict(__dict__) 带入 _sa_instance_state 导致序列化 500。"""
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}
```

并把 `list_schedules` 的 `[dict(r.__dict__) for r in ...]` 改为 `[_schedule_to_dict(r) for r in ...]`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_train_schedule.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: full suite + ruff + commit**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_train/scheduler.py app/plugin/module_train/schedule_service.py`

```bash
git add backend/app/plugin/module_train/scheduler.py backend/app/plugin/module_train/schedule_service.py backend/tests/test_train_schedule.py
git commit -m "fix(train): 定时训练数据补 base_model_id 且失败也推进 last_run_at；schedule 序列化去 _sa_instance_state"
```

---

### Task 2: 容器 label + 按 label 停容器 + 删除运行中任务先停 + start 状态守卫

**背景:** 执行器只在内存 registry 记录 container_id；重启后 `stop` 找不到容器 → 容器继续跑（占 GPU/端口）。删除运行中任务直接删行 → 容器成孤儿。`start_training` 无状态守卫 → 可对 RUNNING/已完成任务重复启动。

**Files:**
- Modify: `backend/app/plugin/module_train/docker_utils.py`
- Modify: `backend/app/plugin/module_train/task_executor.py`
- Modify: `backend/app/plugin/module_train/scheduler.py`（`start_training` 守卫）
- Modify: `backend/app/plugin/module_train/service.py`（`delete_tasks` 先停）
- Test: `backend/tests/test_train_executor_ops.py`

**Interfaces:**
- `run_container(..., labels: dict | None = None)`；容器 label 用 `aistation.task_kind`（train/eval/predict/deploy）与 `aistation.task_id`。
- Produces: `find_task_containers(task_kind: str, task_id: int) -> list[str]` —— 按 label 返回容器 id（同步实现 + 异步包装）。
- `TaskExecutor.stop` 在 registry 无记录时按 label 查找并停容器。

- [ ] **Step 1: Write the failing test**

```python
"""执行器操作测试（不真实跑容器）。"""
import pytest

from app.plugin.module_train import scheduler as sch
from app.plugin.module_train import docker_utils as du


def test_start_training_refuses_running_task(monkeypatch, test_client, auth_headers):
    # 通过 DB 造一个 RUNNING 任务，start 应拒绝而非重复启动
    ...
    # 见 Step 3 说明：用 sqlite 直连把任务状态置 RUNNING，再调用 start_training
    # 期望抛出异常且不调用 docker_utils.run_container


def test_find_task_containers_filters_by_label(monkeypatch):
    class _C:
        def __init__(self, i, labels):
            self.id = i
            self.labels = labels
    class _Containers:
        def list(self, all=True, filters=None):
            return [_C("a", {"aistation.task_kind": "train", "aistation.task_id": "7"}),
                    _C("b", {"aistation.task_kind": "eval", "aistation.task_id": "7"})]
    monkeypatch.setattr(du, "client", type("L", (), {"containers": _Containers()})())
    assert du.find_task_containers("train", 7) == ["a"]
```

（第二个测试直接验证 label 过滤逻辑；第一个测试在 Step 3 补全具体写法。）

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_train_executor_ops.py -q`
Expected: FAIL（`find_task_containers` 不存在；start 无守卫）。

- [ ] **Step 3: Implement**

`docker_utils.py`：
```python
def _run_container(image, cmd, volumes, gpu_id, env, ports=None, entrypoint=None, shm_size=None, labels=None):
    ...
    kwargs = {..., "labels": labels or {}, ...}

async def run_container(..., labels: dict | None = None):  # 透传

def find_task_containers(task_kind: str, task_id: int) -> list[str]:
    """按 label 查找该任务的容器 id（含已退出未删除的）。"""
    try:
        cs = client.containers.list(all=True, filters={
            "label": [f"aistation.task_kind={task_kind}", f"aistation.task_id={task_id}"]})
        return [c.id for c in cs]
    except Exception:
        return []

async def stop_task_containers(task_kind: str, task_id: int) -> None:
    for cid in find_task_containers(task_kind, task_id):
        await stop_container(cid)
```

`task_executor.py`：
- 子类声明 `task_kind`（TrainExecutor→"train"，PaddleXOCRExecutor→"train"，EvalExecutor→"eval"，PredictExecutor→"predict"，DeployExecutor→"deploy"）。
- `_execute` 调 `run_container` 时传 `labels={"aistation.task_kind": cls.task_kind, "aistation.task_id": str(task_id)}`（各子类执行处补；本任务至少 TrainExecutor + PaddleX）。
- `stop`：registry 无 entry 时 `await stop_task_containers(cls.task_kind, task_id)`。

`scheduler.py` `start_training` 开头加守卫：
```python
        if task.status == TrainStatus.RUNNING:
            raise Exception("任务正在运行，请勿重复启动")
```
（放在取到 task 之后、标注任务校验之前。）

`service.py delete_tasks`：删除前对 RUNNING 任务先停：
```python
    async def delete_tasks(cls, ids):
        from .scheduler import stop_training
        async with async_db_session() as db:
            rows = [await db.get(TrainTask, i) for i in ids]
        for t in rows:
            if t and t.status == TrainStatus.RUNNING:
                await stop_training(t.id)
        async with async_db_session.begin() as db:
            for tid in ids:
                t = await db.get(TrainTask, tid)
                if t:
                    await db.delete(t)
```

- [ ] **Step 4: 补全第一个测试**

用 sqlite 直连把某任务 `status` 置 `RUNNING`，monkeypatch `scheduler.asyncio.create_task` 与 `docker_utils.run_container` 断言未被调用，调用 `await sch.start_training(task_id)` 期望抛异常。

- [ ] **Step 5: Run test + full + ruff + commit**

Run: `cd backend && uv run pytest tests/test_train_executor_ops.py -q && uv run pytest -q`

```bash
git add backend/app/plugin/module_train/docker_utils.py backend/app/plugin/module_train/task_executor.py backend/app/plugin/module_train/scheduler.py backend/app/plugin/module_train/service.py backend/tests/test_train_executor_ops.py
git commit -m "fix(train): 容器打 label、按 label 停容器、删除运行中任务先停、start 状态守卫"
```

---

### Task 3: 重启恢复不误标失败（存活容器判定）

**背景:** `TaskExecutor.recover_orphans` 只看内存 registry：重启后 registry 为空，存活容器被忽略，超时后误标 FAILED 且容器/产物丢失。改为：有按 label 命中的存活容器 → 重连日志跟随并收集产物；否则超时标记 FAILED 并清理。

**Files:**
- Modify: `backend/app/plugin/module_train/task_executor.py`
- Modify: `backend/app/plugin/module_train/scheduler.py`（TrainExecutor 重连）
- Test: `backend/tests/test_train_recovery.py`

**Interfaces:**
- Produces: `recovery_decision(has_live_container: bool, started_at, now, timeout_sec) -> str` —— 返回 `"reattach" | "fail" | "wait"`。

- [ ] **Step 1: Write the failing test**

```python
"""重启恢复决策测试。"""
from datetime import datetime, timedelta

from app.plugin.module_train.task_executor import recovery_decision


def test_recovery_decision_reattach_when_container_alive():
    now = datetime.now()
    assert recovery_decision(True, now - timedelta(hours=2), now, 1800) == "reattach"


def test_recovery_decision_wait_before_timeout():
    now = datetime.now()
    assert recovery_decision(False, now - timedelta(seconds=30), now, 1800) == "wait"


def test_recovery_decision_fail_after_timeout():
    now = datetime.now()
    assert recovery_decision(False, now - timedelta(hours=2), now, 1800) == "fail"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_train_recovery.py -q`
Expected: FAIL（`recovery_decision` 不存在）。

- [ ] **Step 3: Implement decision + wire**

`task_executor.py`：
```python
def recovery_decision(has_live_container: bool, started_at, now, timeout_sec: float) -> str:
    """重启恢复决策：存活→重连；否则未超时→等待、超时→标记失败。"""
    if has_live_container:
        return "reattach"
    if started_at and (now - started_at).total_seconds() > timeout_sec:
        return "fail"
    return "wait"
```

`recover_orphans` 改为：对每个 RUNNING 且不在 registry 的行，`has_live = bool(find_task_containers(cls.task_kind, r.id))`，按 `recovery_decision` 分支：
- `"reattach"`：调用子类 `reattach(r.id, container_id)`（新增钩子，默认 `pass`）；TrainExecutor 实现为重新 `follow_logs` + 收尾（抽出 `_finalize(task_id, container)` 供 `_execute` 与 `reattach` 复用）。
- `"wait"`：不动。
- `"fail"`：现有标记 FAILED + 清理容器。

（`reattach` 的实现较大：把 `_execute` 中"跟随日志 + 判定退出码 + export_model + 标状态"抽成 `_finalize`。若完成困难，先实现"存活容器不误标失败 + 记录 warning"并把完整重连作为 DONE_WITH_CONCERNS 上报，附具体卡点。）

- [ ] **Step 4: Run test + full + ruff + commit**

Run: `cd backend && uv run pytest tests/test_train_recovery.py -q && uv run pytest -q`

```bash
git add backend/app/plugin/module_train/task_executor.py backend/app/plugin/module_train/scheduler.py backend/tests/test_train_recovery.py
git commit -m "fix(train): 重启恢复按存活容器重连，避免误标失败与产物丢失"
```

---

### Task 4: base_model_id 接线 + 训练并发上限

**背景:** `base_model_id` 写入后从不读取；训练/PaddleX det/PaddleX rec 各自 `_concurrency=1`，最多 3 个 GPU 作业抢同一卡。

**Files:**
- Modify: `backend/app/plugin/module_train/scheduler.py`
- Modify: `backend/app/plugin/module_train/task_executor.py`
- Test: `backend/tests/test_train_base_model_concurrency.py`

**Interfaces:**
- Produces: `resolve_base_model(task, export_dir) -> str | None` —— 当 `base_model_id` 指向有 `storage_path` 的模型版本时，下载到 `export_dir/base/` 并返回可挂载的相对名（挂载到 `/base`）；否则 None。
- 全局并发：模块级 `asyncio.Semaphore(TRAIN_GPU_CONCURRENCY)`（默认 1）由 TrainExecutor/PaddleXOCRDet/Rec 共享。

- [ ] **Step 1: Write the failing test**

```python
"""base_model 解析与并发配置测试。"""
from app.plugin.module_train import scheduler as sch


def test_resolve_base_model_none_without_id(monkeypatch):
    class T: base_model_id = None
    assert __import__("asyncio").run(sch.resolve_base_model(T(), "/tmp/x")) is None


def test_train_gpu_concurrency_is_module_level():
    from app.plugin.module_train import concurrency
    assert isinstance(concurrency.TRAIN_GPU_CONCURRENCY, int)
    assert concurrency.TRAIN_GPU_CONCURRENCY >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_train_base_model_concurrency.py -q`
Expected: FAIL。

- [ ] **Step 3: Implement**

新增 `backend/app/plugin/module_train/concurrency.py`：
```python
import asyncio

TRAIN_GPU_CONCURRENCY = 1
train_gpu_semaphore = asyncio.Semaphore(TRAIN_GPU_CONCURRENCY)
```

`resolve_base_model`（scheduler.py）：读取 `base_model_id` 对应 `TrainModel.storage_path`，用 `s3_client.download_fileobj` 落盘到 `<export_dir>/base/<basename>`；返回该文件名。命令构造里对 ultralytics：`model=/base/<name>`（并把它加入 volumes 只读挂载 `/base`）。PaddleX：作为 `Global.pretrained_model` 覆盖 `/pretrained/{mode}.pdparams`（若已用 pretrained，优先 base_model）。

执行器：`_execute` 进入前 `async with concurrency.train_gpu_semaphore:` 包裹容器运行阶段（三执行器共享）。

- [ ] **Step 4: Run test + full + ruff + commit**

Run: `cd backend && uv run pytest tests/test_train_base_model_concurrency.py -q && uv run pytest -q`

```bash
git add backend/app/plugin/module_train/concurrency.py backend/app/plugin/module_train/scheduler.py backend/app/plugin/module_train/task_executor.py backend/tests/test_train_base_model_concurrency.py
git commit -m "feat(train): base_model_id 作为初始权重接线 + 全局 GPU 并发上限"
```

---

## Self-Review

**Spec coverage（对照 Phase 2 spec 组件 A）:**
- 定时训练 + schedule 序列化 → Task 1 ✅
- 容器 label/停容器/删除运行中/start 守卫 → Task 2 ✅
- 重启恢复 → Task 3 ✅
- base_model + 并发 → Task 4 ✅

**Placeholder scan:** 无 TBD。Task 3 的 `reattach` 全实现较大，明确了"卡点则 DONE_WITH_CONCERNS 上报"，非占位。

**Type consistency:** `build_scheduled_task_data`/`_schedule_to_dict`/`find_task_containers`/`recovery_decision`/`resolve_base_model`/`TRAIN_GPU_CONCURRENCY` 命名在定义/使用/测试处一致。

**风险:** Task 3 的重连需重构 `_execute` 为 `_start`/`_finalize`，改动面大且需真机验证；Task 4 的 base_model 需要真机验证权重生效（小数据集 1-2 epoch 对比 loss）。
