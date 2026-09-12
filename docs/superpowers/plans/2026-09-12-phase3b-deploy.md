# Phase 3B：部署生命周期与脚本 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 部署注册表可重建、停/删必停真实容器、正常退出更新状态、周期对账、端口可复用；PaddleX 部署配置由模型规格驱动、rec 用检测框裁剪识别；续期 API Key 触发容器重建；推理超参透传；避免每次启动 `pip install`。

**Architecture:** 容器打 label（`aistation.task_kind=deploy`）；`_deploy_running` 从 DB `container_id` 重建；`start_deploy_recovery` 改为周期循环；服务脚本按 `resolve_deploy_spec` 生成。

**Tech Stack:** FastAPI + SQLAlchemy + Docker SDK + pytest。

## Global Constraints

- 后端 `D:\AIStation\backend`（`uv run pytest`/`uv run ruff check`，只判断新增）；中文注释；不新增依赖；提交 `fix(train): 中文描述`；禁 `git add -A`；ruff `fix=true` 时还原无关改动。
- 单测不跑真实容器：monkeypatch docker/DB；**真机验证**用本地镜像 `ultralytics/ultralytics:latest` 与 `paddlex:latest` 各部署一次并检查 `/health`。
- 不改 `start_deployment` 的对外语义（已 running/deploying 直接返回）。

---

### Task 1: 部署生命周期（重建/对账/停止/端口/正常退出）

**背景:** `_deploy_running` 仅内存；重启后 `stop_deployment`（`deploy_executor.py:255-267`）无 entry → 只改 DB 不停真实容器；`_execute_deployment` 正常退出（exit_code==0 且未取消）**什么都不做** → 状态卡 running；`recover_orphan_deploys` 只启动跑一次、不重建注册表；端口选择排除**所有** `host_port>0`（含 stopped/failed）→ 从不复用。

**Files:**
- Modify: `backend/app/plugin/module_train/deploy_executor.py`
- Modify: `backend/app/plugin/module_train/service.py`（`renew_deploy_key` 重启容器；`delete_deploys` 停容器）
- Test: `backend/tests/test_deploy_lifecycle.py`

**Interfaces:**
- Produces: `deploy_exit_status(cancel: bool, exit_code: int) -> str | None` —— 取消→`None`（stop 已处理）；`exit_code==0`→`"stopped"`；否则→`"failed"`。
- Produces: `is_port_reusable(status: str) -> bool` —— `deploying`/`running` 不可复用，其余（stopped/failed/pending）可复用。

- [ ] **Step 1: Write the failing test**

```python
"""部署生命周期决策测试。"""
from app.plugin.module_train.deploy_executor import deploy_exit_status, is_port_reusable


def test_deploy_exit_status():
    assert deploy_exit_status(cancel=True, exit_code=0) is None
    assert deploy_exit_status(cancel=False, exit_code=0) == "stopped"
    assert deploy_exit_status(cancel=False, exit_code=137) == "failed"


def test_is_port_reusable():
    assert is_port_reusable("stopped") is True
    assert is_port_reusable("failed") is True
    assert is_port_reusable("pending") is True
    assert is_port_reusable("running") is False
    assert is_port_reusable("deploying") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_deploy_lifecycle.py -q`
Expected: FAIL（函数不存在）。

- [ ] **Step 3: Implement**

`deploy_executor.py`：
```python
def deploy_exit_status(cancel: bool, exit_code: int) -> str | None:
    """容器退出后的部署状态：取消由 stop 处理；否则成功=stopped、失败=failed。"""
    if cancel:
        return None
    return "stopped" if exit_code == 0 else "failed"


def is_port_reusable(status: str) -> bool:
    return status not in ("deploying", "running")
```
- `_launch` 增加 `labels={"aistation.task_kind": "deploy", "aistation.task_id": str(deploy_id)}`。
- `stop_deployment`：无 registry entry 时，从 DB 读 `container_id` 并停；仍无则按 label 查 `find_task_containers("deploy", deploy_id)` 停。
- `_execute_deployment` 正常退出分支：
```python
        status = deploy_exit_status(bool(_deploy_running.get(deploy_id, {}).get("cancel")), exit_code)
        if status == "failed":
            error_msg = (await get_container_error_tail(container_id)).strip()
        if status is not None:
            await remove_container(container_id)
            async with async_db_session.begin() as db:
                await db.execute(update(TrainDeploy).where(TrainDeploy.id == deploy_id).values(
                    status=status, finished_at=datetime.now(),
                    container_id=None, error_log=(error_msg if status == "failed" else None),
                ))
```
- `recover_orphan_deploys`：对 `running` 且容器存在（`_container_exists`）的行，重建 `_deploy_running[deploy_id] = {"container_id": ..., "cancel": False}`（便于之后 stop）；不存在则标 failed（现有逻辑）。
- `start_deploy_recovery` 改为周期循环（每 30s 调 `recover_orphan_deploys`），并保留首次立即执行。
- 端口预留查询改为只取活跃状态：
```python
                rows = (await db.execute(
                    select(TrainDeploy.host_port).where(
                        TrainDeploy.host_port > 0,
                        TrainDeploy.status.in_(("deploying", "running")),
                    )
                )).scalars().all()
```
- `service.py` `renew_deploy_key`：更新 key 后，调用 `stop_deployment(deploy_id)` 再 `start_deployment(deploy_id)`（或返回标记由前端重启）；`delete_deploys`：删行前对每个 id `await stop_deployment(id)`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_deploy_lifecycle.py -q`
Expected: PASS（2 passed）

- [ ] **Step 5: full suite + ruff + commit + 真机验证**

Run: `cd backend && uv run pytest -q && uv run ruff check app/plugin/module_train/deploy_executor.py app/plugin/module_train/service.py`

真机（可选，本地有 Docker）：部署一个 ultralytics 模型 → 等 `/health` 200 → 重启后端 → 调 stop → 确认容器被停（`docker ps` 无该容器）。

```bash
git add backend/app/plugin/module_train/deploy_executor.py backend/app/plugin/module_train/service.py backend/tests/test_deploy_lifecycle.py
git commit -m "fix(train): 部署注册表重建/周期对账/停止真实容器/端口复用/正常退出落状态"
```

---

### Task 2: 部署服务脚本（规格驱动 / rec 裁剪 / 超参透传）

**背景:** `_generate_paddlex_server_script` 硬编码 `PP-OCRv6_small_det.yml`/`_small_rec.yml`（`deploy_executor.py:169-170`），tiny/medium 部署必崩；`_rec_text(img)` 对**整图**识别（`deploy_executor.py:228`）而非检测框裁剪；Ultralytics 脚本未用部署超参（conf/iou/imgsz）；每次启动 `pip install`（`deploy_executor.py:42`）拖慢健康检查。

**Files:**
- Modify: `backend/app/plugin/module_train/deploy_executor.py`
- Test: `backend/tests/test_deploy_server_script.py`

**Interfaces:**
- Produces: `resolve_deploy_spec(deploy, model_rec) -> tuple[str, str]` —— 返回 `(mode, size)`：优先 deploy.hyperparams，其次产出该模型的训练任务 hyperparams，缺省 `("det","tiny")`。
- Ultralytics 服务脚本内嵌 `conf`/`iou`/`imgsz`；PaddleX 服务脚本 cfg 用解析出的 `size`/`mode`，且 rec 用**检测框裁剪**后识别。

- [ ] **Step 1: Write the failing test**

```python
"""部署服务脚本生成测试。"""
from app.plugin.module_train.deploy_executor import (
    _generate_paddlex_server_script, _generate_server_script,
)


def test_paddlex_script_uses_spec():
    script = _generate_paddlex_server_script("key123", "cpu", mode="rec", size="medium")
    assert "PP-OCRv6_medium_rec.yml" in script
    # rec 必须裁剪检测框后识别（不是整图）
    assert "_rec_text(crop" in script
    assert "key123" in script


def test_ultralytics_script_embeds_hyperparams():
    script = _generate_server_script("k", "cpu", conf=0.3, iou=0.5, imgsz=960)
    assert "conf=0.3" in script or '"conf": 0.3' in script or "0.3" in script
    assert "960" in script
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/test_deploy_server_script.py -q`
Expected: FAIL（签名不含 mode/size/conf 等）。

- [ ] **Step 3: Implement**

`deploy_executor.py`：
```python
async def resolve_deploy_spec(deploy, model_rec) -> tuple[str, str]:
    """推断部署 OCR 的 (mode, size)：deploy.hyperparams → 训练任务 → 默认。"""
    hp = deploy.hyperparams or {}
    mode = str(hp.get("mode", "")).lower()
    size = str(hp.get("model_size", ""))
    if mode not in ("det", "rec") or size not in ("tiny", "small", "medium"):
        from sqlalchemy import desc, select
        from .model import TrainTask
        async with async_db_session() as db:
            task = (await db.execute(
                select(TrainTask).where(TrainTask.model_repo_id == deploy.model_id)
                .order_by(desc(TrainTask.id)).limit(1)
            )).scalar_one_or_none()
        thp = (task.hyperparams or {}) if task else {}
        mode = mode or str(thp.get("mode", "det")).lower()
        size = size or str(thp.get("model_size", "tiny"))
    return (mode if mode in ("det", "rec") else "det",
            size if size in ("tiny", "small", "medium") else "tiny")
```
- `_generate_paddlex_server_script(api_key, device, mode, size)`：把 `DET_CFG`/`REC_CFG` 改为按 `size`/`mode` 拼 `configs/{det,rec}/PP-OCRv6/PP-OCRv6_{size}_{mode}.yml`；`/predict` 循环里改为：
```python
    for box in boxes:
        crop = _crop_box(img, box)
        text, conf = _rec_text(crop)
        ...
```
并定义 `_crop_box(img, box)`（用 `cv2.boundingRect` + 裁剪；越界裁剪保护）。
- `_generate_server_script(api_key, device, conf, iou, imgsz)`：脚本内用这些值调用 `model(img, device=..., conf=..., iou=..., imgsz=...)`。
- 去掉启动即 `pip install`，改为按需：
```python
try:
    import fastapi  # noqa
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "fastapi", "uvicorn", "python-multipart"], check=True)
```
- `_execute_deployment` 调用两个生成器时传入 `resolve_deploy_spec` 结果与 `deploy.hyperparams` 的 conf/iou/imgsz。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/test_deploy_server_script.py -q`
Expected: PASS

- [ ] **Step 5: full suite + ruff + commit + 真机验证**

真机（可选）：用 `paddlex:latest` 部署一个 OCR 模型（size=small/medium），`/predict` 返回的文本应正确（非整图重复）。

```bash
git add backend/app/plugin/module_train/deploy_executor.py backend/tests/test_deploy_server_script.py
git commit -m "fix(train): 部署脚本规格驱动、rec 裁剪识别、超参透传、按需安装依赖"
```

---

## Self-Review

**Spec coverage（对照 Phase 3 spec 组件 B）:**
- 注册表重建/对账/停真实容器/端口复用/正常退出 → Task 1 ✅
- 续期重启 → Task 1 ✅
- 规格驱动/rec 裁剪/超参透传/去掉 pip install → Task 2 ✅

**Placeholder scan:** 无 TBD；每步含代码或明确要点。

**Type consistency:** `deploy_exit_status`/`is_port_reusable`/`resolve_deploy_spec` 命名一致；`_generate_*_server_script` 新签名在调用处同步。

**风险:** `resolve_deploy_spec` 依赖 `TrainTask.model_repo_id==版本id`（与 eval/predict 一致）；真机验证需本地 `paddlex:latest`（size 与模型匹配）。周期性对账若 daemon 不可达需依赖 `_container_exists` 的"无法证明缺失→True"语义，避免误杀。
