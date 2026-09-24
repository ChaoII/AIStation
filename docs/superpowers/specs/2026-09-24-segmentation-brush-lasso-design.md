# 画笔分割：新增「套索」子模式设计

日期：2026-09-24
模块：前端标注（`frontend/src/annotation`）· 实例分割（segmentation）画笔工具
状态：已确认

## 背景与目标

现有「画笔分割」是**涂抹**式：按笔刷粗细画线，松手后把笔迹连通区域转成多边形（`maskToPolygon`，带凸包兜底）。这种方式适合"涂满目标"。

但很多场景用户只想**沿目标外轮廓描一圈**，松手后自动首尾闭合、填充成一块区域（类套索/磁性套索）。本设计为画笔工具新增「套索」子模式，**保留现有涂抹**行为不变。

## 交互（已确认）

- 画笔工具内提供「涂抹 / 套索」两种子模式，可切换。
- 套索：随鼠标实时显示**细线笔迹**，松手**自动连上首尾闭合**、填充成一块实心多边形，**直接出一个标注**（单笔一个），无需二次确认。
- 涂抹：现有行为完全不变。

## 边界取法（已确认）

- 套索**忽略笔刷粗细**，直接取鼠标移动轨迹的**中心线**。
- 抽稀（合并过密/过近的点）后**首尾相连**，产生 ≥3 点的闭合多边形作为标注。
- 套索**不走 `maskToPolygon`**，直接以中心轨迹闭合多边形为结果。
- 内部空洞不计（沿用现状，不做甜甜圈带洞）。

## 实现方案

### 1. `brush.ts` — `useBrushTool` 增强

- 新增 `mode: Ref<"paint" | "lasso">`（默认 `"paint"`）与 `setMode(m)`。
- `end(cw, ch)` 按 `mode` 分流：
  - `"paint"`：维持现有逻辑（`paintStroke` → `maskToPolygon` → Polygon）。
  - `"lasso"`：取全部轨迹点（`strokes` 展平），按中心轨迹抽稀（合并距离小于阈值的相邻点），首尾相连，返回 ≥3 点的闭合 `Polygon`（`class_id: 0`）。

### 2. `segmentation/index.ts` — brush 工具装配

- `state` 暴露 `mode`（`brush.mode`），供预览组件与参数浮层使用。

### 3. `BrushPreview.vue` — 按模式渲染

- `"paint"`：按 `brushSize` 粗细线渲染（现状）。
- `"lasso"`：渲染**细线**笔迹，并在描边过程中显示「末点 → 首点」的**闭合虚线预览**。

### 4. UI：模式切换

- 画笔右键设置浮层（`brushPopover`，位于 `AnnotationWorkbench.vue`）中新增 `el-radio-group`（涂抹 / 套索），调用 `brush.setMode()`。

## 测试

- 新增 e2e `create-lasso.spec.ts`：套索模式沿目标描一圈 → 松手 → 生成闭合填充多边形标注并保存。
- `create-brush.spec.ts`（涂抹）保持通过，确保未回归。
- 前端单测：补套索的抽稀 / 首尾闭合逻辑（纯函数）单测。

## 明确不做（YAGNI）

- 不支持带内环（洞）的多边形（甜甜圈）——沿用现状。
- 不做磁性/吸附套索（沿边缘吸附）。当前仅为基础中心轨迹套索。

## 影响文件

- `frontend/src/annotation/core/brush.ts`
- `frontend/src/annotation/tasks/segmentation/index.ts`
- `frontend/src/annotation/core/BrushPreview.vue`
- `frontend/src/annotation/core/AnnotationWorkbench.vue`（右键浮层加模式切换）
- `frontend/e2e/create-lasso.spec.ts`（新增）
- `frontend/src/annotation/core/__tests__/brush.test.ts`（补套索单测）
