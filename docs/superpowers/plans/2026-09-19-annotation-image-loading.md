# 标注工作台图片加载优化（渐进增强）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 切图时立即用 512px 缩略图显示（秒开、标注立即可见），后台拉全尺寸渐进变清晰且不重置 zoom/pan；会话内缓存全图 URL、预取相邻图，用 `img.decode()` 异步解码消除大图解码卡顿。

**Architecture:** 改动集中在 `frontend/src/annotation/core/AnnotationWorkbench.vue` 与 `AnnotationCanvas.vue`。核心：①图像尺寸改用图片列表返回的 `width/height` 元数据（不再依赖 `<img>` natural 尺寸，否则缩略图会错设 cw/ch）；②缩略图优先显示 + 全尺寸后台预载替换；③全图 URL 缓存 + 相邻图预取 + `decode` 异步。

**Tech Stack:** Vue 3 `<script setup>` + `ref`、`Map` 缓存、`new Image()` + `img.decode()`、presigned URL（复用现有 `getPresignedUrl`）。

## Global Constraints

- 中文回复；提交信息 `feat(annotation): 中文描述`。
- 只改 `frontend/src/annotation/core/AnnotationWorkbench.vue` 与 `frontend/src/annotation/core/AnnotationCanvas.vue`，不动后端、不动任务插件。
- `pnpm exec vue-tsc --noEmit --skipLibCheck` 对 `src/annotation/` 必须无报错（`module_generator`/`module_monitor` 既有报错无关）。
- 标注回归 e2e：`e2e/workbench.spec.ts`、`e2e/annotation-task-classes.spec.ts`、`e2e/annotation-history.spec.ts`（`pnpm exec playwright test <file> --reporter=line`）。
- 验收：切图立即显示缩略图且标注正确叠加；全图到后渐进清晰且**不重置缩放/平移**；重复切回已看图不重复拉全图；相邻图预取命中；`img.decode()` 生效；type-check 无 annotation 报错；上述 e2e 通过。
- 图像权威尺寸：`store.images` 列表项里的 `width` / `height`（图片列表接口已返回）。`store.images` 元素类型为 `any`，可直接访问 `img.width`、`img.height`、`img.thumbnail_url`。

---

### Task 1: 图像尺寸以元数据为准 + 缩略图优先显示 + 首次 fitZoom 守卫

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationCanvas.vue`
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Consumes: `AnnotationCanvas` 模板 `@img-load`（emit `(naturalW, naturalH)`）；`useAnnotationCanvas` 的 `setImageSize(w,h)` / `fitZoom(w,h)` / `cw` / `ch`；`canvasR()`（画布矩形缓存，已存在）。
- Produces: `AnnotationWorkbench` 中模块级 `fittedForImage: boolean`；`onImgLoad(w, h)` 改为接收 `naturalW/naturalH`；`loadCurrentImage` 改为先用 `thumbnail_url` 显示并预置元数据尺寸。

- [ ] **Step 1: `AnnotationCanvas.vue` 的 `onImgLoad` 不再自设尺寸/缩放**

把 `AnnotationCanvas.vue` 中（约第 43-49 行）：

```ts
function onImgLoad(e: Event) {
  const el = e.target as HTMLImageElement;
  canvas.setImageSize(el.naturalWidth, el.naturalHeight);
  const r = wrap.value?.getBoundingClientRect();
  if (r) canvas.fitZoom(r.width, r.height);
  emit("img-load", el.naturalWidth, el.naturalHeight);
}
```

改为：

```ts
function onImgLoad(e: Event) {
  const el = e.target as HTMLImageElement;
  emit("img-load", el.naturalWidth, el.naturalHeight);
}
```

（尺寸与缩放改由父组件 `AnnotationWorkbench` 控制。）

- [ ] **Step 2: `AnnotationWorkbench.vue` 新增 `fittedForImage` 并对 `onImgLoad` 加守卫**

在模块级 `let loadImgToken = 0;`（约第 543 行）附近加：

```ts
let fittedForImage = false;
```

把 `AnnotationWorkbench.vue` 的 `onImgLoad`（约第 843-846 行）改为：

```ts
function onImgLoad(w: number, h: number) {
  imageLoaded.value = true;
  measureCanvas();
  if (!canvas.cw.value && w && h) canvas.setImageSize(w, h);
  if (!fittedForImage) {
    const r = canvasR();
    if (r.width && r.height && canvas.cw.value && canvas.ch.value) {
      canvas.fitZoom(r.width, r.height);
      fittedForImage = true;
    }
  }
}
```

（模板 `@img-load="onImgLoad"` 不变，`emit("img-load", naturalW, naturalH)` 会把两个参数传给 `(w,h)`。）

- [ ] **Step 3: `loadCurrentImage` 改用元数据尺寸并先显示缩略图**

把 `loadCurrentImage` 开头（约第 890-905 行）调整为：在取得 `imageId` 后，从 `store.images` 查 `imgInfo`，用其 `width/height` 预置 `canvas.setImageSize`，并把 `imgUrl` 先设为 `thumbnail_url`。参考代码（替换第 890-905 行）：

```ts
async function loadCurrentImage(imageId: number) {
  const myToken = ++loadImgToken;
  resetDrawingState();
  // 切图：先释放上一张锁
  if (lockedImageId && lockedImageId !== imageId) unlockCurrent();
  imgUrl.value = "";
  imageLoaded.value = false;
  fittedForImage = false;
  store.selectedAnnotationId = "";
  store.annotations = [];
  store.unsaved = false;
  lockedByOther.value = false;
  lockedByUser.value = null;
  const imgInfo = store.images.find((i) => i.id === imageId);
  if (imgInfo?.width && imgInfo?.height) canvas.setImageSize(imgInfo.width, imgInfo.height);
  // 先显示缩略图（秒开）；无缩略图则留空，由后续全图填充
  imgUrl.value = imgInfo?.thumbnail_url || "";
  try {
    const r = await props.api.getPresignedUrl(imageId, store.taskId);
    if (myToken !== loadImgToken) return;
    imgUrl.value = r?.data?.data?.url || imgUrl.value;
```

（保留 `loadCurrentImage` 后续的 `loadAnnotations` 与锁续期逻辑不变。）

- [ ] **Step 4: 验证 type-check**

Run: `cd frontend; pnpm exec vue-tsc --noEmit --skipLibCheck 2>&1 | Select-String "annotation"` — Expected: 无输出。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/annotation/core/AnnotationCanvas.vue frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "feat(annotation): 图像尺寸以元数据为准，切图先显示缩略图并首次适配"
```

---

### Task 2: 全图后台预载渐进替换 + 全图 URL 缓存 + 相邻图预取 + decode 异步

**Files:**
- Modify: `frontend/src/annotation/core/AnnotationWorkbench.vue`

**Interfaces:**
- Consumes: `loadCurrentImage`（Task 1 已改）、`imgUrl`、`loadImgToken`、`fittedForImage`、`props.api.getPresignedUrl`、`goToImage`。
- Produces: 模块级 `fullUrlCache: Map<number, string>`；`preloadFull(fullUrl, imageId, myToken)`；`prefetchNeighbors()`；`warmFull(id, url)`；`addToCache(id, url)`（带容量上限）。`goToImage` / `init` 末尾调用 `prefetchNeighbors()`。

- [ ] **Step 1: 新增全图 URL 缓存（带上限）与辅助函数**

在模块级（`let fittedForImage = false;` 附近）加：

```ts
const FULL_CACHE_MAX = 20;
const fullUrlCache = new Map<number, string>();
function addToCache(id: number, url: string) {
  if (fullUrlCache.has(id)) fullUrlCache.delete(id);
  fullUrlCache.set(id, url);
  if (fullUrlCache.size > FULL_CACHE_MAX) {
    const first = fullUrlCache.keys().next().value;
    if (first !== undefined) fullUrlCache.delete(first);
  }
}
function warmFull(id: number, url: string) {
  const img = new Image();
  img.onload = () => { if (img.decode) img.decode().catch(() => {}); };
  img.onerror = () => {};
  img.src = url;
}
function preloadFull(fullUrl: string, imageId: number, myToken: number) {
  const img = new Image();
  const done = () => {
    if (myToken !== loadImgToken) return;
    addToCache(imageId, fullUrl);
    if (imgUrl.value !== fullUrl) imgUrl.value = fullUrl;
  };
  img.onload = () => { if (img.decode) img.decode().catch(() => {}).finally(done); else done(); };
  img.onerror = () => {};
  img.src = fullUrl;
}
function prefetchNeighbors() {
  const idx = store.currentImageIndex;
  const targets: number[] = [];
  if (idx > 0) targets.push(store.images[idx - 1]?.id);
  if (idx < store.images.length - 1) targets.push(store.images[idx + 1]?.id);
  for (const id of targets) {
    if (!id) continue;
    if (fullUrlCache.has(id)) { warmFull(id, fullUrlCache.get(id)!); continue; }
    props.api
      .getPresignedUrl(id, store.taskId)
      .then((r: any) => {
        const u = r?.data?.data?.url;
        if (u) { addToCache(id, u); warmFull(id, u); }
      })
      .catch(() => {});
  }
}
```

- [ ] **Step 2: `loadCurrentImage` 接入缓存与后台预载**

把 Task 1 Step 3 改出的 `loadCurrentImage` 中 `try { ... }` 内（约第 903-905 行附近）的逻辑替换为：

```ts
  try {
    // 已缓存的全图 URL：直接显示，秒开
    const cachedUrl = fullUrlCache.get(imageId);
    if (cachedUrl) {
      imgUrl.value = cachedUrl;
    } else if (!imgInfo?.thumbnail_url) {
      // 无缩略图：去请求全图
      const r = await props.api.getPresignedUrl(imageId, store.taskId);
      if (myToken !== loadImgToken) return;
      const fu = r?.data?.data?.url || "";
      if (fu) { addToCache(imageId, fu); imgUrl.value = fu; }
    } else {
      // 有缩略图（已显示）：后台请求全图并渐进替换
      props.api
        .getPresignedUrl(imageId, store.taskId)
        .then((r: any) => {
          if (myToken !== loadImgToken) return;
          const fu = r?.data?.data?.url || "";
          if (fu) preloadFull(fu, imageId, myToken);
        })
        .catch(() => {});
    }
```

（`imgInfo` 在函数开头已声明，`imgUrl.value = imgInfo?.thumbnail_url || "";` 保留在 `try` 之前。）

- [ ] **Step 3: `goToImage` 与 `init` 末尾触发相邻图预取**

在 `goToImage`（约第 1029 行）中，`loadCurrentImage(store.images[idx].id);` 之后加：

```ts
prefetchNeighbors();
```

在 `init`（约第 1018 行）中，`await loadCurrentImage(store.images[0].id);` 之后加：

```ts
prefetchNeighbors();
```

- [ ] **Step 4: 卸载时清空缓存**

在 `AnnotationWorkbench.vue` 的 `onBeforeUnmount`（靠近 `unmounted = true;`）加：

```ts
fullUrlCache.clear();
```

- [ ] **Step 5: 验证 type-check**

Run: `cd frontend; pnpm exec vue-tsc --noEmit --skipLibCheck 2>&1 | Select-String "annotation"` — Expected: 无输出。

- [ ] **Step 6: 运行标注回归 e2e**

Run: `cd frontend; pnpm exec playwright test e2e/workbench.spec.ts e2e/annotation-task-classes.spec.ts e2e/annotation-history.spec.ts --reporter=line`
Expected: 5 passed。

- [ ] **Step 7: 提交**

```bash
git add frontend/src/annotation/core/AnnotationWorkbench.vue
git commit -m "feat(annotation): 全图后台预载渐进替换，缓存全图URL并预取相邻图，decode异步"
```

---

## 自审检查

- **Spec 覆盖**：§1 缩略图优先+渐进替换 = Task 1（缩略图显示）+ Task 2（后台全图替换）；§2 zoom/pan 保持 = Task 1 `fittedForImage` 守卫（只在首次 fitZoom）；§3 缓存+预取+decode = Task 2。三者与 spec 三节对应。
- **占位符**：无 TBD/TODO，所有改动含具体代码与行号。
- **类型一致**：`fittedForImage` / `fullUrlCache` / `addToCache` / `warmFull` / `preloadFull` / `prefetchNeighbors` 各 Task 间命名一致；`onImgLoad(w,h)` 与 `emit("img-load", naturalW, naturalH)` 参数一致。
- **关键正确性**：图像尺寸用 `imgInfo.width/height` 元数据（避免缩略图 natural 尺寸错设 cw/ch）；首次 `fitZoom` 用 `fittedForImage` 守卫，全图替换不重置 zoom。
