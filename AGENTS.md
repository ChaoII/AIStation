# AIStation — Agent Guide

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
| `frontend/src/styles/train-detail.css` | `.info-cards`、`.chart-row`、`.metric-grid` 使用 CSS Grid | 页面已知有 scoped CSS 问题，但不影响此文件（全局引入） |
| `frontend/src/views/dashboard/workplace.vue` | 多个 `display: flex/grid` + `@media (width <= ...)` | 使用 scoped 样式，风险较低但已有非标准媒体查询语法 |
| `frontend/src/styles/dashboard.css` | `.dash-metrics`、`.dash-footer` 依然使用 CSS Grid | 当前未出问题，但重蹈覆辙风险高，建议逐步迁移到 el-row/el-col |

### 媒体查询语法警告
项目内多处使用非标准语法 `@media (width <= Xpx)`，这在部分浏览器/场景下可能表现不一致。建议统一改用标准写法：
```css
/* ❌ 非常规，可能在某些场景失效 */
@media (width <= 1100px) { ... }

/* ✅ 标准写法，兼容性最好 */
@media (max-width: 1100px) { ... }
```
```
