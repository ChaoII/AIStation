# 新能力跨仓收口报告（B1 场景能力诚实化 + B2a 分类事件契约）

> 日期：2026-09-17 ｜ 仓库：`D:\AIStation`（云）、`E:\CLionProjects\ModelDeploy`（边缘 Agent）
> 基线：云 `0b2d5bf`、Agent `ff0650c` ｜ 门禁：未改动 `application/surveillance`

## 0. 结论

B1（obb/iseg 接线 + 场景目录诚实化）与 B2a（分类结果进事件）在两侧已互通：
云侧 `scene/contract.py` 声明分类事件契约后，`SCENE_CLS`/`DEFECT_CLS`/`NO_MASK` 由「假可配置」
转为真可配置且默认规则可编译；`OBB_DET`/`I_SEG`/`SCENE_CLS` 的能力校验与下发模型 type 均与
Agent 侧规范名一致。跨仓模型族集合逐项对拍**零漂移**。

## 1. 提交与 tag

| 仓库 | 代码提交 | 报告提交（本文件） | 最终 HEAD | vdp-v1.0.0 目标 |
|---|---|---|---|---|
| D:\AIStation | `a521492` | `（见 git log，随本文件）` | `（本文件提交）` | 指向最终 HEAD（`git tag -f -a`） |
| E:\CLionProjects\ModelDeploy | `ff0650c`（无新改动） | — | `ff0650c` | `ff0650c` |

- 云侧提交：`feat(video): 落地分类事件契约并统一跨仓模型族/类型名（B2a 收口）`，
  6 文件（3 源码 + 3 测试）；**无 `git add -A`**，未触碰 `progress.md`/`docs/issues.md`。
- 两个 tag 均**未 push**。

## 2. 逐事项结果

### 事项 1：翻转三个分类场景（云侧契约落地）

- `scene/contract.py`：`AGENT_EVENT_FEATURES = frozenset({"classification"})`（原为空集），
  docstring 翻转条件改为「已落地（B2a）」并标注 Agent 提交 `ff0650c`。
- 测试锁定（`tests/test_scene_contract_consistency.py`）：
  - `test_classification_scenes_configurable_after_contract_lands`：断言契约位已声明，
    `SCENE_CLS`/`DEFECT_CLS`/`NO_MASK` **可配置**且 `compile_rule` 默认规则可编译；
  - `test_classification_scenes_re_gate_without_contract`：monkeypatch 撤下契约位后三者
    **重新按「分类」原因置灰**（机制未退化为硬编码）；
  - 可配置场景数 20 → **23**（`test_configurable_scenes_compile_default_rule` 断言）。
  - 目录接口测试改为断言这三者 `configurable=True` 且 `unsupported_reason==""`、`blockers==[]`。
- Agent 侧契约满足性（引用 Agent 测试 `application/aistation_agent/tests/test_classification_event.cpp`）：
  - `classification full-frame box reaches event objects with label`：整帧框归一化 `0,0,1,1` +
    `label` + `attributes` 进入事件 JSON；
  - `classification-only model produces cloud-matchable event`（`[agent][pipeline][integration]`）：
    纯分类模型经真实 Pipeline + EventBus，复刻云端 `_matches_label` 语义断言
    「无 label 命中 / label=模型类名命中 / 无关 label 不命中」。
  该测试包含于 `[agent]` 套件，本次连跑两次通过。

### 事项 2：族/类型名跨仓一致性

- `catalog.py:EDGE_ADVERTISED_MODEL_FAMILIES` 已等价于 `contract.AGENT_MODEL_FAMILIES`（B1 改造为别名）。
- **族集合逐项 diff（实测结果）**：

  | 侧 | 集合 | 结果 |
  |---|---|---|
  | Agent `capability.cpp::detect_capabilities` | det, cls, face, pedestrian_attribute, ocr, lpr, tracking, **obb**, **iseg** | AGENT_ONLY=∅ |
  | 云 `contract.AGENT_MODEL_FAMILIES` | 同上 9 个 | CLOUD_ONLY=∅ ❘ **EQUAL=True** |

  测试 `test_agent_capability_cpp_has_no_family_drift` 在 ModelDeploy 工作区可读时直接解析
  `capability.cpp` 对拍（不可读则 skip，CI 安全）；`test_agent_capability_reported_families_match_contract`
  校验枚举常量。
- `canonical_family` 归一（云侧 `edge/**`，已补 2 行）：`capability_satisfies` 对设备上报族与需求族
  **双侧** `contract.canonical_family` 归一，旧设备上报 `face_detection` 不再被 `face` 要求误拒；
  测试 `test_capability_satisfies_normalizes_legacy_family_names`。
- Agent `normalize_model_type` 实测**无需修改**，已接受 `seg`/`iseg`/`instance_seg`（→`iseg`）
  与 `obb`/`obb_det`/`rotated_detection`（→`obb`）；Agent 测试
  `test_inference_obb_iseg.cpp::normalize_model_type accepts obb and iseg aliases` 通过。
- 云侧 `orchestrator._MODEL_TYPE_KEYWORDS["SEG"]` 由 `"seg"` 统一为 `"iseg"`，与 Agent 上报族对齐。

### 事项 3：OBB_DET / I_SEG / SCENE_CLS 端到端能力校验

`tests/test_edge_capability_scene.py` 新增（设备能力 = Agent 上报 9 族）：

- `test_obb_iseg_scene_cls_gate_accepts_agent_reported_families`：三个场景
  `EdgeOrchestrator._check_capability` 均返回 `(True, "")` → **可通过能力门禁并下发**。
- `test_obb_iseg_scene_cls_dispatch_uses_canonical_model_type`：`build_agent_task_config`
  编译出的模型 type 分别为 `obb` / `iseg` / `classification`（Agent 可识别规范名）。

> 顺带修复（本次必要）：原 `build_agent_task_config` 非特化场景一律用算法类型关键词推断，
> `SCENE_CLS` 命中不到 `CLASS*` 会退化为 `det`。现改为「单模型场景以目录 pipeline 规范名为准」，
> `SCENE_CLS/DEFECT_CLS` 正确下发 `classification`；无场景算法（INTRUSION 等）保持 `det` 不变。

### 事项 4：全量回归

| 项 | 命令 | 结果 |
|---|---|---|
| 云后端 | `uv run pytest -q` | **877 passed**（基线 871，新增 6 用例），绿 |
| 云 lint | `uv run ruff check --no-fix <6 改动文件>` | All checks passed |
| 前端类型 | `pnpm run type-check` | 仅既有无关错误（module_generator/monitor/system/task），**0 新增** |
| 前端 e2e（全量，后端 8001） | `pnpm run e2e` | 第 2 次：**44 passed + 1 flaky**（clean-drawer 重试通过）；第 1 次 43 passed + 1 flaky + ai-tool 失败（单独跑通过，属顺序型 flake）。整体绿 |
| Agent 构建 | `cmake --build build --target aistation_agent aistation_agent_test` | exit=0（up to date） |
| Agent 测试 | `aistation_agent_test.exe "[agent]"` ×2 | **110 cases / 106 passed / 4 skipped**（两次一致；断言 2194/2196 全通过） |
| surveillance 构建 | `cmake --build build --target surveillance_test` | exit=0（up to date） |
| surveillance 无改动 | `git status --short application/surveillance` | 空 |

### 事项 5：真机冒烟

`scripts/e2e/edge_agent_e2e.ps1` 不支持 `-Scene SCENE_CLS`（ValidateSet 无该值），
故按预案跑 **DET_ZONE 回归**：`-Transport http -SkipBroker -Scene DET_ZONE`。

- 结果：**9 项断言 8 项通过**。通过的端到端主链路：Agent 任务 `running=true`、
  云端任务 `RUNNING`、`algorithm_type=DET_ZONE` 告警落库、`snapshot_url` 非空、
  重复 `event_id` 去重（新增=1）、时段外任务不告警、stop/delete 同步 Agent。
- 唯一失败：`断言1 设备 status=online`。根因是运行中的 dev 后端 `EDGE_CONTROL_TOKEN` 非空且
  与脚本 `-Secret` 不一致，`POST /video/edge/heartbeat` fail-closed 返回 **403**
  （Agent stderr：`[Heartbeat] post failed (status=403 ...)`）。此为本环境既有状态，
  与 B1/B2a 改动无关，且已在 `fix-concurrency-medium-report.md` 记录为同类已知现象。
  主链路（下发→执行→告警）不受影响。
- 收尾：脚本自动停 Agent、删除 Algorithm/Camera/EdgeDevice；无遗留
  `aistation_agent` 进程、19090 端口空闲、无 `aistation-mqtt-e2e` 容器；
  `.env.dev` SHA256 = `E9718192A48F0909DE1481ECD5B9ECB99CD7B703F38A`（前后一致，未改）。
  e2e 重生成的 6 张 runbook 截图已 `git checkout` 还原。

### 事项 6：重指 tag

- `D:\AIStation`：`git tag -f -a vdp-v1.0.0`（原 `962fc6b` → 最终 HEAD）。
- `E:\CLionProjects\ModelDeploy`：`git tag -f -a vdp-v1.0.0`（原 `a06fbcc` → `ff0650c`）。
- 均未 push。

## 3. 关注点 / 遗留

1. **NO_MASK 语义**：已随契约转为「可配置」，但其目录 pipeline 为 det+cls 双模型，
   `build_agent_task_config` 只下发单模型（det）——与 `SCENE_CLS` 的纯分类下发不同。
   端到端命中 `no_mask` 标签仍需任务侧模型/标签配置配合，本次未改该场景的下发模型构造。
2. **OBB 旋转角未进事件、ISeg 掩码未进事件**（B1 既定取舍），语义已在路线图与 B1 报告标注。
3. **live smoke 设备 online**：需给运行后端配置 `EDGE_CONTROL_TOKEN=<与 -Secret 一致>`
   方可 9/9；属环境配置，非代码问题。
4. **e2e flake**：`ai-tool` 与 `clean-drawer` 在全量顺序执行下偶发首跑失败、重试通过，与本次改动无关。
5. `.superpowers/sdd/progress.md`（既有改动）与 `docs/issues.md`（既有未跟踪）未纳入本批提交。
