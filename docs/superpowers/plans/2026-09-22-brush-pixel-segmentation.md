# 画笔像素分割（SP-A）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给实例 / 语义 / 全景三个分割任务新增「画笔」工具，自由描摹后自动转 `Polygon`；并把 core 的单工具分发泛化为按 `currentTool` 的多工具分发（方案 A）。

**Architecture:** 新增 `core/brush.ts`（`useBrushTool` 状态机 + `maskToPolygon` / `simplifyPolygon` 纯函数）、`core/BrushPreview.vue` 共享预览；扩展 `AnnotationTaskPlugin.toolMap` 与 `AnnotationWorkbench` 的 `activeTool` 分发；三个分割插件在 `tools` 中声明 `polygon` + `brush` 两个可绘制工具。产物复用现有 `Polygon` 数据与导出链路。

**Tech Stack:** Vue 3 + TypeScript + Element Plus（前端），Vitest（新增纯函数单测），Playwright（e2e）。

**Spec:** `docs/superpowers/specs/2026-09-22-brush-pixel-segmentation-design.md`

## Global Constraints

- 产物一律 `Polygon`（`points: Point[]`，归一化 `[0,1]`），**不新增标注类型**；零后端改动、零导出改动。
- 纯函数 `maskToPolygon` / `simplifyPolygon` 输入为**二值掩码**（`Uint8Array` + `cw/ch`），与 canvas 解耦，可单测。
- 多工具分发向后兼容：`toolMap` 缺省时回退单 `tool`（既有单工具插件行为不变），确保回归。
- 中文注释；提交信息 `feat|test|fix(annotation): 中文描述`；前端用 Element Plus 组件与 `--el-*` 变量，不用内联 `font-size`/自造主题化外壳；单根 Vue 组件。
- 引入依赖需代理：`HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:7890`（见 AGENTS.md）。
- 前端 dev `:5180`、后端 `:8001`；e2e 需二者运行。

---

### Task 1: 引入 Vitest 并配置纯函数单测框架

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/annotation/core/__tests__/smoke.test.ts`

**Interfaces:**
- Consumes: 无（从零搭建）。
- Produces: `pnpm run test:unit` 命令；Vitest 配置仅收集 `src/**` 单测、排除 `e2e/`。

- [ ] **Step 1: 安装 Vitest（带代理）**

Run (在 `frontend/`):
```bash
$env:HTTP_PROXY="http://127.0.0.1:7890"; $env:HTTPS_PROXY="http://127.0.0.1:7890"; pnpm add -D vitest
```
Expected: `vitest@^3.x` 写入 `package.json` devDependencies。

- [ ] **Step 2: 创建 `vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
    exclude: ["**/e2e/**", "**/node_modules/**"],
  },
});
```

- [ ] **Step 3: 在 `package.json` 加 `test:unit` 脚本**

在 `"scripts"` 末尾加：
```json
"test:unit": "vitest run"
```

- [ ] **Step 4: 写 smoke 单测确认框架可用**

`frontend/src/annotation/core/__tests__/smoke.test.ts`:
```ts
import { describe, it, expect } from "vitest";

describe("vitest smoke", () => {
  it("runs", () => {
    expect(1 + 1).toBe(2);
  });
});
```

- [ ] **Step 5: 运行确认通过**

Run (在 `frontend/`): `pnpm run test:unit`
Expected: `1 passed`。

- [ ] **Step 6: 提交**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml frontend/vitest.config.ts frontend/src/annotation/core/__tests__/smoke.test.ts
git commit -m "test(annotation): 引入Vitest配置纯函数单测框架"
```

---

### Task 2: `simplifyPolygon`（Douglas-Peucker）纯函数 + 单测

**Files:**
- Create: `frontend/src/annotation/core/brush.ts`
- Test: `frontend/src/annotation/core/__tests__/brush.test.ts`

**Interfaces:**
- Consumes: `Point`（`core/types.ts`）。
- Produces: `simplifyPolygon(points: {x,y}[], tolerance: number): {x,y}[]` —— Douglas-Peucker 简化（保留首尾点），供 `maskToPolygon` 使用。

- [ ] **Step 1: 写失败测试**

`frontend/src/annotation/core/__tests__/brush.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { simplifyPolygon } from "../brush";

describe("simplifyPolygon", () => {
  it("保留首尾点并简化中间共线点", () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 1, y: 0 },
      { x: 2, y: 0 },
      { x: 3, y: 0 },
      { x: 3, y: 3 },
    ];
    const out = simplifyPolygon(pts, 0.1);
    expect(out[0]).toEqual({ x: 0, y: 0 });
    expect(out[out.length - 1]).toEqual({ x: 3, y: 3 });
    // 共线中间点被简化掉
    expect(out.length).toBeLessThan(pts.length);
  });

  it("tolerance 大于特征距离时保留拐点", () => {
    const pts = [
      { x: 0, y: 0 },
      { x: 2, y: 0 },
      { x: 2, y: 2 },
    ];
    const out = simplifyPolygon(pts, 0.1);
    expect(out.length).toBe(3);
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `pnpm run test:unit`
Expected: FAIL（`simplifyPolygon` 未定义）。

- [ ] **Step 3: 实现 `simplifyPolygon`**

`frontend/src/annotation/core/brush.ts`:
```ts
import type { Point } from "./types";

/** Douglas-Peucker 折线简化（保留首尾点），返回新数组。 */
export function simplifyPolygon(points: Point[], tolerance: number): Point[] {
  if (points.length <= 2) return points.slice();
  const sqTol = tolerance * tolerance;
  const keep = new Array<boolean>(points.length).fill(false);
  keep[0] = true;
  keep[points.length - 1] = true;
  const stack: Array<[number, number]> = [[0, points.length - 1]];
  while (stack.length) {
    const [a, b] = stack.pop()!;
    let maxDist = 0;
    let maxIdx = -1;
    for (let i = a + 1; i < b; i++) {
      const d = distToSegmentSq(points[i], points[a], points[b]);
      if (d > maxDist) {
        maxDist = d;
        maxIdx = i;
      }
    }
    if (maxIdx > 0 && maxDist > sqTol) {
      keep[maxIdx] = true;
      stack.push([a, maxIdx], [maxIdx, b]);
    }
  }
  return points.filter((_, i) => keep[i]);
}

function distToSegmentSq(p: Point, a: Point, b: Point): number {
  const abx = b.x - a.x;
  const aby = b.y - a.y;
  const lenSq = abx * abx + aby * aby;
  if (lenSq === 0) return (p.x - a.x) ** 2 + (p.y - a.y) ** 2;
  let t = ((p.x - a.x) * abx + (p.y - a.y) * aby) / lenSq;
  t = Math.max(0, Math.min(1, t));
  const cx = a.x + t * abx;
  const cy = a.y + t * aby;
  return (p.x - cx) ** 2 + (p.y - cy) ** 2;
}
```

- [ ] **Step 4: 运行确认通过**

Run: `pnpm run test:unit`
Expected: `2 passed`。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/core/brush.ts frontend/src/annotation/core/__tests__/brush.test.ts
git commit -m "feat(annotation): 新增Douglas-Peucker多边形简化纯函数"
```

---

### Task 3: `maskToPolygon`（二值掩码 → 最大外轮廓）纯函数 + 单测

**Files:**
- Modify: `frontend/src/annotation/core/brush.ts`
- Test: `frontend/src/annotation/core/__tests__/brush.test.ts`

**Interfaces:**
- Consumes: `simplifyPolygon`（Task 2）。
- Produces: `maskToPolygon(mask: Uint8Array, cw: number, ch: number, tol?: number): Point[]` —— 把二值掩码（1=前景，行优先 `y*cw+x`）提取前景**最大连通域**的**外边界**（Moore-neighbor 追踪），DP 简化后归一化到 `[0,1]`。无前景时返回 `[]`。

- [ ] **Step 1: 写失败测试（追加到 brush.test.ts）**

```ts
import { maskToPolygon } from "../brush";

describe("maskToPolygon", () => {
  // 8x8 掩码，前景为居中 4x4 方块（col/row 2..5），其边界归一化中心约在 (0.5,0.5)
  const mask = new Uint8Array(64);
  for (let y = 2; y < 6; y++)
    for (let x = 2; x < 6; x++) mask[y * 8 + x] = 1;

  it("为空掩码返回空数组", () => {
    expect(maskToPolygon(new Uint8Array(64), 8, 8)).toEqual([]);
  });

  it("对居中4x4方块提取外轮廓并归一化", () => {
    const pts = maskToPolygon(mask, 8, 8);
    expect(pts.length).toBeGreaterThanOrEqual(3);
    for (const p of pts) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(1);
      expect(p.y).toBeGreaterThanOrEqual(0);
      expect(p.y).toBeLessThanOrEqual(1);
    }
    // 中心约在 (0.5,0.5)（居中块中心）
    const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
    expect(Math.abs(cx - 0.5)).toBeLessThan(0.1);
    expect(Math.abs(cy - 0.5)).toBeLessThan(0.1);
  });

  it("两块前景取最大连通域（忽略小碎块）", () => {
    // 7x7：大块在左上(col0..4,row0..4)，小碎块在右下(6,6)
    const m = new Uint8Array(49);
    for (let y = 0; y < 5; y++)
      for (let x = 0; x < 5; x++) m[y * 7 + x] = 1;
    m[6 * 7 + 6] = 1;
    const pts = maskToPolygon(m, 7, 7);
    expect(pts.length).toBeGreaterThan(0);
    // 轮廓应落在左上大块附近（不含右下角）
    const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
    expect(cx).toBeLessThan(0.8);
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `pnpm run test:unit`
Expected: FAIL（`maskToPolygon` 未定义）。

- [ ] **Step 3: 实现 `maskToPolygon`**

`frontend/src/annotation/core/brush.ts`（追加）:
```ts
/** 二值掩码(1=前景) → 最大连通域外边界 → 简化(像素坐标) → 归一化折线。 */
export function maskToPolygon(
  mask: Uint8Array,
  cw: number,
  ch: number,
  tol = 1.0
): Point[] {
  const grid = new Uint8Array(mask.length);
  for (let i = 0; i < mask.length; i++) grid[i] = mask[i] ? 1 : 0;

  // 1) 最大连通域（BFS），忽略前景为0的情况
  const comp = largestComponent(grid, cw, ch);
  if (comp.size < 3) return [];

  // 2) Moore 邻域边界追踪，得到像素坐标外边界（闭环）
  const boundary = traceBoundary(comp, cw, ch);
  if (boundary.length < 3) return [];

  // 3) 在像素坐标下简化（tol 以像素为单位），再归一化 [0,1]
  const closed = [...boundary, boundary[0]];
  const simp = simplifyPolygon(closed, tol);
  return simp
    .slice(0, Math.max(simp.length - 1, 0))
    .map((p) => ({ x: p.x / cw, y: p.y / ch }));
}
```

`largestComponent` 与 `traceBoundary` 纯函数（同文件追加）：

```ts
function largestComponent(
  grid: Uint8Array,
  cw: number,
  ch: number
): Set<number> {
  const visited = new Uint8Array(grid.length);
  let best = new Set<number>();
  const dirs = [
    [1, 0], [-1, 0], [0, 1], [0, -1],
  ];
  for (let i = 0; i < grid.length; i++) {
    if (!grid[i] || visited[i]) continue;
    const queue = [i];
    visited[i] = 1;
    const comp = new Set<number>();
    let head = 0;
    while (head < queue.length) {
      const cur = queue[head++];
      comp.add(cur);
      const cx = cur % cw;
      const cy = (cur - cx) / cw;
      for (const [dx, dy] of dirs) {
        const nx = cx + dx;
        const ny = cy + dy;
        if (nx < 0 || nx >= cw || ny < 0 || ny >= ch) continue;
        const ni = ny * cw + nx;
        if (grid[ni] && !visited[ni]) {
          visited[ni] = 1;
          queue.push(ni);
        }
      }
    }
    if (comp.size > best.size) best = comp;
  }
  return best;
}

/** Moore 邻域边界追踪：从连通域最左上前景像素出发，沿外边界走回起点。 */
function traceBoundary(
  comp: Set<number>,
  cw: number,
  ch: number
): { x: number; y: number }[] {
  if (comp.size === 0) return [];
  const has = (x: number, y: number) =>
    x >= 0 && x < cw && y >= 0 && y < ch && comp.has(y * cw + x);

  // 找起点：最左列中最上面的前景像素
  let start = -1;
  for (let x = 0; x < cw && start < 0; x++)
    for (let y = 0; y < ch; y++)
      if (has(x, y)) {
        start = y * cw + x;
        break;
      }
  if (start < 0) return [];
  const sx = start % cw;
  const sy = (start - sx) / cw;

  // Moore 邻域 8 方向，顺时针
  const dir8 = [
    [1, 0], [1, 1], [0, 1], [-1, 1],
    [-1, 0], [-1, -1], [0, -1], [1, -1],
  ];
  let px = sx;
  let py = sy;
  let dir = 4; // 从西开始
  const out: { x: number; y: number }[] = [];
  let guard = 0;
  const maxSteps = cw * ch * 4 + 100;
  let first = true;
  while (guard++ < maxSteps) {
    const p = { x: px, y: py };
    if (!first || out.length === 0 || p.x !== sx || p.y !== sy) {
      out.push(p);
    }
    if (px === sx && py === sy && !first) break;
    first = false;

    // 顺时针从 dir-1 起扫描下一个前景邻域，更新走向
    let next = -1;
    for (let k = 0; k < 8; k++) {
      const idx = (dir - 1 + 8 - k) % 8; // 从右侧逆时针回溯
      const [dx, dy] = dir8[idx];
      if (has(px + dx, py + dy)) {
        next = idx;
        break;
      }
    }
    if (next < 0) break;
    // 将方向前进到 next，并前移到该邻域像素
    const [dx, dy] = dir8[next];
    px += dx;
    py += dy;
    dir = next;
  }
  return out;
}
```

- [ ] **Step 4: 运行确认通过并修正边界bug**

Run: `pnpm run test:unit`
Expected: 全部 PASS。若边界追踪有循环/顺序问题，逐步调整 `traceBoundary`（以「回到起点停」为准）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/core/brush.ts frontend/src/annotation/core/__tests__/brush.test.ts
git commit -m "feat(annotation): 新增二值掩码转最大外轮廓纯函数"
```

---

### Task 4: `BrushPreview.vue` 共享预览组件

**Files:**
- Create: `frontend/src/annotation/core/BrushPreview.vue`

**Interfaces:**
- Consumes: `state: { strokes: Point[][] }`（每笔画点集，归一化）；`cw`/`ch`；`brushSize`。
- Produces: 渲染当前笔画粗线轨迹的 SVG 组件（`v-for` 笔画 → `<polyline>`，`stroke-width` 按 `brushSize`，`stroke-linecap/join="round"`），供画笔工具 `preview` 使用。

- [ ] **Step 1: 创建组件**

```vue
<template>
  <g>
    <polyline
      v-for="(stroke, si) in (state?.strokes || [])"
      :key="si"
      :points="strokePts(stroke)"
      fill="none"
      stroke="#3b82f6"
      :stroke-width="strokeWidth"
      stroke-linecap="round"
      stroke-linejoin="round"
      vector-effect="non-scaling-stroke"
      :style="peStyle"
    />
  </g>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  state: any;
  cw: number;
  ch: number;
  pointerNone?: boolean;
  brushSize?: number;
}>();
const peStyle = computed(() => (props.pointerNone ? { pointerEvents: "none" as const } : {}));
const strokeWidth = computed(() => props.brushSize ?? 8);
function strokePts(stroke: any[]): string {
  if (!stroke || stroke.length === 0) return "";
  return stroke
    .map((p) => `${p.x * props.cw},${p.y * props.ch}`)
    .join(" ");
}
</script>
```

> 说明：`strokeWidth` 用一个稳定值（默认 8 视图像素单位，随 `brushSize` 缩放）；若担心 `non-scaling-stroke` + 过大值，可改为 `computed` 直接返回 `(props.brushSize ?? 8)`。

- [ ] **Step 2: type-check**

Run (在 `frontend/`): `pnpm run type-check`
Expected: 本组件无新增报错。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/annotation/core/BrushPreview.vue
git commit -m "feat(annotation): 新增画笔轨迹共享预览组件"
```

---

### Task 5: core 多工具分发（`toolMap` + `activeTool`）

**Files:**
- Modify: `frontend/src/annotation/core/types.ts:90-107`（`AnnotationTaskPlugin` 加 `toolMap`）
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`（分发点改 `activeTool`）

**Interfaces:**
- Consumes: `PluginTool`、`AnnotationTaskPlugin`。
- Produces: `AnnotationTaskPlugin.toolMap?: Record<string, PluginTool>`；工作台 `activeTool = computed(() => toolMap?.[currentTool] ?? (currentTool === tool?.name ? tool : undefined))`。既有单工具插件：`toolMap` 缺省 → 回退单 `tool`，行为不变。

- [ ] **Step 1: `types.ts` 加 `toolMap`**

在 `AnnotationTaskPlugin` 的 `tool?: PluginTool;` 之后加：
```ts
    /** 多工具分发：按 name 取对应绘制工具；缺省时回退单 `tool`（向后兼容）。 */
    toolMap?: Record<string, PluginTool>;
```

- [ ] **Step 2: `AnnotationWorkbench.vue` 加 `activeTool` 并替换分发点**

在 `const isDrawing = computed(() => currentTool.value === plugin.value.tool?.name);` 附近加：
```ts
const activeTool = computed(
  () =>
    plugin.value.toolMap?.[currentTool.value] ??
    (currentTool.value === plugin.value.tool?.name ? plugin.value.tool : undefined)
);
```
并把以下所有 `plugin.value.tool` / `plugin.tool` 引用替换为 `activeTool.value`（注意 `.value` 处与模板内差异）：
- `isDrawing`：`const isDrawing = computed(() => !!activeTool.value);`
- 模板中 `plugin.tool.preview` / `plugin.tool.state`（`v-if="plugin.tool && currentTool === plugin.tool.name"`）→ 改用 `activeTool`
- `resetDrawingState` / 加载图后 `plugin.value.tool?.reset?.()` → `activeTool.value?.reset?.()`
- `dblclick`、`down`、`move`、`up`、`keydown` 等分发处 `const tool = plugin.value.tool; if (tool && currentTool === tool.name)` → `const tool = activeTool.value; if (!tool) return;`

> 具体做法：把每处 `const tool = plugin.value.tool; if (tool && currentTool.value === tool.name)` 替换为 `const tool = activeTool.value; if (!tool) return;`；模板处 `plugin.tool` → `activeTool`。逐个分发点改，保持逻辑等价。

- [ ] **Step 3: type-check**

Run (在 `frontend/`): `pnpm run type-check`
Expected: 本模块无新增报错。

- [ ] **Step 4: 回归（既有单工具插件 e2e + 单测）**

Run (在 `frontend/`): `npx playwright test e2e/create-polygon.spec.ts e2e/create-rotatedbox.spec.ts --reporter=list`
Expected: 通过（`toolMap` 缺省回退路径正确）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/core/types.ts frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "feat(annotation): core多工具按currentTool分发(activeTool/toolMap)"
```

---

### Task 6: `useBrushTool` 画笔状态机 + 三分割插件挂载

**Files:**
- Modify: `frontend/src/annotation/core/brush.ts`（加 `useBrushTool`）
- Modify: `frontend/src/annotation/tasks/segmentation/index.ts`
- Modify: `frontend/src/annotation/tasks/semanticSegmentation/index.ts`
- Modify: `frontend/src/annotation/tasks/panopticSegmentation/index.ts`

**Interfaces:**
- Consumes: `maskToPolygon`、`BrushPreview`、`PluginTool`、`Annotation`。
- Produces: `useBrushTool()` 返回 `{ strokes, brushSize, erasing, start(p), move(p), end(): Annotation|null, reset() }`。画笔 `PluginTool`：`down` 开始笔画、`move` 累计、`up` 生成 `Polygon`（含 `maskToPolygon` 结果 + 保留轨迹点以备预览）。

- [ ] **Step 1: 在 `brush.ts` 追加 `useBrushTool`**

```ts
import { ref } from "vue";

/** 画笔状态机：维护当前笔画轨迹与橡皮擦标记；end() 用位图掩码转 Polygon。 */
export function useBrushTool() {
  const strokes = ref<Point[][]>([]);
  const brushSize = ref(8);
  const erasing = ref(false);
  let canvas: HTMLCanvasElement | null = null;

  function ensureCanvas(cw: number, ch: number): HTMLCanvasElement {
    if (!canvas) canvas = document.createElement("canvas");
    if (canvas.width !== cw || canvas.height !== ch) {
      canvas.width = cw;
      canvas.height = ch;
    }
    return canvas;
  }

  function paintStroke(points: Point[], cw: number, ch: number, erase: boolean) {
    const ctx = ensureCanvas(cw, ch).getContext("2d")!;
    ctx.globalCompositeOperation = erase ? "destination-out" : "source-over";
    ctx.strokeStyle = "#000";
    ctx.lineWidth = brushSize.value;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.beginPath();
    points.forEach((p, i) => {
      const x = p.x * cw;
      const y = p.y * ch;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }

  function clearCanvas() {
    if (!canvas) return;
    const ctx = canvas.getContext("2d")!;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  }

  /** 开始一笔：清空上一标注掩码，置首点。 */
  function start(p: Point) {
    clearCanvas();
    strokes.value = [[{ ...p }]];
  }

  /** 追加轨迹点。 */
  function move(p: Point) {
    const cur = strokes.value;
    if (cur.length === 0) cur.push([]);
    (cur[cur.length - 1] ||= []).push({ ...p });
  }

  /** 结束一笔：把轨迹刷到画布 → 二值掩码 → 转 Polygon。 */
  function end(cw: number, ch: number): Annotation | null {
    if (strokes.value.length === 0) return null;
    const all: Point[] = [];
    strokes.value.forEach((s) => all.push(...s));
    paintStroke(all, cw, ch, erasing.value);
    const ctx = ensureCanvas(cw, ch).getContext("2d")!;
    const imageData = ctx.getImageData(0, 0, cw, ch);
    const mask = new Uint8Array(imageData.data.length / 4);
    for (let i = 0; i < mask.length; i++) mask[i] = imageData.data[i * 4 + 3] > 0 ? 1 : 0;
    const pts = maskToPolygon(mask, cw, ch);
    strokes.value = [];
    if (pts.length < 3) return null;
    return {
      id: crypto.randomUUID(),
      type: "Polygon" as const,
      class_id: 0,
      points: pts,
    };
  }

  function reset() {
    strokes.value = [];
    clearCanvas();
  }

  return { strokes, brushSize, erasing, start, move, end, reset };
}
```

> 说明：`end()` 的 `cw/ch` 由挂载插件在 `up` 时从 `DrawContext` 注入（见下方 `DrawContext.cw/ch` 扩展）。

- [ ] **Step 2: 三插件挂载 `brush` 工具**

以 `segmentation/index.ts` 为例（语义/全景同样，仅保留各自 `panel`/`renderer`/`color`）：

在 `import` 处加：
```ts
import BrushPreview from "../../core/BrushPreview.vue";
import { useBrushTool } from "../../core/brush";
```
`tools` 数组改为：
```ts
tools: [
  { name: "polygon", label: "实例分割", title: "逐点绘制，双击闭合" },
  { name: "brush", label: "画笔分割", title: "按住自由描画，松手转多边形" },
],
```

用 `toolMap` 同时提供 `polygon` + `brush` 两个可绘制工具（`tool` 单对象可省略，工作台经 `activeTool` 从 `toolMap` 按 `currentTool` 分发）：

```ts
toolMap: (() => {
  const seg = useSegmentTool();
  const brush = useBrushTool();
  return {
    polygon: {
      name: "polygon",
      preview: SegmentPreview,
      state: { points: seg.points },
      down(ctx) { const p = ctx.point; if (p) seg.addPoint(p); return null; },
      dblclick() { return seg.closePolygon(); },
      reset() { seg.points.value = []; },
    },
    brush: {
      name: "brush",
      preview: BrushPreview,
      state: { strokes: brush.strokes },
      down(ctx) { const p = ctx.point; if (p) brush.start(p); return null; },
      move(ctx) { const p = ctx.point; if (p) brush.move(p); },
      up(ctx) { return brush.end(ctx.cw ?? 0, ctx.ch ?? 0); },
      reset() { brush.reset(); },
    },
  };
})(),
```

> **依赖前置**：`DrawContext` 需增加可选 `cw`/`ch`（`types.ts`），工作台在下发 `down/move/up` 时填入画布像素尺寸 `canvas.cw.value`/`canvas.ch.value`，供画笔 `end` 使用。修改 `types.ts` 的 `DrawContext` 接口加 `cw?: number; ch?: number;`，并在 `AnnotationWorkbench.vue` 的 `tool.down/move/up` 调用处把 `cw`/`ch` 一并传入 ctx。

- [ ] **Step 3: type-check**

Run (在 `frontend/`): `pnpm run type-check`
Expected: 本模块无新增报错。

- [ ] **Step 4: 单元冒烟 + e2e 手动验证（可选，若 `up`/`cw` 尺寸未注入则先补齐）**

Run: `pnpm run test:unit`（确认既有纯函数单测仍绿）

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/core/brush.ts frontend/src/annotation/core/types.ts frontend/src/annotation/core/AnnotationWorkbench.vue frontend/src/annotation/tasks/segmentation/index.ts frontend/src/annotation/tasks/semanticSegmentation/index.ts frontend/src/annotation/tasks/panopticSegmentation/index.ts
git commit -m "feat(annotation): 三分割任务挂载画笔工具并支持多工具切换"
```

---

### Task 7: e2e 画笔创建流程 + 全量回归

**Files:**
- Create: `frontend/e2e/create-brush.spec.ts`

**Interfaces:**
- Consumes: `login`/`createAnnotationTask`/`gotoWorkbench`/`imageBox`/`expectAnnotation`（`e2e/anno-helper.ts`）。
- Produces: 验证「画笔分割」工具自由描画 → 生成 `Polygon` → 保存。

- [ ] **Step 1: 创建 e2e**

```ts
import { test, expect } from "@playwright/test";
import { login, createAnnotationTask, gotoWorkbench, imageBox, expectAnnotation } from "./anno-helper";

test("画笔自由描画生成多边形标注", async ({ page, request }) => {
  const auth = await login(request);
  const taskId = await createAnnotationTask(request, auth, "segmentation", "seg");
  await gotoWorkbench(page, taskId);

  // 切到「画笔分割」工具（按钮 hasText）
  await page.locator(".tool-btn", { hasText: "画笔分割" }).click();

  const img = await imageBox(page);
  // 按住拖动画一笔（mouse down → move → up）
  await page.mouse.move(img.x + img.width * 0.35, img.y + img.height * 0.35);
  await page.mouse.down();
  for (let i = 1; i <= 10; i++) {
    await page.mouse.move(
      img.x + img.width * (0.35 + i * 0.03),
      img.y + img.height * (0.35 + Math.sin(i / 2) * 0.05)
    );
  }
  await page.mouse.up();

  await expectAnnotation(page);
  await page.keyboard.press("Control+s");
  await expectAnnotation(page);
});
```

- [ ] **Step 2: 运行 e2e（需前后端运行）**

Run (在 `frontend/`): `npx playwright test e2e/create-brush.spec.ts --reporter=list`
Expected: 2 passed（含 auth setup）。若未生成标注，检查画笔 `up` 的 `cw/ch` 注入与 `maskToPolygon`。

- [ ] **Step 3: 全量回归**

Run (在 `frontend/`):
`npx playwright test e2e/create-polygon.spec.ts e2e/create-brush.spec.ts --reporter=list`
Expected: 通过（画笔 + 多边形不回归）。

Run (在 `frontend/`): `pnpm run type-check`
Expected: 无新模块报错。

- [ ] **Step 4: 提交**

```bash
git add frontend/e2e/create-brush.spec.ts
git commit -m "test(annotation): 新增画笔生成多边形标注 e2e"
```

---

### Task 8: 收尾验证与核对

**Files:**（无新文件，纯验证）

- [ ] **Step 1: 后端无回归（未改后端）**

Run (在 `backend/`): `uv run pytest tests/test_export_cuboid.py tests/test_export_xanylabeling.py -q`
Expected: PASS（确认后端导出未受影响）。

- [ ] **Step 2: 前端单测 + type-check + lint**

Run (在 `frontend/`): `pnpm run test:unit`；`pnpm run type-check`；`pnpm run lint`
Expected: 单测全绿；type-check 无本模块新增报错；lint 无本次引入。

- [ ] **Step 3: 汇总核对**

确认：`core/brush.ts` 导出 `useBrushTool`/`maskToPolygon`/`simplifyPolygon`；`core/BrushPreview.vue` 存在；`AnnotationTaskPlugin.toolMap` 与工作台 `activeTool` 分发生效；三分割插件 `tools` 含 `polygon`+`brush`。全部无误后结束。

---

## 相关文件汇总

- `frontend/vitest.config.ts`、`frontend/package.json`（vitest）
- `frontend/src/annotation/core/brush.ts`（`useBrushTool`/`maskToPolygon`/`simplifyPolygon`）
- `frontend/src/annotation/core/BrushPreview.vue`
- `frontend/src/annotation/core/types.ts`（`toolMap`、`DrawContext.cw/ch`）
- `frontend/src/annotation/core/AnnotationWorkbench.vue`（`activeTool` 分发）
- `frontend/src/annotation/core/__tests__/brush.test.ts`
- `frontend/src/annotation/tasks/{segmentation,semanticSegmentation,panopticSegmentation}/index.ts`
- `frontend/e2e/create-brush.spec.ts`
