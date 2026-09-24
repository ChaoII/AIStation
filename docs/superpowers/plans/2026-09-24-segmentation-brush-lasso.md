# 画笔分割「套索」子模式实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给「画笔分割」工具新增「套索」子模式：随鼠标实时细线笔迹，松手自动首尾闭合、填充成一块实心多边形标注，同时保留现有「涂抹」行为。

**Architecture:** 在 `useBrushTool`（`brush.ts`）内新增 `mode: Ref<"paint"|"lasso">` 与 `end()` 分流；套索直接取中心轨迹，经 `lassoToPolygon`（复用现有 `simplifyPolygon` 抽稀）后返回闭合 Polygon，不走 `maskToPolygon`。`BrushPreview` 按 mode 渲染（套索=细线+闭合虚线预览）。UI 在画笔右键浮层加「涂抹/套索」切换。

**Tech Stack:** Vue 3 + TypeScript + Vitest（前端单测）+ Playwright（e2e）。

## Global Constraints

- 套索忽略笔刷粗细，只取移动轨迹中心线。
- 套索不走 `maskToPolygon`；结果直接为中心轨迹抽稀后的闭合 Polygon。
- 套索内部空洞不计（不做甜甜圈带洞）。
- 涂抹行为保持完全不变。
- 所有对用户说明/注释用中文；提交信息用 `feat(annotation): 中文描述`。
- 功能分支上**禁止**跑 `pnpm run lint`；type-check 用 `npx vue-tsc --noEmit --skipLibCheck`（在 `frontend/` 下执行）。

---

### Task 1: `brush.ts` 增加套索模式（mode + lassoToPolygon + end 分流 + 单测）

**Files:**
- Modify: `frontend/src/annotation/core/brush.ts`
- Test: `frontend/src/annotation/core/__tests__/brush.test.ts`

**Interfaces:**
- Produces:
  - `export function lassoToPolygon(points: Point[]): Point[]` — 抽稀轨迹点，≥3 返回（否则返回 `[]`）。
  - `useBrushTool()` 新增 `mode: Ref<"paint"|"lasso">`（默认 `"paint"`）、`setBrushMode(m)`；返回对象增加 `mode`、`setBrushMode`。

- [ ] **Step 1: 写失败单测（追加到 `brush.test.ts`）**

在文件顶部 import 增加 `lassoToPolygon`：

```ts
import { simplifyPolygon, maskToPolygon, lassoToPolygon } from "../brush";
```

在文件末尾追加：

```ts
describe("lassoToPolygon", () => {
  it("点数不足 3 返回空数组", () => {
    const pts = [
      { x: 0.1, y: 0.1 },
      { x: 0.2, y: 0.2 },
    ];
    expect(lassoToPolygon(pts)).toEqual([]);
  });

  it("闭合矩形轨迹抽稀后返回合法闭合多边形", () => {
    const pts: { x: number; y: number }[] = [];
    const rect = (x: number, y: number) => ({ x, y });
    for (let i = 0; i <= 40; i++) pts.push(rect(0.2 + 0.6 * (i / 40), 0.2)); // 上边
    for (let i = 0; i <= 40; i++) pts.push(rect(0.8, 0.2 + 0.6 * (i / 40))); // 右边
    for (let i = 0; i <= 40; i++) pts.push(rect(0.8 - 0.6 * (i / 40), 0.8)); // 下边
    for (let i = 0; i <= 40; i++) pts.push(rect(0.2, 0.8 - 0.6 * (i / 40))); // 左边
    const out = lassoToPolygon(pts);
    expect(out.length).toBeGreaterThanOrEqual(3);
    for (const p of out) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(1);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(1);
    }
    // 抽稀后点数应显著少于原始 160+ 点
    expect(out.length).toBeLessThan(pts.length);
  });
});
```

- [ ] **Step 2: 运行验证失败**

Run: `npx vitest run src/annotation/core/__tests__/brush.test.ts`
Expected: 失败，`lassoToPolygon is not a function`。

- [ ] **Step 3: 实现 `lassoToPolygon` 与 `useBrushTool` 增强**

在 `brush.ts` 中（`convexHull` 定义之后、`useBrushTool` 之前）新增：

```ts
/** 套索：中心轨迹抽稀并返回闭合多边形点（≥3），否则空数组。 */
export function lassoToPolygon(points: Point[]): Point[] {
  if (points.length < 3) return [];
  const out = simplifyPolygon(points, 0.01);
  if (out.length >= 3) return out;
  return points.length >= 3 ? points : [];
}
```

修改 `useBrushTool()`：

```ts
export function useBrushTool() {
  const strokes = ref<Point[][]>([]);
  const brushSize = ref(8);
  const erasing = ref(false);
  const mode = ref<"paint" | "lasso">("paint");
  let canvas: HTMLCanvasElement | null = null;
  // ... ensureCanvas / paintStroke / clearCanvas 不变 ...
```

在 `end` 前新增：

```ts
  function setBrushMode(m: "paint" | "lasso") {
    mode.value = m;
  }
```

将 `end` 改为按 mode 分流：

```ts
  function end(cw: number, ch: number): Annotation | null {
    if (strokes.value.length === 0) return null;
    const all: Point[] = [];
    strokes.value.forEach((s) => all.push(...s));
    strokes.value = [];
    if (mode.value === "lasso") {
      const pts = lassoToPolygon(all);
      if (pts.length < 3) return null;
      return {
        id: crypto.randomUUID(),
        type: "Polygon" as const,
        class_id: 0,
        points: pts,
      };
    }
    paintStroke(all, cw, ch, erasing.value);
    const ctx = ensureCanvas(cw, ch).getContext("2d")!;
    const imageData = ctx.getImageData(0, 0, cw, ch);
    const mask = new Uint8Array(imageData.data.length / 4);
    for (let i = 0; i < mask.length; i++) mask[i] = imageData.data[i * 4 + 3] > 0 ? 1 : 0;
    const pts = maskToPolygon(mask, cw, ch);
    if (pts.length < 3) return null;
    return {
      id: crypto.randomUUID(),
      type: "Polygon" as const,
      class_id: 0,
      points: pts,
    };
  }
```

将返回语句改为：

```ts
  return { strokes, brushSize, erasing, mode, setBrushMode, start, move, end, reset };
```

（说明：原 `end` 中 `strokes.value = []` 需在 lasso 分支前清空，上面代码已把清空移到最前。）

- [ ] **Step 4: 运行验证通过**

Run: `npx vitest run src/annotation/core/__tests__/brush.test.ts`
Expected: PASS（全部用例）。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/annotation/core/brush.ts frontend/src/annotation/core/__tests__/brush.test.ts
git commit -m "feat(annotation): 画笔工具新增套索模式（中心轨迹闭合填充）"
```

---

### Task 2: 画笔工具 `state` 暴露 mode

**Files:**
- Modify: `frontend/src/annotation/tasks/segmentation/index.ts:49-57`

**Interfaces:**
- Consumes: Task 1 的 `brush.mode`、`brush.setBrushMode`。
- Produces: brush tool 的 `state` 新增 `mode`、`setBrushMode`，供预览与 UI 使用。

- [ ] **Step 1: 修改 brush 工具 state**

将 `segmentation/index.ts` 中 brush 的 `state` 行（第 52 行）改为：

```ts
        state: {
          strokes: brush.strokes,
          brushSize: brush.brushSize,
          mode: brush.mode,
          setBrushMode: brush.setBrushMode,
        },
```

- [ ] **Step 2: type-check**

Run: `npx vue-tsc --noEmit --skipLibCheck`
Expected: 无 `segmentation/index.ts` 相关新错误（其余既有错误忽略）。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/annotation/tasks/segmentation/index.ts
git commit -m "feat(annotation): 画笔工具 state 暴露套索模式"
```

---

### Task 3: `BrushPreview.vue` 按模式渲染（套索=细线+闭合虚线）

**Files:**
- Modify: `frontend/src/annotation/core/BrushPreview.vue`

**Interfaces:**
- Consumes: `props.state.mode`（来自 Task 2 的 `brush.mode`）、`props.cw/ch`。
- Produces: 套索模式下的实时细线笔迹 + 「末点→首点」闭合虚线预览。

- [ ] **Step 1: 改模板与脚本**

将 `BrushPreview.vue` 整体替换为：

```vue
<template>
  <g>
    <polyline
      v-for="(stroke, si) in strokes"
      :key="si"
      :points="strokePts(stroke)"
      fill="none"
      :stroke="isLasso ? lassoColor : '#3b82f6'"
      :stroke-width="isLasso ? 1.5 : strokeWidth"
      stroke-linecap="round"
      stroke-linejoin="round"
      vector-effect="non-scaling-stroke"
      :style="peStyle"
    />
    <line
      v-if="isLasso && closePreview"
      :x1="closePreview.x1"
      :y1="closePreview.y1"
      :x2="closePreview.x2"
      :y2="closePreview.y2"
      :stroke="lassoColor"
      stroke-width="1"
      stroke-dasharray="4 4"
      vector-effect="non-scaling-stroke"
      :style="peStyle"
    />
  </g>
</template>

<script setup lang="ts">
import { computed, unref } from "vue";
import type { Point } from "./types";

const props = defineProps<{
  state: any;
  cw: number;
  ch: number;
  zoom?: number;
  pointerNone?: boolean;
  brushSize?: number;
}>();
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));
const strokes = computed<Point[][]>(() => unref(props.state?.strokes) ?? []);
const isLasso = computed(() => unref(props.state?.mode) === "lasso");
const lassoColor = "#3b82f6";
const strokeWidth = computed(
  () => unref(props.state?.brushSize) ?? unref(props.brushSize) ?? 8
);
// 套索闭合预览：首条第一点 → 末条最后一点
const closePreview = computed(() => {
  const s = strokes.value;
  if (!s.length) return null;
  const first = s[0]?.[0];
  const last = s[s.length - 1]?.[s[s.length - 1].length - 1];
  if (!first || !last) return null;
  return {
    x1: first.x * props.cw,
    y1: first.y * props.ch,
    x2: last.x * props.cw,
    y2: last.y * props.ch,
  };
});
function strokePts(stroke: any[]): string {
  if (!stroke || stroke.length === 0) return "";
  return stroke
    .map((p) => `${p.x * props.cw},${p.y * props.ch}`)
    .join(" ");
}
</script>
```

- [ ] **Step 2: type-check**

Run: `npx vue-tsc --noEmit --skipLibCheck`
Expected: 无 `BrushPreview.vue` 相关新错误。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/annotation/core/BrushPreview.vue
git commit -m "feat(annotation): BrushPreview 支持套索模式（细线+闭合虚线预览）"
```

---

### Task 4: 画笔右键浮层加「涂抹 / 套索」切换

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Consumes: `activeTool.state.mode`、`activeTool.state.setBrushMode`（来自 Task 2），`unref`（已 import）。
- Produces: 画笔右键设置浮层（`brushPopover`）内可见模式切换。

- [ ] **Step 1: 新增 `brushMode` computed**

在 `brush.ts` 相关脚本区（`setBrushSize` 之后、`canvasAreaRef` 之前）插入：

```ts
const brushMode = computed({
  get: () => (unref(activeTool.value?.state?.mode) as "paint" | "lasso") ?? "paint",
  set: (v: "paint" | "lasso") => activeTool.value?.state?.setBrushMode?.(v),
});
```

- [ ] **Step 2: 浮层模板加模式切换**

在 `brushPopover` 的 `<div class="brush-popover-head">画笔大小</div>` 之后插入：

```html
          <div class="brush-popover-mode">
            <el-radio-group v-model="brushMode" size="small">
              <el-radio-button value="paint">涂抹</el-radio-button>
              <el-radio-button value="lasso">套索</el-radio-button>
            </el-radio-group>
          </div>
```

- [ ] **Step 3: 样式**

在 scoped 样式中 `.brush-popover-head` 规则后追加：

```css
.brush-popover-mode {
  margin-bottom: 8px;
}
```

- [ ] **Step 4: type-check**

Run: `npx vue-tsc --noEmit --skipLibCheck`
Expected: 无 `AnnotationWorkbench.vue` 相关新错误。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "feat(annotation): 画笔右键浮层支持涂抹/套索切换"
```

---

### Task 5: 套索 e2e 测试

**Files:**
- Create: `frontend/e2e/create-lasso.spec.ts`

**Interfaces:**
- Consumes: `anno-helper` 的 `login`、`createAnnotationTask`、`gotoWorkbench`、`imageBox`、`expectAnnotation`（同 `create-brush.spec.ts`）。

- [ ] **Step 1: 写 e2e（复制 `create-brush.spec.ts` 结构调整）**

创建 `frontend/e2e/create-lasso.spec.ts`：

```ts
import { test, expect } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

// 套索：沿目标外轮廓描一圈 → 松手自动闭合填充成多边形标注。

test("套索描圈生成闭合填充多边形标注", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "segmentation", "seg");
  await gotoWorkbench(page, taskId);

  await page.locator(".tool-btn", { hasText: "画笔分割" }).click();

  // 切到套索模式：打开右键浮层并选择「套索」
  const img = await imageBox(page);
  await page.mouse.click(img.x + img.width * 0.3, img.y + img.height * 0.5, { button: "right" });
  await page.locator(".brush-popover .el-radio-button", { hasText: "套索" }).click();
  await page.mouse.click(img.x + img.width * 0.1, img.y + img.height * 0.9); // 关浮层避免遮挡

  // 描一圈（从顶部中点逆时针绕一圈回到起点附近）
  const cx = img.x + img.width * 0.5;
  const cy = img.y + img.height * 0.5;
  const r = Math.min(img.width, img.height) * 0.25;
  await page.mouse.move(cx, cy - r);
  await page.mouse.down();
  for (let i = 1; i <= 40; i++) {
    const a = (i / 40) * Math.PI * 2 - Math.PI / 2;
    await page.mouse.move(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
  }
  await page.mouse.up();

  await expectAnnotation(page);
  await page.keyboard.press("Control+s");
  await page.screenshot({ path: "C:/Users/aichao/AppData/Local/Temp/opencode/lasso-result.png", fullPage: true });
});
```

- [ ] **Step 2: 运行**

Run: `npx playwright test create-lasso.spec.ts`
Expected: PASS（生成闭合填充多边形并保存）。

- [ ] **Step 3: 回归 `create-brush`**

Run: `npx playwright test create-brush.spec.ts`
Expected: PASS（涂抹行为未回归）。

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/create-lasso.spec.ts
git commit -m "test(annotation): 套索描圈闭合填充 e2e"
```

---

## Self-Review

- **Spec 覆盖：** 交互（模式切换/实时细线/松手闭合=Task 3+4+5）、边界取法（中心轨迹/不走 maskToPolygon/忽略粗细=Task 1）、改动点（brush.ts=Task 1、index=Task 2、BrushPreview=Task 3、浮层切换=Task 4、e2e=Task 5）均已覆盖。
- **类型一致性：** `mode`/`setBrushMode`/`lassoToPolygon`/`brushMode` 名称在各任务间一致。
- **无占位符：** 所有步骤含完整代码与命令。
