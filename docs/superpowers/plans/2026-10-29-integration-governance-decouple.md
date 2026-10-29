# 「数据与集成」治理 Tab 拆出为独立页面 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 把「数据与集成」页面顶层的「治理」tab 从嵌套中拆出，提升为「智能问数」目录下的独立子菜单页面（`/ai/governance`），并把治理内部子 tab 从 8 个精简为 5 个（驾驶舱/权限/数据质量/数据域/交付命题）。

**Architecture:** 前端新建 `module_ai/governance/index.vue` 复用 `GovernancePanel.vue` 作主体并套白面板外壳；`integration/index.vue` 删掉 `gov` tab 及 `GovernancePanel` 引用、简化布局三元；`GovernancePanel.vue` 删 3 个子 tab（ontgov/action/lifecycle）及其关联 script；后端 `init_app.py` 的 `QUERY_GROUP_MENUS` 加「治理」菜单（沿用 `module_ai:query:ask` 权限幂等注册）。

**Tech Stack:** Vue 3 + Element Plus + TS（前端）、FastAPI + SQLAlchemy（后端菜单注册）。

**Spec:** `docs/superpowers/specs/2026-10-29-integration-governance-decouple.md`

## Global Constraints

- 复用现有治理接口，**只删前端展示、不改后端接口**（`/ai/query/governance/*`、`/ai/abac/*`、`/ai/dq/*`、`/ai/domain/*`、`/ai/query/fde/*` 保持不变）。
- 治理菜单 `order=5`（现有 1-4 被 数据与集成/智能问数/问数评测/报表模板 占用），`permission="module_ai:query:ask"`（QUERY_GROUP 子菜单统一此码）。
- 新页面必须满足 AGENTS.md「页面外壳与框架同构」：`app-container` 满高 flex + `el-card shadow="never"` 铺满；覆盖样式用**非 scoped + 唯一类名**。
- 删除子 tab 时须同步删 `onTab` 对应分支 + 数据 ref + 加载函数 + 相关 dialog/函数，避免残留未使用引用触发 lint。
- 提交信息：`feat(ai): 中文描述`；代码注释中文。
- i18n key（`ig_govOnt`/`ig_govAction`/`ig_govLifecycle` 等）**保留在语言文件不删**（只改前端引用，避免动多语言文件造成大 diff；未引用的 key 不影响运行）。

## Review Focus

1. 「数据与集成」顶部 tab 应只剩 9 个，**不再有「治理」**；左数据源栏恒显示（不再因 `tab==='gov'` 隐藏）。
2. 治理独立页子 tab = 驾驶舱/权限/数据质量/数据域/交付命题 共 **5 个**，且各子 tab 数据能正常加载（复用现有接口）。
3. 删除 3 个子 tab 后，`GovernancePanel` 无残留引用（`ontGov`/`pendingActions`/`actionList`/`actionLogs`/`lifecycle` 及 `loadOntGov`/`loadAction`/`loadLifecycle`/`loadObjects`/`apAction` 等全部清干净）。
4. 治理独立页白面板铺满、四边留白一致、无贴边，视觉与框架同构。

---

### Task 1: `GovernancePanel.vue` 精简子 tab（删 ontgov/action/lifecycle）

**Files:**
- Modify: `frontend/src/views/module_ai/integration/components/GovernancePanel.vue`

**Interfaces:**
- Consumes: 现有 `onTab`/`load*` 函数、数据 ref（本任务读取现状）。
- Produces: `GovernancePanel` 子 tab = overview/access/dq/domain/fde 五个分支；`onTab` 只含这五支；删除 `ontGov`/`pendingActions`/`actionList`/`actionLogs`/`lifecycle`/`govObjects` 及 `loadOntGov`/`loadAction`/`loadLifecycle`/`loadObjects`/`apAction`/`getPendingActions`/`getActionList`/`getActionLogs`/`approveAction`/`rejectAction`/`getOntologyGovernance`/`getObjectLifecycle` 相关调用与 import。Task 2 复用该组件。

- [x] **Step 1: 备份现状并确认删除范围（先跑前端静态检查基线）**

Run: `cd frontend && pnpm run type-check`
Expected: baseline 通过（记录是否有既有 lint 错误，若有、与本任务无关则忽略）。

- [x] **Step 2: 删除 `ontgov`（本体对象）子 tab**

模板删除 `<el-tab-pane :label="t('ai_workflow.ig_govOnt')" name="ontgov">…`（约 L393-491 整块）。

- [x] **Step 3: 删除 `action`（表级写回·旧版）子 tab**

模板删除 `… name="action">…`（约 L494-637 整块，含待审批/定义/审计三个 table）。

- [x] **Step 4: 删除 `lifecycle`（生命周期）子 tab**

模板删除 `… name="lifecycle">…`（约 L729-791 整块）。

- [x] **Step 5: script 清理——删数据 ref 与加载函数**

删除：
- `const lifecycle = ref<any>(null);`（L1400）、`const ontGov = ref<any>(...)`（L1413）、`const govObjects = ref<any[]>([])`（L1414）、`const pendingActions/actionList/actionLogs`（L1416-1418）。
- `loadLifecycle`（L1402-1409）、`loadOntGov`（L1424-1427）、`loadObjects`（L1444-1447）、`loadAction`（L1463-1478）、`apAction`（L1480 起，含 approve/reject 分支）。
- `onTab` 中 `ontgov`/`action`/`lifecycle` 三个分支。
- import 中不再使用的 `getOntologyGovernance`/`getObjectLifecycle`/`getPendingActions`/`getActionList`/`getActionLogs`/`approveAction`/`rejectAction`。

> 策略：删完跑 `pnpm run type-check`，按报错逐项清残留（此时最可靠），勿凭猜测删 import。

- [x] **Step 6: 前端静态检查**

Run: `cd frontend && pnpm run type-check 2>&1 | last 20`
Expected: 通过（无因删除引发的 `is defined but never used` / 引用不存在报错）。

- [x] **Step 7: 提交**

```bash
git add frontend/src/views/module_ai/integration/components/GovernancePanel.vue
git commit -m "feat(ai): 治理面板精简子tab删本体对象/旧版写回/生命周期"
```

---

### Task 2: 新建治理独立页 + `integration/index.vue` 移除 gov tab

**Files:**
- Create: `frontend/src/views/module_ai/governance/index.vue`
- Modify: `frontend/src/views/module_ai/integration/index.vue`

**Interfaces:**
- Consumes: Task 1 的 `GovernancePanel`（现已 5 子 tab）。`QUERY_GROUP_MENUS` 的菜单结构（Task 3 用）。
- Produces: 新页面组件 `module_ai/governance/index.vue`（Task 3 菜单 `component_path` 引用它）；`integration/index.vue` 顶部 tab 恒 9 个。

- [x] **Step 1: 新建 `module_ai/governance/index.vue`**

```vue
<!-- 治理：数据治理独立页（原「数据与集成」内嵌套的治理 tab 拆出） -->
<template>
  <div class="app-container ai-mod governance-page">
    <el-card shadow="never" class="gov-shell">
      <GovernancePanel />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import GovernancePanel from "./../integration/components/GovernancePanel.vue";
defineOptions({ name: "GovernancePage" });
</script>

<style lang="scss">
/* 非 scoped：避免 keep-alive/HMR 下 data-v 失效；对齐框架白面板外壳 */
.app-container.governance-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: 12px;
  box-sizing: border-box;
}
.governance-page .gov-shell {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}
</style>
```
> 说明：`GovernancePanel` 内部是 `<el-tabs>`，自带 `.gp-wrap { padding:12px }`；独立页卡片内可白板铺满。若 `GovernancePanel` 高度未撑满，可在 `index.vue` 的非 scoped 样式中给 `.gov-shell :deep(.el-card__body)` 补 flex 高度链。

- [x] **Step 2: `integration/index.vue` 删除 gov tab**

删 `<el-tab-pane :label="t('ai_workflow.ig_governance')" name="gov"><GovernancePanel /></el-tab-pane>`（约 L942-944）。
删 `import GovernancePanel from "./components/GovernancePanel.vue";`（约 L1640）。
简化右列布局三元（约 L65-67）：因 `tab` 不再可能等于 `'gov'`，把 `:sm="tab === 'gov' ? 24 : 16"` 简化为常量 `:sm="16"`，`:md` 恒 `18`，`:lg` 恒 `19`；同时左列 `v-if="tab !== 'gov'"` 简化为恒显示（去掉 `v-if`）。左侧 `el-col` 保留 `:xs="24" :sm="8" :md="6" :lg="5"`。

- [x] **Step 3: 前端静态检查**

Run: `cd frontend && pnpm run type-check 2>&1 | last 20`
Expected: 通过。

- [x] **Step 4: 浏览器冒烟（若 dev 前端在跑，打开验证）**

用无头浏览器打开 `/ai/governance`（若该路由尚未注册会 404，属预期——Task 3 注册菜单后才可访问；此处仅用 `pnpm run type-check` 保证编译层通过即可，路由访问验收放 Task 3）。

- [x] **Step 5: 提交**

```bash
git add frontend/src/views/module_ai/governance/index.vue frontend/src/views/module_ai/integration/index.vue
git commit -m "feat(ai): 治理拆出为独立页面并从数据与集成移除嵌套tab"
```

---

### Task 3: 后端菜单注册 + 端到端验证 + 收尾

**Files:**
- Modify: `backend/app/scripts/init_app.py`（`QUERY_GROUP_MENUS`，约 L793-798）
- Test: `backend/tests/test_report_permission_registration.py` 等菜单注册相关用例回归

**Interfaces:**
- Consumes: Task 2 的 `module_ai/governance/index.vue` 组件路径。
- Produces: 菜单行 `(title="治理", route_name="AiGovernance", route_path="/ai/governance", component="module_ai/governance/index", order=5)`，权限 `module_ai:query:ask`。

- [x] **Step 1: 在 `QUERY_GROUP_MENUS` 增加治理菜单**

`backend/app/scripts/init_app.py` 的 `QUERY_GROUP_MENUS` 列表（L793-798）加一行：
```python
("治理", "AiGovernance", "/ai/governance", "module_ai/governance/index", 5, "el-icon-DataBoard"),
```
> `QUERY_GROUP_MENUS` 现有 4 条（order 1-4），治理放 order 5，`_ensure_ai_menus` 的循环（L921-959）会幂等 upsert 该菜单 + 绑 role_id=1，无需其它改动。

- [x] **Step 2: 后端静态检查 + 菜单注册用例回归**

Run: `cd backend && uv run ruff check app/scripts/init_app.py && uv run pytest tests/test_report_permission_registration.py -q`
Expected: ruff 全过 + 菜单注册用例通过。

- [x] **Step 3: 重启后端（--no-reload）并验证菜单注册**

按 AGENTS.md 规矩重启 dev 后端（8002）：杀掉 `*main.py*`、确认端口空、`SERVER_PORT=8002 CAPTCHA_ENABLE=false main.py run --env=dev --no-reload`，等就绪后：
`Invoke-WebRequest http://127.0.0.1:8002/api/v1/system/menu/list -Headers @{Authorization="Bearer <token>"}`
Expected: 返回菜单树含 `AiGovernance`（`/ai/governance`）。
（若无现成 token，可先在 `init_app.py` 启动日志确认“AI 菜单分组已就绪/已注册”，再核对菜单表行：`SELECT * FROM sys_menu WHERE route_name='AiGovernance'`。）

- [x] **Step 4: 前端访问验证**

前端 dev（如在跑）打开 `/ai/governance`，确认：整页白面板铺满、不贴边；子 tab = 驾驶舱/权限/数据质量/数据域/交付命题 5 个；各 tab 数据加载正常。同时打开 `/ai/integration` 确认顶部 tab 只剩 9 个（无「治理」）、左数据源栏恒显示。

- [x] **Step 5: 提交**

```bash
git add backend/app/scripts/init_app.py
git commit -m "feat(ai): 注册治理独立菜单到智能问数目录"
```

- [x] **Step 6: 勾选计划 Task 并收尾**

本计划各 Task checkbox 全部勾选；确认与 spec `docs/superpowers/specs/2026-10-29-integration-governance-decouple.md` 对齐。

---

## 执行说明

- Task 1 删除范围大，**删除后务必 `pnpm run type-check` 按报错逐项清残留**，勿凭猜测删 import。
- 治理页白面板只须外层 `el-card`，`GovernancePanel` 内部 tabs 已有 `.gp-wrap` 留白。
- 后端只加菜单，**不改任何治理接口**；`/objects/lifecycle`、`/ontology/governance` 接口虽不再被前端调用但保留。
- 前端 dev/后端 8002 均为既有服务，若在使用勿擅自重启；验证路由访问需在菜单注册后。
