# 语义分割标注（S1：核心类型）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增「语义分割」标注任务类型，提供多边形勾勒 + 同类按类别合并渲染 + 背景类填充，体现类别级语义。

**Architecture:** 复用现有 `Polygon` shape 与多边形交互，新增 `semanticSegmentation` 插件（`frontend/src/annotation/tasks/semanticSegmentation/`）。同类合并/背景垫底由插件内模块级共享 ref（`sharedState.ts`）驱动渲染器；「填充背景」按钮经壳新增的 `panel` 契约挂载。后端加 `AnnotationType` 枚举值 + PG `ALTER TYPE` 迁移。

**Tech Stack:** FastAPI + SQLAlchemy/Alembic（后端）；Vue3 + Vite + Element Plus + TypeScript（前端）。

## Global Constraints

- 交流语言：中文（注释/提交信息/给用户文本）。
- `core/` 不得 import 业务模块；API/协作经 props 注入。
- 数据模型：复用 `Polygon` shape（`type:"Polygon"`, `points`, `class_id`），**不改** `ShapeAnnotation` 判别联合。
- 删除/覆盖类操作必须二次确认（`ElMessageBox.confirm`），按钮带 `v-hasPerm`。
- 前端 `frontend/src/`（`frontend/web/` 为独立副本，不动）。`frontend/views` 目录是 `src/views`。
- PG `Enum` 列加值须用 `ALTER TYPE ... ADD VALUE`，且不能在事务块内执行（用 `autocommit_block`）。
- 提交信息：`feat(annotation): ...` / `refactor(annotation): ...`。

---

### Task 1: 后端枚举 + Alembic 迁移

**Files:**
- Modify: `backend/app/api/v1/module_annotation/dataset/model.py:10-16`
- Create: `backend/app/alembic/versions/<new>_semantic_segmentation_enum.py`

**Interfaces:**
- Consumes: 现有 `AnnotationType`（`DETECTION/ROTATED_DETECTION/SEGMENTATION/KEYPOINT/OCR/CLASSIFICATION`）。
- Produces: `AnnotationType.SEMANTIC_SEGMENTATION = "semantic_segmentation"`；PG 枚举 `annotationtype` 新增值。

- [ ] **Step 1: 更新后端枚举**

在 `backend/app/api/v1/module_annotation/dataset/model.py` 的 `AnnotationType` 中（`SEGMENTATION = "segmentation"` 之后）加：

```python
    SEGMENTATION = "segmentation"
    SEMANTIC_SEGMENTATION = "semantic_segmentation"
    KEYPOINT = "keypoint"
```

- [ ] **Step 2: 生成迁移占位并填入内容**

运行（在 `backend/` 下）：
```bash
uv run main.py revision --message "semantic_segmentation enum" --env=dev
```
自动生成一个空迁移（Alembic 不检测 enum 值变更），将生成的 `backend/app/alembic/versions/<rev>_semantic_segmentation_enum.py` 内容替换为：

```python
"""semantic_segmentation enum

Revision ID: <填入自动生成的 revision>
Revises: <填入自动生成的 down_revision>
"""
from collections.abc import Sequence

from alembic import op

from app.alembic.dialect_compat import is_postgres

revision: str = "<自动生成>"
down_revision: str | Sequence[str] | None = "<自动生成>"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """给 annotationtype 枚举增加 semantic_segmentation 值（仅 PostgreSQL）。"""
    if is_postgres(op.get_bind()):
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE annotationtype ADD VALUE IF NOT EXISTS "
                "'semantic_segmentation'"
            )


def downgrade() -> None:
    """PG 不支持移除枚举值，downgrade 为空操作（保留该值）。"""
    pass
```

- [ ] **Step 3: 应用迁移**

```bash
uv run main.py upgrade --env=dev
```
Expected: 无报错，告警性输出可忽略。

- [ ] **Step 4: 校验枚举值可创建任务**

运行后端 shell（或用已有 e2e 前置验证），确认 `AnnotationType("semantic_segmentation")` 可用：
```bash
uv run python -c "from app.api.v1.module_annotation.dataset.model import AnnotationType; print(AnnotationType('semantic_segmentation'))"
```
Expected: `AnnotationType.SEMANTIC_SEGMENTATION`

- [ ] **Step 5: Lint + Commit**

```bash
cd backend && uv run ruff check
git add backend/app/api/v1/module_annotation/dataset/model.py backend/app/alembic/versions/<新增迁移>
git commit -m "feat(annotation): 后端新增 semantic_segmentation 标注类型枚举与迁移"
```

---

### Task 2: 前端任务类型映射

**Files:**
- Modify: `frontend/src/views/module_annotation/task/index.vue:177-183`（el-option）、`:346-352`（options）、`:622-643`（label/tag 映射）

**Interfaces:**
- Consumes: 无。
- Produces: `semantic_segmentation` 任务类型在下拉与表格显示为「语义分割」。

- [ ] **Step 1: 模板下拉加选项**

在 `index.vue` 模板 `<el-option label="实例分割" value="segmentation" />`（约 180 行）之后加：

```html
<el-option label="语义分割" value="semantic_segmentation" />
```

- [ ] **Step 2: scripts options 加项**

在 `:346-352` 的 `options` 数组中 `{ label: "实例分割", value: "segmentation" }` 之后加：

```js
{ label: "语义分割", value: "semantic_segmentation" },
```

- [ ] **Step 3: label/tag 映射加项**

`annotationTypeLabel` 的 map（`:622-632`）中 `segmentation: "实例分割"` 后加：

```js
semantic_segmentation: "语义分割",
```

`annotationTypeTag` 的 map（`:634-643`）中 `segmentation: "danger"` 后加：

```js
semantic_segmentation: "warning",
```

- [ ] **Step 4: Verify + Commit**

```bash
cd frontend && npx vue-tsc --noEmit --skipLibCheck   # annotation 无新增错误
git add frontend/src/views/module_annotation/task/index.vue
git commit -m "feat(annotation): 前端任务类型映射新增语义分割"
```

---

### Task 3: core 插件面板扩展（最小契约）

**Files:**
- Modify: `frontend/src/annotation/core/types.ts`（`PluginPanelContext` + `AnnotationTaskPlugin.panel`）
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`（渲染 `plugin.panel` 并注入 `ctx`）

**Interfaces:**
- Consumes: `Annotation` / `AnnotationTaskPlugin` 既有契约。
- Produces:
  - `PluginPanelContext { classes: any[]; selectedClassId: number | null; commit: (ann: Annotation) => void }`
  - `AnnotationTaskPlugin.panel?: Component`
  - 壳暴露 `panelCtx` 给 panel 组件。

- [ ] **Step 1: types.ts 加 `PluginPanelContext` 与 `panel`**

在 `frontend/src/annotation/core/types.ts` 顶部 import 区加（若未引入 `Component`）：
```ts
import type { Component } from "vue";
```
在 `AnnotationTaskPlugin` 接口（`tools/create/interaction/tool` 之后、`onDrag` 之前）加：

```ts
  /** 插件级自定义面板组件（如「填充背景」等操作），由壳渲染并注入 ctx，不 import 业务 */
  panel?: Component;
```

在同文件（如 `PluginTool` 之后）定义：

```ts
export interface PluginPanelContext {
  /** 任务类别列表 */
  classes: any[];
  /** 当前选中类别 id */
  selectedClassId: number | null;
  /** 提交一个新标注（壳会对齐 create 校验 + push + 历史） */
  commit: (ann: Annotation) => void;
}
```

- [ ] **Step 2: 壳渲染 `plugin.panel`**

在 `AnnotationWorkbench.vue` 模板，`.ann-header` 之后、`.ann-body` 之前插入：

```html
    <component
      v-if="plugin.panel"
      :is="plugin.panel"
      :ctx="panelCtx"
      class="ann-plugin-panel"
    />
```

- [ ] **Step 3: 壳定义 `panelCtx`**

在 `AnnotationWorkbench.vue` script（`taskClasses` 定义之后）加：

```ts
const panelCtx = computed<PluginPanelContext>(() => ({
  classes: taskClasses.value,
  selectedClassId: selectedClassId.value,
  commit: (ann: Annotation) => commitCreated(ann),
}));
```

并在 import 区引入类型：`import type { PluginPanelContext } from "./types";`（确认 `Annotation` / `computed` 已引入）。

- [ ] **Step 4: Verify + Commit**

```bash
cd frontend && npx vue-tsc --noEmit --skipLibCheck && npx eslint src/annotation/core
git add frontend/src/annotation/core/types.ts frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "refactor(annotation): core 增加插件级面板挂载点（最小契约扩展）"
```

---

### Task 4: 语义分割插件（共享态 + 渲染器 + 面板 + index）

**Files:**
- Create: `frontend/src/annotation/tasks/semanticSegmentation/sharedState.ts`
- Create: `frontend/src/annotation/tasks/semanticSegmentation/SemanticSegCanvas.vue`
- Create: `frontend/src/annotation/tasks/semanticSegmentation/SemanticSegPanel.vue`
- Create: `frontend/src/annotation/tasks/semanticSegmentation/index.ts`

**Interfaces:**
- Consumes: `useSegmentTool`（`../segmentation/useSegmentTool`，提供 `addPoint/closePolygon/polygonPath/polyBBox`）；壳 `PluginPanelContext`；壳渲染器通用 props。
- Produces:
  - `semanticSegmentationPlugin: AnnotationTaskPlugin`（`name:"semantic_segmentation"`, `label:"语义分割"`, `renderer`, `tools`, `create`, `tool`, `interaction`, `panel`）。
  - `segBackgroundClassId: Ref<number|null>`（模块级共享）。

- [ ] **Step 1: 共享状态**

创建 `frontend/src/annotation/tasks/semanticSegmentation/sharedState.ts`：

```ts
import { ref } from "vue";

/** 语义分割「背景」类别 id（面板设置，渲染器据此垫底），插件内共享，不依赖 core。 */
export const segBackgroundClassId = ref<number | null>(null);
```

- [ ] **Step 2: 渲染器**

创建 `frontend/src/annotation/tasks/semanticSegmentation/SemanticSegCanvas.vue`。参照 `SegmentCanvas.vue`，但：
- 渲染前按「背景类别垫底、其它类别在上」排序（背景类多边形用底层 `fill`）。
- 同类同色（用 `color(ann)`），呈现类别级合并。
- 保留多边形顶点/中点编辑 handles（选中态）与外接矩形参考框、`@ann-down`/`@handle-down`。

```vue
<template>
  <g v-for="ann in rendered" :key="ann.id" :data-ann-id="ann.id">
    <rect
      :x="bbox(ann).x"
      :y="bbox(ann).y"
      :width="bbox(ann).w"
      :height="bbox(ann).h"
      :stroke="color(ann)"
      stroke-width="1"
      fill="none"
      stroke-dasharray="4 2"
      class="seg-bbox-reference"
      vector-effect="non-scaling-stroke"
      style="pointer-events: none"
    />
    <path
      :d="path(ann)"
      :stroke="color(ann)"
      :stroke-width="ann.id === selectedId ? selStroke : stroke"
      fill-rule="evenodd"
      :fill="color(ann) + '20'"
      :style="peStyle"
      vector-effect="non-scaling-stroke"
      @mousedown.stop.prevent="$emit('ann-down', $event, ann)"
    />
    <template v-if="ann.id === selectedId">
      <circle
        v-for="(pt, i) in ann.points"
        :key="i"
        :cx="pt.x * cw"
        :cy="pt.y * ch"
        r="4"
        fill="#fff"
        stroke="#1a1a1a"
        stroke-width="1.5"
        class="handle"
        :style="peStyle"
        :data-handle="'poly-' + i"
        @mousedown.stop.prevent="$emit('handle-down', $event, ann, 'poly-' + i)"
      />
      <circle
        v-for="(pt, i) in ann.points"
        :key="'ins-' + i"
        :cx="midpoints(ann)[i]?.x"
        :cy="midpoints(ann)[i]?.y"
        r="3"
        fill="#fff"
        stroke="#3b82f6"
        stroke-width="1"
        class="handle"
        :style="peStyle"
        :data-handle="'poly-ins-' + i"
        @mousedown.stop.prevent="$emit('handle-down', $event, ann, 'poly-ins-' + i)"
      />
    </template>
  </g>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { Annotation, Point } from "../../core/types";
import { useSegmentTool } from "../segmentation/useSegmentTool";
import { segBackgroundClassId } from "./sharedState";

const props = defineProps<{
  annotations: Annotation[];
  cw: number;
  ch: number;
  selectedId: string;
  color: (a: Annotation) => string;
  clsName: (a: Annotation) => string;
  fontSize: number;
  tagH: number;
  stroke?: number;
  selStroke?: number;
  pointerNone?: boolean;
}>();

defineEmits<{
  (e: "ann-down", ev: MouseEvent, ann: Annotation): void;
  (e: "handle-down", ev: MouseEvent, ann: Annotation, handle: string): void;
}>();

const seg = useSegmentTool();
const stroke = computed(() => props.stroke ?? 1.5);
const selStroke = computed(() => props.selStroke ?? 2);
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));

// 背景类垫底、其它类别在上叠加（类别级合并渲染）
const rendered = computed(() => {
  const bg = segBackgroundClassId.value;
  const order = [...props.annotations];
  if (bg != null) order.sort((a, b) => Number(b.class_id === bg) - Number(a.class_id === bg));
  return order;
});

function path(a: Annotation) {
  return seg.polygonPath(a, props.cw, props.ch);
}
function bbox(a: Annotation) {
  if (!a.points || a.points.length === 0) return { x: 0, y: 0, w: 0, h: 0 };
  return seg.polyBBox(a, props.cw, props.ch);
}
function midpoints(a: Annotation) {
  const pts = a.points || [];
  return pts.map((p: Point, i: number) => {
    const n = pts[(i + 1) % pts.length];
    return { x: ((p.x + n.x) / 2) * props.cw, y: ((p.y + n.y) / 2) * props.ch };
  });
}
</script>
```

- [ ] **Step 3: 面板组件**

创建 `frontend/src/annotation/tasks/semanticSegmentation/SemanticSegPanel.vue`：背景类别选择 + 「填充背景」按钮（二次确认）。填充生成覆盖整图的背景类多边形并 `ctx.commit`，同时 `segBackgroundClassId` 更新为所选背景类。

```vue
<template>
  <div class="seg-panel">
    <el-select
      v-model="bgId"
      placeholder="选择背景类别"
      size="small"
      style="width: 160px"
      clearable
      @change="onBgChange"
    >
      <el-option v-for="c in ctx.classes" :key="c.id" :label="c.name" :value="c.id" />
    </el-select>
    <el-button
      size="small"
      type="primary"
      :disabled="bgId == null"
      @click="fillBackground"
    >
      填充背景
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from "vue";
import { ElMessageBox, ElMessage } from "element-plus";
import type { PluginPanelContext, Annotation } from "../../core/types";
import { segBackgroundClassId } from "./sharedState";

const props = defineProps<{ ctx: PluginPanelContext }>();
const bgId = ref<number | null>(null);

const hasBg = computed(() =>
  props.ctx.classes.some((c) => c.id === segBackgroundClassId.value)
);

function onBgChange() {
  segBackgroundClassId.value = bgId.value;
}

async function fillBackground() {
  if (bgId.value == null) return;
  await ElMessageBox.confirm(
    "将把整图填充为背景类别，未标注处将显示为背景色（可撤销）。是否继续？",
    "填充背景",
    { confirmButtonText: "填充", cancelButtonText: "取消", type: "warning" }
  );
  const ann: Annotation = {
    id: crypto.randomUUID(),
    type: "Polygon",
    class_id: bgId.value,
    points: [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 1 },
      { x: 0, y: 1 },
    ],
  };
  props.ctx.commit(ann);
  segBackgroundClassId.value = bgId.value;
  ElMessage.success("已填充背景");
}

// 进入时若已有背景选择则回填控件
if (segBackgroundClassId.value != null) bgId.value = segBackgroundClassId.value;
</script>
```

- [ ] **Step 4: 插件 index**

创建 `frontend/src/annotation/tasks/semanticSegmentation/index.ts`，复用 `useSegmentTool`（tool）并实现与 segmentation 相同的 `interaction`：

```ts
import type { AnnotationTaskPlugin, Annotation, DragContext } from "../../core/types";
import SemanticSegCanvas from "./SemanticSegCanvas.vue";
import SemanticSegPanel from "./SemanticSegPanel.vue";
import { useSegmentTool } from "../segmentation/useSegmentTool";

export const semanticSegmentationPlugin: AnnotationTaskPlugin = {
  name: "semantic_segmentation",
  label: "语义分割",
  color: "warning",
  renderer: SemanticSegCanvas,
  tools: [{ name: "polygon", label: "语义分割", title: "逐点绘制轮廓，双击闭合" }],
  panel: SemanticSegPanel,
  create(shape: Annotation): boolean {
    if (shape.type !== "Polygon") return false;
    if (!Array.isArray(shape.points) || shape.points.length < 3) return false;
    return shape.points.every((p: any) => 0 <= p.x && p.x <= 1 && 0 <= p.y && p.y <= 1);
  },
  tool: (() => {
    const seg = useSegmentTool();
    return {
      name: "polygon",
      down(ctx) {
        const p = ctx.point;
        if (p) seg.addPoint(p);
        return null;
      },
      dblclick() {
        return seg.closePolygon();
      },
      reset() {
        seg.points.value = [];
      },
    };
  })(),
  interaction: {
    move(ctx: DragContext): void {
      const movePoints = (pts: any[]) =>
        pts.map((p: any) => ({
          ...p,
          x: Math.max(0, Math.min(1, p.x + ctx.dx)),
          y: Math.max(0, Math.min(1, p.y + ctx.dy)),
        }));
      ctx.ann.points = movePoints(ctx.orig.points);
      ctx.trigger();
    },
    vertexMove(ctx: DragContext): void {
      if (!ctx.point || !ctx.ann.points?.[Number(ctx.handle)]) return;
      ctx.ann.points[Number(ctx.handle)] = {
        ...ctx.ann.points[Number(ctx.handle)],
        x: Math.max(0, Math.min(1, ctx.point.x)),
        y: Math.max(0, Math.min(1, ctx.point.y)),
      };
      ctx.trigger();
    },
    vertexInsert(ann: Annotation, handle: string): void {
      const idx = Number(handle);
      if (isNaN(idx) || !ann.points?.length) return;
      const a = ann.points[idx],
        b = ann.points[(idx + 1) % ann.points.length];
      ann.points.splice(idx + 1, 0, { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
    },
    vertexDelete(ann: Annotation, handle: string): void {
      const idx = Number(handle);
      if (isNaN(idx) || !ann.points?.length) return;
      if (ann.points.length > 3) ann.points.splice(idx, 1);
    },
    tagAnchor(ann: Annotation): { x: number; y: number } {
      const xs = ann.points.map((p: any) => p.x);
      const ys = ann.points.map((p: any) => p.y);
      return { x: Math.min(...xs), y: Math.min(...ys) };
    },
  },
};
```

- [ ] **Step 5: Verify + Commit**

```bash
cd frontend && npx vue-tsc --noEmit --skipLibCheck && npx eslint src/annotation/tasks/semanticSegmentation
git add frontend/src/annotation/tasks/semanticSegmentation
git commit -m "feat(annotation): 新增语义分割插件（渲染+面板+交互）"
```

---

### Task 5: 注册插件 + e2e + 回归

**Files:**
- Modify: `frontend/src/annotation/index.ts:5-8`
- Create: `frontend/e2e/create-semantic-seg.spec.ts`

**Interfaces:**
- Consumes: `semanticSegmentationPlugin`。
- Produces: 语义分割类型在 `plugins` 列表可被工作台识别。

- [ ] **Step 1: 注册插件**

在 `frontend/src/annotation/index.ts` 的 `segmentationPlugin` 行之后加：

```ts
export { semanticSegmentationPlugin } from "./tasks/semanticSegmentation";
```

- [ ] **Step 2: 新增 e2e**

创建 `frontend/e2e/create-semantic-seg.spec.ts`（参照 `create-polygon.spec.ts`；填充背景用面板按钮定位）：

```ts
import { test } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

test("semantic_segmentation 画多边形 + 填充背景生成标注", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "semantic_segmentation", "semseg");
  await gotoWorkbench(page, taskId);

  await page.keyboard.press("p");
  const img = await imageBox(page);
  await page.mouse.click(img.x + img.width * 0.3, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.7, img.y + img.height * 0.3);
  await page.mouse.click(img.x + img.width * 0.5, img.y + img.height * 0.6);
  await page.mouse.dblclick(img.x + img.width * 0.6, img.y + img.height * 0.7);

  await expectAnnotation(page);
});
```

（注：若工作台需要类别才能画/填背景，e2e 通过 `createAnnotationTask` 的 `classes` 传一个背景类别；如当前类别为空，面板「填充背景」在无类别时可省略按钮校验，或 e2e 先加类别。）

- [ ] **Step 3: 运行 e2e**

```bash
cd frontend && npx playwright test e2e/create-semantic-seg.spec.ts --reporter=list
```
Expected: 通过（polygon 生成 + 至少一个标注出现）。

- [ ] **Step 4: 整体回归 + Commit**

```bash
cd frontend && npx eslint src/annotation frontend/src/views/module_annotation/task/index.vue
npx vue-tsc --noEmit --skipLibCheck   # annotation 无新增错误
npx playwright test e2e/create-semantic-seg.spec.ts e2e/create-polygon.spec.ts --reporter=list
git add frontend/src/annotation/index.ts frontend/e2e/create-semantic-seg.spec.ts
git commit -m "feat(annotation): 注册语义分割插件并新增创建 e2e"
```

---

## Self-Review

**Spec 覆盖核对：**
- 后端枚举 + 迁移 → Task 1。
- 前端任务类型映射 → Task 2。
- 复用 `Polygon` shape、不改联合 → Task 4（`create`/`tool`/`interaction` 均基于 `Polygon`）。
- 同类合并渲染 + 背景垫底 → Task 4 Step 2（`rendered` computed）。
- 填充背景按钮 + 二次确认 → Task 4 Step 3。
- core 插件面板挂载点 → Task 3。
- 注册 → Task 5。

**占位符：** 无 TBD/TODO；每个代码步骤含完整代码。

**类型一致性：** `PluginPanelContext.commit(ann)` 对应壳 `commitCreated(ann)`；`AnnotationTaskPlugin.panel?: Component`；`semanticSegmentationPlugin` 的 `name` 与后端枚举值 `"semantic_segmentation"` 一致；`panel` 注入 `ctx` 字段名在面板 `defineProps<{ ctx }>` 与壳 `:ctx="panelCtx"` 一致。

**注意事项已覆盖：** `ALTER TYPE ADD VALUE` 用 `autocommit_block`；填充背景二次确认。
