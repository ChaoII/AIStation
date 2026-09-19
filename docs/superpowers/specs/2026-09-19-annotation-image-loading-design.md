# 标注工作台图片加载优化设计（渐进增强：缩略图优先）

日期：2026-09-19
分支：`feat/annotation-annotator`
范围：`frontend/src/annotation/`（可复用标注组件库，主要 `AnnotationWorkbench.vue` / `AnnotationCanvas.vue`）
前置：标注工作台组件化重构完成；实时交互性能优化（阶段一 rAF/缓存/拖拽脱离深响应式）已完成。

## 背景与问题

图片存于 RustFS（S3 兼容对象存储），单张通常 1080p / 2K，也可能 4K。当前工作台切图流程（`AnnotationWorkbench.vue` 的 `loadCurrentImage`）只请求全尺寸 presigned URL 并直接作为 `<img :src>` 显示，导致：

1. **从存储加载慢**：每次切图都从对象存储拉取原始全尺寸大图，无占位、无缓存、无预取，等待下载期间画布空白。
2. **界面渲染慢**：全尺寸大图在浏览器解码/绘制耗时，切图时卡顿/白屏。

## 关键现状（已确认）

- 后端在导入图片时已为每张图生成 **512px JPEG 缩略图**（`THUMBNAIL_MAX_SIDE = 512`，quality 85），并写入 `thumbnail_key`。
- `getImages` 列表接口返回的每项已含 `width`、`height`、`thumbnail_key`、`thumbnail_url`（对 `thumbnail_key` 的 presigned URL）。
- 工作台当前 `loadCurrentImage` **未使用** `thumbnail_url`，只拉全尺寸 URL。

## 方案选择

- **方案 A（仅渐进+缓存）**：缩略图优先 + 会话内缓存。改动最小，但无 decode 异步/zoom 保持等增强。
- **方案 B（后端多档+稳定 URL）**：后端生成多档尺寸 + 稳定缓存 URL。跨会话缓存最优，但改后端、成本高。
- **方案 C（前端渐进增强，选定）**：在 A 基础上叠加 `img.decode()` 异步解码、缩略图→全图替换不重置 zoom/pan、相邻图预取。复用现有 512 缩略图数据，不改后端。

**选定方案 C。**

## 用户确认

- 图片为 RustFS/S3 兼容对象存储，1080p/2K/4K 大图。
- 切图体验期望：**缩略图占位 → 渐进清晰**。

## 设计

### 1. 缩略图优先 + 全尺寸渐进替换

`loadCurrentImage(imageId)` 改为：

- 先取 `store.images` 中该项的 `thumbnail_url` 设为 `imgUrl`（立即显示；若无缩略图则直接走全尺寸）。
- 随后请求全尺寸 presigned URL；用 `new Image()` 预下载并 `img.decode()`（若支持）；成功后**仅当仍为当前图（token 校验）**时把 `imgUrl` 替换为全尺寸 URL。

说明：缩略图与全图共用同一 `<img>` 元素（`:src` 切换）。标注渲染在 SVG `viewBox`（全尺寸 `cw/ch`）上，`dw/dh` 为显示尺寸，与图像源分辨率无关——缩略图只是低分辨率源，CSS 拉伸到显示尺寸，全图到后自然变清晰。

### 2. zoom/pan 保持 + 渐进替换不重置视图

- 首次进入某张图（`imageLoaded` 由 false→true）时正常 `fitZoom`（基于全尺寸 `cw/ch` 与容器）。
- 全尺寸图替换时**不再触发 `fitZoom`**，保留当前 zoom/pan，仅更新 `<img>` 源。
- 实现：给 `AnnotationCanvas` 的 `onImgLoad` 加"是否已初始化缩放"守卫——只有首个 `img-load`（imageLoaded 首次置 true）时执行 `fitZoom`；后续源替换（缩略图→全图）只更新图像不重设缩放。
- 切换图片时仍按每张图首装载入、`fitZoom` 重置为默认适配视图。

### 3. 会话内全图缓存 + 相邻图预取 + decode 异步

- **全图缓存**：模块级 `Map<imageId, string>`（imageId → 全尺寸 presigned URL）。已缓存的图切到时直接复用 URL，不重复请求；并去重后台下载。组件卸载时清空缓存；用 LRU 或固定上限（如最近 20 张）控制内存。
- **相邻图预取**：进入某张图或翻页时，后台对当前 ±1（或当前页附近几张）的全尺寸 URL 发起 `new Image()` 预下载 + `decode()`，仅补缓存不与显示竞争，使下次切图命中缓存、秒换。
- **decode 异步**：全尺寸加载统一走 `img.decode()`（若支持）把解码从主线程解耦；缩略图加载失败/异常时回退到直接拉全尺寸。

## 明确不做（范围外）

- 不改后端（不生成多档尺寸、不动 presigned URL 过期/签名、不加 CDN 缓存头）。跨会话持久 HTTP 缓存不在本阶段。
- 不做 Canvas 2D 标注渲染迁移（属交互性能阶段二）。
- 不做缩略图/图片的磁盘或 Service Worker 持久缓存。

## 验收标准

- 切图时画布立即显示缩略图（近乎瞬时）且标注正确叠加；全尺寸下载完成后渐进变清晰且**不重置用户缩放/平移**。
- 会话内重复切回已看过的图：直接从缓存显示，不再重复请求全尺寸 URL。
- 切到相邻图（如下一张）明显更快（预取命中）。
- 大图（4K）切换时无明显主线程卡顿（`img.decode()` 生效）。
- `pnpm run type-check` 对 `src/annotation/` 无报错。
- 标注回归 e2e（`workbench`/`annotation-task-classes`/`annotation-history`）通过。

## 相关文件

- `frontend/src/annotation/core/AnnotationWorkbench.vue`：`loadCurrentImage`、`imgUrl`、预取与缓存逻辑、`fitZoom` 守卫、`loadImgToken`。
- `frontend/src/annotation/core/AnnotationCanvas.vue`：`onImgLoad`（fitZoom 守卫）、`<img>` 切换。
- `frontend/src/annotation/core/useAnnotationCanvas.ts`：`fitZoom`（若需按 zoom 保持调整）。
