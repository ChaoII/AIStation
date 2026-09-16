# SP6-c 模型热更新实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agent 侧把模型替换改为线程安全热交换（不中断任务、加载失败保留旧模型）；云端支持一键热更新（下发到所有引用该模型的任务）与回滚。

**Architecture:** `InferGroup` 内部改为 COW（`shared_ptr<const vector<Entry>>` + 原子换指针），`run_models` 全程只读快照；云端经既有 `EdgeAgentClient` 调 Agent 新增控制面接口，逐任务下发并汇总结果。

**Tech Stack:** C++17 + CMake/Ninja + Catch2；FastAPI + SQLAlchemy 2.0 + Alembic；Vue 3 + Element Plus + Playwright。

**Spec:** `docs/superpowers/specs/2026-09-15-sp6c-model-hot-update-design.md`

## Global Constraints

- 代码注释与提交信息一律**中文**；格式 `feat(agent): …` / `feat(video): …` / `feat(ui): …`。
- 只 `git add` 本任务列出文件；**禁止 `git add -A`**。
- ModelDeploy：**不得改动 `application/surveillance`**；构建 `cmake --build build --target aistation_agent aistation_agent_test --parallel`（需先 `vcvars64.bat`）；测试 `& build\bin\aistation_agent_test.exe "[agent]"` 从仓库根运行。
- AIStation：`cd backend && uv run pytest -q` + `uv run ruff check` 全绿；**禁止新增依赖**。
- 前端：`pnpm run type-check` 0 新增。
- 热交换必须 **fail-safe**：新模型加载失败时旧模型继续服务。
- 新形态字段一律带默认值/可空，既有行为不变。

---

### Task 1: ModelDeploy — `InferGroup` COW 热交换

**Files:**
- Modify: `application/infer_group.hpp`
- Modify: `application/infer_group.cpp`
- Modify: `application/pipeline.cpp`（`update_model` 改为走 InferGroup 的新原语）
- Test: `application/aistation_agent/tests/test_infer_group_hotswap.cpp`（新建，并在 `CMakeLists.txt` 测试目标中注册——如项目用 glob 则无需改动，**报告实际情况**）

**Interfaces:**
- Produces（对外签名保持不变，新增 `update_model`）：
  - `bool InferGroup::load_models(const std::vector<ModelConfig>&, ModelFactory)`
  - `bool add_model(const ModelConfig&, ModelFactory)`
  - `bool remove_model(const std::string& name)`
  - **新增** `bool update_model(const ModelConfig& mcfg, ModelFactory factory)`（按 `mcfg.name` 替换；不存在则等价 `add_model`）
  - `bool empty() const` / `void clear()` / `det_model(name)` / `config_of(name)` / `run_models(frame, sdk_dets, non_det)` —— **签名与语义不变**

- [ ] **Step 1: 先读现有实现**

读 `application/infer_group.hpp`（41 行）与 `application/infer_group.cpp`（158 行），确认：
- `Entry` 的字段与 `run_models` 中逐模型分支（detection 走 ROI crop + `sdk_dets`，非 detection 走 `non_det`）、`interval` 跳帧复用 `last_dets`/`last_non_det`；
- `Pipeline::detect_loop` 对 `infer_group_` 的调用点（`run_models` / `config_of` / `det_model`）；
- `Pipeline::update_model(name, mcfg)` 现为 `remove_model + add_model`（`pipeline.cpp:516`）。

- [ ] **Step 2: 写失败测试（并发不崩溃 + 语义）**

`application/aistation_agent/tests/test_infer_group_hotswap.cpp`：

```cpp
#include <catch2/catch_test_macros.hpp>
#include <atomic>
#include <thread>
#include "infer_group.hpp"

// 说明：用最简 ModelConfig + 自定义 ModelFactory 注入"假引擎"，避免依赖真实模型文件。
// 若项目已有 test_pipeline_sink.cpp 之类的假引擎/Mock 手法，优先复用其写法。

TEST_CASE("InferGroup 热替换与并发读取不崩溃", "[agent][hotswap]") {
    InferGroup g;
    // 载入 2 个假模型（name=m1/m2）
    // 起一个线程反复 run_models(假帧)，另一个线程反复 update_model(m2 的新配置)
    // 断言：全程无崩溃；替换后 config_of("m2") 反映新配置
}

TEST_CASE("InferGroup 未变更模型不被重建", "[agent][hotswap]") {
    // update_model("m1") 后，m2 的引擎实例地址（或等价标识）保持不变
}

TEST_CASE("InferGroup 更新失败保持旧模型（fail-safe）", "[agent][hotswap]") {
    // factory 对某配置返回 nullptr → update_model 返回 false，且 config_of/行为仍为旧模型
}
```

- [ ] **Step 3: 运行确认失败**（编译失败/行为不符）

Run: `cmake --build build --target aistation_agent_test --parallel` → 预期编译失败（`update_model` 不存在）

- [ ] **Step 4: 实现 COW**

`infer_group.hpp`：

```cpp
    struct EntryState {                     // per-entry 可变状态：仅 detect 线程访问
        int64_t frame_idx = 0;
        bool has_last = false;
        std::vector<modeldeploy::vision::DetectionResult> last_dets;
        InferResult last_non_det;
    };
    struct Entry {
        std::shared_ptr<InferenceEngine> engine;
        std::shared_ptr<EntryState> state;  // 副本间复用（替换模型不重置跳帧计数）
    };

    // 不可变快照：run_models 只读；增删改在副本上完成后原子替换指针
    std::shared_ptr<const std::vector<Entry>> entries_ =
        std::make_shared<const std::vector<Entry>>();
    mutable std::mutex entries_mtx_;         // 仅保护"读指针/复制/换指针"
```

`infer_group.cpp`：
- `run_models` 首行：`const auto snap = entries_;`（`shared_ptr` 拷贝 → 整段只读期间引擎存活），后续只读 `*snap`；`state` 为 `shared_ptr<EntryState>`，其字段可写（仅 detect 线程）。
- `add_model` / `remove_model` / `update_model`：

```cpp
bool InferGroup::update_model(const ModelConfig& mcfg, ModelFactory factory) {
    auto engine = factory ? factory(mcfg) : nullptr;      // 先构造（锁外，可能耗时/下载）
    if (!engine) return false;                            // fail-safe：不改快照
    std::lock_guard<std::mutex> lk(entries_mtx_);
    auto next = std::make_shared<std::vector<Entry>>(*entries_);   // 复制快照
    bool found = false;
    for (auto& e : *next) {
        if (e.engine && e.engine->config().name == mcfg.name) {
            e.engine = std::move(engine);                 // 仅替换目标引擎，state 复用
            found = true;
            break;
        }
    }
    if (!found) next->push_back(Entry{std::move(engine), std::make_shared<EntryState>()});
    entries_ = std::move(next);                           // 原子换指针（写时复制）
    return true;
}
```

- `add_model` / `remove_model` 同法（复制 → 改副本 → 换指针）；`remove_model` 需按 `engine->config().name` 匹配。
- `clear()`：换空快照。
- `det_model` / `config_of`：取本地快照后查（返回指针需注意生命周期——**保持既有返回语义**；若既有返回裸指针指向 `entries_` 内部，则改为返回快照内的指针并说明其生命周期限制，若无调用方长期持有则安全）。
- **注意**：`load_models` 一次性构造后整体换指针（避免逐个替换）。
- `Pipeline::update_model` 改为 `return infer_group_.update_model(mcfg, model_factory_);`。

- [ ] **Step 5: 构建 + 测试**

Run: `cmake --build build --target aistation_agent aistation_agent_test --parallel`
Run: `& build\bin\aistation_agent_test.exe "[agent][hotswap]"` → 全绿
Run: `& build\bin\aistation_agent_test.exe "[agent]"` → 全绿（**既有行为不变**）

- [ ] **Step 6: 提交**

```bash
git add application/infer_group.hpp application/infer_group.cpp application/pipeline.cpp application/aistation_agent/tests/test_infer_group_hotswap.cpp
git commit -m "feat(agent): InferGroup 模型热交换改为写时复制（修线程安全）"
```

---

### Task 2: ModelDeploy — Agent 控制面热更新接口

**Files:**
- Modify: `application/aistation_agent/agent_server.hpp/.cpp`
- Modify: `application/aistation_agent/agent_runtime.hpp/.cpp`（如需暴露 mgr_ 的 update）
- Test: `application/aistation_agent/tests/test_agent_server.cpp`（扩展）

**Interfaces:**
- Produces: `POST /api/v1/tasks/{task_id}/models/{name}/update`，body = `ModelConfig` JSON；返回 `{"ok": bool, "error"?: str, "generation": int}`。

- [ ] **Step 1: 写失败测试**：控制面调用 API（沿用 `test_agent_server.cpp` 既有 HTTP 测试手法）覆盖：任务不存在 → 404；模型名不存在 → 404（或按既有约定）；成功 → `ok=true` 且 `generation` 递增；`ModelConfig` 非法 → 400 且**旧模型不变**。
- [ ] **Step 2-4: 实现**
  - `AgentServer` 新增路由，解析路径参数 → 走 `ConfigAdapter` 把 `ModelConfig` JSON 映射为 SDK `ModelConfig`（复用既有 from_json 逻辑；如无单模型解析入口，新增 `ConfigAdapter::parse_model(json, ModelConfig*)`）；
  - 经 `PipelineManager::update_model(task_id, name, mcfg)` → `Pipeline::update_model` → `InferGroup::update_model`；
  - 维护 per-runtime `generation` 计数（`std::atomic<uint64_t>`），成功替换后递增；
  - 鉴权沿用既有 `set_api_key`/secret 校验。
- [ ] **Step 5: 构建 + 测试**：`[agent]` 全绿。
- [ ] **Step 6: 提交** `feat(agent): 新增模型热更新控制面接口`

---

### Task 3: ModelDeploy — 回归

- [ ] `cmake --build build --target aistation_agent aistation_agent_test --parallel`
- [ ] `& build\bin\aistation_agent_test.exe "[agent]"` → 全绿；记录断言/用例数
- [ ] `cmake --build build --target surveillance_test --parallel` 成功；`git status --short application/surveillance` 为空
- [ ] 报告写入 `E:\CLionProjects\ModelDeploy\.superpowers\sdd\sp6c-task-3-report.md`

---

### Task 4: AIStation — 云端热更新/回滚接口 + 迁移

**Files:**
- Modify: `backend/app/api/v1/module_video/algorithm/model.py`、`schema.py`、`controller.py`、`service.py`
- Create: Alembic 迁移
- Test: `backend/tests/test_model_hot_update.py`

**Interfaces:**
- Produces：
  - `AlgorithmModel.previous_model_path` / `previous_version`（可空）
  - `POST /video/algorithm/{id}/hot-update` → `{succeeded: [task_id], failed: [{task_id, error}]}`
  - `POST /video/algorithm/{id}/rollback` → 同上

- [ ] **Step 1: 写失败测试**（monkeypatch `EdgeAgentClient` 的调用，断言：枚举的引用任务集合正确；成功/失败汇总；回滚交换 `previous_*`；无可回滚版本 → 400；任务控制面调用异常被捕获计入 `failed`）。
- [ ] **Step 2-4: 实现**
  - 模型加两列 + schema；迁移最小化；
  - `service.py` 新增 `hot_update_service` / `rollback_service`：枚举 `AlgorithmTaskModel`（按既有 `algorithm_id` 关联；实现前核实外键与查询路径并写进报告）→ 逐任务解析 `EdgeDevice.control_url` + secret → 调 `EdgeAgentClient` 新接口 → 汇总；
  - 权限沿用算法模块既有写权限串。
- [ ] **Step 5: 全量回归** `uv run pytest -q` + `uv run ruff check`
- [ ] **Step 6: 提交** `feat(video): 模型热更新与回滚接口（下发所有引用任务）`

---

### Task 5: AIStation — 前端按钮与结果反馈

**Files:** `frontend/src/api/module_video/algorithm.ts`、`frontend/src/views/module_video/algorithm/index.vue`

- [ ] 新增「热更新」「回滚」按钮（`v-hasPerm` 保护）+ 结果提示（成功/失败任务数、失败原因列表）；无 `previous_*` 时回滚按钮禁用。
- [ ] `pnpm run type-check`（0 新增）+ 本任务文件 lint 干净。
- [ ] 提交 `feat(ui): 算法管理支持模型热更新与回滚`

---

### Task 6: 真机联调

- [ ] 起 Agent + 后端（默认模式即可，控制面走 HTTP）跑单相机 `DET_ZONE` 任务；
- [ ] 触发 `hot-update`（换另一个 det 模型或同模型不同阈值文件）→ 断言：任务**不中断**（帧率与事件流不断）、`generation` 递增、检测结果变化；
- [ ] `rollback` → 恢复旧模型；
- [ ] 还原环境；结论写入 `.superpowers/sdd/sp6c-task-6-report.md`。

---

### Task 7: 总回归

- [ ] ModelDeploy：`[agent]` 全量 + surveillance 仅编译。
- [ ] AIStation：`uv run pytest -q` + `ruff check`；`pnpm run type-check && pnpm run lint && pnpm run e2e`（环境性 429 抖动需隔离复跑确认）。
- [ ] 报告写入 `.superpowers/sdd/sp6c-task-7-report.md`。

---

## Self-Review

**Spec 覆盖：**

| Spec 条目 | 落点 |
|-----------|------|
| §3.1 COW 热交换（快照只读/原子换指针/Entry 改 shared_ptr/EntryState 复用/旧引擎引用计数析构/fail-safe） | Task 1 |
| §3.1 控制面 `POST /tasks/{id}/models/{name}/update` + `generation` | Task 2 |
| §3.2 云端 `hot-update`（枚举引用任务 + 逐任务下发 + 部分失败汇总） | Task 4 |
| §3.2 `rollback`（`previous_*`） | Task 4 |
| §3.3 `previous_model_path`/`previous_version` + 迁移 | Task 4 |
| §3.4 前端按钮与结果反馈 | Task 5 |
| §4 验收（Catch2 并发/fail-safe/析构；真机不中断+generation+rollback；两仓回归） | Task 1/2/3、Task 6、Task 7 |
| §5 风险（竞态/内存峰值/首帧抖动/部分失败/兼容性校验/回滚空值） | Task 1（快照+交错测试）、Task 4（部分失败汇总、空值 400）、Task 2（构造期校验 fail-safe） |
| §6 兼容性（仅新增列/端点；未调用时行为不变） | Task 1（签名不变 + 全量回归）、Task 4（可空列） |

**类型一致性：** `InferGroup::update_model(mcfg, factory)`（Task 1 定义）与 `Pipeline::update_model`（Task 1 改调用）、`PipelineManager::update_model`、`AgentServer` 路由（Task 2）逐层签名一致；`generation` 语义（Task 2 返回）与 Task 6 断言一致；`previous_model_path/previous_version`（Task 4 定义）与 rollback 使用一致。

**占位符扫描：** Task 1 含完整关键代码（COW 结构与 `update_model` 实现）并要求先读既有实现再改；Task 2/4 给出接口契约、失败语义与前置调研要求（外键路径、ModelConfig 解析入口）；Task 3/6/7 为验证任务，含明确命令与验收标准。
