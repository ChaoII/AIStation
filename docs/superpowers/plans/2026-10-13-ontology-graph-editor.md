# 本体图谱化编辑 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把本体页右侧的「20 个 tab + 清单」改为「一张可编辑的 cytoscape 图谱」，节点=对象类型、边=关系类型，点节点弹详情抽屉，辅助功能收进概览/维护抽屉。

**Architecture:** 右侧图谱工作区封装为独立组件 `OntGraphWorkspace.vue`（复用现有 `GraphCanvas.vue` cytoscape 引擎 + `useOntologyData` 数据层）。`index.vue` 大幅瘦身：右栏渲染 `OntGraphWorkspace` + 概览/维护抽屉，移除旧 tab 导航与 `mode/page` 分支。节点/边由纯函数 `buildOntGraph` 从 `scopedObjects/scopedLinks` 构建（可单测）。编辑走现有 `stage()` 暂存机制。

**Tech Stack:** Vue 3 + Vite + TypeScript + Element Plus + cytoscape(GraphCanvas.vue) + vitest + vue-tsc

**Spec:** `docs/superpowers/specs/2026-10-13-ontology-graph-editor-design.md`

## Global Constraints

- 图谱一律用 `GraphCanvas.vue`（cytoscape），**严禁自绘 SVG**。
- 交互全部用 Element Plus 原生组件 + `--el-*` 变量，不加自定义主题；弹窗/抽屉放页面单根内。
- 删除类操作必须 `ElMessageBox.confirm` 二次确认，文案写明影响范围。
- 所有编辑走 `stage()` 暂存 + 右上角「保存/丢弃」，不直接落库。
- 后端不改动（复用现有 objects/links/actions/functions/domains API）。
- 提交信息中文，格式 `feat(ai): 中文描述`。
- `index.vue` 当前含大量未提交 WIP（旧本体页 + 上一轮本体列表改动），**保留左栏本体列表不动**，只重构右栏。

## Review Focus

1. **空本体 / 无对象**：某个本体下没有任何对象类型时，图谱应显示空状态提示（el-empty），不渲染空画布报错。
2. **无关系的孤立对象**：「只显示有关联」开关开启时，`link_count===0` 的对象应从节点中过滤掉；关闭时全部显示。
3. **点节点后对象不存在**：`objectByCode` 找不到时（数据过期），详情抽屉应优雅关闭/提示，不抛错。
4. **同一对象自环 / 重复边**：`links` 里 source===target 或重复关系不应产生重复边导致 cytoscape 警告。
5. **切本体后图谱重绘**：切换左栏本体 → `scopedObjects/scopedLinks` 变化 → 图谱 nodes/edges 应更新（watch 深比较触发）。

---

## 阶段 1：图谱骨架（只读浏览 + 详情抽屉）

### Task 1: 图谱数据构建纯函数 `buildOntGraph`

**Files:**
- Create: `frontend/src/views/module_ai/ontology/graph.ts`
- Test: `frontend/src/views/module_ai/ontology/__tests__/buildOntGraph.spec.ts`

**Interfaces:**
- Consumes: 无（纯函数，输入为对象/关系数组）
- Produces: `buildOntGraph(objects: any[], links: any[], opts?: { onlyConnected?: boolean }): { nodes: OntNode[]; edges: OntEdge[] }`。`OntNode = { id: number; name: string; etype: string; weight: number; objectCode: string }`（`name` 用对象显示名，`etype` 固定 `"object"`）；`OntEdge = { source: string; target: string; rtype: string }`（`source/target` 用节点 `name`，`rtype` 用关系名）。

- [ ] **Step 1: 写失败测试**

```ts
// __tests__/buildOntGraph.spec.ts
import { describe, it, expect } from "vitest";
import { buildOntGraph } from "../graph";

const objs = [
  { code: "A", name: "客户", link_count: 2 },
  { code: "B", name: "订单", link_count: 1 },
  { code: "C", name: "孤儿", link_count: 0 },
];
const links = [
  { source_object: "A", target_object: "B", name: "下单" },
];

describe("buildOntGraph", () => {
  it("默认返回所有对象作为节点", () => {
    const g = buildOntGraph(objs, links);
    expect(g.nodes).toHaveLength(3);
    expect(g.nodes.map((n) => n.name)).toContain("客户");
  });
  it("边连接 source/target 的 name", () => {
    const g = buildOntGraph(objs, links);
    const e = g.edges[0];
    expect(e.source).toBe("客户");
    expect(e.target).toBe("订单");
    expect(e.rtype).toBe("下单");
  });
  it("只显示有关联时过滤 link_count===0 的孤立对象", () => {
    const g = buildOntGraph(objs, links, { onlyConnected: true });
    expect(g.nodes.map((n) => n.name)).not.toContain("孤儿");
  });
  it("自环/重复边不产生重复 edge", () => {
    const selfLink = { source_object: "A", target_object: "A", name: "自关联" };
    const g = buildOntGraph(objs, [...links, selfLink]);
    // 自环只产生一条边
    expect(g.edges.filter((e) => e.rtype === "自关联")).toHaveLength(1);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd frontend && npx vitest run src/views/module_ai/ontology/__tests__/buildOntGraph.spec.ts`
Expected: FAIL（`buildOntGraph` 未定义）

- [ ] **Step 3: 实现 `buildOntGraph`**

实现要点：节点 `name` 用 `o.name`（去重，若遇重名则附 code 后缀）；边仅当 source/target 都在节点集且不是自环时加入；`onlyConnected` 时过滤 `(o.link_count || 0) === 0`。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd frontend && npx vitest run src/views/module_ai/ontology/__tests__/buildOntGraph.spec.ts`
Expected: PASS（4 个用例）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/module_ai/ontology/graph.ts frontend/src/views/module_ai/ontology/__tests__/buildOntGraph.spec.ts
git commit -m "feat(ai-ontology): 新增图谱数据构建纯函数 buildOntGraph(可单测)"
```

### Task 2: `OntGraphWorkspace.vue` 图谱工作区（工具条 + GraphCanvas + 筛选）

**Files:**
- Create: `frontend/src/views/module_ai/ontology/components/OntGraphWorkspace.vue`
- Modify: `frontend/src/views/module_ai/ontology/index.vue`（右栏接入，见 Task 4；本任务先只建组件）

**Interfaces:**
- Consumes: `buildOntGraph`（Task 1）；`useOntologyData()` 的 `scopedObjects/scopedLinks/currentDomain`；`GraphCanvas.vue`（props：`nodes/edges/layoutName/graphRef`、emits：`node-tap`、expose：`search/fit/zoom/setLayout`）
- Produces: 组件 props `{ domainCode: string }`；emits `node-tap(objectCode: string)`（供 index.vue 打开详情）。内部工具条含：`el-select` 布局（力导向/同心/树/网格/环形）、`el-input` 搜索、功能开关（只显示有关联）、`el-button-group` 缩放/适配、节点/边计数 `el-tag`。

- [ ] **Step 1: 建组件骨架 + 图谱渲染**

实现 `OntGraphWorkspace.vue`：模板含工具条 + `<GraphCanvas ref="graphRef" :nodes="nodes" :edges="edges" :layout-name="layout" height="100%" .../>`；`nodes/edges` 由 `computed(() => buildOntGraph(scopedObjects, scopedLinks, { onlyConnected: onlyConnected.value }))`；其余用 `useOntologyData()` 取作用域数据。空数据时 `v-if` 用 `el-empty` 提示「该本体暂无对象类型」。

- [ ] **Step 2: 接入 index.vue 右栏并移除旧 tab 导航**

在 `index.vue` 右栏 `<el-card>` 内，把原「header 面包屑 + el-tabs + 各 page 分支」替换为 `<OntGraphWorkspace :domain-code="currentDomain" />`；删除 `el-tabs` 及 `<template v-else>` 内所有 `v-if page==='xxx'` 分支（概览/搜索/对象/属性/关系/动作/函数/决策/场景/索引/提案/健康/清理/历史/transfer/usage/explore/shared/interfaces/advanced）。**保留**右上「保存/丢弃」与「去问数验证」按钮，上移到工具条或 card header。删除不再引用的子组件 import（OntDecisionView/OntScenarioView/OntIndexView/OntProposalView/OntInstanceExplorer/OntAdvancedTypes/OntObjectTypeView/OntLinkTypeView/OntActionTypeView）与 `navItems/HOME_NAV/OBJECT_NAV/LINK_NAV/ACTION_NAV/mode/page/onNav/onTabChange/backHome` 等导航逻辑（若 `resIcon/resTitle` 不再用一并清理）。

- [ ] **Step 3: 类型检查**

Run: `cd frontend && pnpm run type-check`
Expected: 无 `module_ai/ontology` 相关 error TS（既有其它模块错误忽略）。

- [ ] **Step 4: 浏览器验证图谱渲染**

启动前端（5181）登录 admin/123456 → 进入本体页 → 确认左栏本体列表保留、右栏显示 GraphCanvas，节点为对象类型、边为关系类型；点工具条「只显示有关联」开关生效。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/module_ai/ontology/components/OntGraphWorkspace.vue frontend/src/views/module_ai/ontology/index.vue frontend/src/views/module_ai/ontology/graph.ts
git commit -m "feat(ai-ontology): 右栏改为图谱工作区(cytoscape)，移除旧 tab 导航"
```

### Task 3: 点节点弹对象详情抽屉（复用 OntObjectTypeView）

**Files:**
- Modify: `frontend/src/views/module_ai/ontology/index.vue`
- Modify: `frontend/src/views/module_ai/ontology/components/OntGraphWorkspace.vue`（转发 `node-tap`）

**Interfaces:**
- Consumes: `OntObjectTypeView`（props `code/page`，emits `edit-object/new-action/new-link`）；`objectByCode`；`openObjectEdit/openActionEdit/openLinkEdit/removeObj`（index.vue 已有）
- Produces: 点击图谱节点 → index.vue 打开右侧 `el-drawer`，内含 `<OntObjectTypeView :code="selKey" page="overview" />`。右上角提供「编辑/物化」操作。

- [ ] **Step 1: 组件转发 node-tap**

`OntGraphWorkspace.vue` 的 `GraphCanvas` `@node-tap` 事件 → `emit('node-tap', code)`。

- [ ] **Step 2: index.vue 加详情抽屉**

在 index.vue 加 `el-drawer`（`v-model="objectDrawer"`，size 约 560px，右侧），内放 `<OntObjectTypeView v-if="selObject" :code="selKey" page="overview" />`。`onGraphNodeTap(code)` 设 `selKey=code; objectDrawer=true`。处理 Review Focus 第 3 条：`objectByCode` 找不到时 `ElMessage.warning` 并关闭抽屉。

- [ ] **Step 3: 编辑在抽屉内可用**

抽屉内「编辑元数据/新建属性/新建动作/新建函数」调用 index.vue 现有 `openObjectEdit/openActionEdit/openFuncEdit`（这些是 index.vue 里的 dialog，append-to-body，可与抽屉共存）。

- [ ] **Step 4: 类型检查**

Run: `cd frontend && pnpm run type-check`
Expected: 无 ontology 相关 error。

- [ ] **Step 5: 浏览器验证**

点击某个对象节点 → 右侧抽屉展开显示该对象类型详情（元数据/属性/动作/函数）。空/找不到对象时行为符合 Review Focus 第 3 条。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/module_ai/ontology/index.vue frontend/src/views/module_ai/ontology/components/OntGraphWorkspace.vue
git commit -m "feat(ai-ontology): 点图谱节点打开对象详情抽屉(复用 OntObjectTypeView)"
```

---

## 阶段 2：双向编辑

### Task 4: 拖拽节点建关系 + 点边编辑关系

**Files:**
- Modify: `frontend/src/views/module_ai/ontology/components/OntGraphWorkspace.vue`
- Modify: `frontend/src/views/module_ai/ontology/index.vue`

**Interfaces:**
- Consumes: `GraphCanvas` `linkMode` prop + `link-draw` emit（`(source, target, x, y)`）；`openLinkEdit`（index.vue 已有，`openLinkEdit(link?)` 打开关系 dialog）
- Produces: `link-draw(sourceName, targetName)` → index.vue 查 `objectByCode`（按 name 反查 code）→ `openLinkEdit()` 预填 source_object/target_object。

- [ ] **Step 1: GraphCanvas 开启 linkMode**

`OntGraphWorkspace.vue` 给 `GraphCanvas` 加 `:link-mode="true"`，`@link-draw="onLinkDraw"`。

- [ ] **Step 2: onLinkDraw 反查 code 并打开关系编辑**

实现 `onLinkDraw(sourceName, targetName)`：通过 `scopedObjects` 按 `name` 找到两个 code，调用 emit(`link-draw`, srcCode, dstCode)；index.vue 收到后 `openLinkEdit()` 且把 `linkForm` 的 `source_object/target_object` 预填为两 code，打开关系 dialog。

- [ ] **Step 3: 点边编辑现有关系**

GraphCanvas 目前未 emit 边点击。在 `OntGraphWorkspace.vue` 用 GraphCanvas 的 `edge-ctx`（右键）或加 `edge-tap` 支持（若 GraphCanvas 无则复用其 `edge-ctx`）→ 弹出关系上下文：编辑该关系（按 source/target name 反查 link → `openLinkEdit(link)`）。同 name 可能有多个关系，用第一个匹配（Review Focus 第 4 条不产生运行时错误即可）。

- [ ] **Step 4: 类型检查 + 浏览器验证**

Run type-check（无 ontology error）。浏览器验证：拖拽一个节点到另一节点 → 弹出关系编辑 dialog 且源/目标已预填；保存走暂存（右上角出现「保存」角标）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/module_ai/ontology/components/OntGraphWorkspace.vue frontend/src/views/module_ai/ontology/index.vue
git commit -m "feat(ai-ontology): 图谱拖拽建边/点边编辑关系(走暂存)"
```

### Task 5: 右键新建/编辑/删除对象（走暂存）

**Files:**
- Modify: `frontend/src/views/module_ai/ontology/components/OntGraphWorkspace.vue`
- Modify: `frontend/src/views/module_ai/ontology/index.vue`

**Interfaces:**
- Consumes: GraphCanvas `node-ctx(name,x,y)` / `blank-ctx(x,y)`；`openObjectEdit(null)`/`openObjectEdit(obj)`/`removeObj(obj)`/`materialize(obj)`（index.vue 已有，走 stage 暂存）
- Produces: 右键节点 → `el-dropdown` 菜单（编辑/物化/删除）；右键空白 → 新建对象类型。删除用 `removeObj`（内含二次确认）。

- [ ] **Step 1: 右键节点菜单**

`OntGraphWorkspace.vue` 监听 `@node-ctx`，记录当前右键对象与坐标，用 `el-dropdown`（absolute 定位）或 Element 的 contextmenu 处理，选项：编辑元数据 / 物化为表 / 删除（删除红色，走 `removeObj`）。`@blank-ctx` → 「新建对象类型」→ `openObjectEdit(null)`。

- [ ] **Step 2: 编辑后重绘图谱**

`openObjectEdit` 保存后现有逻辑已 `reloadAll()`；确保 `OntGraphWorkspace` 的 nodes/edges computed 因 `scopedObjects` 更新而重绘（watch 深比较已由 GraphCanvas 内置）。

- [ ] **Step 3: 类型检查 + 浏览器验证**

Run type-check。浏览器验证：右键节点 → 删除弹二次确认（带对象数、不可恢复），确认后走暂存；右键空白 → 新建对象类型 dialog。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/module_ai/ontology/components/OntGraphWorkspace.vue frontend/src/views/module_ai/ontology/index.vue
git commit -m "feat(ai-ontology): 图谱右键新建/编辑/删除对象(二次确认+暂存)"
```

---

## 阶段 3：辅助功能抽屉

### Task 6: 概览抽屉

**Files:**
- Create: `frontend/src/views/module_ai/ontology/components/OntOverviewDrawer.vue`
- Modify: `frontend/src/views/module_ai/ontology/index.vue`

**Interfaces:**
- Consumes: index.vue 原 `page==='overview'` 模板（演示数据 `doLoadDemo/doClearDemo/demoStatus/demoReport`、`homeStats`、数据源导入 `impDs/onImportDsChange/doBatchImport/industryTemplates/applyTemplate`）——这些状态与函数需从 index.vue 移到/传给 `OntOverviewDrawer`。
- Produces: props `{ domainCode: string }`；在工具条加「概览」按钮 → 打开此 drawer。

- [ ] **Step 1: 抽取概览模板到 OntOverviewDrawer.vue**

把 index.vue 原 overview 区块（L192-L316 附近，演示数据卡片、homeStats 统计、数据源导入、行业模板）剪切进 `OntOverviewDrawer.vue`，迁移相关 ref/函数（`demoStatus/demoReport/demoBusy/doLoadDemo/doClearDemo/refreshDemo/homeStats/impDs/impTableCount/impIncludeTechnical/onImportDsChange/doBatchImport/industryTemplates/tplLoading/applyTemplate`）。homeStats 改用 `useOntologyData` 的 `scopedObjects` 等推导。

- [ ] **Step 2: index.vue 加「概览」按钮 + 抽屉**

工具条（OntGraphWorkspace 或 card header）加「概览」按钮 → `<OntOverviewDrawer v-if="overviewDrawer" .../>`。

- [ ] **Step 3: 类型检查 + 浏览器验证**

Run type-check。浏览器验证：点「概览」→ 抽屉展示演示数据/统计/导入/模板；载入演示数据可用。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/module_ai/ontology/components/OntOverviewDrawer.vue frontend/src/views/module_ai/ontology/index.vue
git commit -m "feat(ai-ontology): 概览收进右侧抽屉(演示数据/统计/导入/模板)"
```

### Task 7: 维护下拉 + 各辅助功能抽屉

**Files:**
- Create: `frontend/src/views/module_ai/ontology/components/OntMaintenanceDrawer.vue`
- Modify: `frontend/src/views/module_ai/ontology/index.vue`

**Interfaces:**
- Consumes: 原 `page==='indexing'/'proposals'/'scenarios'/'decisions'/'health'/'cleanup'/'history'/'usage'/'transfer'/'explore'/'shared'/'interfaces'/'advanced'` 模板与 `OntIndexView/OntProposalView/OntScenarioView/OntDecisionView/OntInstanceExplorer/OntAdvancedTypes`；`reloadAll`
- Produces: 一个可参数化的 `OntMaintenanceDrawer`（prop `panel`），内含 `v-if` 各面板；或在 index.vue 用多个 `el-drawer`。工具条「维护」`el-dropdown` 列出面板名 → 打开对应 drawer。

- [ ] **Step 1: 建 OntMaintenanceDrawer + 收纳各面板**

把：索引(`OntIndexView`)、提案(`OntProposalView`)、场景(`OntScenarioView`)、决策(`OntDecisionView`)、对象探索(`OntInstanceExplorer`)、高级类型/接口/共享属性(`OntAdvancedTypes`)、健康检查/清理/历史/使用量/导入导出（原内联）——迁入 drawer。内联的健康/清理/历史/usage/transfer 模板从 index.vue 剪切进 drawer，迁移相关 ref/函数（`cleanupList/loadCleanup`、`usageStats`、`importPanel/loadImportPanel` 等）。

- [ ] **Step 2: index.vue 加「维护」下拉**

工具条加「维护」`el-dropdown`（索引/提案/场景/决策/对象探索/健康/清理/历史/使用量/导入导出/高级类型），`@command` 打开 `OntMaintenanceDrawer` 指定 panel。

- [ ] **Step 3: 移除遗留分支与未用代码**

删除 index.vue 中其余 `page` 分支残留、`mode/page` 相关已无用逻辑、相关未用 ref。确保 type-check 无 ontology 相关 error、无未使用变量（`vue-tsc` 会提示）。

- [ ] **Step 4: 类型检查 + 浏览器验证**

Run type-check（0 ontology error）。浏览器验证：维护下拉各面板抽屉可打开且内容正常。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/views/module_ai/ontology/components/OntMaintenanceDrawer.vue frontend/src/views/module_ai/ontology/index.vue
git commit -m "feat(ai-ontology): 辅助功能收进维护下拉抽屉(索引/提案/场景/决策/健康等)"
```

---

## 收尾

### Task 8: 全量回归 + 类型检查

- [ ] **Step 1: 全量 type-check**

Run: `cd frontend && pnpm run type-check`
Expected: 无 `module_ai/ontology` 相关 error TS。

- [ ] **Step 2: 浏览器全流程验证**

验证：左栏切本体 → 图谱重绘；点节点 → 详情抽屉；拖拽建边；右键编辑/删除（二次确认）；概览抽屉；维护下拉各抽屉；右上「保存/丢弃」工作副本闭环。

- [ ] **Step 3: 提交最终清理**

```bash
git add -A frontend/src/views/module_ai/ontology
git commit -m "chore(ai-ontology): 本体图谱化编辑全量清理与回归"
```
