# AIStation ↔ TorchKiln 简单模式（Simple Mode）Bridge 设计

- 日期：2026-10-19
- 状态：**设计定稿（待用户终审）**
- 范围：AIStation（`backend/app/plugin/module_train`、前端 `module_train`）与 TorchKiln（`ptcore/`、`torchkiln/`、`service/`）两个仓库 + submodule 引入 + 事件流改造
- 关联文档：`docs/superpowers/plans/2026-09-30-torchkiln-per-job-container.md`（容器模式现状与踩坑总档）

## 一、背景与目标

**现状**：AIStation 与 TorchKiln 是两个独立 git 仓库（`github.com/ChaoII/*`），无 submodule。集成方式为「每个训练任务起一个 `torchkiln:0.1.0` Docker 容器（约 10GB 基础镜像）→ 容器内跑 TorchKiln service → 平台 HTTP 提交 JobSpec + SSE 拉指标/日志 + 轮询状态机」。痛点：

1. 改 TorchKiln 代码必须重新构建约 10GB 镜像（并有镜像代码身份校验 `TORKILN_EXPECTED_REVISION`），开发调试慢；
2. 需要「启动好几套服务」（Docker 守护 + 每任务容器 + 平台），部署门槛高；
3. 系统环境指标（GPU 利用率/温度/功耗等）未与训练任务绑定（平台 monitor 只做主机的 NVML 监控，TorchKiln 只有 `meta.json` 快照 + step 事件显存字段）；
4. 平台侧 `metrics_log` 是「整列覆盖写 JSONL + 5000 行上限 + 前端全量拉取解析」的文本通道，存在 TOAST 吃满、断线重画等缺陷。

**目标**（与用户确认的决策）：

1. **简单模式**：AIStation 直接以源码（submodule）方式使用 TorchKiln（`import torchkiln` / `import ptcore`），简化部署与开发调试，不再启动多套服务；
2. **Docker 模式保留**（默认 `container`，现状不变），两种模式并存互不影响；
3. **Bridge 四链路全打通**：训练 / 评估 / 预测 / 导出部署（常驻部署服务第一版不并入 simple，仅到「生成部署包」）；
4. **系统环境指标**：GPU / CPU / 内存 / 磁盘 IO / 网络 IO 全类别，采样间隔可配（默认 5s），**两条模式共享**（TorchKiln 侧采集）；
5. **训练步骤指标直接回调**，平台侧改为**结构化事件流**（`train_metric_events` 表）替代 `metrics_log` 文本通道；
6. **Windows 原生可跑**（CPU 或 CUDA 版 torch）；
7. **依赖按需安装**：core（AIStation 本体）与 training-stack（torchkiln + torch + 训练依赖）分层；
8. **动态并发调度**：按本地 CUDA 数量、显存占用、GPU 利用率动态决策，小模型可同卡多任务并行。

## 二、总体架构

```
AIStation 仓库                                TorchKiln 仓库（git submodule）
┌──────────────────────────────────┐          ┌─────────────────────────────┐
│ backend/submodules/torchkiln ──────git submodule (pin commit)──► github.com/ChaoII/TorchKiln
│                                  │          │  ptcore/env_sampler.py  (新增)
│ TorchKilnExecutor                │          │  ptcore/events.py       (新增)
│   ├─ mode=container（现状不动）───┼──每任务一容器 + HTTP/SSE          │  torchkiln/simple_run.py (新增)
│   └─ mode=simple（新增）──────────┼──子进程 python -m torchkiln.simple_run
│                                  │          │  （JobSpec 同契约 + 事件回调）│
│ EventReceiver （内部端点）◄────────┼──HTTP loopback POST 事件(带token)   │  Windows 平台无关化      │
│   └─ train_metric_events（新表）  │          │  metrics.jsonl 文件契约保留 │
│      └─ SSE 扇出（前端不变）       │          └─────────────────────────────┘
└──────────────────────────────────┘
```

## 三、详细设计

### 3.1 集成形态（submodule 与依赖）

- **submodule**：`backend/submodules/torchkiln` → `https://github.com/ChaoII/TorchKiln.git`，**pin 到 commit**（可复现；升级时手动 `git submodule update --remote` + bump，不自动跟随）。
- **依赖分层**（`backend/pyproject.toml`）：
  - core：AIStation 本体（FastAPI/agno/SQLAlchemy/DB/Redis 等），**不含 torch/torchkiln**；
  - `[project.optional-dependencies] simple`（训练栈）：`torchkiln`（path 指向 submodule）+ torch（CPU/CUDA wheel 分开说明、清华源，pytorch CUDA 轮子走清华 `pytorch-wheels` 镜像）+ TorchKiln 依赖（opencv 等）；命令形如 `pip install .[simple]` / `uv sync --extra simple`。
  - **懒加载**：`torchkiln`/`torch` 仅在 simple 模式执行作业时 `importlib` 延迟导入；AIStation 启动、问数、AI 应用等路径永不触碰训练栈。
  - **清晰报错**：`TORKILN_MODE=simple` 但训练栈未安装时，训练相关入口返回明确提示（「未安装训练依赖，请安装 simple 可选组」），而非 import 崩溃。
- **源码即配置**：simple 模式下模型清单/超参 schema/训练配置**直接读 submodule 源码**：`torchkiln/configs/*.yml`（55 个 YOLO 配置、OCR det/rec 配置）+ `torchkiln/` 任务定义；调试时改 yaml 即时生效；容器模式保留原 registry/schema 通路。

### 3.2 执行器双后端

`TorchKilnExecutor.run()` 顶部按 `settings.TORKILN_MODE` 分派：

- `container`：现有 `_execute`（起容器 + 提交 JobSpec + SSE/轮询）**整体保留，一行不动**。
- `simple`：新增 `_execute_simple`，单任务链路：

```
1) 数据导出      exporter 复用（不变）
2) 资源决策      动态并发调度（见 3.4）：选卡/排队
3) 起子进程      asyncio.create_subprocess_exec(python, "-m", "torchkiln.simple_run",
                 job_spec.json, --callback-url, --token)
4) 回调通道      子进程内 EventCallback --HTTP POST--> EventReceiver（step/eval/best/env/end/failed）
5) 状态收敛      _mark_status 复用（子进程退出码 + end/failed 事件；progress/best_metrics 照旧）
6) 权重入库      exporter/model_persist 复用（不变）
```

- **子进程入口 `torchkiln.simple_run`**（TorchKiln 侧新增）：读 JobSpec（复用 `service/schemas.py`，**与容器模式同一契约**）→ 分派 train/eval/predict/export 四类作业 → 训练循环内注入 `EventCallback` → 按退出码报终态。
- **崩溃/恢复**：执行器持有子进程（`task_id → pid` 记 Redis + 心跳/退出码监控）；simple 模式孤儿恢复按「任务表状态 + Redis pid 存活」判定，与容器版（容器 label 过滤）**分家互不干扰**；平台重启后 simple 任务按现有 `_mark_status` 恢复语义（不自动续跑，与容器模式一致）。
- **并发控制**：由 3.4 动态决策；`TORKILN_SIMPLE_MAX_CONCURRENT` 设硬上限兜底（默认 4）。

### 3.3 事件回调数据流

- **通道**：子进程 → `http://127.0.0.1:{平台端口}/internal/torchkiln/events`（**内部私有端点 + 一次性 token**，`TORKILN_SIMPLE_CALLBACK_TOKEN`）。选 HTTP loopback 而非 multiprocessing 队列：跨平台可靠（无 pickle 兼容坑）、可调试、未来 Docker 模式（service 转发）可复用同一端点。
- **事件模型**（TorchKiln `ptcore/events.py`）：`StepEvent / EvalEvent / BestEvent / EnvEvent / EndEvent / FailedEvent`，均为结构化 dataclass，带 `seq`（自增）、`ts`、`task_id`。
- **平台侧**：`EventReceiver` 校验 token → 按 `seq` 去重/补序（断连重发不重画曲线）→ 落 `train_metric_events` → `publish_metric` 扇出给前端 SSE 订阅者（现有机制不变）。
- **TorchKiln 侧双路输出**：`metrics.jsonl` 文件契约**保留**（TorchKiln 内部契约：崩溃后指标真值、容器模式 service tail 源、恢复场景）；`EventCallback` 是**并行新增通道**，不是替换。

### 3.4 动态并发调度

- **资源台账（Redis）**：每 CUDA 设备实时 `free 显存 / 利用率 / 温度 / 功耗`（来自 EnvSampler env 回调 + NVML 兜底轮询）+ 运行中任务台账（`task_id → gpu_id、预估/实测显存、开始时间`）。
- **决策函数**：

```
候选卡 = 显存余量 ≥ 预计需求 × 安全系数  且  当前利用率 < 阈值(默认 85%)
选卡   = 优先「余量富余多 + 利用率低」的卡（多卡均衡）
不满足 → 任务排队（复用现有 status 守卫，不占资源）
```

- **显存预估**：模型配置推导（yaml 的 batch/img_size/model size 等）→ **首个 step 实测回填校准**（step 事件 `mem_reserved` 喂回台账）。
- **闭环**：env 事件（GPU 利用率/显存实时值）→ 台账更新 → 下次决策更准。
- 效果：小模型（yolo11n/tiny、小 OCR）同卡多任务并行；大模型自动串行。

### 3.5 指标存储：统一结构化事件表

- **新表 `train_metric_events`**：

```sql
CREATE TABLE train_metric_events (
  id        BIGSERIAL PRIMARY KEY,
  task_id   BIGINT NOT NULL,            -- 关联 train_tasks.id
  seq       INT  NOT NULL,              -- 事件自增号（用于去重/补序）
  ts        TIMESTAMPTZ NOT NULL,
  type      VARCHAR(16) NOT NULL,       -- step|eval|best|env|end|failed
  payload   JSONB NOT NULL,             -- 结构化事件体
  created_time TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_tme_task_type_ts ON train_metric_events (task_id, type, ts);
```

- **迁移手写**（遵循本项目教训：dev 库有 400+ 未被模型覆盖的历史/影子表，禁 autogenerate）；插件表增列需 `sa.inspect(bind).has_table()` 判断（防空库全链重放），新建本表无此问题但同样手写。
- **写入改向**：`_consume_metrics`/`save_metrics` 改为「事件落表」，`_row_from_event` 摊平逻辑简化（事件本身即结构化对象）；**容器模式 SSE 事件同样改为落 events 表**（两种模式共享同一落库代码——bridge 核心收益）。
- **`metrics_log` 退役**：不再有新写入；存量任务历史数据保留，展示层做兼容读。
- **layer 决策**：`env` 也是事件的一种（`type='env'`），不单独建表；前端按区间查询。

### 3.6 四链路执行形态

| 链路 | simple 模式执行 | 契约复用 |
|------|----------------|---------|
| 训练 | 子进程长任务 + 事件回调 | JobSpec；`_STATUS_MAP`/`_mark_status` 不变 |
| 评估 | 子进程跑 eval（simple_run eval 分支） | EVAL_METRIC_JSON 契约不变，`eval_scheduler` 解析复用 |
| 预测 | 子进程跑一次性推理（simple_run predict 分支），结果经回调/文件回传 | 现有预测结果回传逻辑复用 |
| 导出/部署 | 子进程跑 export 生成权重/部署包 | exporter/model_persist 复用；**常驻部署服务第一版保留现有形态**（simple 只管「生成」） |

### 3.7 TorchKiln 侧同步优化（两条模式共享）

1. **`ptcore/env_sampler.py`**：跨平台采样（`psutil` CPU/内存/磁盘/网络 + `pynvml` GPU 每卡利用率/显存/温度/功耗，Windows 可用；无 GPU 回退只报 CPU/内存）；间隔可配（默认 5s）；产出 `EnvEvent`；**双路输出**：写 `metrics.jsonl` 新 `env` 事件（容器模式 service tail 无需改动即转发）+ EventCallback emit。
2. **`ptcore/events.py`**：事件 dataclass + `BaseTrainer` 关键点 `emit()`（step/eval/best/end 沿用现有点位 + 周期 env）；`metrics.jsonl` 照写（并行，不替换）。
3. **`torchkiln/simple_run.py`**：`python -m torchkiln.simple_run <job_spec.json> --callback-url --token`；复用 `service/schemas.py` JobSpec；读源码 `configs/*.yml`；四类作业分派；HTTP callback 推事件；终态退出码。
4. **Windows 平台无关化**：排查修复 `signal`（Windows 无 SIGALRM 等）、posixpath 假设、`multiprocessing` spawn、`/dev/shm` 等 Linux 假设、pynvml 回退——交付「平台无关兼容清单」作为 TorchKiln 测试项。
5. **版本**：以上在 TorchKiln worktree 分支实现（验收后合并 main；独立发版 0.1.x，不破现有 service 契约）；AIStation submodule bump pin 到对应 commit。

### 3.8 前端改动

- 训练详情页新增**环境指标面板**：GPU 利用率/温度/功耗/显存 + CPU/内存/磁盘/网络曲线，按区间查询 `train_metric_events(type='env')` 渲染。
- `trainMetrics.ts` / `detail.vue` 数据源从 `metrics_log` 改为事件表接口（按类型+区间）。
- 沿用现有图表组件与 Element Plus `--el-*` 规范（不新增图表库、不自定义字号/主题色）；完成后面向既有页面做无头截图 + 多模态视觉核对（项目规范）。
- SSE 实时扇出不变（实时曲线照旧）。

### 3.9 配置项（AIStation `settings.py`）

```python
TORKILN_MODE: Literal["container", "simple"] = "container"  # 默认容器（现状不变）
TORKILN_SIMPLE_CALLBACK_TOKEN: str | None = None             # 内部事件端点 token
TORKILN_SIMPLE_ENV_INTERVAL: float = 5.0                     # 环境采样间隔（秒）
TORKILN_SIMPLE_MAX_CONCURRENT: int = 4                       # 并发硬上限（动态决策之上）
```

## 四、非功能与约束

- **不加 Celery**：训练是「少数长任务 + 状态机」而非消息队列需求；调度用已有 APScheduler（定时/触发）+ 子进程执行 + `train_tasks` 状态机 + Redis 资源池。未来若出现大量异步短任务再评估 Arq（Redis+asyncio，轻量）。
- **依赖按需** + 国内镜像（apt/pip/uv 清华源；pytorch CUDA 轮子走清华 `pytorch-wheels` 镜像）——遵循 AGENTS.md 硬规矩。
- **Windows 原生**（CPU/CUDA）为第一优先兼容目标；Linux 同样支持。
- **容器模式零回归**：所有现有契约测试（`test_torchkiln_*`、`test_train_executor_ops` 等）必须保持全绿。

## 五、测试策略（TDD）

| 仓库 | 测试 | 说明 |
|------|------|------|
| TorchKiln | `env_sampler` 单测（mock psutil/nvml、无 GPU 回退）、`events` 单测（字段/seq/emit 点位）、`simple_run` 契约测试（JobSpec → 小 smoke）、Windows 兼容清单回归 | 现有 service 契约测试保持全绿 |
| AIStation | `test_metric_events.py`（事件表写入/查询/seq 去重/旧 metrics_log 兼容读）、`test_simple_executor.py`（mode 分派/子进程启动/回调落库/状态收敛/动态并发决策） | 容器模式现有测试保持全绿；前端 type-check + 无头截图视觉核对 |

（按项目测试效率规范：纯逻辑测试用 `PYTEST_NO_APP=1` 快速模式；落库类按单文件跑。）

## 六、实施顺序

1. **阶段 1（TorchKiln worktree）**：EnvSampler → EventCallback → simple_run → Windows 平台无关化 → 配套测试 → 提交到 TorchKiln worktree 分支（**验收后合并回 main**，与第七节一致）。
2. **阶段 2（AIStation worktree）**：submodule 引入 + pin → 可选依赖组 → settings → EventReceiver → executor 双后端分派 → `train_metric_events` 表（手写迁移）→ 落库改向（含容器模式）→ 前端 env 面板/数据源改造 → 测试。
3. **阶段 3（验证）**：真实小模型 smoke（CPU/GPU 小数据跑通 train/eval/predict/export 四链路）+ 前端视觉核对 + submodule bump + 提交。

## 七、worktree 与验收

- **AIStation**：`git worktree`（基于 main HEAD 新建分支），**不影响当前主工作区**（主工作区现有未提交改动——含「智能问数」目录结构改造——留在原地，与本次工作隔离，另行收尾）。
- **TorchKiln**（`D:\TorchKiln`）：同样 `git worktree` 新建分支。
- **验收**：两仓库在 worktree 内完成全部验证（契约测试全绿 + smoke + 视觉核对）后，经用户确认再各自合并回 main（用户要求：worktree 直到验收）。

## 八、风险与开放问题

- **风险**：TorchKiln Windows 化可能遇到未知平台假设——阶段 1 以「兼容清单 + 回归测试」兜底，遇到障碍逐条解决并回写清单；torch CUDA wheel 依赖清华 `pytorch-wheels` 镜像（AGENTS.md 已实测可用）；submodule pin 与 TorchKiln 演进节奏需手动协调；常驻部署服务第一版不并入 simple（后续真实需求再扩）。
- **开放问题**：无（核心取舍均已在本文定稿：统一事件表、HTTP loopback 回调、动态并发、四链路范围、按需依赖、Windows 目标）。
