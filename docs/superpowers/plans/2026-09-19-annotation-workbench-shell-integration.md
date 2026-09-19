# 标注工作台 · 壳层整合进可复用组件库（阶段 5b）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) 或 subagent-driven-development. Steps use `- [ ]` checkbox syntax.

**Goal:** 把旧 `frontend/src/views/module_annotation/annotation/index.vue` 的**完整工作台壳功能**（任务加载、图片列表分页、保存、类别管理、协作锁、历史、右键、快捷键、分类面板、编辑弹窗、未保存拦截）迁入可复用的 `frontend/src/annotation/core/AnnotationWorkbench.vue`，通过 **API 注入**保持组件库可复用、不依赖本项目业务模块；完成后即可把生产工作台路由切换到新组件并归档旧文件。

**Architecture:** 组件库 workbench 通过 props 接收一个 `api` 对象与 `config`（task_type / classes / classification_mode），自己承载布局（顶栏/左工具/画布/右栏）与全部壳层交互；任务编辑能力仍由任务插件提供。core 不 import 本项目业务模块，API 全部注入。

**Tech Stack:** Vue 3 + TS + Element Plus + Pinia + Playwright(e2e)。

## Global Constraints

- 组件库 `frontend/src/annotation/core` **不得 import 项目业务模块**（`@/api/*`、`store` 等）；全部通过 props 注入。
- 保持与旧工作台**完全一致的生产行为**（同一后端接口、数据格式、交互、锁定/历史/右键/快捷键）。
- 复用边界仅前端；后端不变。
- 提交信息中文；每任务 type-check + 相关 e2e 回归。
- 删除/危险操作需二次确认；只读（他人锁定）禁止编辑；`v-hasPerm` 权限与后端一致。

## 文件结构（本计划新增/改动）

```
frontend/src/annotation/core/
  AnnotationWorkbench.vue        # 由"编辑核心"扩展为"完整工作台壳"
  useAnnotationStore.ts          # 扩展：task/images/currentImage/progress/classes…
  AnnotationTypes.ts             # 新增：WorkbenchApi / WorkbenchConfig 注入接口
frontend/src/views/module_annotation/annotation/
  index.vue                      # 阶段末切换为新组件并归档（复制为 .bak 后替换）
```

---

### Task A: 定义注入接口（`WorkbenchApi`/`WorkbenchConfig`）+ 扩展 store

**Files:**
- Create: `frontend/src/annotation/core/annotationTypes.ts`
- Modify: `frontend/src/annotation/core/useAnnotationStore.ts`

**Interfaces:**
- Produces: `WorkbenchApi`（getTaskDetail/listImages/getPresignedUrl/loadAnnotations/saveAnnotations/lockImage/unlockImage/updateTask/getTaskProgress）、`WorkbenchConfig`（taskType/classes/classificationMode）、store 扩展：`task`、`images`、`currentImage`、`progress`、`annotatedCount/totalCount`、`loading`。

- [ ] **Step 1: 创建 `annotationTypes.ts`**

```ts
export interface WorkbenchApi {
  getTaskDetail(taskId: number): Promise<any>;
  listImages(params: any): Promise<any>;
  getPresignedUrl(imageId: number, taskId: number): Promise<any>;
  loadAnnotations(taskId: number, imageId: number): Promise<any>;
  saveAnnotations(taskId: number, imageId: number, data: any[]): Promise<any>;
  lockImage(imageId: number, taskId: number): Promise<any>;
  unlockImage(imageId: number, taskId: number): Promise<any>;
  updateTask(taskId: number, patch: any): Promise<any>;
  getTaskProgress(taskId: number): Promise<any>;
}
export interface WorkbenchConfig {
  taskType: string;
  classes: { id: number; name: string; color: string; keypoint_names?: string[] }[];
  classificationMode: "single" | "multi";
}
```

- [ ] **Step 2: 扩展 `useAnnotationStore.ts`**，state 增加 `task`、`images`、`currentImageIndex`、`loading`、`annotatedCount`、`totalCount`；getter `currentImage`、`currentImageId`、`progress`。

```ts
const state = () => ({
  taskId: 0,
  task: null as any,
  annotations: [] as Annotation[],
  selectedAnnotationId: "" as string,
  images: [] as any[],
  currentImageIndex: 0,
  loading: false,
  annotatedCount: 0,
  totalCount: 0,
  unsaved: false,
});
const getters = {
  currentImage(state) { return state.images[state.currentImageIndex] ?? null; },
};
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/annotation
git commit -m "feat(annotation): 定义工作台注入接口(WorkbenchApi/Config)并扩展 store"
```

---

### Task B: 迁入布局壳（header/leftbar/canvas/rightbar）

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`（模板增加 header/leftbar/rightbar 布局，复用现有画布与插件渲染）

**Interfaces:**
- Consumes: `WorkbenchApi`/`WorkbenchConfig`、`useAnnotationStore`
- Produces: 组件具备完整三栏布局：顶栏(任务类型 tag + 名称 + 进度) / 左侧工具栏(通用工具+任务工具+撤销重做删除) / 画布 / 右侧(图片列表+类别+标注列表面板)。

- [ ] **Step 1: 重写 `AnnotationWorkbench.vue` 模板为三栏布局**（顶栏/左工具/画布/右栏），沿用 Element Plus（`el-tag/el-progress/el-card/el-button/el-select/el-input/el-dialog/el-popconfirm` 等），复用现有画布与 `<component :is="plugin.renderer">`。

- [ ] **Step 2: type-check** 通过。

- [ ] **Step 3: 提交** `feat(annotation): 工作台壳三栏布局`

---

### Task C: 迁入任务加载 + 图片分页渐进加载

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Consumes: `WorkbenchApi`，`store`
- Produces: `onMounted` 读取 config 传入的 taskId → `api.getTaskDetail` → 设 taskType/classes → 列表 `api.listImages` 首页 → 首图 `loadCurrent()`；`prefetch` 渐进加载其余页；`fetchProgress`。

- [ ] **Step 1: 在 `AnnotationWorkbench` 实现 `init()`**（任务加载/图片首页/首图/进度），复用旧 `index.vue` 的 `loadImagePage/prefetchRemainingImages/loadImg/fetchTaskProgress` 逻辑，改为经 `props.api` 注入调用。

- [ ] **Step 2: type-check + 临时 e2e（加载真实任务 → `.ann-svg` 可见）**通过。

- [ ] **Step 3: 提交** `feat(annotation): 工作台壳任务加载与图片分页`

---

### Task D: 迁入保存 + 锁定/只读

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Produces: `saveAnn()`（`api.saveAnnotations` + 更新图片状态/进度）、`lockImage/unlockImage`（只读提示）、未保存拦截（`beforeunload`）。

- [ ] **Step 1: 实现 `saveAnn/lockCurrent/unlockCurrent/onBeforeUnload`**，复用旧逻辑。
- [ ] **Step 2: type-check + 回归**。
- [ ] **Step 3: 提交** `feat(annotation): 工作台壳保存与协作锁定`

---

### Task E: 迁入历史(undo/redo/历史抽屉) + 未保存标记

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Produces: `annotKey/pushHistory/undo/redo/restoreHistory`（复用旧逻辑，历史抽屉组件保留在旧页面或注入）。

- [ ] **Step 1: 实现历史栈**（`pushHistory/undo/redo/restore`），复用旧 `index.vue` 逻辑；恢复仅在真实变更时 `markUnsaved`。
- [ ] **Step 2: type-check + 回归**。
- [ ] **Step 3: 提交** `feat(annotation): 工作台壳历史撤销重做`

---

### Task F: 迁入右键菜单 + 编辑弹窗(含关键点/Ocr)

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Produces: 标注右键菜单（编辑/删除）、编辑弹窗（类别 + OCR 文本 + 关键点 visibility/name）、删除二次确认。

- [ ] **Step 1: 实现 `annMenu/openEditDialog/menuEdit/menuDelete`**，复用旧逻辑；删除用 `ElMessageBox.confirm`。
- [ ] **Step 2: type-check + 回归**。
- [ ] **Step 3: 提交** `feat(annotation): 工作台壳右键菜单与编辑弹窗`

---

### Task G: 迁入快捷键 + 分类面板 + 工具图标

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Produces: `onKey`（Ctrl+Z/Y/Del、工具切换 1-7）、`toggleClassification`（单标可取消/多标）、任务工具图标（Element Plus icons）。

- [ ] **Step 1: 实现 `onKey` 与 `classification` 面板**；工具栏图标用 Element Plus 图标（`v-hasPerm` 权限）。
- [ ] **Step 2: type-check + 回归**。
- [ ] **Step 3: 提交** `feat(annotation): 工作台壳快捷键与分类面板`

---

### Task H: 切换生产路由到新组件 + 归档旧文件 + 全面回归

**Files:**
- Modify: `frontend/src/views/module_annotation/annotation/index.vue`（改为渲染 `AnnotationWorkbench`，传入 api/config）
- Modify: `frontend/src/views/module_annotation/annotation/index.vue` 原壳逻辑归档为 `index.legacy.vue`

**Interfaces:**
- Consumes: 完整 `AnnotationWorkbench`

- [ ] **Step 1: 复制旧 `index.vue` 为 `index.legacy.vue`（备份）**。
- [ ] **Step 2: 重写 `index.vue` 为 `AnnotationWorkbench` 包装**：`<AnnotationWorkbench :api="workbenchApi" :config="config" :task-id="tid" />`，`workbenchApi` 由 `@/api/module_annotation` 组装。
- [ ] **Step 3: 全面回归**：`workbench.spec / annotation-task-classes / annotation-history / collaboration / clean` 全过；`pnpm run type-check` 干净。
- [ ] **Step 4: 提交** `refactor(annotation): 工作台切换到可复用组件库并归档旧实现`

---

## 验收标准

- 生产工作台功能与重构前一致（加载/图片列表/标注/保存/锁定/历史/右键/快捷键/分类/编辑）。
- `frontend/src/annotation/core` 不 import 项目业务模块（可拷贝复用）。
- type-check 干净 + 上述 e2e 全过。
