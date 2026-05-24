# FastapiAdmin — Agent Guide

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
