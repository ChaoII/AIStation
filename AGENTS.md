# AIStation — Agent Guide

## 交流语言

- 向用户提问（question 工具）、汇报进度、总结结果时，一律使用中文。
- 代码注释使用中文；提交信息使用 `fix(train): 中文描述` 等中文描述格式。

## Quick Start

## Setup

```bash
# Backend — create Python 3.13 virtual env, install deps with Tsinghua mirror
cd backend
uv venv --python 3.13   # creates .venv/ with Python 3.13
uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple

# Start backend (first run auto-inits DB schema + seed data)
uv run main.py run --env=dev

# Lint
uv run ruff check && uv run ruff check --fix

# Alembic (only needed after model changes)
uv run main.py revision --env=dev
uv run main.py upgrade --env=dev

# Frontend
cd frontend && pnpm install
pnpm run dev                   # Vite at http://localhost:5180
pnpm run type-check            # vue-tsc --noEmit --skipLibCheck
pnpm run lint                  # eslint + prettier + stylelint
```

## Architecture

**Monorepo**: `backend/` (FastAPI + SQLAlchemy 2.0 + Pydantic v2), `frontend/` (Vue 3 + Vite + Element Plus + TypeScript).

### Backend — package-by-feature (vertical slices)

Each business module under `app/api/v1/module_*/` contains:

```
controller.py  →  service.py  →  crud.py  →  model.py  schema.py  param.py
```

Static routes are wired explicitly in `app/scripts/init_app.py:register_routers()`.  
Dynamic routes auto-discovered from `app/plugin/module_*/**/controller.py` via `app/core/discover.py`.

**Important**: New submodules under `app/api/v1/module_*` **must** be manually imported in that module's `__init__.py` and registered in `register_routers()`. Plugin modules (`app/plugin/`), however, are auto-discovered.

### Backend model base classes (`app/core/base_model.py`)

- **`MappedBase`** — bare DeclarativeBase with `__permission_strategy__`. No common columns.
- **`ModelMixin(MappedBase)`** — adds id, uuid, status, created_time, updated_time, is_deleted, deleted_time.
- **`UserMixin(MappedBase)`** — adds created_id, updated_id, deleted_id + FK relationships.
- **`TenantMixin(MappedBase)`** — adds tenant_id FK.

Models that inherit only `MappedBase` (e.g., `CameraGroupModel`) have **no soft-delete, no user audit fields**. CRUDBase's `delete()` will physically delete them.

### Backend CRUDBase (`app/core/base_crud.py`)

Generic class `CRUDBase[ModelType, CreateSchemaType, UpdateSchemaType]` provides:  
`get`, `list`, `tree_list`, `page`, `create`, `update`, `delete`, `clear`, `set`, `restore`.

- Query conditions: `[("like", value)]`, `[("eq", value)]`, `[("between", (min, max))]`, etc.
- `page()` returns `{page_no, page_size, total, has_next, items}`.
- `delete()` soft-deletes if model has `is_deleted` field, otherwise physical delete.
- Auto-filters by data-scope permissions via `__permission_strategy__`.

### Frontend page CRUD pattern

Every CRUD page follows:

```
PageSearch (search form, config-driven) +
PageContent (table, config-driven) +
EnhancedDialog (create/update form)
```

Key imports:
- `useCrudList()` from `@/components/CURD/useCrudList` — provides `searchRef`, `contentRef`, `handleQueryClick`, `handleResetClick`, `refreshList`.
- `v-hasPerm` directive — removes DOM element if user lacks permission string.
- `contentConfig.indexAction` — async function returning `{ total, list }`.
- `contentConfig.deleteAction` — async function receiving comma-separated IDs.

Backend `page_size` is **not constrained server-side**; the CRUDBase.page accepts any valid integer.

### API conventions

- Prefix: `ROOT_PATH = "/api/v1"`
- Response: `SuccessResponse(data=..., msg="...")` / `ErrorResponse(msg="...")`.
- Pagination request: `page_no`, `page_size` query params.
- Pagination response: `{ page_no, page_size, total, has_next, items }`.
- Auth: every endpoint uses `Depends(AuthPermission(["module:feature:action"]))`.
- Datetime serialization: `DateTimeStr` / `DateStr` / `TimeStr` in `app/core/validator.py` — use `model_dump(mode='json')` for Redis writes.

### Environment & services

- DB: PostgreSQL, configured in `backend/env/.env.dev`. Also supports MySQL / SQLite.
- Redis: required. Configured in same `.env.dev` file.
- Ports: backend `8001`, frontend `5180`.
- Login: admin / 123456 (from seed data). Captcha is required.
- Docker Compose: `docker-compose.yaml` includes postgres:17, redis:7, zlmediakit.

### Menu + permission registration

New menu entries must be:
1. Inserted into `sys_menu` table (seed data only runs on empty DB).
2. Assigned to admin role via `sys_role_menus`.
For existing DBs, use the menu management UI or manual `INSERT`.

### Notable gotchas

- `auth/dependencies.py` has a circular import that does not block normal runtime.
- Frontend `src/views/` (not `src/view/` as some docs say).
- Frontend router is hash-based (`createWebHashHistory`); dynamic routes come from backend menu data.
- Pre-existing lint errors exist in `LivePlayer.vue`, `live/index.vue`, `playback/index.vue` (unrelated to new work).
- When creating a model that inherits `MappedBase` directly (no `ModelMixin`), CRUDBase skips `created_id`/`updated_id` but also skips soft-delete.
- Tree structures use `parent_id` FK + `children` relationship + `traversal_to_tree(flat_dicts)` from `app/utils/common_util.py`.
- Frontend API functions are named `getXxxList`, `getXxxDetail`, `createXxx`, `updateXxx`, `deleteXxx` — co-located by module in `src/api/`.

### Gotcha: `v-model` with separate reactive object + dynamic keys

When using `v-for="(val, key) in objA"` with `v-model="objB[key]"` where `objB` is a **separate** reactive object populated from `objA`, the initial value may not be tracked correctly by Vue 3's reactivity system — especially with `el-switch` (boolean values appear as `undefined` despite being set).  

**Fix**: bind `v-model` directly to the same object being iterated: `v-model="objA[key]"`. No intermediate mapping object.

### Gotcha: Using `watch` vs `@change` for async data loading

A `watch` on a reactive property that triggers an async data load can race with other code that also modifies the same property. **Use `@change` on the form control instead** + a dedicated async handler function. This guarantees synchronous control flow and avoids double-fetch/race conditions.

### Gotcha: Multi-root component inside `<Transition mode="out-in">` causes white screen

When a component with **two or more root elements** in its `<template>` is rendered inside `<transition mode="out-in">` (e.g., via `<router-view>`), Vue cannot animate the leave transition. The `<Transition>` component hangs waiting for the leave animation to complete, so the **enter phase never starts** and the next page never mounts — resulting in a blank white screen.

Vue logs: `"Component inside <Transition> renders non-element root node that cannot be animated"`.

**Fix**: Ensure the component has exactly **one root element** by wrapping all content (including dialogs, modals, etc.) inside a single container `<div>`. For example, move `<el-dialog>` from a sibling position to inside the main container div:

```html
<!-- ❌ BAD: two roots -->
<template>
  <div class="page">...</div>
  <el-dialog v-model="visible">...</el-dialog>
</template>

<!-- ✅ GOOD: single root, dialog inside wrapper -->
<template>
  <div class="page">
    ...
    <el-dialog v-model="visible">...</el-dialog>
  </div>
</template>
```

## 标注标签渲染经验（标注重中之重）

### 坐标系统
- SVG `viewBox="0 0 cw ch"`，CSS大小 `dw = cw * zoom`，1 viewBox单位 = zoom CSS像素
- 所有 `getBBox()` 返回值在 viewBox 坐标系

### 文字 `<text>` 属性关键
| 属性 | 作用 |
|------|------|
| `y` | 默认是 **基线**（baseline），中文基线在字符底部 |
| `dominant-baseline="text-after-edge"` | **强制** y=文字最底部，不依赖字体基线 |
| `text-anchor="start"` | 文字从左到右，x 是文字左边缘 |
| `font-size="6"` | 6 viewBox单位，不用 `style="font-size:6px"`（CSS像素会和 getBBox 测量不一致） |
| `font-family="Microsoft YaHei,sans-serif"` | 必须设置，否则默认字体影响 getBBox |

### 标签布局公式（AxisAlignedBox）
```
框左上角 = (ann.x1*cw, ann.y1*ch)
文字底部 = 框上 - 2 (2px间隙)
文字y = ann.y1*ch - 2, dominant-baseline="text-after-edge"
文字x = ann.x1*cw + 2 (框左边+2px)
文字大小 = font-size="6"

背景框:
  左边 = ann.x1*cw (和框左边对齐)
  底部 = ann.y1*ch (和框上边对齐)
  宽 = getBBox文字宽 + 2 (2px边距)
  高 = getBBox文字高 + 4 (含2px下间隙+2px上边距)
  背景y = 框上 - 文字高 - 4
  背景底部 = 背景y + 背景高 = 框上 ✅
```

### 标签布局公式（RotatedBox）
```
旋转后左上角 = rbHandlePos(ann, 'tl', cw, ch)
文字底部 = 旋转后左上角.y - 2
文字x = 旋转后左上角.x + 2
文字大小 = font-size="6", dominant-baseline="text-after-edge"

背景框:
  左边 = 旋转后左上角.x
  底部 = 旋转后左上角.y
  宽高 / 边距 / 填充 与 AxisAlignedBox 完全一致
```

### 测量流程
```js
// 1. 先渲染文字（`font-size="6"` SVG属性，不要CSS像素）
// 2. 等100ms让SVG完成布局
// 3. getBBox() 获取实际渲染宽高
// 4. 用测量值设置背景框宽高
// 5. 测量值存到 labelTextRects Map，后续通过 ann.id 取用
```

### 关键陷阱
- ❌ 不要混用 `font-size="6"`（SVG属性）和 `style="font-size:6px"`（CSS）→ getBBox 测不准
- ❌ 不要让文字基线直接用 `y=框上` → 文字可能比框线低（字体基线问题）
- ✅ 用 `dominant-baseline="text-after-edge"` 解决
- ✅ 背景宽高都用 getBBox 实测值 + 固定边距，不猜
```

## 调试记忆：Vue scoped CSS + el-card flex shrink 导致内容不可见

### 问题现象
页面渲染后，部分 `<el-card>` 内部内容完全不可见，但 Vue 模板正常渲染、数据正确加载。

### 根因链
1. **全局 `.app-container`** 有 `display: flex; flex-direction: column; height: 100%; overflow: auto`
2. **`el-card`** 自带 `overflow: hidden` → 在 flex 容器中触发 CSS 规范：`overflow != visible` 时 `min-height` 被设为 `0`（而非默认的 `auto`）
3. 当 flex 容器有**确定高度**（`height: 100%` 继承自父级）且子项总高度超出时，flex 算法收缩所有 `flex-shrink: 1` 的子项
4. `el-card` 因 `min-height: 0` 可被收缩到**近零高度**，其内部内容被 `overflow: hidden` 裁剪，表现为"不见了"

### 调试方法（当怀疑 scoped CSS 未生效时）
1. 在模板顶部添加可见的调试元素（如 `<div class="debug-bar">{{ state }}</div>`）
2. 在 scoped 和非 scoped 中分别设置不同样式（如 `background: #ffeeba`）
3. 若 scoped 样式未生效但非 scoped 生效 → 判定 scoped CSS 的 `data-v-xxx` hash 不匹配

### 修复方案
**不要依赖 scoped CSS 覆盖全局 `.app-container` 的 flex 布局**。改用**非 scoped `<style>` 块** + 唯一类选择器：

```vue
<style lang="scss">
.app-container.train-detail-page {
  display: block !important;
  height: auto !important;
  overflow: visible !important;
}
</style>
```

并在根元素上同时使用两个 class：`<div class="app-container train-detail-page">`

### 已知限制
- `data-v-xxx` hash 可能在 keep-alive 缓存 + Vite HMR 场景下不同步，原因尚不完全明确
- 非 scoped 样式是已知可靠的回避方案
- flex 容器中只要同时满足：确定高度 + `overflow != visible` + `flex-shrink: 1`，就存在收缩风险

### 相关文件
- `frontend/src/views/module_train/task/detail.vue` — 问题页面，非 scoped 修复入口
- `frontend/src/styles/index.scss` — 全局 `.app-container` 定义
- `frontend/src/layouts/components/AppMain/index.vue` — 父容器 `.app-main`

---

## 调试记忆：Dashboard 图表布局被全局样式覆盖（CSS Grid 失效）

### 问题现象
Dashboard `index.vue` 图表区使用自定义 CSS Grid (`display: grid; grid-template-columns: 1fr 1fr`)，但始终渲染为单列，无法两列并排。el-card 不随 grid 父容器分流。

### 排查过程（踩坑记录）
1. 确认模板通过简单的 `<div class="dash-charts">` 包裹 el-card
2. 确认 `.dash-charts { display: grid; grid-template-columns: 1fr 1fr; }` 已写入全局 `dashboard.css`
3. 确认 `main.ts` 已正确 `import "@/styles/dashboard.css"`
4. 确认无 scoped style 覆盖
5. 在 `dashboard.css` 加 `!important` 仍无效
6. 在 `dashboard.css` 的 `.dash-charts` 加红色背景 → 确认 CSS 文件已加载
7. 仍单列 → CSS 中 `display: grid` 和 `grid-template-columns` 被更深层规则覆盖
8. 在 `.dash-charts` 上加内联 `style="display: grid !important; grid-template-columns: 1fr 1fr !important;"` → 终于生效，确认并排
9. 但 `!important` 会让手机端无法自适应单列 → 不可持续
10. 最终改用 **Element Plus 原生 `el-row` / `el-col`** 立即解决：`<el-col :xs="24" :sm="24" :md="12" :lg="12">`

### 根因分析
- **未完全确认的根因**：项目存在复杂的 CSS 层叠（Element Plus 全局样式、UnoCSS、scss 变量、其他全局 CSS），自写的 `display: grid` 被某条全局规则覆盖
- `@media (width <= 1100px)` 曾把 `.dash-charts` 改成 `1fr`，是一次直接触发因素
- **核心教训**：在这个项目中，**自定义 CSS Grid/Flex 布局在主布局级不稳定**，容易被全局样式或响应式断点意外覆盖

### 修复方案（ definitive fix ）
```html
<el-row :gutter="12">
  <el-col :xs="24" :sm="24" :md="12" :lg="12">...</el-col>
  <el-col :xs="24" :sm="24" :md="12" :lg="12">...</el-col>
</el-row>
```

### 预防措施（以后不要再踩）
1. **优先使用 Element Plus 栅格 (`el-row` / `el-col`)**：这是项目已深度集成的响应式布局方案，不会被全局 CSS 覆盖
2. **谨慎使用自定义 CSS Grid**：仅在 Element Plus 栅格无法满足的极端场景使用，且必须加 `!important` 兜底
3. **媒体查询断点统一用 `max-width`**：避免使用 `@media (width <= Xpx)` 这种非常规语法，减少意外覆盖风险
4. **调试 CSS 时先加视觉标记**：如 `background: red !important`，确认"规则是否被加载"比确认"规则内容"更重要
5. **如果 3 次以上 CSS patch 都失效 → 立即换架构**：不要继续在 CSS 层加 `!important` 叠加，应切换到框架原生组件

### 相关文件
- `frontend/src/views/dashboard/index.vue` — 问题页面，已改为 el-row/el-col
- `frontend/src/styles/dashboard.css` — 原自定义 CSS Grid 定义地

### 同类风险文件（其他可能存在相似布局覆盖问题的位置）
这些文件使用了自定义 CSS Grid/Flex，若出现布局异常，优先考虑改用 el-row/el-col：

| 文件 | 风险点 | 当前状态 |
|------|--------|----------|
| `frontend/src/styles/train-detail.css` | ~~`.info-cards`、`.chart-row`、`.metric-grid` 使用 CSS Grid~~ | **已修复** — grid 规则已删除，布局移交 el-row/el-col |
| `frontend/src/views/dashboard/workplace.vue` | 多个 `display: flex/grid` + `@media (width <= ...)` | 使用 scoped 样式，风险较低但已有非标准媒体查询语法 |
| `frontend/src/styles/dashboard.css` | ~~`.dash-metrics`、`.dash-footer`、`.dash-charts` 使用 CSS Grid~~ | **已修复** — 全部迁移到 el-row/el-col，只保留视觉装饰类 |

### 媒体查询语法警告
项目内多处使用非标准语法 `@media (width <= Xpx)`，这在部分浏览器/场景下可能表现不一致。建议统一改用标准写法：
```css
/* ❌ 非常规，可能在某些场景失效 */
@media (width <= 1100px) { ... }

/* ✅ 标准写法，兼容性最好 */
@media (max-width: 1100px) { ... }
```

---

## OCR 模型规格（pytorch-ocr）

### PP-OCRv6 det 规格（configs/det/PP-OCRv6/*.yml）

| 规格 | Backbone | Neck | out | dilated | Head aux | EMA | box_thresh |
|------|----------|------|-----|---------|----------|-----|-----------|
| tiny | PPLCNetV4 tiny | RepLKFPN | 64 | 5 | aux_in 64 | 0.9998 | 0.4 |
| small | PPLCNetV4 small | RepLKFPN | 96 | 7 | aux_in 96 | 0.9997 | 0.45 |
| medium | PPLCNetV4 medium | **RepLKPAN** | 256 | - | aux_in 256 | 0.9996 | 0.45 |

- DBLoss: `main_loss_type=DiceFocalLoss`, alpha=5, beta=10, focal_alpha=0.25, focal_gamma=2.5, aux_weight p4/p3/p2 = 0.2/0.3/0.4
- CLI: `train-det --model-size {tiny,small,medium} --neck {rep_lk_fpn,rep_lk_pan} --pretrained <det_converted.pt> [--freeze-backbone]`

### PP-OCRv6 rec 规格（configs/rec/PP-OCRv6/*.yml）

| 规格 | Backbone | CTCHead neck | dims | mlp_ratio | NRTR dim | dict |
|------|----------|-------------|------|-----------|----------|------|
| tiny | PPLCNetV4 tiny | reshape (use_guide+mid80) | - | - | 384 | ppocrv6_tiny_dict (6904) |
| small | PPLCNetV4 small | **lightsvtr** | 120 | 2.0 | 384 | ppocrv6_dict (18707) |
| medium | PPLCNetV4 medium | **lightsvtr** | 192 | 4.0 | **512** | ppocrv6_dict (18707) |

- CTC 词表 = dict + space + blank（tiny: 6904+1+1=6906；small/medium: 18707+1+1≈18710）
- NRTR 词表 = CTC 词表 + 4 特殊 token（tiny 6910, small/medium 18714）——转换加载时这 2 层 shape 不匹配会被跳过（可接受，NRTR 是辅助头）
- CLI: `train-rec --model-size {tiny,small,medium} --dict <dict.txt> --pretrained <rec_converted.pt>`

### 权重转换

- det: `convert_ppocr_v6_det(paddle_state, model_size, fpn_out_channels, neck, dilated_kernel_size, intracl, aux_in_channels)` → 官方 .pdparams 语义名映射
- rec: `convert_ppocr_v6_rec(paddle_state, model_size, out_channels, neck)` → lightsvtr 需 `neck="lightsvtr"`
- 官方权重 URL: `https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv6_{size}_{det|rec}_pretrained.pdparams`
- 注意 det/rec 权重文件名需区分（如 `PP-OCRv6_small_det_converted.pt` / `PP-OCRv6_small_rec_converted.pt`），避免覆盖

### 训练要点（对照官方 PaddleOCR 发现）

- **DBLoss shrink 通道必须用 DiceFocalLoss（Dice + mask 内 Focal）**，纯 BCE 在文字占 2% 时梯度被背景稀释 → 模型全零崩溃
- **EMA**（ema_decay 0.9996-0.9998）抑制小数据集梯度噪声（BN bias 梯度可到 1212 量级）
- **eval 用官方 DetResizeForTest**（limit_side_len=736 min + round 32 → 实际近原尺寸），640×640 会低估 hmean 0.13-0.17
- 微调小数据集 det 时 **freeze-backbone**（BN 梯度爆炸会摧毁预训练权重）
- PP-OCRv5 det 用 PPLCNetV3+RSEFPN+DiceLoss，与 v6 架构不同，无法直接对比数字

### pytorch-ocr 训练对齐经验（2026-08 深入排查）

**结论**：逐行对照官方 PaddleOCR config + train.py 做了 15 轮对齐，pytorch det 训练从 0.79 提升到 **0.82**（v18 配置），但无法达到 PaddleX 训练的 0.93。剩余差距是 Paddle 框架级数值行为，代码层面无法完全复现。

**v18 最佳 det 训练配置**（`cfg_small_v6_full.json`）：
- `lr=0.001`（官方 small，不是 0.0005！medium 才是 0.0005）
- `ema_decay=0.9997`（small；tiny 0.9998，medium 0.9996）
- `RandomCropV6`（官方 v6 用 RandomCrop，不是 EastRandomCropData！v5 才用 EastRandomCropData）
- `IaaAugment`: Affine rotate[-45,45] fit_output, Resize[0.1,2]
- `use_color_jitter=false`（官方 small 无 ColorJitter）
- 移除 grad clip（官方 train.py 无 clip）
- eval 用直接拉伸 DetResizeForTest（非 letterbox！之前 letterbox 导致 eval 低估 0.13）
- shrink_ratio 动态 0.4+0.2*epoch/total_epoch（total_epoch 用官方 500 或 100 均可，100 略好）

**关键坑**：
1. **推理 `_preprocess` 必须直接拉伸**（官方 DetResizeForTest），letterbox 会让同一权重 eval 从 0.935 掉到 0.847
2. **MakeShrinkMap mask 是全图**（有效区域，只排除 ignore），不是文字区域！之前当文字区域导致 loss 计算范围错误
3. **DBLoss thresh 用 MaskL1**（mask 内平均），不是 smooth_l1——修后 DBLoss 与官方逐位一致
4. **官方 small det lr=0.001**，medium=0.0005，rec 都是 0.0005
5. **官方 eval 每 N step 用 val 数据**，但本项目 val 15 张与 train 重叠，全图 eval 选 best 反而更好

**权重转换已验证逐位一致**（backbone 118/118），**前向 maps 一致**（mean 0.0161 vs 0.0164）。DBLoss 逐位一致（loss 18.969619 完全相同）。数据流统计对齐（shrink>0.5, mask>0, thresh_mask>0）。

**PaddleX 官方训练方法**（本机 `paddlex:latest` 镜像，内置 PaddleOCR 插件）：
```
docker run --gpus all -w /paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR \
  -v <det_dataset>:/data/det -v <weights>:/weights -v <out>:/output \
  paddlex:latest python tools/train.py \
  -c configs/det/PP-OCRv6/PP-OCRv6_small_det.yml \
  -o Global.epoch_num=100 Global.save_model_dir=/output/det \
     Global.pretrained_model=/weights/PP-OCRv6_small_det_pretrained.pdparams \
     Train.dataset.data_dir=/data/det 'Train.dataset.label_file_list=["/data/det/train.txt"]' \
     Train.loader.batch_size_per_card=8 Eval.dataset.data_dir=/data/det 'Eval.dataset.label_file_list=["/data/det/val.txt"]'
```
PaddleX 官方 small det 训练 100 轮 hmean **0.926**（recall 0.968），rec small 训练 acc **0.9975**。这是 pytorch-ocr 训练无法企及的。
```

## PaddleX 训练框架（已恢复，2026-08）

### 架构

- `TrainFramework.PADDLEX = "paddlex"`（PG enum `trainframework` 一直含 PADDLEX，无需迁移）
- 镜像 `paddlex:latest`（内置 PaddleOCR，`/paddlex_workspace/paddlex/repo_manager/repos/PaddleOCR`）
- det/rec 区分：`hyperparams.mode`（"det"/"rec"），模型规格 `hyperparams.model_size`（tiny/small/medium）
- 训练命令：`_build_paddlex_ocr_cmd`（scheduler.py）→ `bash -c "cd ... && python tools/train.py -c configs/{det,rec}/PP-OCRv6/PP-OCRv6_{size}_{mode}.yml -o <单个 -o + 空格分隔 opts>"`
- 执行器：`PaddleXOCRDet/RecExecutor`（paddlex_executor.py），det/rec 用 mode 派发
- 数据导出：`_export_paddle_ocr`（exporter.py）→ `<out>/{det,rec}/dataset/{train,val}.txt + images/`（PaddleX JSON `[{"transcription","points"}]`，label 带 `images/` 前缀）
- 产物：`<out>/{det,rec}/{best_accuracy,latest}.pdparams` + `config.yml`（export_model 支持查找）
- eval：容器内脚本 `_PADDLEX_EVAL_SCRIPT`（eval_scheduler.py）加载 .pdparams 跑 `program.eval` → `EVAL_METRIC_JSON {precision,recall,hmean}`
- predict：`infer_det.py`/`infer_rec.py`（`Global.pretrained_model=.pdparams`）
- deploy：`_generate_paddlex_server_script`（deploy_executor.py）FastAPI det+rec，需 rec_model_path

### 关键坑

1. **PaddleOCR `-o` 用 `nargs='+'`，多个 `-o` 时 argparse 只保留最后一个**！必须单个 `-o` + 所有 key=value 空格分隔。label_file_list 用单引号包裹（bash -c 内）。
2. **DataLoader 需要大 /dev/shm**：`run_container` 加 `shm_size="4g"`（PaddleOCR num_workers>0 时 BUS error）。
3. **eval loader 默认 batch_size_per_card=1**（det 图 shape 不同无法 batch），不要覆盖成 >1。
4. **rec MultiHead 需要 `out_channels_list`**（从 character_dict 算 char_num），build_model 前注入（对齐 tools/eval.py）。det 不需要。
5. **rec 用官方默认词表** `ppocr/utils/dict/ppocrv6_dict.txt`（与官方预训练权重匹配），不要覆盖 character_dict_path。
6. `program.preprocess(is_train=False)` 的 `sys.argv` 需含 `-c` + `-o`；容器内脚本要先 `os.chdir(PaddleOCR目录)` + sys.path 加 PaddleOCR。
7. 预训练权重 URL：`https://paddle-model-ecology.bj.bcebos.com/paddlex/official_pretrained_model/PP-OCRv6_{size}_{det|rec}_pretrained.pdparams`（executor 下载到 pretrained_host）。

### 验证结果（真实容器）

- det small 从头 3ep：loss 14.8→13.5，`save model`，`best metric hmean: 0`（ep 太少）
- det small pretrained 1ep：`load pretrain successful`，loss 4.35（权重生效）
- rec tiny 从头 2ep：acc 指标正常记录
- eval det（15 val 图）：hmean **0.795**，precision 0.695，recall 0.928
- deploy server：det 模型加载 + 单图 75 框 + rec 模型加载

### 测试

`backend/tests/test_paddlex_removal.py` 已改为 PaddleX 支持测试（枚举/权重规格/cmd 构建），64 测试全通过。

## AI 管理模块（v2，进行中）

- 位置：后端 `backend/app/plugin/module_ai/`（自动发现，容器前缀 `/ai`）；前端 `frontend/src/views/module_ai/`。
- 结构：
  - `providers/` 提供商 CRUD + `GET /ai/providers/remote-models/{id}`（拉远端模型列表）
  - `provider/` 模型配置 CRUD（归属 provider、usage/capabilities/context_window、自定义请求头）+ `/ai/model/test` 连接测试
  - `assistant/` 工具调用助手：`POST /ai/assistant/chat`（非流式）、`POST /ai/assistant/stream`（SSE：`reasoning`/`delta`/`tool`/`done`）
  - `overview/` 调用日志 `ai_call_logs` + `GET /ai/overview/stats`
  - `report/` AI 报告
- 新控制台（旧 Agno 聊天/记忆页已 hidden 下线，父菜单 redirect `/ai/overview`）：
  - `/ai/overview` 控制台、`/ai/playground` 运行台、`/ai/provider`、`/ai/model`、`/ai/report`
- 运行时模型解析：模型 → 所属 provider → env（`OPENAI_*`）；`usage` 为空视为通用（兼容旧数据）。
- opencode 网关（`opencode.ai`）需 `x-opencode-session` 头：`provider/service.build_headers` 自动注入，另支持模型/提供商自定义头。

### 前端视觉约束（重要）
- AI 页面**必须与既有模块风格一致**（参考 `module_system/param`）：直接复用 Element Plus 组件（`el-card/el-descriptions/el-table/el-form/el-tag/el-statistic`）与 `--el-*` 变量；**不要自造主题化外壳/自定义配色**（`styles/ai-console.css` 的自定义观感曾被否定，需按框架组件重做）。
- 完成界面后**用无头浏览器截图 + 视觉分析**（`vision-recognition` 技能）核对，避免与框架割裂。

### 连接超时（QueuePool 耗尽）排查与修复
- 现象：长时运行或大量 e2e 后，登录/接口返回"请求超时"；日志 `QueuePool limit of size ... overflow ... reached, connection timed out`。
- 修复：调大连接池 —— `setting.py` 与 `env/.env.dev` 的 `POOL_SIZE=20`、`MAX_OVERFLOW=40`、`POOL_TIMEOUT=30`，保留 `POOL_RECYCLE=1800`、`POOL_PRE_PING=true`；出现时先重启后端。
- 排查建议：关注流式接口/长事务是否长期占用会话；`OperationLogRoute` 会在响应后另开会话写日志。

## 工程原则：优先成熟第三方库（用户强制要求）

- **能用成熟库就不要手撸**（网络/流式/解析/图表/编辑器/日期等通用能力）。
- **只选维护活跃**的项目，避免停更/僵尸库；引入前先调研（star/最近发布/issue 活跃度）。
- 选型要有依据并写进设计与账本；优先 Web 事实标准（如 Vercel AI SDK）。

### 流式（SSE）选型结论
- 浏览器原生 `EventSource` 仅支持 GET、无法带 body/自定义头 → **聊天类必须用 fetch POST + ReadableStream 解析 SSE**。
- **推荐：Vercel AI SDK**（`ai` v5 + `@ai-sdk/vue` 的 `useChat`）：负责传输/流式/消息状态/工具与推理分片，维护活跃、跨框架。
- 解析层备选：`eventsource-parser`（AI SDK 亦使用）。
- 不推荐：`@microsoft/fetch-event-source`（发布基本停滞）。
- 生产常见坑：压缩中间件/反向代理会**缓冲**导致"整块才到"；需 `Cache-Control: no-transform` + `X-Accel-Buffering: no`，并避免压缩 SSE。
- 现状：AI 聊天当前是手写 SSE 解析（`frontend/src/api/module_ai/assistant.ts`），**待迁移到 Vercel AI SDK**。

### 编辑器 / 表单构造类 UI 选型结论（用户强制要求）
- **凡“编辑器/构造器”类交互（条件树、规则/公式编辑器、代码编辑器、富文本、表格字段构造、查询构造等），必须采用成熟第三方组件，禁止手写实现**（用 `el-card`+`el-tree`+表单自己拼装也属手写，不允许）。
- 选型门槛：MIT/Apache 等宽松许可、维护活跃（近一年有发布）、Vue 3 原生、TypeScript 类型完整。
- 引入前必须在设计与账本写明候选对比（许可/最近发布/star/依赖洁净度）与落选原因。

#### SP5-a 规则编辑器（条件树）选型候选
| 包 | 许可 | 最近发布 | 评估 |
|----|------|----------|------|
| `@svar-ui/vue-filter`（FilterBuilder） | MIT | 2026-09（活跃） | Vue 3 原生 + 嵌套 AND/OR + JSON 进出 + TS；生态新（star 少），**首选** |
| `@syncfusion/ej2-vue-querybuilder` | 商业许可 | 2026-09（很活跃） | 最成熟（217 版本），但需商业授权，暂不采用 |
| `vue3-advanced-query-builder` | MIT | 2023-09（停更 ~3 年） | 违反“维护活跃”门槛，落选 |
| `@form-create/element-ui` | MIT | 2024-12 | 是表单构造器而非条件构造器，仍需自定义嵌套逻辑，备选 |

- 注意：多数第三方 query builder 只支持 AND/OR（不支持一元 NOT）→ 叶子层面的否定用算子表达（如 `attribute op=ge`），条件树的 `not` 仅在后端兼容。

#### 集成坑（SP5-a 实测）
- `@svar-ui/vue-filter` 的按钮是**无 `type` 的原生 `<button>`**；放进 Element Plus `el-form`（渲染裸 `<form>`）时点「Add filter/Apply」会触发表单提交导致**整页刷新、对话框数据全丢**。修复：在包裹元素上加 `@submit.prevent`。
- 该库 `all.css` 必须配 `<Willow :fonts="false">` 包裹，否则无样式；主题变量定义在 `.wx-willow-theme` 上，覆盖样式需用**非 scoped** 选择器。
- 该库**不支持自定义 value 编辑组件、不支持按字段禁用/限制算子**（算子由 field `type` 推导）；因此异构叶子参数统一放到「参数区」编辑，条件树只选 field + 算子 + 值。
- 画布（Konva）容器若用 `ResizeObserver` 观测**被 Konva 自身撑大**的元素会形成自反馈锁定尺寸 → 必须观测外层包裹容器。
