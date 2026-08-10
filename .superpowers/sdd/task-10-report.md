# Task 10 Report: 清理与回归验证

## Status: DONE_WITH_CONCERNS

## Commit
- `db1966f` chore(train): temp dir cleanup and regression verification

## 1. Migration (`f1a2b3c4d5e6`) on live dev DB

### Problem found and fixed
The migration as committed was **unrunnable against any DB**: the new `train_model_repos` table declared `sa.Enum(name="trainframework")` with **no values**, causing SQLAlchemy to emit `CREATE TYPE trainframework AS ENUM ()`, which collided with the already-existing PG type (used by `train_models.framework`). This made `alembic upgrade` fail with `DuplicateObjectError`.

**Fix**: switched to `postgresql.ENUM("PADDLEX", "ULTRALYTICS", name="trainframework", create_type=False)` so the existing enum is reused and no `CREATE TYPE` is emitted (verified `postgresql.ENUM` honors `create_type`, while generic `sa.Enum` silently ignores it).

### Additional issue: leftover empty table
A leftover empty `train_model_repos` table existed (0 rows) from a prior partial attempt / the running backend's `create_all` (model is committed, migration wasn't applied). It was dropped before re-running the migration.

### Final migration output
```
INFO  [alembic.runtime.migration] Running upgrade e5f6a7b8c9d0 -> f1a2b3c4d5e6
```
No errors. `alembic_version` is now `f1a2b3c4d5e6`.

### Data verification (after migration)
```
alembic_version=f1a2b3c4d5e6
repos=29 orphan=0 double_v=0 total_models=41 repos_without_latest=0
```
- 29 repos (distinct names), all 41 old `train_models` rows linked (`repo_id` set, 0 orphan)
- 0 double-`v` versions (`vv1` → `v1` normalization worked)
- All 29 repos have `latest_version_id` backfilled

## 2. Backend restart

- Stopped all python processes; started `uv run main.py run --env=dev` (uvicorn dev mode, reload enabled).
- **captcha/get still returns 500**, but with message `未开启验证码服务` — because `CAPTCHA_ENABLE = false` in `backend/env/.env.dev`. This is a **pre-existing config condition, NOT the migration issue** described in the brief (the "no train_model_repos table" 500 was from the old schema; the schema is now correct).
- **Login works**: `POST /api/v1/system/auth/login` returns 200 with access_token (captcha disabled in dev, so login succeeds).

## 3. Repo/version APIs end-to-end

```
login status: 200
repos status: 200, total=29
  repo 2 ultralytics_test version_count=1
  repo 3 e2e_model        version_count=1
  repo 4 production_test  version_count=5   (DB real count = 5 ✅)
  repo 5 detection_yolo   version_count=5   (DB real count = 5 ✅)
  repo 1 ac               version_count=1
versions status: 200
  version 2 v1 (ultralytics_test)  — no double-v ✅
double-v versions: []
```
All sampled `version_count` values match the real per-repo row counts in `train_models`. No `vv1` in any version string.

## 4. Cleanup module

- Created `backend/app/plugin/module_train/cleanup.py` with `cleanup_loop(keep_days=7, interval_sec=3600)` per brief.
- Verified all 7 cleanup dirs match dirs actually created in the codebase:
  - `train_output` (service.py:34, scheduler.py:125, controller.py:258)
  - `eval_output` (service.py:409, eval_scheduler.py:67, controller.py:198)
  - `predict_output` (service.py:445, predict_executor.py:68, controller.py:308)
  - `deploy_output` (deploy_executor.py:252, controller.py:526)
  - `model_export` (export_service.py:168)
  - `dataset_export` (service.py:532)
  - `model_export_logs` (export_service.py:70)
- Wired in `app/scripts/init_app.py` after deploy recovery startup (following the existing `asyncio.create_task(...)` pattern, lines 551-553).
- Confirmed the running backend reloaded and logged `临时训练产物目录清理已启动` (17:17:01), so the cleanup loop is active in the live process.

## 5. Regression

| Check | Result |
|-------|--------|
| `uv run pytest tests/ -v` | **36 passed** (2 pre-existing deprecation warnings) |
| `uv run ruff check app/plugin/module_train/cleanup.py app/scripts/init_app.py` | **All checks passed** |
| `uv run ruff check app/alembic/versions/f1a2b3c4d5e6_model_repo_split.py` | **All checks passed** |
| `uv run ruff check app/plugin/module_train/` | 89 errors (all pre-existing; none from cleanup.py) |
| `uv run ruff check app/scripts/` | 11 errors (all pre-existing; none from init_app.py change) |
| `pnpm run type-check` | **0 errors** |
| `npx vite build` | **built in 46.53s** ✅ |

No NEW ruff errors were introduced by this task's changes.

## 6. Files changed
- `backend/app/plugin/module_train/cleanup.py` (new — temp dir cleanup loop)
- `backend/app/scripts/init_app.py` (wire cleanup_loop startup)
- `backend/app/alembic/versions/f1a2b3c4d5e6_model_repo_split.py` (bugfix: reuse existing enum via `postgresql.ENUM(..., create_type=False)`)

## Concerns
1. **captcha/get 500 persists** — not caused by this task. `CAPTCHA_ENABLE = false` in `env/.env.dev` makes the captcha endpoint intentionally return `未开启验证码服务`. The brief's Step 2 expectation (captcha 200) is unachievable without enabling captcha in the env config. Login + business APIs verified working instead.
2. **Migration was fixed post-review** — the committed Task 2 migration was broken (would fail on any DB). The `create_type=False` fix is included in this commit; it was verified against the live dev DB.
3. **Not fully transactional migration rollback** — the leftover table indicates partial DDL persistence on failure in this environment; not blocking, but worth noting for future migration runs.
4. Brief Step 5's full UI smoke (create train task, eval, predict, deploy) was **not** executed (requires frontend/UI + running docker training); API-level verification + unit tests + type-check + build were done instead.
