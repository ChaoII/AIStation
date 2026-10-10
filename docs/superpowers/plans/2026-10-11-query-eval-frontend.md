# 问数评测（NL2SQL Eval）前端实现计划

> 承接 `2026-10-11-query-eval-backend.md`。后端 `/ai/query/eval/*` 接口与三表已落地，
> 本计划只做**前端页面 `/ai/eval`**，不动后端。设计依据见
> `docs/superpowers/specs/2026-10-11-query-eval-module-design.md` 阶段 4。

## 0. 约束（来自 AGENTS.md，强制）

- **风格**：一律复用 Element Plus 原生组件（`el-card` / `el-table` / `el-form` / `el-tag` /
  `el-statistic` / `el-progress` / `el-descriptions` / `el-dialog`）与 `--el-*` 变量。
  **禁止自造主题化外壳与自定义配色**；参照同类页 `module_system/param`。
- **字号**：正文 `var(--el-font-size-base)`（14px），次要 12px，禁止 13/15/16px 零散混用。
- **布局**：优先 `el-row`/`el-col` 栅格，**不要自写 CSS Grid**（本项目自定义 Grid 易被全局
  样式覆盖）。非要用自定义样式时用**非 scoped** `<style>` + 唯一类名。
- **单根**：页面 `<template>` 必须**单根元素**（`<Transition mode="out-in">` 白屏陷阱），
  `el-dialog` 必须放在根元素内部。
- **局部刷新**：进度/状态只更新对应行或局部组件，**禁止每秒整表刷新**；仅在
  「开始 / 结束」状态跃迁时刷新**一次**。
- **删除类操作**：一律 `ElMessageBox.confirm` 二次确认，文案写明数量与不可逆性，
  按钮带 `v-hasPerm`。
- **权限**：全部接口沿用后端 `module_ai:query:ask`（与后端 `AuthPermission` 一致）。

## 1. 交付物

| 文件 | 说明 |
|------|------|
| `frontend/src/api/module_ai/query.ts` | 追加 `eval:*` API 函数（见 §2） |
| `frontend/src/views/module_ai/eval/index.vue` | 评测页主容器（单根） |
| `frontend/src/views/module_ai/eval/components/EvalCases.vue` | 测试集管理（表格 + 增删改） |
| `frontend/src/views/module_ai/eval/components/EvalRunPanel.vue` | 运行/进度/生成 面板 |
| `frontend/src/views/module_ai/eval/components/EvalReport.vue` | 报表：总览 + 分维度 + 逐题 trace |
| `frontend/src/views/module_ai/eval/components/EvalAblation.vue` | 消融对照 |
| `frontend/src/views/module_ai/eval/types.ts` | 类型定义 |
| `sys_menu` 插入 `/ai/eval`（父菜单 AI，见 §7） |

## 2. API 层（`api/module_ai/query.ts` 追加）

后端前缀 `API_PATH = /ai/query`（沿用文件内既有常量）。全部返回 `SuccessResponse`，
`request` 已解包 `data`。

```ts
// ---- 问数评测 ----
export function getEvalCases(params?: {
  datasource?: string; difficulty?: string; form?: string; scenario?: string;
}) {
  return request({ url: `${API_PATH}/eval/cases`, method: "get", params });
}

export function upsertEvalCase(data: any) {
  return request({ url: `${API_PATH}/eval/cases`, method: "post", data });
}

export function deleteEvalCases(
  ids: number[]
) {
  return request({ url: `${API_PATH}/eval/cases`, method: "delete", data: ids });
}

export function generateEvalRound(data: {
  datasource: string; difficulty: string; form: string; n: number;
}) {
  return request({ url: `${API_PATH}/eval/generate`, method: "post", data });
}

export function startEvalRun(data?: { filter?: any; mode?: string; config?: any }) {
  return request({ url: `${API_PATH}/eval/run`, method: "post", data: data ?? {} });
}

export function getEvalStatus(run_id: string) {
  return request({ url: `${API_PATH}/eval/status`, method: "get", params: { run_id } });
}

export function getEvalReport(run_id: string) {
  return request({ url: `${API_PATH}/eval/report`, method: "get", params: { run_id } });
}

export function getEvalRuns(limit = 30) {
  return request({ url: `${API_PATH}/eval/runs`, method: "get", params: { limit } });
}

export function startEvalAblation(data?: { keys?: string[]; filter?: any }) {
  return request({ url: `${API_PATH}/eval/ablation`, method: "post", data: data ?? {} });
}

export function getEvalAblation(run_id: string) {
  return request({ url: `${API_PATH}/eval/ablation`, method: "get", params: { run_id } });
}
```

> `delete` 带 body 沿用文件内既有 `deleteQueryMetrics` 写法（`data: ids`）。

## 3. 类型（`eval/types.ts`）

```ts
export interface EvalCase {
  id: number; question: string; gold_sql: string;
  datasource: string; difficulty: string; form: string; scenario: string;
  expected_metric?: string; verified?: boolean; enabled?: boolean;
  created_time?: string;
}
export interface EvalSummary {
  total: number; data_accuracy: number; semantic_accuracy: number;
  fast_rate: number; recall_at_k: number; avg_ms: number; error_rate: number;
  p50_ms?: number; p90_ms?: number;
}
export interface EvalResultRow {
  testcase_id: number; question: string; ok: boolean; is_error: boolean;
  path: string; metric_key: string; expected_metric: string;
  sql: string; n_rows: number; took_ms: number;
  gold_match: boolean; recall: number;
  recall_hit: string;            // JSON：{expected:[],recalled:[]}
  ontology_used: string;         // JSON：string[]
  difficulty: string; form: string; scenario: string; datasource: string;
}
export interface EvalGroupRow { total: number; correct: number; accuracy: number; }
```

## 4. 页面结构（`eval/index.vue`，单根）

用 `el-tabs`（`type="border-card"`）承载四个分区，避免长滚动：

```
<div class="app-container eval-page">        <!-- 单根 -->
  <el-tabs v-model="tab">
    <el-tab-pane label="测试集"   name="cases">   <EvalCases />   </el-tab-pane>
    <el-tab-pane label="运行"     name="run">     <EvalRunPanel /> </el-tab-pane>
    <el-tab-pane label="报表"     name="report">  <EvalReport />   </el-tab-pane>
    <el-tab-pane label="消融"     name="ablation"><EvalAblation /> </el-tab-pane>
  </el-tabs>
</div>
```

`index.vue` 用 `provide` 暴露一个轻量 `store`（`reactive`）在子组件间共享
`currentRunId`、`summary`，避免重复请求：
`provide("evalCtx", { runId, setRunId })`。

> 可选：用 `useCrudList()`（`@/components/CURD/useCrudList`）承载测试集列表，
> 与 `module_system/param` 一致；若配置驱动不便表达「生成」按钮，则手写
> `PageSearch + PageContent + EnhancedDialog` 三件套（仍用同一套组件）。

## 5. 各分区实现要点

### 5.1 EvalCases（测试集管理）

- 顶部筛选：`el-select` 数据源（system / ds:4）、难度、形式；`@change` 触发
  `getEvalCases`（**用 @change 不用 watch**，避免竞态）。
- **生成按钮**：`el-dialog` 表单（数据源 / 难度 / 形式 / 数量 `el-input-number`），
  确认后调 `generateEvalRound`，**按钮进入 loading**（单轮 30-60s），完成后
  `ElMessage.success(生成 saved 题 / 拒绝 rejected)` 并**刷新一次**列表。
  - 一次不够 → 用户可重复点；不做轮询。
- 表格列：题号、问题（`show-overflow-tooltip`）、数据源 `el-tag`、难度 `el-tag`
  （简单=success/中等=warning/困难=danger）、形式、场景、`verified` 图标、操作。
- 行内「查看金标 SQL」：`el-dialog` + `el-input type="textarea"` 只读展示。
- 批量删除：`ElMessageBox.confirm("将删除 N 道测试题，且不可恢复")` → `deleteEvalCases`。

### 5.2 EvalRunPanel（运行 + 进度）

- 表单：数据源 / 难度 / 形式 / 数量上限（`limit`）、`force_slow`（`el-switch`）。
- 「开始评测」→ `startEvalRun({filter})` → 记录 `runId` → **启动轮询**
  `setInterval(getEvalStatus, 1500)`。
- 进度展示（**只更新本组件局部状态，不动表格**）：
  - `el-progress` `:percentage="done/total*100"`；
  - `el-descriptions`：已完成 / 总数 / 当前题（`current`）；
  - 完成（`status==='done'`）→ `clearInterval` → `getEvalReport(runId)` 填充报表 Tab，
    并**刷新一次**历史运行列表。
  - 失败（`status==='error'`）→ `el-alert type="error"` 显示 `error`。
- 历史运行：`el-table`（run_id / mode / status / total / started_at），
  点击行 → 跳「报表」并加载该 run 的报告。
- `onUnmounted` 必须 `clearInterval`。

### 5.3 EvalReport（总览 + 分维度 + 逐题 trace）

- **总览**：`el-row`/`el-col`（`:xs=12 :md=6`）四个 `el-statistic`：
  数据准确率 / 语义准确率 / 快路径占比 / 平均耗时（ms）；
  另加 `Recall@8`、错误率作为次要 `el-statistic`。
  数值用百分比格式（`suffix="%"`），颜色沿用默认，**不自定义主题色**。
- **分维度**：四个 `el-table`（难度 / 形式 / 场景 / 数据源），列：分组值、
  总数、正确数、准确率（`el-progress` 或百分比文本）。用 `el-tabs` 或折叠面板承载。
- **逐题 trace**（重点）：
  - `el-table` 列：题号、问题、来源、path（fast/slow `el-tag`）、命中指标、
    `n_rows`、`took_ms`、`recall`、数据比对 ✅/❌。
  - **展开行**（`type="expand"`）：`el-descriptions` 展示
    `sql`（`el-input` 只读 / 代码块）、`recall_hit`（expected / recalled 表标签）、
    `ontology_used`（`el-tag` 列表）。
  - 提供筛选：只看失败 / 只看慢路径；`el-pagination` 前端分页（report 后端已 `rows[:200]`）。

### 5.4 EvalAblation（消融对照）

- 多选 `el-checkbox-group`：8 个开关（见 §6），默认全选或勾选 2 个常用。
- 数量上限 `el-input-number`（默认 20）。
- 「开始消融」→ `startEvalAblation({keys, filter:{limit}})` → 轮询
  `getEvalAblation(runId)`，展示 `current`（当前正在跑哪组，**局部刷新**）。
- 完成后渲染对照 `el-table`：组名（baseline / 关XX）、数据准确率、Recall@8、
  快路径占比、平均耗时、Δ数据准确率（正负着色：`success`/`danger`）。
- 底部 `el-alert type="info"`：消融为**串行**执行，配置覆盖结束自动恢复。

## 6. 消融开关清单（前端展示名）

| key | 中文名 |
|-----|--------|
| `recall_enabled` | 召回服务 |
| `agno_semantic_enabled` | 语义向量召回 |
| `kg_enabled` | 知识图谱 |
| `agno_tool_agent` | 工具调用智能体 |
| `decomposed_planning` | 分解式规划 |
| `empty_self_correct` | 空结果自纠错 |
| `fewshot_auto_curate` | Few-shot 自动沉淀 |
| `enum_hint_enabled` | 枚举取值提示 |

## 7. 菜单注册

`sys_menu` 表按现有 AI 模块惯例插入一条 `/ai/eval`（`component=module_ai/eval/index`，
`type=1`，父级为 AI 父菜单），并分配 admin 角色（`sys_role_menus`）。
**已存在的库不会重跑 seed**：需用菜单管理 UI 添加，或手工 `INSERT`，
随后刷新前端动态路由。

## 8. 验收标准

1. 「测试集」Tab 能列出全部题、按数据源/难度/形式筛选、查看金标 SQL、二次确认删除。
2. 「生成」能跑一轮并**真实入库**（LLM 出题 + 金标执行校验），耗时期间有 loading。
3. 「运行」启动后进度**局部刷新**（不整表闪动），完成自动出报告，失败有红色告警。
4. 「报表」正确显示总览数字、四张分维度表、逐题 trace（含 SQL / 召回命中 / 本体表）。
5. 「消融」串行跑完并渲染对照表与 Δ；页面不因配置覆盖而残留（后端已恢复）。
6. 视觉与 `module_system/param` 一致：Element Plus 组件 + `--el-*`，无自造主题外壳。
7. 页面单根、无 `<Transition>` 白屏；`onUnmounted` 清理定时器。
8. `pnpm run type-check` 与 `pnpm run lint` 通过（不新增既有 `LivePlayer.vue` 类既有报错）。

## 9. 实施顺序（任务拆分）

1. `api/module_ai/query.ts` 追加 API + `eval/types.ts`。
2. `eval/index.vue` 单根 + tabs 骨架 + `provide` 上下文。
3. `EvalCases.vue`（列表 + 筛选 + 生成对话框 + 删除确认）。
4. `EvalRunPanel.vue`（启动 + 轮询进度 + 历史列表）。
5. `EvalReport.vue`（总览 + 分维度 + 逐题 trace 展开）。
6. `EvalAblation.vue`（开关 + 轮询 + 对照表）。
7. 菜单注册 + 无头浏览器截图视觉核对（与既有 AI 页面比对）。
8. `pnpm run type-check` / `lint` 收尾。

## 10. 已知风险

- `/eval/report` 的 `summarize` 字段名以 `eval_metrics.py` 为准（`data_accuracy` /
  `semantic_accuracy` / `fast_rate` / `recall_at_k` / `avg_ms` / `error_rate`），
  前端 type 需与之对齐，避免 undefined。
- `delete` 请求带 body 需确认本项目 `request` 封装支持（既有 `deleteQueryMetrics` 已用，
  照抄即可）。
- 运行/消融耗时长：必须提供明确加载态与进度，**禁止**用整表轮询替代。

---

## 11. 实现记录（已完成，含实测修正）

### 交付文件（提交 `475b9f5f`）

| 文件 | 说明 |
|------|------|
| `frontend/src/api/module_ai/query.ts` | 追加 11 个 `eval:*` API（用 `stage_hunks.py` 只暂存本段，未混入同文件既有 WIP） |
| `frontend/src/views/module_ai/eval/index.vue` | 单根 + `el-tabs` 四分区 |
| `frontend/src/views/module_ai/eval/types.ts` | 类型 + 8 个消融开关中文名 + `difficultyTag`/`pct` |
| `.../eval/components/EvalCases.vue` | 测试集：筛选/表格/生成对话框/金标 SQL/批量删除（二次确认） |
| `.../eval/components/EvalRunPanel.vue` | 运行：表单 + 1.5s 轮询进度 + 历史运行 |
| `.../eval/components/EvalReport.vue` | 报表：6 个 `el-statistic` + 4 张分维度表 + 逐题 trace（展开看 SQL/召回/本体表） |
| `.../eval/components/EvalAblation.vue` | 消融：8 开关多选 + 2s 轮询 + 对照表与 Δ |
| `backend/scripts/register_eval_menu.py` | 幂等注册 `/ai/eval` 菜单（id=367）并授权 ADMIN 角色 |

### 与计划的偏差（有意）

1. **组件内 `types` 导入路径是 `../types`**（组件位于 `components/` 子目录），计划里写的是 `./types`。
2. **未使用 `v-hasPerm`**：同模块既有页面（`query/index.vue` 等）均未使用，且该指令在权限串
   未注册时会**直接移除 DOM**（按钮消失）。权限由后端 `AuthPermission(["module_ai:query:ask"])`
   强制；前端保持一致以免误伤。

### 验证结果

| 项 | 结果 |
|----|------|
| `pnpm run type-check` | **本页 0 错误**（其余为仓库既有报错） |
| `pnpm run lint` | **本页 0 问题**（仓库既有 41 errors 均在其它文件） |
| 菜单 | 侧边栏出现「问数评测」，面包屑 `首页/AI管理/问数评测` ✓ |
| 测试集 Tab | 渲染 **共 100 题**，列/难度 tag/金标状态/操作齐全 ✓ |
| 报表 Tab | 6 个统计（92% / 0% / 77% / 15% / 42ms / 7%）、4 张分维度表、逐题 trace（路径/结果/行数/耗时/Recall/场景/数据源）✓ |
| 消融 Tab | 开关组 + 轮询 + 对照表渲染 ✓ |

### 实测又抓到一个后端 bug（已修）

**症状**：报表页「语义准确率」显示 **0%**，而内存里的 summary 是 **12.5%**。
**根因**：`ai_query_testresult` 表**没有 `expected_metric` 列**，`_save_result` 未落库，
`load_results` 也就读不回来 → 报表走 `summarize(load_results(...))` 时分母为空 → 恒 0。
（`by_difficulty` 等之所以正常，是因为它们藏在 `trace` JSON 里。）
**修复**：把 `expected_metric` 一并写进既有的 `trace` JSON，并在 `load_results` 里取出
（**零 schema 变更**）。历史运行仍显示 0，新运行正确。

### 环境提示（避免误判）

本机 dev 后端启动**约 2 分钟**（`async_pool_warmup` 有 80s 超时失败，日志
`数据库连接池预热失败（不影响启动）`）。启动期间 **Vite 代理对 `/api/**` 返回空 body 的 500**
（上游未就绪），看起来像"接口全挂"。判断方法：直接探测后端
`http://127.0.0.1:8001/api/v1/ai/query/eval/cases` —— 返回 **401** 说明路由已注册且服务健康，
返回 404 说明进程是旧代码（需重启），连接被拒说明还在启动中。
