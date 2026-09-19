# 标注工作台性能优化设计（阶段一——实时交互丝滑化）

日期：2026-09-19
分支：`feat/annotation-annotator`
范围：`frontend/src/annotation/`（可复用标注组件库）
前置：已完成标注工作台组件化重构（骨架 + 壳 + 6 任务插件 + 生产切换）

## 背景与问题

工作台画布在拖动/编辑标注、高密度标注、大图缩放/平移、切图时帧率不足、不够丝滑。核心痛点在于：

1. **`onMove` 逐事件全量重渲染**：`frontend/src/annotation/core/AnnotationWorkbench.vue` 中 `onMove` 在每次 `mousemove` 事件里逐属性突变响应式 store 对象（如 `ann.x1 = ...`），并每次调用 `store.markUnsaved()`。每个鼠标事件都触发一次整层（SVG 标注层 + HTML 标签层）重渲染。
2. **重复昂贵测量**：`tagStyle()` / `toImagePoint()` 对**每个标注、每帧**调用 `getCanvasEl().getBoundingClientRect()`。`getBoundingClientRect()` 会强制布局刷新（reflow），在标签层 `v-for` 中逐标签调用成本极高。
3. **拖拽期间深度响应式扩散**：拖拽中直接修改 deep-reactive 的标注对象，响应式系统把变更扩散到所有依赖该数组的模板绑定（SVG 层 + 标签层全部重算）。

## 方案选择

对用户主诉（帧率不足、不够丝滑）按最坏情况（高密度标注/大图）评估，提出三方案：

- **方案 A（仅渐进）**：rAF 合帧 + 拖拽局部渲染 + Pointer 事件。改动小，但标注层仍为 SVG DOM，高密度整体提升有限。
- **方案 B（直接 Canvas 2D）**：把 SVG 标注层整体迁到 `<canvas>` 2D 渲染。性能上限最高，但需重写全部任务插件渲染与命中逻辑，工作量大、回归面广。
- **方案 C（分两阶段，选定）**：阶段一先落地 rAF 合帧 + 缓存画布测量 + 拖拽脱离深响应式，快速解决"不跟手/掉帧"主诉；阶段二（后续）再把批量显示层抽为 Canvas 2D 渲染，应对高密度大图。

**选定方案 C**，本设计文档只覆盖**阶段一**。

## 用户对性能的确认

- 卡顿场景：拖动/编辑标注、标注数量多、大图缩放/平移、首次加载/切图（全选）。
- 最关键的：绘制出来不够丝滑、帧率低。
- 规模量级：按最坏情况（单图几百框以上、4K+）来设计。

## 阶段一设计

### 1. rAF 合帧调度

- 新增一个 rAF 调度器：`onMove` 不再直接处理逻辑，而是把最新事件存入 `pendingMove`，用 `requestAnimationFrame` 派发回调，**每帧只执行一次**真正的移动处理逻辑。
- 覆盖所有实时交互路径：拖框移动/缩放/旋转、移动关键点、移动多边形顶点、平移（空格）、绘制预览（box / rotated_box / keypoint / polygon）。
- 一帧内即使触发多次 mousemove，也只做一次状态更新 + 一次渲染。

实现要点：
- 引入 `scheduleMove(e)`，内部记录 `pendingMove = e`，若未调度 `rAF` 则调度；回调中取走 `pendingMove` 并执行原 `onMove` 逻辑。
- 监听/清理时机不变（`window.addEventListener("mousemove", scheduleMove)`，卸载时 `removeEventListener` 并取消未决的 `rAF`）。

### 2. 缓存画布测量，消除逐标注 getBoundingClientRect

- 用 `ResizeObserver` 监听画布容器尺寸，配合图片加载/平移/缩放，缓存 `canvasRect`（画布矩形）与画布容器原点。
- `toImagePoint()` / `tagStyle()` / 旋转框最近点计算不再对每个标注、每帧调用 `el.getBoundingClientRect()`，改为读缓存的矩形。
- 变更时机：`ResizeObserver` 回调、`@img-load`、`setImageSize`、初始挂载时更新一次缓存；浏览器窗口 resize 由 `ResizeObserver` 自动捕获。

实现要点：
- 在 `AnnotationWorkbench.vue`（或共享的 `useAnnotationCanvas` 钩子）维护 `canvasRectRef`（`shallowRef<DOMRect | null>`）与配套更新函数。
- `ResizeObserver` 观察画布容器 `.annotation-canvas` 元素，尺寸变化时重测并更新缓存。
- `tagStyle()` 中 `getCanvasEl().getBoundingClientRect()` 改为读取缓存矩形；`toImagePoint()` 同理。

### 3. 拖拽期间脱离深响应式，避免逐属性触发整层渲染

- 拖拽/编辑到 `mouseup` 之前，把该标注对象从 deep-reactive 追踪中临时脱离：拖拽开始时基于快照，拖拽中直接修改**非深响应式**的拖拽副本对象，`mouseup` 时才一次性写回 `store.annotations` 并 `markUnsaved()`。
- 拖拽期间只通过 rAF 每帧触发一次受控重绘（`bumpRenderTick` 一个 `shallowRef` 计数），保证视觉跟手但不再每个 mousemove 扩散到整层。
- SVG 标注层 + HTML 标签层都只在拖拽期间每帧重绘一次（而非每次 mousemove），解决"拖动不跟手/掉帧"。

实现要点：
- 拖拽开始时复制原标注为普通（非响应式）快照 `draft`，`dragState` 持有该 `draft`。
- 拖拽中修改 `draft`，并 `bumpRenderTick.value++`（在 rAF 内）以驱动每帧重绘。
- 渲染产物的来源：把 `draft` 注入到渲染层（模板上针对 `dragState.ann.id` 优先使用 `draft`，其余用 `store.annotations`），`mouseup` 时把 `draft` 写回 `store.annotations` 对应项并 `markUnsaved()`。
- 所有拖拽子类型（move / resize / rotate / kp-move / kp-resize / kp-vertex / poly-vertex）统一走此机制。

## 明确不做（阶段一范围外）

- 不迁移 Canvas 2D 渲染（留给阶段二）。
- 不改动 6 个任务插件的渲染/命中逻辑（仅注入拖拽副本驱动）。
- 不处理首次加载/切图的图片加载耗时（属阶段二/独立优化）。

## 验收标准

- 拖动标注框 / 关键点 / 多边形顶点 / 旋转框时，画面跟手、无逐 mousemove 的卡顿感。
- 平移（空格拖拽）、缩放（滚轮/Ctrl+滚轮）流畅。
- 拖动/编辑期间，SVG 标注层与 HTML 标签层每帧只重绘一次。
- `tagStyle()` / `toImagePoint()` 不再逐标注调用 `getBoundingClientRect()`。
- 标注相关 e2e（`workbench` / `annotation-task-classes` / `annotation-history`）全部通过；`pnpm run type-check` 对 `src/annotation/` 无报错。
- 用无头浏览器截图核对拖动/缩放前后画布、标签位置正确，风格与既有页面对齐。

## 相关文件

- `frontend/src/annotation/core/AnnotationWorkbench.vue`：`onMove`、`toImagePoint`、`tagStyle`、`dragState`、`markUnsaved`、`bumpRenderTick`。
- `frontend/src/annotation/core/useAnnotationCanvas.ts`：画布坐标系工具（`imageOffset`、`containerToImage`），缓存矩形可放此钩子。
- `frontend/src/annotation/core/AnnotationCanvas.vue`：画布容器元素，`ResizeObserver` 观察点。
