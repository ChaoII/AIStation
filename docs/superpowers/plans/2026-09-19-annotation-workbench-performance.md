# 标注工作台性能优化（阶段一）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 通过 rAF 合帧、缓存画布测量、拖拽脱离深响应式三项改动，让标注工作台实时交互（拖动/平移/缩放/绘制预览）跟手、帧率提升。

**Architecture:** 全部改动集中在 `frontend/src/annotation/core/AnnotationWorkbench.vue`（单文件）。不改任务插件渲染/命中逻辑；只在工作台层引入 rAF 调度器、画布矩形缓存、拖拽副本（draftAnn）+ 每帧受控重绘。不改 SVG 渲染架构（Canvas 2D 留给阶段二）。

**Tech Stack:** Vue 3 `<script setup>` + `ref`/`shallowRef`/`computed`/`triggerRef` + `requestAnimationFrame` + `ResizeObserver`。

## Global Constraints

- 中文回复；提交信息 `fix(annotation): 中文描述`。
- 已知无关 type-check 报错存在于 `module_generator`/`module_monitor`；本项目只需保证 `src/annotation/` 无报错。
- 前端 dev 运行在 `:5180`（base `/web`），登录 `admin/123456`。
- 标注回归 e2e：`e2e/workbench.spec.ts`、`e2e/annotation-task-classes.spec.ts`、`e2e/annotation-history.spec.ts`（用 `pnpm exec playwright test <file> --reporter=line` 运行）。
- 最终验证：`pnpm run type-check` 对 `src/annotation/` 无报错 + 上述 e2e 全通过。
- 保留既有 `getCanvasEl()` 的懒查询缓存（`_canvasEl`），不要改它。

---

### Task 1: rAF 合帧调度——把 mousemove 处理降为每帧一次

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Consumes: 既有 `onMove(e: MouseEvent)`（第 1248 行）、`onMounted`/`onBeforeUnmount`（第 1610/1619 行）。
- Produces: `scheduleMove(e: MouseEvent)`（每帧只执行一次 `onMove`）；模块级 `pendingMove: MouseEvent | null` 与 `moveRafId: number`。

- [ ] **Step 1: 在 `onMove` 之前新增 rAF 调度器**

在 `function onMove(e: MouseEvent) {`（第 1248 行）之前插入：

```ts
let pendingMove: MouseEvent | null = null;
let moveRafId = 0;
function scheduleMove(e: MouseEvent) {
  pendingMove = e;
  if (moveRafId) return;
  moveRafId = requestAnimationFrame(() => {
    moveRafId = 0;
    const ev = pendingMove;
    pendingMove = null;
    if (ev) onMove(ev);
  });
}
```

- [ ] **Step 2: 把 mousemove 监听改绑到 `scheduleMove`**

第 1611 行：`window.addEventListener("mousemove", onMove);` 改为 `window.addEventListener("mousemove", scheduleMove);`

- [ ] **Step 3: 卸载时解绑并取消未决 rAF**

第 1621 行：`window.removeEventListener("mousemove", onMove);` 改为 `window.removeEventListener("mousemove", scheduleMove);`

并在 `onBeforeUnmount` 末尾（`unmounted = true;` 之后）加：

```ts
if (moveRafId) { cancelAnimationFrame(moveRafId); moveRafId = 0; }
pendingMove = null;
```

- [ ] **Step 4: 验证**

Run: `cd frontend; pnpm exec vue-tsc --noEmit --skipLibCheck 2>&1 | Select-String "annotation"` — Expected: 无输出（annotation 无报错）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "fix(annotation): mousemove 处理改为 rAF 合帧，每帧只执行一次"
```

---

### Task 2: 缓存画布测量，消除逐标注 getBoundingClientRect

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Consumes: 既有 `getCanvasEl()`（第 768 行）、`canvas`（`useAnnotationCanvas`）。
- Produces: 模块级 `canvasRect = { left, top, width, height }`、`rectTick: Ref<number>`、`measureCanvas(): void`、`canvasR()`（返回 `canvasRect`）。所有原本 `el.getBoundingClientRect()` 的读取改为读 `canvasR()`。

- [ ] **Step 1: 新增画布矩形缓存与测量函数**

在 `function getCanvasEl()`（第 768 行）之后插入：

```ts
const canvasRect = { left: 0, top: 0, width: 0, height: 0 };
const rectTick = ref(0);
function measureCanvas() {
  const el = getCanvasEl();
  if (!el) return;
  const r = el.getBoundingClientRect();
  canvasRect.left = r.left;
  canvasRect.top = r.top;
  canvasRect.width = r.width;
  canvasRect.height = r.height;
}
function canvasR() {
  return canvasRect;
}
```

- [ ] **Step 2: `toImagePoint` 改用缓存矩形**

第 776-779 行改为：

```ts
function toImagePoint(e: MouseEvent): { x: number; y: number } | null {
  const r = canvasR();
  if (!r.width || !r.height) return null;
  return canvas.containerToImage(e.clientX - r.left, e.clientY - r.top, r.width, r.height);
}
```

- [ ] **Step 3: `tagStyle` 改用缓存矩形并依赖 `rectTick`**

第 1442-1444 行：

```ts
  if (dw.value && dh.value) {
    void rectTick.value;
    const r = canvasR();
    const off = canvas.imageOffset(r.width, r.height);
```

并删除原来 `const el = getCanvasEl();` 与该分支的 `const r = el.getBoundingClientRect();`（保留函数开头的 `const el = getCanvasEl();` 可删除，因不再用 el）。

- [ ] **Step 4: `annScreenPos` 改用缓存矩形**

第 1423-1425 行改为：

```ts
function annScreenPos(ann: any) {
  if (!dw.value || !dh.value) return { x: 0, y: 0 };
  const r = canvasR();
  const off = canvas.imageOffset(r.width, r.height);
```

删除 `const el = getCanvasEl();` 与 `const r = el.getBoundingClientRect();`（第 1422-1424 行）。

- [ ] **Step 5: `onWheel` / `boxZoom` / `zoomAt` 改用缓存矩形**

`onWheel`（第 822-826 行）改为：

```ts
function onWheel(e: WheelEvent) {
  if (!cw.value || !ch.value) return;
  const r = canvasR();
  const cx = e.clientX - r.left;
  const cy = e.clientY - r.top;
  const factor = e.deltaY < 0 ? 1.1 : 0.9;
  zoomAt(factor, cx, cy);
}
```

`boxZoom`（第 831-835 行）改为：

```ts
function boxZoom(factor: number, clientX: number, clientY: number) {
  const r = canvasR();
  zoomAt(factor, clientX - r.left, clientY - r.top);
}
```

`zoomAt`（第 839-843 行）改为：

```ts
function zoomAt(factor: number, cx: number, cy: number) {
  if (!cw.value || !ch.value) return;
  const r = canvasR();
```

并删除上述三处 `const el = getCanvasEl();` / `const r = el.getBoundingClientRect();`。

- [ ] **Step 6: 挂载时测量并用 ResizeObserver 保持刷新**

在 `onMounted` 内、`init();` 之后加：

```ts
measureCanvas();
if (getCanvasEl()) {
  _resizeObserver = new ResizeObserver(() => {
    measureCanvas();
    rectTick.value++;
  });
  _resizeObserver.observe(getCanvasEl()!);
}
```

在模块级（`unmounted` 声明旁）加 `let _resizeObserver: ResizeObserver | null = null;`

在 `onBeforeUnmount` 末尾（`unmountCurrent` 前）加：

```ts
if (_resizeObserver) { _resizeObserver.disconnect(); _resizeObserver = null; }
```

- [ ] **Step 7: 验证**

Run: `cd frontend; pnpm exec vue-tsc --noEmit --skipLibCheck 2>&1 | Select-String "annotation"` — Expected: 无输出。

- [ ] **Step 8: 提交**

```bash
git add frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "fix(annotation): 缓存画布测量矩形，消除逐标注 getBoundingClientRect"
```

---

### Task 3: 拖拽期间脱离深响应式，每帧受控重绘

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Consumes: 既有 `dragState`（第 529 行）、`onMove` 的各拖拽子分支、`onUp`（第 1369 行）、`resetDrawingState`（第 786 行）、`store.markUnsaved()`、`pushHistory()`。
- Produces: 模块级 `draftAnn: ShallowRef<Annotation | null>`、`displayAnnotations: ComputedRef<Annotation[]>`、`draftOf(ann): Annotation`。模板中标注渲染（SVG 层 + HTML 标签层）改读 `displayAnnotations`。

- [ ] **Step 1: 新增 draftAnn / displayAnnotations / draftOf**

在 `let panState ... let dragState ...`（第 528-531 行）之后加：

```ts
const draftAnn = shallowRef<Annotation | null>(null);
const displayAnnotations = computed<Annotation[]>(() => {
  const d = draftAnn.value;
  if (!d) return store.annotations;
  return store.annotations.map((a) => (a.id === d.id ? d : a));
});
function draftOf(ann: Annotation): Annotation {
  const d = JSON.parse(JSON.stringify(ann));
  draftAnn.value = d;
  return d;
}
```

确保顶部从 `vue` 引入 `shallowRef`、`computed`、`triggerRef`（检查 `import { ... } from "vue"` 是否已含，缺则补）。

- [ ] **Step 2: 模板标注渲染改读 `displayAnnotations`**

第 51 行：`:annotations="store.annotations"`（plugin renderer）改为 `:annotations="displayAnnotations"`。

第 206 行：`v-for="a in store.annotations"`（HTML 标签层）改为 `v-for="a in displayAnnotations"`。

（第 223 行右栏 `:annotations="store.annotations"` 保持不变。）

- [ ] **Step 3: 各拖拽子状态启动时改用 draft**

把 `onCanvasDown`/各 handler 中每一处 `dragState = { type: ..., ann, ... }` 的 `ann` 参数替换为 `draftOf(ann)`。涉及行：第 1173、1185、1187、1199、1212、1234、1237、1246 行。

示例（第 1173 行）改为：

```ts
dragState = { type: "move", ann: draftOf(ann), handle: "", startX: e.clientX, startY: e.clientY, orig: JSON.parse(JSON.stringify(ann)) };
```

其余各行按同样规则把 `ann` 换成 `draftOf(ann)`（`orig` 仍为对原始 `ann` 的深拷贝）。

- [ ] **Step 4: onMove 各拖拽子分支改为改 draft 并 trigger，去掉逐次 markUnsaved**

在 `onMove` 末尾，所有 `store.markUnsaved();` 调用的各拖拽子分支里，把 `store.markUnsaved()` 删除，并在 `dragState` 修改完成的每个 `return` 前加一次 `triggerRef(draftAnn)`；同时把该分支内对 `dragState.ann` 的修改保留（`dragState.ann` 即 `draftAnn.value`，是普通对象）。

为减少重复，可在 `function onMove` 里、`if (dragState) {` 分支末尾统一加 `triggerRef(draftAnn);`（放在各子分支 return 之前）。

- [ ] **Step 5: onUp 写回 store、markUnsaved、pushHistory**

`onUp`（第 1402-1403 行）改为：

```ts
if (dragState) {
  const d = draftAnn.value;
  if (d) {
    const target = store.annotations.find((a) => a.id === d.id);
    if (target) Object.assign(target, d);
    store.markUnsaved();
    pushHistory();
  }
  draftAnn.value = null;
}
dragState = null;
```

- [ ] **Step 6: resetDrawingState 清空 draftAnn**

`resetDrawingState`（第 786 行起）开头加 `draftAnn.value = null;`。

- [ ] **Step 7: 验证**

Run: `cd frontend; pnpm exec vue-tsc --noEmit --skipLibCheck 2>&1 | Select-String "annotation"` — Expected: 无输出。

- [ ] **Step 8: 运行标注回归 e2e**

Run: `cd frontend; pnpm exec playwright test e2e/workbench.spec.ts e2e/annotation-task-classes.spec.ts e2e/annotation-history.spec.ts --reporter=line`
Expected: 5 passed。

- [ ] **Step 9: 提交**

```bash
git add frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "fix(annotation): 拖拽期间脱离深响应式，经 draft 副本每帧受控重绘"
```

---

## 自审检查

- **Spec 覆盖**：第 1 节（rAF）= Task 1；第 2 节（缓存测量）= Task 2；第 3 节（拖拽脱离深响应式）= Task 3。三者均对应 spec 三小节。
- **占位符**：无 TBD/TODO，所有改动含具体代码与行号。
- **类型一致**：`draftAnn`/`displayAnnotations`/`draftOf`/`canvasR`/`measureCanvas`/`rectTick`/`scheduleMove` 在各 Task 间命名一致。
