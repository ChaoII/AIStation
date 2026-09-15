# SP6-c 模型热更新设计（Agent 无中断热交换 + 云端下发/回滚）

- 日期：2026-09-15
- 上游：`2026-09-14-visual-deployment-program-design.md` §8（SP6 进阶）、`2026-09-15-sp6b-rule-rollout-design.md`
- 范围：ModelDeploy（Agent 热交换）+ AIStation（云端下发与回滚）

## 1. 背景与现状

| 现状 | 证据 |
|------|------|
| Agent 已有模型增删改原语 | `PipelineManager::{add,remove,update}_model`、`Pipeline::{add,remove,update}_model`；另有模型库 `*_model_to/in_library` |
| **但"更新"是数据竞争** | `pipeline.cpp::update_model` = `infer_group_.remove_model(name)` + `add_model(...)`（"因 InferGroup 无原语 update"）；`InferGroup` **无任何锁**（`infer_group.cpp` 无 mutex/lock），而 `detect_loop` 正在遍历 `entries_` → **vector 迭代器失效 / UB / 崩溃风险** |
| 任务更新必中断 | `AgentRuntime::on_updated` = `on_removed` + `on_created`（停任务再起） |
| 云端有版本字段但无"热更新"动作 | `AlgorithmModel.version`（semver 字符串）、`model_path`、`model_file_config`、`runtime_config`；有模型上传接口；**无** hot-update/rollback |
| 控制面通道已具备 | `edge/orchestrator.py::EdgeAgentClient(control_url, secret)` + `EDGE_CONTROL_TOKEN`；`ModelFetcher` 支持 local/http/s3 + 解密 |

因此"换模型不中断任务"当前**既不可用也不安全**。

## 2. 目标 / 非目标

**目标**

1. **修掉数据竞争**：Agent 侧模型替换改为线程安全热交换，任务不中断。
2. **云端下发**：更新 `AlgorithmModel` → 自动下发到**所有引用它的 `AlgorithmTask`** 对应 Agent。
3. **回滚**：保留上一版本并支持一键回滚。

**非目标**

- 完整模型版本表 / 发布历史 UI / 按比例灰度发布（SP6-b 的 `rollout` 是规则级，不覆盖模型）。
- 多模型更新的整体原子性（逐模型独立）。
- 引入 CGraph（热路径不上图，见 `2026-09-15-cgraph-pipeline-evaluation.md`）。

## 3. 设计

### 3.1 Agent：COW 热交换（核心）

**问题**：`InferGroup::entries_` 为 `std::vector<Entry>`，`run_models` 在其上遍历；`remove/add` 并发修改 → UB。

**方案（写时复制 + 原子指针交换）**：

```cpp
class InferGroup {
    // 不可变快照：run_models 只读；增删改在副本上完成后再原子替换
    std::shared_ptr<const std::vector<Entry>> entries_ =
        std::make_shared<const std::vector<Entry>>();
    mutable std::mutex entries_mtx_;          // 仅保护指针交换与副本构造
};
```

- `run_models` 首行取快照：`auto snap = entries_;`（`shared_ptr` 拷贝保证整段只读期间引擎存活），后续全程只读 `*snap`。
- `add/remove/update_model`：加锁 → 复制当前 vector → 在副本上增/删/改 → `entries_ = std::move(new_vec)`（原子替换）→ 解锁。
- **`Entry` 改造**：
  - `unique_ptr<InferenceEngine>` → `shared_ptr<InferenceEngine>`（可在副本间共享，未变更的模型不重建）；
  - per-entry 可变状态（`frame_idx`/`has_last`/`last_dets`/`last_non_det`）抽为 `std::shared_ptr<EntryState>`，**副本复用同一 `EntryState`**（避免每次替换重置跳帧计数），`EntryState` 内可变字段由 detect 线程独占访问（仅该线程读写）。
- **生命周期**：被替换掉的旧引擎由 `shared_ptr` 引用计数管理；等当前在飞帧的 `run_models` 返回（快照释放）后自动析构 → **无需停任务、无需 join**。
- **fail-safe**：新模型下载/加载失败 → **不改快照**，旧模型继续服务，接口返回错误。

**新增控制面接口**（`agent_server.cpp`）：`POST /api/v1/tasks/{task_id}/models/{name}/update`，body 为 `ModelConfig`(JSON)：
1. 经 `ModelFetcher` 解析/下载（local/http/s3 + 解密）；
2. 构造新引擎并做一次自检（如空跑/尺寸校验）；
3. 成功 → 热交换并返回 `{ok: true, generation: <递增序号>}`；失败 → `{ok: false, error}` 且**旧模型保持不变**。

### 3.2 云端：下发与回滚

`algorithm/controller.py` 新增：

| 接口 | 行为 |
|------|------|
| `POST /video/algorithm/{id}/hot-update` | ① 记录 `previous_model_path/previous_version`（当前值）；② 查出所有引用该算法的 `AlgorithmTask`；③ 逐任务经 `EdgeAgentClient` 下发模型热更新；④ 返回 `{succeeded:[task_id], failed:[{task_id, error}]}`；⑤ 写操作日志 |
| `POST /video/algorithm/{id}/rollback` | 用 `previous_*` 重跑同一流程（并交换 `previous_*` 与当前值），返回同上 |

- **引用任务枚举**：`AlgorithmTask` 通过 `algorithm_id`（或 `scene_type`/`model_path` 归属）关联；实现者先核实既有外键与查询路径（`algorithm/model.py::AlgorithmTaskModel`）。
- **权限**：沿用算法模块既有权限串；hot-update/rollback 为写操作。
- **部分失败语义**：不整体回滚；返回逐任务结果，失败任务可由调用方重试；操作日志留痕。

### 3.3 数据模型

`AlgorithmModel` 新增：

```python
previous_model_path: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="上一版本模型路径（回滚用）")
previous_version: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="上一版本号（回滚用）")
```

新增 Alembic 迁移（仅两列）。

### 3.4 前端（最小）

算法管理页新增「热更新」「回滚」按钮（`v-hasPerm` 保护）+ 结果反馈（成功/失败任务数、失败原因列表）。不做发布历史页。

## 4. 测试与验收

**ModelDeploy**
- Catch2：
  - COW 语义：并发 `run_models` 与 `update_model` 反复交错不崩溃、结果自洽（无迭代器失效）；
  - 未变更模型不被重建（引擎实例地址保持）；
  - 新模型加载失败 → 快照未变、旧模型继续可用；
  - 替换后旧引擎在快照释放时析构（用计数器/弱引用断言）。
- `[agent]` 全量 + `surveillance` 仅编译（不得改动 `application/surveillance`）。

**AIStation**
- 单测：引用任务枚举正确；下发成功/部分失败汇总；回滚走 `previous_*` 且交换正确；权限校验；控制面调用失败被捕获并计入 `failed`。
- 全量 `uv run pytest -q` + `uv run ruff check`。

**真机**
- 起 Agent 跑单相机任务 → 触发 `hot-update`（换另一个模型文件）→ 断言：任务**不中断**（帧率与事件流不断）、新模型生效（检测结果发生变化）、`generation` 递增；再 `rollback` → 恢复旧模型。环境随后还原。

**前端**
- `pnpm run type-check`/`lint` + e2e（按钮可见性 + 结果提示）+ 无头截图 + `vision-recognition` 核对。

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| COW 改造引入新竞态 | 快照只读 + 指针原子替换；`EntryState` 仅 detect 线程访问；并发交错单测 |
| 引擎重建开销 / 内存峰值（新旧并存） | 替换期间短暂双份内存（可接受）；未变更模型复用 `shared_ptr` 不重建 |
| 热更新导致首帧延迟抖动 | 新引擎自检在 swap 前完成；swap 后下一帧直接使用 |
| 部分任务下发失败 | 逐任务结果返回 + 可重试；不整体回滚；日志留痕 |
| 新旧模型输入尺寸/精度不兼容 | `update` 请求携带完整 `ModelConfig`；Agent 侧构造时校验（如 `input_size`），失败则 fail-safe 保留旧模型 |
| 回滚时 `previous_*` 为空 | 接口校验返回 400（无可回滚版本） |

## 6. 兼容性

- `AlgorithmModel` 仅新增两列（可空）→ 既有数据不受影响。
- Agent 控制面仅**新增**端点；既有 `POST /tasks` 等不变。
- `InferGroup` 对外行为不变（`run_models` 仍逐模型执行，`interval` 跳帧语义保持）；仅并发安全性提升。
- 未调用热更新时，行为与现状完全一致。
- 不新增第三方依赖。
