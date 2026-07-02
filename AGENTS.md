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
