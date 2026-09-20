# 标注「创建流程」下沉（阶段 C）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把「创建新标注的绘制流程」从核心壳下沉到各任务插件，使新增任务类型只需新增 `tasks/<name>/` 目录 + 注册，无需改 `core/`。

**Architecture:** 每个插件新增 `tool: PluginTool`（绘制运行时：down/move/up/dblclick + 预览 state），并提供独立 `<Name>Preview.vue` 预览组件。核心壳改为按「当前激活工具是否属于当前插件」做通用派发，逐步删除各任务的 cURL 分支与 `use*Tool` import，最后清理。

**Tech Stack:** Vue 3 + TypeScript + Element Plus，Playwright e2e。

设计文档：`docs/superpowers/specs/2026-09-21-annotation-creation-sink-design.md`

## Global Constraints

- 所有对用户的说明、注释、提交信息用中文；提交格式 `feat(annotator): ...`。
- 预览组件模板**根节点必须为 `<g>`（SVG）**，因为壳把它们嵌入 `<AnnotationCanvas>` 的 SVG default slot 内；不得使用非 SVG 根。
- 预览/绘制颜色沿用现有（box 蓝 `#3b82f6`、rot 红 `#f56c6c`、kp 橙 `#e6a23c`、ocr 橙、seg 蓝），统一 `--el-*` 不适用（SVG 内固定即可，与现状一致）。
- `state` 为普通对象（字段是 `ref`），Preview 组件通过 props `{ state, cw, ch, zoom }` 读取，用 `.value`。
- 壳的通用派发逻辑：`const tool = plugin.value.tool; if (tool && currentTool.value === tool.name) { ... return; }`，未加 `tool` 的插件保持原 `currentTool` fallback 分支（保证增量子任务间不回归）。
- 新增/修改文件不得在 `core/` 中 import 业务模块；预览组件与 tool 一律放在 `tasks/<name>/` 下。
- 结束前运行 `npx vue-tsc --noEmit --skipLibCheck` 与 `npx eslint src/annotation`（确认无新增功能性错误），并跑相关 e2e。
- e2e 提示：El-Dropdown 菜单项真实类名为 `el-dropdown-menu__item`（`role="menuitem"`）；表格固定列克隆层会拦截 `.click()`，需用 `evaluate((el) => el.click())`。

---

### Task 0: 定义 PluginTool/DrawContext 接口 + 壳通用派发骨架

**Files:**
- Modify: `frontend/src/annotation/core/types.ts`
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Produces: `DrawContext`（`{ point?: Point; event: MouseEvent; classes?: any[]; selectedClassId?: number; visibility?: string }`）、`PluginTool`（`{ name; preview?; state?; down?; move?; up?; dblclick?; reset? }`，其中 `down/up/dblclick` 返回 `Annotation | null`），`AnnotationTaskPlugin.tool?: PluginTool`。
- Consumes: 无。

- [ ] **Step 1: types.ts 追加接口**

在 `frontend/src/annotation/core/types.ts` 的 `AnnotationInteraction` 之后追加：

```ts
/** 绘制运行上下文（壳在画布事件时传入） */
export interface DrawContext {
  /** 归一化图像坐标 */
  point?: Point;
  /** 原始鼠标事件 */
  event: MouseEvent;
  /** 当前任务类别（含 keypoint_names） */
  classes?: any[];
  /** 当前选中类别 id */
  selectedClassId?: number;
  /** 新增关键点的可见性（keypoint） */
  visibility?: string;
}

/** 任务绘制工具运行时（阶段 C 下沉） */
export interface PluginTool {
  /** 工具名（= tools[0].name），壳据此判断绘制模式 */
  name: string;
  /** 绘制激活时挂载的临时预览组件（SVG 根，用 <g>） */
  preview?: TaskCanvasRenderer;
  /** 绘制状态（字段为 ref），供 preview 读取 */
  state?: Record<string, any>;
  /** 按下：返回合法标注则壳 push（如 rotated_box 第 3 步 / ocr 第 2 点） */
  down?(ctx: DrawContext): Annotation | null;
  /** 移动：更新预览 */
  move?(ctx: DrawContext): void;
  /** 抬起：返回合法标注则壳 push */
  up?(ctx: DrawContext): Annotation | null;
  /** 双击：闭合多边形 / 进入包围盒 / OCR 闭合，返回标注则壳 push */
  dblclick?(ctx: DrawContext): Annotation | null;
  /** 切换工具/换图/清空时重置绘制状态 */
  reset?(): void;
}
```

`AnnotationTaskPlugin` 增加字段（在 `onDrag` 前）：
```ts
  /** 绘制工具运行时（阶段 C 下沉） */
  tool?: PluginTool;
```

- [ ] **Step 2: 壳加通用派发（onCanvasDown/onMove/onUp/onDblClick）**

在 `AnnotationWorkbench.vue` 中新增一个辅助提交函数（放在 `onDblClick` 附近）：

```ts
function commitCreated(created: Annotation | null): void {
  if (!created || !plugin.value.create(created)) return;
  created.class_id = selectedClassId.value ?? created.class_id;
  if (created.type === "Ocr") {
    pendingOcr = created;
    ocrInput.value = "";
    ocrInputVisible.value = true;
    return;
  }
  store.annotations.push(created);
  store.markUnsaved();
  pushHistory();
}
```

**onCanvasDown**（`currentTool === "zoom"` 分支之后，原 `if (currentTool.value === "box")` 绘制分支之前）插入：

```ts
  const tool = plugin.value.tool;
  if (tool && currentTool.value === tool.name) {
    const created = tool.down?.({
      point: p,
      event: e,
      classes: taskClasses.value,
      selectedClassId: selectedClassId.value,
      visibility: pendingKpVisibility.value,
    });
    if (created) commitCreated(created);
    return;
  }
```

**onMove**（`if (currentTool.value === "box" && drawStart)` 分支之前）插入：

```ts
  const tool = plugin.value.tool;
  if (tool && currentTool.value === tool.name) {
    tool.move?.({ point: ip, event: e, classes: taskClasses.value, selectedClassId: selectedClassId.value, visibility: pendingKpVisibility.value });
    return;
  }
```

**onUp**（`if (currentTool.value === "box" && drawStart)` 分支之前）插入：

```ts
  const tool = plugin.value.tool;
  if (tool && currentTool.value === tool.name) {
    const created = tool.up?.({ event: e });
    if (created) commitCreated(created);
    return;
  }
```

**onDblClick**（当前函数开始处，命中已有标注的 `if (hit)` 之后插入）：

```ts
  const tool = plugin.value.tool;
  if (tool && currentTool.value === tool.name) {
    const p = toImagePoint(e);
    const created = tool.dblclick?.({
      point: p ?? undefined,
      event: e,
      classes: taskClasses.value,
      selectedClassId: selectedClassId.value,
      visibility: pendingKpVisibility.value,
    });
    if (created) commitCreated(created);
    return;
  }
```

**模板挂载预览组件**（在 `<AnnotationCanvas>` 的 default slot 内、`plugin.renderer` 组件之后、`<line v-if="crossVisible" .../>` 之前）：

```html
<component
  v-if="plugin.tool && currentTool === plugin.tool.name && plugin.tool.preview"
  :is="plugin.tool.preview"
  :state="plugin.tool.state"
  :cw="cw"
  :ch="ch"
  :zoom="canvas.zoom.value"
/>
```

**切换工具 / 换图时重置**（在壳的 `currentTool` 定义附近加 watch，并在换图处理中调用）：

```ts
watch(currentTool, () => plugin.value.tool?.reset?.());
```

并在 `onImgLoad`（换图）与清空标注处理中调用 `plugin.value.tool?.reset?.()`（与既有 `drawStart = null` / `kpBoxDrafting.value = false` 等清理并列）。

- [ ] **Step 3: 校验编译**

Run: `cd frontend && npx vue-tsc --noEmit --skipLibCheck`
Expected: 无 annotation 相关错误（`pendingKpVisibility`/`pendingOcr`/`ocrInput`/`ocrInputVisible`/`taskClasses`/`selectedClassId` 均为既有变量，确认存在）。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/annotation/core/types.ts frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "feat(annotator): 定义 PluginTool 接口并给壳加通用绘制派发骨架"
```

---

### Task 1: detection 绘制流程下沉

**Files:**
- Modify: `frontend/src/annotation/tasks/detection/index.ts`
- Create: `frontend/src/annotation/tasks/detection/DetectionPreview.vue`
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`（删 box 绘制分支）

**Interfaces:**
- Consumes: `PluginTool`/`DrawContext`（Task 0）。
- Produces: `detectionPlugin.tool`（name="box"，state.preview，down/move/up/reset），`DetectionPreview` 组件。

- [ ] **Step 1: 创建 DetectionPreview.vue**

```vue
<template>
  <g v-if="state.preview.value">
    <rect
      :x="state.preview.value.x * cw"
      :y="state.preview.value.y * ch"
      :width="state.preview.value.w * cw"
      :height="state.preview.value.h * ch"
      fill="none"
      stroke="#3b82f6"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
  </g>
</template>
<script setup lang="ts">
defineProps<{ state: any; cw: number; ch: number; zoom: number }>();
</script>
```

- [ ] **Step 2: detection/index.ts 增加 tool**

在 `import { useDetectionTool } from "./useDetectionTool";`（若无则新增）并增加 `import { ref } from "vue";` 与 `import DetectionPreview from "./DetectionPreview.vue";`。在 `create(...)` 之后、`interaction` 之前加：

```ts
  tool: (() => {
    const det = useDetectionTool();
    const preview = ref<{ x: number; y: number; w: number; h: number } | null>(null);
    const s = det.startImg;
    return {
      name: "box",
      preview: DetectionPreview,
      state: { preview },
      down(ctx) {
        const p = ctx.point;
        if (!p) return null;
        det.onStart(p);
        preview.value = { x: p.x, y: p.y, w: 0, h: 0 };
        return null;
      },
      move(ctx) {
        const p = ctx.point;
        if (!p || !det.drawing.value || !s.value) return;
        preview.value = {
          x: Math.min(s.value.x, p.x),
          y: Math.min(s.value.y, p.y),
          w: Math.abs(p.x - s.value.x),
          h: Math.abs(p.y - s.value.y),
        };
      },
      up() {
        const pr = preview.value;
        const created = det.onMoveEnd(pr ? { x: pr.x + pr.w, y: pr.y + pr.h } : { x: 0, y: 0 });
        preview.value = null;
        return created;
      },
      reset() {
        det.drawing.value = false;
        preview.value = null;
      },
    };
  })(),
```

- [ ] **Step 3: 壳删除 box 绘制分支**

在 `AnnotationWorkbench.vue`：
- 删除 `onCanvasDown` 里 `if (currentTool.value === "box") { det.onStart(p); drawStart = p; preview.value = ...; }` 整个分支（保留后续 else if）。
- 删除 `onMove` 里 `if (currentTool.value === "box" && drawStart) { ... preview.value = ... }` 分支。
- 删除 `onUp` 里 `if (currentTool.value === "box" && drawStart) { ... det.onMoveEnd ... }` 分支。
- 删除模板中 box 预览 `<rect v-if="preview" .../>`（102 行附近，即蓝框）。
- 删除 `drawStart` 状态定义与 `import { useDetectionTool }` 与 `const det = useDetectionTool();`（若无其他引用）。
- 删除 `preview` ref 定义（若仅 box 用）。

并在文件内搜索 `det.` 确认无残留引用后再删。

- [ ] **Step 4: type-check + e2e**

Run: `npx vue-tsc --noEmit --skipLibCheck`；`npx eslint src/annotation`（无新增功能性错误）。
Run 检测任务 e2e（用现成 detection 工作台用例或编写 `e2e/_det_create.spec.ts` 验证「选框选框 → 拖拽 → 标注出现」）。expected: 标注能创建且可移动。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/tasks/detection frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "feat(annotator): detection 绘制流程下沉（tool+预览）"
```

---

### Task 2: rotatedBox 绘制流程下沉

**Files:**
- Modify: `frontend/src/annotation/tasks/rotatedBox/index.ts`
- Create: `frontend/src/annotation/tasks/rotatedBox/RotatedBoxPreview.vue`
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Consumes: `PluginTool`/`DrawContext`（Task 0）、`useRotatedTool` 的 `onStep/pt1/pt2/step` 与 `rotatedBoxFromEdgeAndPoint`。
- Produces: `rotatedBoxPlugin.tool`（name="rotated_box"，state={step,pt1,pt2,last,preview}，down/move/reset），`RotatedBoxPreview`。

- [ ] **Step 1: 创建 RotatedBoxPreview.vue**

```vue
<template>
  <g v-if="state.step.value > 0">
    <line
      v-if="state.pt1.value && state.last.value"
      :x1="state.pt1.value.x * cw"
      :y1="state.pt1.value.y * ch"
      :x2="state.last.value.x * cw"
      :y2="state.last.value.y * ch"
      stroke="#f56c6c"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
    <line
      v-if="state.pt1.value && state.pt2.value && state.last.value"
      :x1="state.pt2.value.x * cw"
      :y1="state.pt2.value.y * ch"
      :x2="state.last.value.x * cw"
      :y2="state.last.value.y * ch"
      stroke="#f56c6c"
      stroke-width="1"
      stroke-dasharray="2 2"
    />
    <circle
      v-if="state.pt1.value"
      :cx="state.pt1.value.x * cw"
      :cy="state.pt1.value.y * ch"
      r="4"
      fill="#fff"
      stroke="#f56c6c"
      stroke-width="1.5"
    />
    <circle
      v-if="state.pt2.value"
      :cx="state.pt2.value.x * cw"
      :cy="state.pt2.value.y * ch"
      r="4"
      fill="#fff"
      stroke="#f56c6c"
      stroke-width="1.5"
    />
    <rect
      v-if="state.preview.value"
      :x="state.preview.value.cx * cw - state.preview.value.width * cw / 2"
      :y="state.preview.value.cy * ch - state.preview.value.height * ch / 2"
      :width="state.preview.value.width * cw"
      :height="state.preview.value.height * ch"
      fill="none"
      stroke="#f56c6c"
      stroke-width="1.5"
      stroke-dasharray="4 3"
      :transform="`rotate(${state.preview.value.angle * 180 / Math.PI} ${state.preview.value.cx * cw} ${state.preview.value.cy * ch})`"
    />
  </g>
</template>
<script setup lang="ts">
defineProps<{ state: any; cw: number; ch: number; zoom: number }>();
</script>
```

- [ ] **Step 2: rotatedBox/index.ts 增加 tool**

新增 `import { ref } from "vue"`、`import RotatedBoxPreview from "./RotatedBoxPreview.vue";`、`import { useRotatedTool, rotatedBoxFromEdgeAndPoint } from "./useRotatedTool";`（确认已有）。在 `create(...)` 后加：

```ts
  tool: (() => {
    const rot = useRotatedTool();
    const last = ref<Point | null>(null);
    const preview = ref<any>(null);
    return {
      name: "rotated_box",
      preview: RotatedBoxPreview,
      state: { step: rot.step, pt1: rot.pt1, pt2: rot.pt2, last, preview },
      down(ctx) {
        const p = ctx.point;
        if (!p) return null;
        last.value = p;
        const created = rot.onStep(p);
        if (created) preview.value = null;
        return created;
      },
      move(ctx) {
        const p = ctx.point;
        if (!p) return;
        last.value = p;
        if (rot.pt1.value && rot.pt2.value) {
          const g = rotatedBoxFromEdgeAndPoint(rot.pt1.value, rot.pt2.value, p);
          if (g) preview.value = { ...g };
        }
      },
      reset() {
        last.value = null;
        preview.value = null;
      },
    };
  })(),
```

（需在 `index.ts` 顶部 `import type { ..., Point }` 确保 `Point` 类型可用。）

- [ ] **Step 3: 壳删除 rotated_box 绘制分支**

- 删除 `onCanvasDown` 里 `else if (currentTool.value === "rotated_box") { rbLast = p; const created = rot.onStep(p); ... }`。
- 删除 `onMove` 里 `if (currentTool.value === "rotated_box") { ... rbLast = p; rbPreview ... }`。
- 删除 `onUp` 里 `if (currentTool.value === "rotated_box") { rbPreview.value = null; return; }`。
- 删除模板中 `<rect v-if="rbPreview" ...>` 与 `<template v-if="currentTool === 'rotated_box' && rot.step.value > 0">...`（112-213 区域）。
- 删除 `rbLast`/`rbPreview` 状态定义、`import { ... rotatedBoxFromEdgeAndPoint }`（不再用）、`const rot = useRotatedTool();`。
- 确认 `rot.` 无残留引用再删。

- [ ] **Step 4: type-check + e2e**（rotatedBox 任务绘制三步验证）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/tasks/rotatedBox frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "feat(annotator): rotatedBox 绘制流程下沉（tool+预览）"
```

---

### Task 3: segmentation 绘制流程下沉

**Files:**
- Modify: `frontend/src/annotation/tasks/segmentation/index.ts`
- Create: `frontend/src/annotation/tasks/segmentation/SegmentPreview.vue`
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Consumes: `PluginTool`/`DrawContext`、`useSegmentTool`。
- Produces: `segmentationPlugin.tool`（name="polygon"，state.points，down/move/dblclick/reset），`SegmentPreview`。

- [ ] **Step 1: 创建 SegmentPreview.vue**

```vue
<template>
  <g v-if="state.points.value.length">
    <polyline
      :points="pts"
      fill="none"
      stroke="#3b82f6"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
    <circle
      v-for="(pt, i) in state.points.value"
      :key="'pp' + i"
      :cx="pt.x * cw"
      :cy="pt.y * ch"
      r="3"
      fill="#fff"
      stroke="#3b82f6"
      stroke-width="1"
    />
    <circle
      :cx="state.points.value[0].x * cw"
      :cy="state.points.value[0].y * ch"
      r="4"
      fill="none"
      stroke="#3b82f6"
      stroke-width="1.5"
    />
  </g>
</template>
<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ state: any; cw: number; ch: number; zoom: number }>();
const pts = computed(() =>
  props.state.points.value
    .map((p: any, i: number) => `${i === 0 ? "M" : "L"}${p.x * props.cw},${p.y * props.ch}`)
    .join(" ") + " Z"
);
</script>
```

- [ ] **Step 2: segmentation/index.ts 增加 tool**

新增 `import { useSegmentTool } from "./useSegmentTool";`（若无）、`import SegmentPreview from "./SegmentPreview.vue";`。在 `create(...)` 后加：

```ts
  tool: (() => {
    const seg = useSegmentTool();
    return {
      name: "polygon",
      preview: SegmentPreview,
      state: { points: seg.points },
      down(ctx) {
        const p = ctx.point;
        if (p) seg.addPoint(p);
        return null;
      },
      dblclick(ctx) {
        return seg.closePolygon();
      },
      reset() {
        seg.points.value = [];
      },
    };
  })(),
```

- [ ] **Step 3: 壳删除 polygon 绘制分支**

- 删除 `onCanvasDown` 里 `else if (currentTool.value === "polygon") { seg.addPoint(p); }`。
- 删除 `onDblClick` 里 `if (currentTool.value === "polygon") { const created = seg.closePolygon(); ... }`。
- 删除模板中 `<polyline v-if="currentTool === 'polygon' && seg.points.value.length">`、`<circle v-for ... currentTool === 'polygon' ? seg.points.value : []">`、首点提示 circle（125-142、215-223）。
- 删除壳中 `polyPts` computed（若仅 polygon 用）、`import { useSegmentTool }`、`const seg = useSegmentTool();`、`import { useSegmentTool ... }`。
- 确认 `seg.` 无残留再删。

- [ ] **Step 4: type-check + e2e**（polygon 逐点+双击闭合）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/tasks/segmentation frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "feat(annotator): segmentation 绘制流程下沉（tool+预览）"
```

---

### Task 4: ocr 绘制流程下沉

**Files:**
- Modify: `frontend/src/annotation/tasks/ocr/index.ts`
- Create: `frontend/src/annotation/tasks/ocr/OcrPreview.vue`
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Consumes: `PluginTool`/`DrawContext`、`useOcrTool`。
- Produces: `ocrPlugin.tool`（name="ocr"，state.mode/quadPoints，down/dblclick/reset），`OcrPreview`。

- [ ] **Step 1: 创建 OcrPreview.vue**

```vue
<template>
  <g v-if="state.mode.value === 'quad' && state.quadPoints.value.length">
    <polyline
      :points="pts"
      fill="none"
      stroke="#e6a23c"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
    <circle
      v-for="(pt, i) in state.quadPoints.value"
      :key="'oq' + i"
      :cx="pt.x * cw"
      :cy="pt.y * ch"
      r="3"
      fill="#fff"
      stroke="#e6a23c"
      stroke-width="1"
    />
  </g>
</template>
<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{ state: any; cw: number; ch: number; zoom: number }>();
const pts = computed(() =>
  props.state.quadPoints.value
    .map((p: any) => `${p.x * props.cw},${p.y * props.ch}`)
    .join(" ")
);
</script>
```

- [ ] **Step 2: ocr/index.ts 增加 tool**

新增 `import { useOcrTool } from "./useOcrTool";`、`import OcrPreview from "./OcrPreview.vue";`。在 `create(...)` 后加：

```ts
  tool: (() => {
    const ocr = useOcrTool();
    return {
      name: "ocr",
      preview: OcrPreview,
      state: { mode: ocr.mode, quadPoints: ocr.quadPoints },
      down(ctx) {
        const p = ctx.point;
        if (!p) return null;
        if (ocr.mode.value === "quad") {
          ocr.addQuadPoint(p);
          return null;
        }
        return ocr.onPoint(p);
      },
      dblclick(ctx) {
        if (ocr.mode.value === "quad") return ocr.closeQuad();
        return null;
      },
      reset() {
        ocr.reset();
      },
    };
  })(),
```

（注：`ocr.reset` 已存在于 useOcrTool。）

- [ ] **Step 3: 壳删除 ocr 绘制分支**

- 删除 `onCanvasDown` 里 `else if (currentTool.value === "ocr") { if (ocr.mode.value === "quad") { ocr.addQuadPoint(p); } else { const created = ocr.onPoint(p); ... } }`。
- 删除 `onDblClick` 里 `else if (currentTool.value === "ocr" && ocr.mode.value === "quad") { ... }`。
- 删除模板中 `<polyline v-if="currentTool === 'ocr' && ocr.mode.value === 'quad' ...">`、quad 点 circle（153-172）。
- 删除壳中 `ocrQuadPts` computed、`import { useOcrTool }`、`const ocr = useOcrTool();`。
- **保留** Ocr 文本弹窗相关状态与 `confirmOcr`/`pendingOcr`/`ocrInput`/`ocrInputVisible`（该弹窗留壳，由 `commitCreated` 触发）。确认 `ocr.` 无残留（弹窗流程不引用 `ocr.`）再删。

- [ ] **Step 4: type-check + e2e**（OCR 矩形/四边形绘制 → 弹窗 → 确认后出现标注）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/tasks/ocr frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "feat(annotator): ocr 绘制流程下沉（tool+预览）"
```

---

### Task 5: keypoint 绘制流程下沉

**Files:**
- Modify: `frontend/src/annotation/tasks/keypoint/index.ts`
- Create: `frontend/src/annotation/tasks/keypoint/KeypointPreview.vue`
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Consumes: `PluginTool`/`DrawContext`、`useKeypointTool`。
- Produces: `keypointPlugin.tool`（name="keypoint"，state.pending/boxStart/boxEnd/boxDrafting，down/dblclick/up/reset），`KeypointPreview`。

- [ ] **Step 1: 创建 KeypointPreview.vue**

```vue
<template>
  <g>
    <rect
      v-if="state.boxDrafting.value && state.boxStart.value && state.boxEnd.value"
      :x="Math.min(state.boxStart.value.x, state.boxEnd.value.x) * cw"
      :y="Math.min(state.boxStart.value.y, state.boxEnd.value.y) * ch"
      :width="Math.abs(state.boxEnd.value.x - state.boxStart.value.x) * cw"
      :height="Math.abs(state.boxEnd.value.y - state.boxStart.value.y) * ch"
      fill="none"
      stroke="#e6a23c"
      stroke-width="1.5"
      stroke-dasharray="4 3"
    />
    <circle
      v-for="(pt, i) in state.pending.value"
      :key="'kp' + i"
      :cx="pt.x * cw"
      :cy="pt.y * ch"
      r="4"
      fill="none"
      stroke="#e6a23c"
      stroke-width="1.5"
    />
  </g>
</template>
<script setup lang="ts">
defineProps<{ state: any; cw: number; ch: number; zoom: number }>();
</script>
```

- [ ] **Step 2: keypoint/index.ts 增加 tool**

在 `create(...)` 后、`interaction` 前加：

```ts
  tool: (() => {
    const kp = useKeypointTool();
    const boxDrafting = ref(false);
    return {
      name: "keypoint",
      preview: KeypointPreview,
      state: { pending: kp.pending, boxStart: kp.boxStart, boxEnd: kp.boxEnd, boxDrafting },
      down(ctx) {
        const p = ctx.point;
        if (!p) return null;
        if (kp.boxMode.value) {
          kp.setBoxStart(p);
          boxDrafting.value = true;
          return null;
        }
        const kpNames = ctx.classes?.find((c) => c.id === ctx.selectedClassId)?.keypoint_names || [];
        kp.setNames(kpNames);
        kp.addPoint(p, ctx.visibility ?? "Visible");
        return null;
      },
      move(ctx) {
        const p = ctx.point;
        if (boxDrafting.value && p) kp.updateBox(p);
      },
      up() {
        if (!boxDrafting.value) return null;
        boxDrafting.value = false;
        return kp.build();
      },
      dblclick() {
        kp.beginBox();
        return null;
      },
      reset() {
        boxDrafting.value = false;
        kp.reset?.();
      },
    };
  })(),
```

需在 `index.ts` 顶部新增 `import { ref } from "vue";`、`import KeypointPreview from "./KeypointPreview.vue";`、`import { useKeypointTool } from "./useKeypointTool";`（若无）。注意 `useKeypointTool` 无 `reset` 方法——若调用需在 tool.reset 里自行清理：可改为 `kp.pending.value = []; kp.boxMode.value = false; kp.boxStart.value = null; kp.boxEnd.value = null; boxDrafting.value = false;`（替代 `kp.reset?.()`）。

- [ ] **Step 3: 壳删除 keypoint 绘制分支**

- 删除 `onCanvasDown` 里 `else if (currentTool.value === "keypoint") { ... }` 分支。
- 删除 `onMove` 里 `if (currentTool.value === "keypoint" && kpBoxDrafting.value) { kp.updateBox(p); return; }`。
- 删除 `onUp` 里 `if (currentTool.value === "keypoint" && kpBoxDrafting.value) { ... kp.build() ... }`。
- 删除 `onDblClick` 里 `else if (currentTool.value === "keypoint") { kp.beginBox(); }`。
- 删除模板中 kp 预览 rect 与点位 circle（114-124、143-152）。
- 删除 `kpBoxDrafting` 状态、`import { useKeypointTool }`、`const kp = useKeypointTool();`。
- 确认 `kp.` 无残留（编辑弹窗内的 `kp.name`/`kp.visibility` 若来自同一变量需保留——确认编辑弹窗用的是 `editForm` 而非 `kp`，若确为 `kp` 则保留该引用，仅删绘制相关）。

- [ ] **Step 4: type-check + e2e**（keypoint 布点 + 双击框选）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/tasks/keypoint frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "feat(annotator): keypoint 绘制流程下沉（tool+预览）"
```

---

### Task 6: 壳清理与全量回归

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`
- Modify: `docs/superpowers/specs/2026-09-21-annotation-creation-sink-design.md`（补执行记录）

**Interfaces:**
- Consumes: 全部插件 `tool` 已就绪（Task 1-5）。
- Produces: 清理后的壳（删除全部绘制 fallback 分支、冗余状态/import）。

- [ ] **Step 1: 确认全部插件已提供 tool**

确认每个任务的 `plugin.tool` 均已定义；确认壳中 `isDrawing`/通用派发已覆盖全部 5 类工具。

- [ ] **Step 2: 清理残留**

- 删除壳中仍存在的任何 `currentTool.value === "box"/"rotated_box"/"polygon"/"keypoint"/"ocr"` 绘制分支（本应在 Task 1-5 逐步删除，此处兜底）。
- 确认模板中不再有按 `currentTool` 渲染的预览图形（删除任何遗留 `<template v-if="currentTool ...">`、`v-for ... currentTool ...`）。
- 删除所有不再使用的 `use*Tool` import、对应的 `const xxx = use*Tool();`、`drawStart`/`preview`/`rbLast`/`rbPreview`/`kpBoxDrafting`/`polyPts`/`ocrQuadPts` 等仅绘制用状态。
- 校验 `tagStyle`/`onMove` 中 `dragState` 相关逻辑未受波及。
- 保留：`selectedClassId`、`pendingOcr`/`ocrInput`/`ocrInputVisible`/`confirmOcr`、编辑弹窗相关、`pendingKpVisibility`。

- [ ] **Step 3: 全量校验**

Run: `npx vue-tsc --noEmit --skipLibCheck`
Run: `npx eslint src/annotation`
Run: 六类任务工作台 e2e 全量回归（`npx playwright test workbench annotation-history annotation-task-classes collaboration` 及各自创建用例），确认无回归。

- [ ] **Step 4: 更新设计文档**

在 `docs/superpowers/specs/2026-09-21-annotation-creation-sink-design.md` 追加「阶段 C 执行记录」小节，记录各任务下沉、验证结果。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/core frontend/src/annotation/tasks docs/superpowers/specs/2026-09-21-annotation-creation-sink-design.md
git commit -m "refactor(annotator): 壳清理并全量回归（创建流程全部下沉插件）"
```

---

## 自查备注

- **down 返回 Annotation|null**：覆盖 rotated_box 第 3 步与 ocr 第 2 点产生标注的情况（原壳在这两处 `onCanvasDown` 内 push）。
- **Ocr 文本弹窗留壳**：`commitCreated` 对 `type === "Ocr"` 不立即 push，而是设 `pendingOcr` + 弹窗，由 `confirmOcr` 确认后 push（保留原行为）。
- **keypoint 依赖壳的类别/可见性**：通过 `DrawContext.classes/selectedClassId/visibility` 传入 tool，避免 tool 依赖壳全局。
- 各 Task 逐类下沉时，未加 tool 的插件仍走壳原 fallback 分支，保证增量不回归；Task 6 兜底清理。
