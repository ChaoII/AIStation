# 标注工作台组件化 · 阶段 0（骨架 + detection 插件）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 `frontend/src/annotation/` 组件库骨架（core 通用层 + `defineAnnotationTask` 插件接口），并把 **detection（矩形框）** 任务迁移为第一个任务插件，行为与重构前完全一致。

**Architecture:** 骨架（画布/状态/标签渲染/工作台壳）+ 任务插件（每个任务一个文件夹，注册 `defineAnnotationTask`）。框架只负责通用能力，任务层负责几何/编辑/渲染。

**Tech Stack:** Vue 3 + TypeScript + Element Plus + Pinia + Vite；e2e 用 Playwright（复用现有 `e2e/workbench.spec.ts` 作为行为回归基线）。

## Global Constraints

- 复用边界：仅前端；后端 `module_annotation` 接口与数据结构**不变**。
- `frontend/src/annotation/` 不得 import 本项目内部业务模块，保证可拷贝复用。
- 保持与重构前**完全一致的行为**（同一后端接口、同一 `annotation_data` 格式、同一交互）。
- 迁移采用分阶段渐进；本计划只做阶段 0。
- 代码/提交信息用中文；e2e 用现有的 `workbench.spec.ts`、`annotation-task-classes.spec.ts`、`annotation-history.spec.ts` 做回归。
- 标签背景保持确定性：宽高按文字实际渲染 `getBBox()`+边距，同步触发，不引入异步跳变。

## 文件结构（阶段 0 锁定）

```
frontend/src/annotation/
  index.ts                          # 公共 API 出口
  core/
    AnnotationWorkbench.vue         # 工作台壳（继承现有 index.vue 的壳层）
    AnnotationCanvas.vue            # 画布容器（缩放/平移/容器相对坐标）
    AnnotationToolbar.vue           # 通用工具 + 任务工具（来自插件）
    AnnotationLabelRenderer.vue     # 通用标签渲染（确定性背景）
    useAnnotationCanvas.ts          # 画布 hook：缩放/平移/坐标换算
    useAnnotationStore.ts           # 标注状态（Pinia）
    types.ts                        # 坐标/标注对象/插件接口类型
  tasks/
    detection/
      index.ts                      # defineAnnotationTask({ name:'detection', ... })
      DetectionCanvas.vue           # 渲染 AxisAlignedBox + 手柄
      useDetectionTool.ts           # 矩形绘制/拖拽/缩放/校验
```

> 说明：为控制范围与风险，阶段 0 先**新增并并行**这套骨架与 detection 插件，跑通 e2e；不立即删 `views/.../annotation/index.vue`（阶段 5 再切换并归档）。骨架先只承载 detection，其余 5 类仍走旧文件，验证接口合理后再逐类迁移。

---

### Task 1: 目录骨架 + 类型定义

**Files:**
- Create: `frontend/src/annotation/core/types.ts`
- Create: `frontend/src/annotation/index.ts`（先只导出 types，后续任务补导出）

**Interfaces:**
- Produces: 类型 `Annotation`、`TaskShapeType`、`AnnotationTaskPlugin`、`ToolDefinition`、`Point`、`BoxRect`。

- [ ] **Step 1: 创建 `core/types.ts`**

```ts
export type TaskShapeType =
  | "AxisAlignedBox" | "RotatedBox" | "Polygon"
  | "Keypoint" | "Ocr" | "Classification";

export interface Point { x: number; y: number }

export interface Annotation {
  id: string;
  type: TaskShapeType;
  class_id: number;
  [key: string]: any;
}

export interface ToolDefinition {
  name: string;
  label: string;
  title: string;
}

export interface AnnotationTaskPlugin {
  name: string;                 // 'detection'
  label: string;                // '目标检测'
  color: string;                // 'primary' | 'warning' | ... (el-tag 类型)
  renderer: any;                // Vue 渲染组件
  tools: ToolDefinition[];      // 专属工具，如 [{ name:'box', label:'框选', title:'矩形框' }]
  create(shape: Annotation): boolean;  // 几何校验
  onDrag?(ctx: any, handle: string): void;
}
```

- [ ] **Step 2: 创建 `index.ts`**

```ts
export * from "./core/types";
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/annotation
git commit -m "feat(annotation): 组件库骨架与任务插件类型定义"
```

---

### Task 2: 标注状态 store（Pinia 化）

**Files:**
- Create: `frontend/src/annotation/core/useAnnotationStore.ts`
- Test: 复用现有 `e2e/workbench.spec.ts` 行为回归（阶段 0 先用 store 承载状态，验证字段与旧版一致）

**Interfaces:**
- Consumes: `Annotation`（Task 1）
- Produces: `useAnnotationStore()`，暴露 `annotations`、`selectedAnnotationId`、`taskId`、`images`、`unsaved`、`set*` / `clear*` 方法。

- [ ] **Step 1: 创建 `useAnnotationStore.ts`**

```ts
import { defineStore } from "pinia";
import type { Annotation } from "./types";

export const useAnnotationStore = defineStore("annotationWorkbench", {
  state: () => ({
    taskId: 0,
    annotations: [] as Annotation[],
    selectedAnnotationId: "" as string,
    images: [] as any[],
    currentImageIndex: 0,
    unsaved: false,
  }),
  getters: {
    selectedAnnotation(state): Annotation | null {
      return state.annotations.find((a) => a.id === state.selectedAnnotationId) ?? null;
    },
  },
  actions: {
    reset() {
      this.annotations = [];
      this.selectedAnnotationId = "";
      this.unsaved = false;
    },
    markUnsaved() { this.unsaved = true; },
  },
});
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/annotation/core/useAnnotationStore.ts
git commit -m "feat(annotation): 标注状态 store(Pinia)"
```

---

### Task 3: 画布 hook + 画布容器

**Files:**
- Create: `frontend/src/annotation/core/useAnnotationCanvas.ts`
- Create: `frontend/src/annotation/core/AnnotationCanvas.vue`

**Interfaces:**
- Consumes: `Point`（Task 1）
- Produces: `useAnnotationCanvas()` 返回 `{ cw, ch, zoom, pan, dw, dh, mouseToImage, svgViewBox, svgStyle }`；`AnnotationCanvas.vue` 提供 `<svg :viewBox>` 渲染容器与鼠标事件透传。

- [ ] **Step 1: 创建 `useAnnotationCanvas.ts`**

```ts
import { ref } from "vue";
export function useAnnotationCanvas() {
  const cw = ref(0);   // 图像自然宽(px)
  const ch = ref(0);   // 图像自然高(px)
  const dw = ref(0);   // 图像显示宽(px)
  const dh = ref(0);   // 图像显示高(px)
  const zoom = ref(1);
  const panX = ref(0);
  const panY = ref(0);
  const svgViewBox = () => `0 0 ${cw.value} ${ch.value}`;
  const svgStyle = () => ({
    width: dw.value + "px",
    height: dh.value + "px",
    transform: `translate(-50%,-50%) translate(${panX.value}px,${panY.value}px)`,
  });
  function setImageSize(w: number, h: number) { cw.value = w; ch.value = h; }
  function setDisplaySize(w: number, h: number) { dw.value = w; dh.value = h; }
  function fitZoom(containerW: number, containerH: number) {
    if (!cw.value || !ch.value) return;
    zoom.value = Math.min(containerW / cw.value, containerH / ch.value, 3);
    dw.value = cw.value * zoom.value;
    dh.value = ch.value * zoom.value;
  }
  // 容器相对坐标 → 图像归一化 [0,1]
  function containerToImage(cx: number, cy: number, rectLeft: number, rectTop: number) {
    const imgL = rectLeft + rectLeftOffset();
    // 简化：占位，阶段 0 迁移时以旧文件 mouseToImage 为准
    return { x: 0, y: 0 } as Point;
  }
  function rectLeftOffset() { return 0; }
  return { cw, ch, dw, dh, zoom, panX, panY, svgViewBox, svgStyle, setImageSize, setDisplaySize, fitZoom, containerToImage };
}
```

- [ ] **Step 2: 创建 `AnnotationCanvas.vue`**

```vue
<template>
  <div ref="wrap" class="annotation-canvas" :style="{ cursor }">
    <img v-if="imgUrl" :src="imgUrl" class="ann-img" :style="svgStyle" @load="onImgLoad" />
    <svg v-if="imageLoaded" class="ann-svg" :style="svgStyle" :viewBox="viewBox">
      <slot />
    </svg>
  </div>
</template>
<script setup lang="ts">
import { ref, computed } from "vue";
import { useAnnotationCanvas } from "./useAnnotationCanvas";
const props = defineProps<{ imgUrl: string; imageLoaded: boolean; cursor?: string }>();
const emit = defineEmits<{ (e: "img-load", w: number, h: number): void }>();
const wrap = ref<HTMLElement | null>(null);
const canvas = useAnnotationCanvas();
const viewBox = computed(() => canvas.svgViewBox());
const svgStyle = computed(() => canvas.svgStyle());
function onImgLoad(e: Event) {
  const el = e.target as HTMLImageElement;
  canvas.setImageSize(el.naturalWidth, el.naturalHeight);
  canvas.setDisplaySize(el.naturalWidth, el.naturalHeight);
  const r = wrap.value?.getBoundingClientRect();
  if (r) canvas.fitZoom(r.width, r.height);
  emit("img-load", el.naturalWidth, el.naturalHeight);
}
</script>
```

> 注：阶段 0 的坐标换算（`containerToImage`）先做占位，真正的换算细节在 Task 5 迁移 detection 时按旧文件 `mouseToImage` 逻辑补全。为保证可运行，`containerToImage` 暂不抛错。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/annotation/core
git commit -m "feat(annotation): 画布 hook 与画布容器组件"
```

---

### Task 4: 通用标签渲染（确定性背景）

**Files:**
- Create: `frontend/src/annotation/core/AnnotationLabelRenderer.vue`

**Interfaces:**
- Consumes: `Annotation`（Task 1）
- Produces: 接收 `{ ann, cw, ch, label, color, fontSize, tagH }`，渲染文字 + 背景 rect（背景宽高 = 文字同步 `getBBox()` + 边距），并暴露 `labelTagH()`。

- [ ] **Step 1: 创建 `AnnotationLabelRenderer.vue`**

```vue
<template>
  <g class="ann-label">
    <rect
      :x="labelX"
      :y="labelY"
      :width="w + 8"
      :height="h + 4"
      :fill="color" :stroke="color" stroke-width="0.5" rx="1"
      vector-effect="non-scaling-stroke"
    />
    <text
      :x="labelX + 2" :y="baseY"
      fill="#fff" font-weight="500" text-anchor="start"
      font-family="Microsoft YaHei,sans-serif"
      :font-size="fontSize" dominant-baseline="text-after-edge"
    >{{ label }}</text>
  </g>
</template>
<script setup lang="ts">
import { ref, watch, onMounted } from "vue";
const props = defineProps<{
  labelX: number; baseY: number; label: string; color: string;
  fontSize: number; tagH: number;
}>();
const w = ref(0); const h = ref(0);
function measure() {
  // 同步读取该文字实际 bbox，保证背景必然包住文字
  const el = (document.querySelector(".ann-label text.det-label") ||
    document.querySelector(".ann-label text")) as SVGTextElement | null;
  if (!el) return;
  try { const b = el.getBBox(); if (b.width > 0) { w.value = b.width; h.value = b.height; } } catch {}
}
onMounted(() => measure());
</script>
```

> 注：阶段 0 的 measure 用 document 查询为简化占位；迁移检测时按旧 `measureLabelRects` 以 `.ann-label text` 为准并去掉 100ms 异步。

- [ ] **Step 2: 提交**

```bash
git add frontend/src/annotation/core/AnnotationLabelRenderer.vue
git commit -m "feat(annotation): 通用标签渲染(确定性背景)"
```

---

### Task 5: detection 任务插件（渲染 + 绘制 + 编辑 + 校验）

**Files:**
- Create: `frontend/src/annotation/tasks/detection/index.ts`
- Create: `frontend/src/annotation/tasks/detection/DetectionCanvas.vue`
- Create: `frontend/src/annotation/tasks/detection/useDetectionTool.ts`

**Interfaces:**
- Consumes: `AnnotationTaskPlugin`、`Annotation`、`Point`（Task 1）、`useAnnotationCanvas`（Task 3）、`AnnotationLabelRenderer`（Task 4）
- Produces: `detectionPlugin: AnnotationTaskPlugin`，其 `renderer` 为 `DetectionCanvas.vue`，`tools` 为 `[{ name:'box', label:'框选', title:'矩形框' }]`，`create()` 校验零面积/越界。

- [ ] **Step 1: 创建 `useDetectionTool.ts`**（矩形框的绘制/拖拽/缩放手势，迁移自旧文件 box 逻辑）

```ts
import { ref } from "vue";
import type { Annotation, Point } from "../../core/types";
export function useDetectionTool() {
  const drawing = ref(false);
  const startImg = ref<Point | null>(null);
  function onStart(p: Point) { drawing.value = true; startImg.value = p; }
  function onMoveEnd(p: Point): Annotation | null {
    if (!drawing.value || !startImg.value) return null;
    drawing.value = false;
    const s = startImg.value;
    if (Math.abs(p.x - s.x) < 0.005 || Math.abs(p.y - s.y) < 0.005) return null;
    return {
      id: crypto.randomUUID(), type: "AxisAlignedBox", class_id: 0,
      x1: Math.min(s.x, p.x), y1: Math.min(s.y, p.y),
      x2: Math.max(s.x, p.x), y2: Math.max(s.y, p.y),
    };
  }
  // 拖拽移动：按 handle 移动/缩放到归一化坐标（迁移自旧 onMouseMove resize/move）
  function onDrag(ann: Annotation, handle: string, dx: number, dy: number) {
    const o = JSON.parse(JSON.stringify(ann));
    if (handle.includes("l")) ann.x1 = Math.max(0, Math.min(o.x2 - 0.01, o.x1 + dx));
    if (handle.includes("r")) ann.x2 = Math.min(1, Math.max(o.x1 + 0.01, o.x2 + dx));
    if (handle.includes("t")) ann.y1 = Math.max(0, Math.min(o.y2 - 0.01, o.y1 + dy));
    if (handle.includes("b")) ann.y2 = Math.min(1, Math.max(o.y1 + 0.01, o.y2 + dy));
  }
  return { drawing, onStart, onMoveEnd, onDrag };
}
```

- [ ] **Step 2: 创建 `DetectionCanvas.vue`**（渲染 AxisAlignedBox + 手柄 + 标签）

```vue
<template>
  <g v-for="ann in annotations" :key="ann.id" :data-ann-id="ann.id">
    <rect
      :x="ann.x1 * cw" :y="ann.y1 * ch"
      :width="(ann.x2 - ann.x1) * cw" :height="(ann.y2 - ann.y1) * ch"
      :stroke="color(ann)" :stroke-width="ann.id === selectedId ? 2 : 1.5"
      :fill="ann.id === selectedId ? color(ann) + '28' : 'none'"
      vector-effect="non-scaling-stroke" @mousedown.stop.prevent="$emit('ann-down', $event, ann)"
    />
    <template v-if="ann.id === selectedId">
      <rect v-for="h in handles" :key="h" class="handle"
        :x="handlePos(ann, h).x - 4" :y="handlePos(ann, h).y - 4"
        width="8" height="8" fill="#fff" stroke="#1a1a1a" stroke-width="1.5"
        :data-handle="h" vector-effect="non-scaling-stroke" />
    </template>
    <AnnotationLabelRenderer
      :label-x="ann.x1 * cw" :base-y="ann.y1 * ch - 2"
      :label="clsName(ann)" :color="color(ann)" :font-size="fontSize" :tag-h="tagH" />
  </g>
</template>
<script setup lang="ts">
import { computed } from "vue";
import type { Annotation } from "../../core/types";
import AnnotationLabelRenderer from "../../core/AnnotationLabelRenderer.vue";
const props = defineProps<{ annotations: Annotation[]; cw: number; ch: number; selectedId: string; color: (a: Annotation) => string; clsName: (a: Annotation) => string; fontSize: number; tagH: number; }>();
const emit = defineEmits<{ (e: "ann-down", ev: MouseEvent, ann: Annotation): void }>();
const handles = ["tl", "tr", "bl", "br"];
function handlePos(a: Annotation, h: string) {
  const x = h.includes("l") ? a.x1 : a.x2, y = h.includes("t") ? a.y1 : a.y2;
  return { x: x * props.cw, y: y * props.ch };
}
</script>
```

- [ ] **Step 3: 创建 `tasks/detection/index.ts`**

```ts
import type { AnnotationTaskPlugin, Annotation } from "../../core/types";
import DetectionCanvas from "./DetectionCanvas.vue";
export const detectionPlugin: AnnotationTaskPlugin = {
  name: "detection",
  label: "目标检测",
  color: "primary",
  renderer: DetectionCanvas,
  tools: [{ name: "box", label: "框选", title: "矩形框" }],
  create(shape: Annotation): boolean {
    if (shape.type !== "AxisAlignedBox") return false;
    return !(shape.x2 <= shape.x1 || shape.y2 <= shape.y1 || shape.x1 < 0 || shape.y1 < 0 || shape.x2 > 1 || shape.y2 > 1);
  },
};
```

- [ ] **Step 4: 在 `index.ts` 导出插件**

```ts
export * from "./core/types";
export { default as AnnotationWorkbench } from "./core/AnnotationWorkbench.vue";
export { detectionPlugin } from "./tasks/detection";
export { useAnnotationCanvas } from "./core/useAnnotationCanvas";
export { useAnnotationStore } from "./core/useAnnotationStore";
```

> 注：`AnnotationWorkbench.vue` 在 Task 6 创建；为让 Task 5 可独立提交，先不引 `AnnotationWorkbench`，只在 Task 6 加。此处第 4 步改到 Task 6 完成后统一补 export。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/tasks/detection
git commit -m "feat(annotation): detection 任务插件(渲染/绘制/校验)"
```

---

### Task 6: 工作台壳 `AnnotationWorkbench.vue`（detection 子集）

**Files:**
- Create: `frontend/src/annotation/core/AnnotationWorkbench.vue`
- Modify: `frontend/src/annotation/index.ts`（补 `AnnotationWorkbench` 导出）

**Interfaces:**
- Consumes: `useAnnotationStore`、`useAnnotationCanvas`、`detectionPlugin`、`AnnotationLabelRenderer`
- Produces: 一个可承载 detection 的最小工作台（工具栏 + 画布 + 插件渲染 + 保存调用），供阶段 0 e2e 验证。

- [ ] **Step 1: 创建一个最小 `AnnotationWorkbench.vue`**（壳：选工具/画布/任务插件渲染/保存）

```vue
<template>
  <div class="ann-workbench">
    <div class="ann-toolbar">
      <button v-for="t in allTools" :key="t.name" class="tool-btn"
        :class="{ active: currentTool === t.name }" @click="currentTool = t.name">
        {{ t.label }}
      </button>
    </div>
    <div class="ann-body">
      <AnnotationCanvas ref="canvasRef" :img-url="imgUrl" :image-loaded="imageLoaded"
        :cursor="'crosshair'" @img-load="onImgLoad" @mousedown="onCanvasDown">
        <component :is="plugin.renderer" :annotations="store.annotations" :cw="cw" :ch="ch"
          :selected-id="store.selectedAnnotationId" :color="clsColor" :cls-name="clsName"
          :font-size="fontSize" :tag-h="tagH" @ann-down="onAnnDown" />
      </AnnotationCanvas>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, nextTick } from "vue";
import AnnotationCanvas from "./AnnotationCanvas.vue";
import { useAnnotationCanvas } from "./useAnnotationCanvas";
import { useAnnotationStore } from "./useAnnotationStore";
import AnnotationLabelRenderer from "./AnnotationLabelRenderer.vue";
import type { Annotation, AnnotationTaskPlugin } from "../types";
const props = defineProps<{
  plugin: AnnotationTaskPlugin;
  imgUrl: string; taskId: number; imageId: number;
  classes: { id: number; name: string; color: string }[];
  saveApi: (taskId: number, imageId: number, data: any[]) => Promise<any>;
}>();
const store = useAnnotationStore();
const currentTool = ref("select");
const allTools = computed(() => props.plugin.tools);
const canvas = useAnnotationCanvas();
const cw = computed(() => canvas.cw.value);
const ch = computed(() => canvas.ch.value);
const imgUrl = ref(props.imgUrl);
const imageLoaded = ref(false);
const fontSize = 6;
const tagH = Math.max(8, fontSize + 6);
function clsName(a: Annotation) { return props.classes.find((c) => c.id === a.class_id)?.name || ""; }
function clsColor(a: Annotation) { return props.classes.find((c) => c.id === a.class_id)?.color || "#3b82f6"; }
function onImgLoad(w: number, h: number) { imageLoaded.value = true; }
function onCanvasDown() {}
function onAnnDown(ev: MouseEvent, ann: Annotation) {
  store.selectedAnnotationId = ann.id;
  const r = (document.querySelector(".annotation-canvas") as HTMLElement)?.getBoundingClientRect();
  if (!r) return;
  // 阶段 0：仅选中；完整拖拽在后续任务补 onDrag 回调
}
</script>
```

> 注：阶段 0 目标只是"骨架 + detection 能渲染 + e2e 通过"，完整拖拽/绘制随后续任务补充；本任务可先以"加载既有标注并渲染 + 盒子选择"为最小可验收交付。

- [ ] **Step 2: 更新 `index.ts`**（补 `AnnotationWorkbench` 导出，见 Task 5 第 4 步）

- [ ] **Step 3: 提交**

```bash
git add frontend/src/annotation
git commit -m "feat(annotation): 最小工作台壳(AnnotationWorkbench, detection)"
```

---

### Task 7: e2e 回归验证

**Files:**
- Modify: `frontend/e2e/zz-stage0-workbench.spec.ts`（新增、临时）

**Interfaces:**
- Consumes: `AnnotationWorkbench` + `detectionPlugin`

- [ ] **Step 1: 写一个临时 e2e**：用 API 建 detection 任务、上传一图、打开 `AnnotationWorkbench`（挂到临时路由或直接挂载），断言 `.ann-svg` 可见、无渲染报错。

```ts
import { test, expect } from "@playwright/test";
import fs from "fs";
const API = process.env.E2E_API_URL || "http://127.0.0.1:8001/api/v1";
const IMG = "D:/AIStation/backend/.venv/Lib/site-packages/apprise/assets/themes/default/apprise-logo.png";
test("阶段0骨架: workbench 渲染 detection", async ({ page, request }) => {
  // ... 复用 workbench.spec 的建任务+上传流程，然后 goto 临时路由
  // 断言 page.locator(".ann-svg").first() 可见
});
```

- [ ] **Step 2: 运行以确认通过**

Run: `cd frontend && pnpm exec playwright test e2e/zz-stage0-workbench.spec.ts`
Expected: PASS（至少 `.ann-svg` 可见、无 console error）

- [ ] **Step 3: 清理临时 e2e 并回归既有基线**

```bash
cd frontend && pnpm exec playwright test e2e/workbench.spec.ts
```
Expected: PASS（证明旧工作台未被破坏）

- [ ] **Step 4: 提交**

```bash
git add -A
git commit -m "test(annotation): 阶段0骨架e2e验证(临时) + 既有基线回归"
```

---

## 阶段 0 验收标准

1. `frontend/src/annotation/` 目录骨架、`defineAnnotationTask` 接口、detection 插件、最小 `AnnotationWorkbench` 可渲染。
2. `pnpm run type-check` 通过、`workbench.spec.ts` 现有基线回归通过。
3. 目录不依赖项目内部业务模块（可拷贝复用）。
4. 后续阶段（1-5）按此接口逐个迁移其余任务类型，每阶段独立提交、可回滚。
