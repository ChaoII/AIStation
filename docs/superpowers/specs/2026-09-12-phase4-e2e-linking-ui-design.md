# Phase 4：端到端串联 + UI/UX 统一 设计

> 创建日期：2026-09-12
> 状态：设计已确认（用户批准）
> 关联：
> - `2026-09-11-pipeline-optimization-program-design.md`（Phase 4：端到端串联 + UI/UX 统一）
> - Phase 0-3 已完成的 spec/plan（本设计只覆盖当前仍存在的缺口）

## 1. 背景与目标

Phase 0-3 已打通标注→训练→评估→预测→部署的后端能力与大部分页面，但**跨页串联**与**UI 一致性**仍有缺口（经只读审计确认）：

- **训练详情→评估是死链**：`task/detail.vue` 的 `handleEvaluate()` 仅弹「评估功能需要后端支持」，训练完成后的核心下一步不可用；评估页也不会因带参而自动开窗预填。
- **模型仓库→预测无入口**；`评估→预测` 无跳转；`predict/index.vue` 创建时把**版本 id 当作仓库 id**（`model_repo_id` 语义错误）。
- **数据集→训练无入口**；`数据集→标注任务` 已带 `task_id` 但落地页不消费。
- **列表/详情显示 ID 而非名称**：训练任务列 `dataset_id`、评估列 `eval_dataset_id`、详情页均为裸数字。
- **表单补全缺失**：`base_model_id` 无 UI、编辑不回填；PaddleX 默认超参缺 `trainRatio`。
- **重复 toast**：部分页面在拦截器之外又弹一次成功/失败提示。
- **UI 不一致/残留**：train 的 eval/predict/deploy 仍用原生 `el-dialog`；module_video 残留自定义 CSS Grid 与非标准 `@media (width <= Xpx)`；存在死代码与占位文案。
- **搜索失效**：预测列表 `name` 搜索前端有、后端 controller 未声明该参数。

**目标**：把上述缺口补齐，使「数据集→训练→评估→预测→部署」任一环节都能带上下文跳到下一步，列表显示人类可读名称，界面提示与弹窗统一，无重复提示与明显死代码。

**范围（P0+P1+P2）**：
1. 后端名称 enrich。
2. 训练→评估闭环。
3. 仓库/评估→预测 + `model_repo_id` 修复 + 预测搜索接线。
4. 数据集→训练 + 标注任务上下文消费。
5. 表单补全（base_model_id / 编辑回填 / 默认超参）。
6. 清理与统一（toast 去重、死代码、CSS 语法、train 三弹窗→EnhancedDialog）。
7. 测试与验收。

**非目标**：
- 新的业务功能（只做串联、补全与统一）。
- module_video 原生 el-dialog 的大规模迁移（仅限 train 的 eval/predict/deploy 三个 CRUD 弹窗）。
- 真机全链路训练（Phase 6 范畴）。
- 全项目 pre-existing 的 vue-tsc / ruff FAST002 清理。

## 2. 关键决策（已与用户确认）

| 决策点 | 结论 |
|---|---|
| 范围 | P0+P1+P2 全做；el-dialog 迁移仅限 train 的 eval/predict/deploy |
| 名称展示 | **后端补名称字段**（`dataset_name` / `eval_dataset_name`），前端直接展示 |
| 数据集→训练入口 | **数据集管理页操作列**加「去训练」，带 `dataset_id` 预填 |
| 实施结构 | **按用户链路纵向切片**（每任务一条可独立验收的链路 + 对应 E2E） |
| 测试 | 后端 pytest + 前端 Playwright E2E + type-check/lint |

## 3. 架构总览

```
                     ┌──────────── 跨页 query 契约（前端） ────────────┐
  /annotation/dataset ─ dataset_id ─▶ /train/task?dataset_id&autoCreate=1
  model repo 卡片     ─ model_id/model_repo_id ─▶ /train/task|eval|predict?...
  /train/task/:id 详情 ─ 评估按钮 ─▶ /train/eval?model_id&model_repo_id&autoCreate=1
  /train/eval/:id 详情 ─ 去预测 ─▶ /train/predict?model_id&model_repo_id&autoCreate=1
                     └──────────────────────────────────────────────┘
                                     │
                                     ▼
                    落地页 onMounted 读 query → 预填表单 → 自动开窗 → 清 query

  后端 module_train/service：_enrich_task / eval enricher 批量注入 dataset 名称
```

**统一 query 约定**：`model_id`（版本 id）、`model_repo_id`（仓库 id）、`dataset_id`、`framework`、`autoCreate=1`。落地页消费后使用 `router.replace` 清除相关 query，避免刷新/回退时重复弹窗。

## 4. 后端设计

### 4.1 训练任务名称 enrich
- `TrainTaskOutSchema` 新增 `dataset_name: str | None = None`。
- `TrainService.get_task_list`：取当前页 `dataset_id` 去重集合，一次性查询 `annotation_dataset`（`DatasetModel`）得到 `{id: name}`，注入每行 `dataset_name`。
- `TrainService.get_task`（详情）：单条查询注入。
- `TrainService._enrich_task(row, name_map=None)`：在保留现有 running 进度逻辑的基础上，支持传入名称映射。

### 4.2 评估名称 enrich
- `TrainEvalOutSchema` 新增 `eval_dataset_name: str | None = None`。
- 评估列表按页收集 `eval_dataset_id` 批量查询；详情单条查询。
- `annotation_dataset` 的 `is_deleted` 过滤沿用项目软删除约定（查询时加 `is_deleted.is_(False)`）。

### 4.3 预测搜索接线
- `module_train` predict 列表 controller 增加 `name: str | None = Query(None)`，透传给 service 的 name 过滤（service 已实现）。

## 5. 前端设计

### 5.1 训练→评估闭环
- `views/module_train/task/detail.vue`：
  - `handleEvaluate()` 改为：若任务已有产物模型（存在 `model_repo_id`/`model_id`）→ `router.push({ path: "/train/eval", query: { model_id, model_repo_id, autoCreate: "1" } })`；否则 `ElMessage.warning("请先完成训练并生成模型")`。
- `views/module_train/eval/index.vue`：
  - `onMounted` 读 `route.query`；当 `autoCreate === "1"` 且解析到模型（`model_id` 或 `model_repo_id`）→ 预填并 `handleOpenCreateDialog()`；
  - 消费后用 `router.replace({ query: {} })` 清除 `autoCreate`/`model_id`。

### 5.2 仓库/评估→预测 + 修复
- `views/module_train/repo/index.vue`：操作列新增「预测」→ `/train/predict?model_id=<版本id>&model_repo_id=<仓库id>&autoCreate=1`。
- `views/module_train/eval/detail.vue`：成功态操作区新增「去预测」，query 同上（取评估记录的 model_id/model_repo_id）。
- `views/module_train/predict/index.vue`：
  - `onMounted` 读 query，`autoCreate` 时预填并开窗；
  - 修正创建 payload：`model_repo_id` 取所选模型的 `repo_id`（而非 `id`）；
  - 搜索 `name` 参数保持前端已有，后端接线后即可生效。

### 5.3 数据集→训练 + 标注上下文
- `views/module_annotation/dataset/index.vue`：操作列新增「去训练」→ `/train/task?dataset_id=<id>&autoCreate=1`。
- `views/module_train/task/index.vue`：`onMounted` 读 `dataset_id` 预填并（当 `autoCreate=1`）自动开窗；与既有 `edit_id/framework/model_id` 处理共存、互不覆盖。
- `views/module_annotation/task/index.vue`：读 `route.query.task_id`，落地时按该任务过滤/定位（至少作为搜索条件预填）。

### 5.4 表单补全
- `views/module_train/task/index.vue`：
  - 新增 `base_model_id` 展示/选择控件（来源：模型仓库/版本列表；可为空表示从零训练）；
  - 编辑回填 `annotation_task_id`、`base_model_id`；
  - `defaultHpPaddle()` 补 `trainRatio`，避免切到 PaddleX 时滑杆初始 undefined。
- 列表/详情：训练任务列与详情、评估列与详情改用 `dataset_name` / `eval_dataset_name`（回退 `#id`）。

### 5.5 清理与统一
- **toast 去重**：移除与拦截器重复的页面级 `ElMessage.success/error`（`module_video/camera`、`record`、`alarm`、`algorithm`、`module_annotation/annotation`），仅保留拦截器覆盖不到的自定义提示（配 `_silent`）。
- **死代码**：`repo/index.vue` 冗余条件、`task/index.vue` 未引用的 `groupLabel()`；占位文案仅清理确实无实现的（保留真实能力判断，如云台不支持）。
- **CSS 语法**：仅将非标准 `@media (width <= Xpx)` 改为标准 `@media (max-width: Xpx)`（行为等价）；**不改动任何 `display: grid` 规则与布局**（module_video 的 grid 属既有实现，避免回归）。
- **UI 统一**：`train/eval`、`train/predict`、`train/deploy` 的原生 `el-dialog` 迁移为 `EnhancedDialog`，保持 `v-model`、宽度、footer 与提交行为不变。

## 6. 错误处理

| 场景 | 行为 |
|---|---|
| 跳转时上下文缺失（无 model/model_repo） | 落地页不自动开窗，仅进入列表；不报错 |
| query 参数非法（非数字） | 忽略该参数 |
| 名称 enrich 查不到数据集 | `dataset_name=null`，前端回退 `#id` |
| 自动开窗后用户取消 | query 已清除，刷新不再弹 |
| 删除/失败提示 | 统一由拦截器负责一次提示 |

## 7. 测试与验收

**后端 pytest**
- `get_task_list`/`get_task` 返回 `dataset_name`（有值/缺失回退）。
- 评估列表/详情返回 `eval_dataset_name`。
- predict 列表 `name` 过滤生效。

**前端 E2E（Playwright）**
- 训练详情点「评估」→ URL 含 `/train/eval` 且 query 带 `model_id`/`autoCreate`，评估创建弹窗自动打开并预填模型。
- 模型仓库点「预测」→ `/train/predict` 自动开窗且预填模型；创建 payload（路由拦截断言）`model_repo_id` 为仓库 id。
- 数据集页点「去训练」→ `/train/task` 自动开窗且预填 `dataset_id`。
- 某写操作的 toast 数量为 1（沿用现有 toast 断言范式）。

**静态检查**
- 新增/改动前端文件 `eslint` + `prettier` clean；`vue-tsc` 新增文件 0 错误（项目级 pre-existing 不追平）。

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| 自动开窗与既有 query 处理（edit_id/framework/model_id）冲突 | 统一在 `onMounted` 一处解析优先级，消费后 `router.replace` 清 query |
| EnhancedDialog 迁移改变提交流程 | 逐页对照原 `el-dialog` 的 v-model/footer/width，迁移后 E2E 点验 |
| 名称 enrich 引入 N+1 | 列表按页批量一次查询，详情单查 |
| toast 去重误删必要提示 | 区分「拦截器已覆盖」与「自定义/silent 分支」，仅删重复项 |
| CSS 语法替换影响布局 | 仅改媒体查询语法，不改规则内容；视觉回归靠人工/现有 E2E 冒烟 |

## 9. 交付拆分（供 writing-plans 参考）

1. 后端名称 enrich + predict name 搜索接线 + pytest。
2. 训练详情→评估闭环 + 评估自动开窗预填。
3. 仓库/评估→预测 + `model_repo_id` 修复 + 预测自动开窗。
4. 数据集→训练 + 标注任务 `task_id` 上下文。
5. 表单补全（base_model_id/编辑回填/默认超参）+ 列表详情名称展示。
6. toast 去重 + 死代码 + CSS 语法清理。
7. train eval/predict/deploy 三个弹窗 → EnhancedDialog。
8. 回归：pytest + E2E + type-check/lint。
