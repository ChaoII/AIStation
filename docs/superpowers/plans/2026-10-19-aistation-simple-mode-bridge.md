# AIStation Simple Mode Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 AIStation 平台侧打通「简单模式」bridge：submodule 引入 TorchKiln、执行器双后端（container 现状不动 / simple 子进程+回调）、`train_metric_events` 结构化事件表（替代 metrics_log 新写入）、前端环境指标面板。

**Architecture:** `TorchKilnExecutor._execute` 顶部按 `settings.TORKILN_MODE` 分派；simple 模式走「资源动态决策 → 子进程 `python -m torchkiln.simple_run` → 内部端点 EventReceiver 收事件 → 落 `train_metric_events` 表 + SSE 扇出」；指标展示层保留现有行结构（事件表物化为行），前端零破坏性改造 + 新增 env 面板。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + PostgreSQL（SQLite 测试）、uv、Vue3 + Element Plus + ECharts（vue-echarts）。

**Spec:** `docs/superpowers/specs/2026-10-19-aistation-torchkiln-bridge-design.md`（第 3.1 / 3.2 / 3.5 / 3.8 节）；依赖 TorchKiln 侧 plan（`2026-10-19-torchkiln-simple-mode-support.md`）完成后的 commit pin。

## Global Constraints

- **容器模式零回归**：`TORKILN_MODE` 默认 `container`，现有 `_execute`/`_pump`/`gpu_pool`/`tk_job_container` 逻辑**不修改**（仅加分支）；`test_torchkiln_task_status.py`、`test_train_executor_ops.py`、`test_torchkiln_job_container.py`、`test_torchkiln_client_eval.py`、`test_predict_torchkiln_contract.py` 必须全绿。
- **懒加载**：`torchkiln`/`ptcore` 仅在 `_execute_simple` 内 import；启动/问数/AI 应用路径不得触碰训练栈；未装训练依赖时 simple 入口给清晰报错（`RuntimeError("未安装训练依赖，请安装 simple 可选组")`）。
- **迁移必须手写**（AGENTS.md 教训：dev 库 400+ 影子表，禁 autogenerate）；`train_metric_events` 为迁移链内新表（用 `op.create_table`），插件表增列才需 `has_table` 判定。
- **事件 seq 幂等**：同一 `(task_id, seq)` 只落一次（`UniqueConstraint(task_id, seq)` + 冲突忽略）。
- **测试命令**：`cd backend; PYTEST_NO_APP=1 .venv/Scripts/python.exe -m pytest tests/<file>.py -q`（纯逻辑）；`uv run pytest tests/<file>.py -q`（需 DB/应用）；全量用 `-n 4` 不用 `-n 8`。
- **本 plan 在 AIStation worktree 分支实施，验收后合并 main；期间不动主工作区。**

## Review Focus

1. **旧任务兼容**：存量任务只有 `metrics_log` 没有事件表——`/metrics` 与 SSE 必须回退读 `metrics_log`（老逻辑），不能白屏/空曲线。→ 任务 6 测试覆盖。
2. **事件风暴**：训练 5s 一条 env + 高频 step，EventReceiver 必须异步落库（`asyncio.create_task` 或队列），且限流/RATE_LIMIT 不误伤内部端点。→ 任务 4 测试覆盖。
3. **子进程崩溃**：simple 模式子进程被杀/`returncode != 0`——任务必须收敛到 FAILED（不悬挂 RUNNING），并通过 recover_orphans 兜底。→ 任务 5 测试覆盖。
4. **回调端点是内部接口**：必须 `include_in_schema=False` + token 校验（`hmac.compare_digest`，fail-closed），不暴露 OpenAPI。→ 任务 4 测试覆盖。
5. **动态并发边界**：同卡多任务时总显存不超；`TORKILN_SIMPLE_MAX_CONCURRENT` 为硬上限。→ 任务 5 测试覆盖。

---

### Task 1: submodule 引入与可选依赖

**Files:**
- Create: `backend/submodules/torchkiln`（git submodule）
- Modify: `backend/pyproject.toml`（新增 `[project.optional-dependencies] simple`）
- Modify: `.gitmodules`（由 `git submodule add` 生成）

**Interfaces:**
- Consumes: TorchKiln 侧 plan 最终 commit `TK_COMMIT`
- Produces: `pyproject.toml` 新增：
  ```toml
  [project.optional-dependencies]
  simple = ["torchkiln @ file://./submodules/torchkiln"]
  ```
  （torch/CUDA 按文档由用户按机器安装；TorchKiln 自身依赖会连带安装。）

- [ ] **Step 1: submodule add**
  `git submodule add https://github.com/ChaoII/TorchKiln.git backend/submodules/torchkiln` → `git submodule update --init`（在 TorchKiln 侧 plan 完成后执行，并 checkout 到 `TK_COMMIT`）

- [ ] **Step 2: 更新 pyproject**（如上；`uv lock` 更新——注意锁文件只记录 simple extra，不影响默认安装）

- [ ] **Step 3: 验证**：`cd backend; uv sync --extra simple --dry-run` 成功解析（不实际装 torch）；默认 `uv sync` 不含 torch。

- [ ] **Step 4: 提交**
  `git add .gitmodules backend/submodules backend/pyproject.toml uv.lock && git commit -m "feat(train): 引入 torchkiln submodule 与 simple 可选依赖组"`

---

### Task 2: 配置项（settings）

**Files:**
- Modify: `backend/app/config/setting.py`（347-401 行 TORKILN 区块附近）
- Test: `tests/test_simple_mode_settings.py`

**Interfaces:**
- Produces（带默认值）：
  ```python
  TORKILN_MODE: Literal["container", "simple"] = "container"
  TORKILN_SIMPLE_CALLBACK_TOKEN: str = ""
  TORKILN_SIMPLE_ENV_INTERVAL: float = 5.0
  TORKILN_SIMPLE_MAX_CONCURRENT: int = 4
  ```

- [ ] **Step 1: 写失败测试**（`PYTEST_NO_APP=1` 快速模式；断言默认值 + 从 `TORKILN_MODE=simple` 环境变量可覆盖）

- [ ] **Step 2: 运行确认失败** → **Step 3: 实现** → **Step 4: 通过**

- [ ] **Step 5: 提交**
  `git commit -m "feat(train): 新增 simple mode 配置项"`

---

### Task 3: `train_metric_events` 模型与手写迁移

**Files:**
- Modify: `backend/app/plugin/module_train/model.py`（新增 `TrainMetricEvent`，表 `train_metric_events`）
- Create: `backend/app/alembic/versions/2026_10_19_train_metric_events.py`
- Test: `tests/test_train_metric_events_model.py`

**Interfaces:**
- Produces:
  ```python
  class TrainMetricEvent(MappedBase):
      __tablename__ = "train_metric_events"
      id / task_id(FK train_tasks.id) / seq / ts(DateTime) / type(str16) / payload(JSONB)
      __table_args__ = (UniqueConstraint("task_id", "seq", name="uq_tme_task_seq"),)
  ```
- `async def insert_event(session, task_id, seq, ts, type_, payload) -> bool`（返回是否新插入；冲突时 `ROLLBACK` 后返回 False——见任务 4 容器化）
- 查询函数（任务 6 消费）：`async def list_events(session, task_id, type_=None, limit=5000, offset=None) -> list[dict]`

- [ ] **Step 1: 写失败测试**（用 `test_client`/SQLite fixture：建表后插入两条同 `(task_id, seq)` → 第二条不重复；`list_events` 按 type 过滤）

- [ ] **Step 2: 运行确认失败**（无模型/无迁移）

- [ ] **Step 3: 实现**：模型类（`MappedBase` 即可，带 id/created_time）；手写迁移 `upgrade()` 用 `op.create_table`（列 + `sa.UniqueConstraint` + 索引 `(task_id, type, ts)`），`downgrade()` drop；`sa.inspect(bind).has_table()` 幂等判定。

- [ ] **Step 4: 运行确认通过**：`uv run pytest tests/test_train_metric_events_model.py -q`；再 `uv run main.py upgrade --env=dev`（dev 库真实建表）

- [ ] **Step 5: 提交**
  `git commit -m "feat(train): train_metric_events 模型与手写迁移（task_id+seq 唯一）"`

---

### Task 4: EventReceiver 内部端点 + 落库 + SSE 扇出

**Files:**
- Modify: `backend/app/plugin/module_train/controller.py`（新增内部端点）
- Create: `backend/app/plugin/module_train/event_ingest.py`（解析/物化/落库逻辑，纯函数便于测试）
- Test: `tests/test_simple_event_ingest.py`

**Interfaces:**
- Consumes: Task 3 `insert_event`/`list_events`；现 `TorchKilnExecutor.publish_metric(task_id, row)`；`settings.TORKILN_SIMPLE_CALLBACK_TOKEN`
- Produces:
  - 端点：`POST /api/v1/train/internal/events`（`include_in_schema=False`，**不挂 AuthPermission**，header `X-Torchkiln-Token` 与 `settings.TORKILN_SIMPLE_CALLBACK_TOKEN` `hmac.compare_digest` 校验，fail-closed；token 为空或 401 → `ErrorResponse`/HTTP 401）
  - 请求体：`{"task_id": int, "seq": int, "ts": float, "type": str, **fields}`（字段平铺）
  - `def render_event_row(ev: dict) -> dict`：**把事件渲染为与现有 `_row_from_event` 相同结构的行**（step 摊平 `comps`、eval/best 摊平 `metrics`、带 `_kind`/`seq`/`total_epochs` 等——保持前端行格式不变）
  - 处理器流程：校验 token → `insert_event`（幂等）→ `publish_metric(task_id, render_event_row(ev))` → 201
  - 环境指标台账更新钩子：`async def update_usage_tasks(ev)`（type="env" 时更新 Redis 台账，供任务 5 调度用；**第一版可 no-op 占位 + 注释**，任务 5 接线）

- [ ] **Step 1: 写失败测试**（`test_client` + monkeypatch `publish_metric`）：

```python
def test_receiver_auth_fail_closed(client):
    r = client.post("/api/v1/train/internal/events", json={...}, headers={})   # 无 token
    assert r.status_code == 401

def test_receiver_ingest_and_publish(client, monkeypatch):
    published = []
    monkeypatch.setattr("...publish_metric", lambda tid, row: published.append((tid, row)))
    r = client.post(..., headers={"X-Torchkiln-Token": settings.TORKILN_SIMPLE_CALLBACK_TOKEN},
                    json={"task_id": 1, "seq": 1, "ts": 1.0, "type": "step", "loss": 0.5, "epoch": 1})
    assert r.status_code == 201 and published and published[0][1]["_kind"] == "step"

def test_duplicate_seq_not_reingested(client, ...):
    # 同一 seq 发两次 → 只落一次（publish 仅一次）
```

- [ ] **Step 2: 运行确认失败**（无端点）

- [ ] **Step 3: 实现**：`event_ingest.py`（`render_event_row` 复制现有 `_row_from_event` 的摊平语义——从 `torchkiln_executor.py` 复用/抽取，注意**不改现有函数**，新建独立实现避免破坏容器路径）；controller 加端点（`@router.post("/internal/events", include_in_schema=False)` 无权限依赖 + token 校验 + `async def` 落库）。

- [ ] **Step 4: 运行确认通过**（含容器模式现有测试回归）

- [ ] **Step 5: 提交**
  `git commit -m "feat(train): 内部事件接收端点（token 校验 + 幂等落库 + SSE 扇出）"`

---

### Task 5: Executor 双后端分派 + `_execute_simple` + 动态并发

**Files:**
- Modify: `backend/app/plugin/module_train/torchkiln_executor.py`（`_execute` 557 行加分支；新增 `_execute_simple`、`_simple_scheduler` 相关）
- Create: `backend/app/plugin/module_train/simple_scheduler.py`
- Test: `tests/test_simple_executor.py`、`tests/test_simple_scheduler.py`

**Interfaces:**
- Consumes: Task 2 配置、Task 3 `insert_event`、Task 4 `render_event_row`；现有 `_mark_status`/`_STATUS_MAP`/`progress_from_rows`/`exporter`/`model_persist`
- Produces:
  - `_execute_simple(cls, task_id)`：懒 import（`import torchkiln` 包）→ 读 task/`_build_spec()`（复用现有）→ 成功后把 `hyperparams["__tk_mode"]="simple"` 写回任务（供恢复/读取判定，复用 `set_job_id` 类似机制）→ `simple_scheduler.acquire(task_id, need_mem_gb, est_mem_gb)` → 写 spec.json 到 `task_workdir` → `asyncio.create_subprocess_exec(sys.executable, "-m", "torchkiln.simple_run", spec_path, "--callback-url", callback_url, "--token", settings.TORKILN_SIMPLE_CALLBACK_TOKEN, "--task-id", str(task_id), "--repo-root", settings.TORKILN_REPO_PATH, cwd=settings.TORKILN_REPO_PATH)` → 记录 `task_id→pid` 到 Redis 台账 → 等 `returncode`（期间 env/step 事件由 EventReceiver 驱动）→ `_mark_status` 按 `end` 事件 + 退出码（`_STATUS_MAP` 复用）→ SUCCESS 时 `export_model`（复用现有）→ finally `release`
  - `simple_scheduler.py`：
    - `async def acquire(task_id, need_mem_gb, est_mem_gb) -> Allocation | None`：用 `gpu_pool.device` 的 NVML 枚举函数（import 复用，不改造），按「free_gb ≥ max(need, est) × 1.2 且 util < 85%」选卡（允许**同卡多任务**——不取整卡锁；写 Redis 台账 `simple_tasks:{task_id}` = `{gpu_id, mem_reserved, ts}`）；超 `TORKILN_SIMPLE_MAX_CONCURRENT` → 返回 None（排队）
    - `async def release(task_id)`；`def usage_snapshot() -> dict`（各卡 free/util/占用台账，供测试与看板）
    - 更新钩子 `update_usage_tasks(ev)` 接线（env 事件 → `hset` 台账）

- [ ] **Step 1: 写失败测试**（monkeypatch `create_subprocess_exec` 为假进程（可控 returncode）；断言：mode=simple 时调用 `_execute_simple`、子进程 argv 正确（含 `-m torchkiln.simple_run` + spec 路径 + `--task-id`）、`_mark_status` 收到 SUCCESS/FAILED、`release` 被调用；scheduler：mock NVML 数据 → 显存足够时同卡两次 acquire 都成功（同卡多任务）、超上限时返回 None；**孤儿恢复**：`recover_orphans` 下 simple 任务（hyperparams 有 `__tk_mode=simple` 且 Redis pid 已死/超时无事件）→ 置 FAILED，pid 存活则 reattach）

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**（按 Interfaces；`recover_orphans` 增加 simple 分支：读取任务 `hyperparams.__tk_mode`，simple 任务按「Redis pid 存活 + 最近事件时间戳（超 3 分钟无事件视为异常）」判定，死亡/超时 → `_mark_status(FAILED)`，存活 → 后台 reattach 继续等待）

- [ ] **Step 4: 运行确认通过** + 容器模式回归（`test_torchkiln_task_status.py` 等全绿）

- [ ] **Step 5: 提交**
  `git commit -m "feat(train): simple 模式执行器与动态并发调度（子进程+回调，容器路径不动）"`

---

### Task 6: 指标读取改造（事件表物化 + metrics_log 兼容回退）

**Files:**
- Modify: `backend/app/plugin/module_train/torchkiln_executor.py`（`load_metrics_rows` 132 行改为事件表优先/兼容读；`_pump` 不触碰——容器模式仍走旧路径）
- Modify: `backend/app/plugin/module_train/service.py`（`get_task`/指标相关接口：simple 任务从事件表物化 rows 返回）
- Modify: `backend/app/plugin/module_train/controller.py`（`GET /task/{id}/metrics` 290 行、`/metrics/stream` 323 行：simple 任务从事件表读；新增 `GET /task/{id}/env-metrics`：按 `type="env"` 区间返回）
- Test: `tests/test_simple_metrics_read.py`

**Interfaces:**
- Consumes: Task 3 `list_events`、Task 4 `render_event_row`
- Produces: `def task_uses_events(task) -> bool`（hyperparams 有 `__tk_mode=simple` 标记或 `TORKILN_MODE=simple` 且任务为 simple 创建）；`load_rows(task_id) -> list[dict]`（事件表按 seq 物化；无事件 → 回退 `metrics_log`）

- [ ] **Step 1: 写失败测试**：建 simple 任务（插入事件表）→ `/metrics` 返回物化行（结构与旧行一致）；旧任务（只 metrics_log）→ 仍返回旧行（兼容）；`/env-metrics` 只返回 env 类型行。

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**（按 Interfaces；SSE 订阅端 `subscribe_metrics` 上游事件已是行格式，无需改）

- [ ] **Step 4: 运行确认通过**

- [ ] **Step 5: 提交**
  `git commit -m "feat(train): 指标读取改事件表物化（存量 metrics_log 兼容回退）"`

---

### Task 7: 前端 env 面板与数据源适配

**Files:**
- Modify: `frontend/src/api/module_train.ts`（新增 `getEnvMetrics(id, start, end)`）
- Modify: `frontend/src/views/module_train/task/detail.vue`（新增环境指标面板区块；`metricEventToRow`/`enumerateMetricsFromLog` 增加 `env` 类型分支；MAX_METRIC_ROWS 适配）
- Modify: `frontend/src/views/module_train/components/`（复用 MetricMiniChart；或新增 `EnvMetricPanel.vue` 单根组件）
- Test: `pnpm run type-check` + `pnpm run lint` + 无头截图视觉核对（项目规范）

**Interfaces:**
- Consumes: Task 6 接口
- Produces: env 面板显示 GPU 利用率/温度/功耗/显存 + CPU/内存/磁盘/网络（el-row/el-col 布局，复用 MetricMiniChart；样式走 `--el-*`，不自定义字号/配色）

- [ ] **Step 1: 实现**：detail.vue 在指标卡区域后新增 `<EnvMetricPanel :rows="envRows"/>`（单根 div 包裹，避免 Transition 白屏陷阱）；`envRows` 初载调 `getEnvMetrics`，SSE 收到的 `env` 行实时追加（局部更新，不整表刷新——AGENTS.md 规范）。

- [ ] **Step 2: 验证**：`pnpm run type-check`、`pnpm run lint` 干净

- [ ] **Step 3: 视觉核对**：无头浏览器截图（训练详情页，含 env 面板），多模态读图与既有页面风格对照（Element Plus 组件、字号、间距一致）

- [ ] **Step 4: 提交**
  `git commit -m "feat(train): 训练详情环境指标面板（GPU/CPU/内存/磁盘/网络）"`

---

### Task 8: 集成验证（smoke）与文档

**Files:**
- Create: `backend/scripts/smoke_simple_mode.py`（一键 smoke：CPU 小数据跑通 train → eval → predict → export 四链路，打印事件计数与退出码）
- Modify: 相关文档（AGENTS.md 无——文档落 `docs/superpowers/specs/` 关联处或 README 训练章节）
- Test: 无新增（smoke 脚本即验证）

- [ ] **Step 1: 写 smoke 脚本**（win/linux 通用：CPU 模式，yolo11n 小数据集或 OCR tiny；四链路顺序执行；断言各链路退出码 0 且有 `end` 事件）

- [ ] **Step 2: 运行**：`.venv/Scripts/python.exe scripts/smoke_simple_mode.py` → 四链路全 PASS（无 GPU 时用 CPU；若环境无 torch 则打印「未安装 simple 依赖」引导）

- [ ] **Step 3: 提交**
  `git commit -m "test(train): simple mode 四链路 smoke 脚本"`

---

## Execution Notes

- 任务 1（submodule）需 TorchKiln 侧 plan 完成并提交后执行；任务 3-8 中 3 先行（表是落库前提），4 → 5 → 6 → 7 按依赖序；2 可并行。
- 每任务提交前跑对应测试 + 容器模式关键回归（`test_torchkiln_task_status.py`、`test_train_executor_ops.py`）。
- 全部完成后：全量 `uv run pytest -q -n 4` 绿 + 前端 type-check/lint + 视觉核对 → 请用户验收 → 合并 main。
