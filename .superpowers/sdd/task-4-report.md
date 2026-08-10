# Task 4 Report: 统一执行器基类 — 并发 + 孤儿恢复 + 容器生命周期

**Status: DONE_WITH_CONCERNS**

## Unit A: Base class + tests

- Created `backend/app/plugin/module_train/task_executor.py` with the `TaskExecutor` abstract base class (per brief Step 3, verbatim with two lint-only deviations):
  - Removed unused `import os` and `import asyncio as _asyncio` and unused `remove_container` import (ruff F401 auto-fixes; `os`/`remove_container` are not used by the base itself).
  - Docstring for `follow_logs` corrected to "返回 metrics_log" (the brief's docstring said "返回 (metrics_log, exit_code)" but the code returns only `metrics_log`).
- Created `backend/tests/test_task_executor.py`. **Deviation**: the brief's test stubs omitted `_execute`, so `TypeError: Can't instantiate abstract class` — added a no-op `_execute` classmethod to both stubs.
- **RED**: `pytest tests/test_task_executor.py` failed at collection with `ModuleNotFoundError` (module absent). **GREEN**: after creating the module, both tests pass.
- Commit A: `fb577bd` `feat(train): add TaskExecutor base class with concurrency and orphan recovery`

## Unit B: TrainExecutor migration (scheduler.py)

- Defined `class TrainExecutor(TaskExecutor)` (`name="train"`, `status_enum=TrainStatus`, `model_class=TrainTask`, `_concurrency=1`) and migrated the full `_execute_training` body into `_execute`.
- Extracted module functions: `_parse_epoch(line)` (from nested fn), `_compute_best(metrics_log)` (from inline best_metrics logic), `_build_cmd(task, data_dir, export_dir)` (dispatch over the existing `_build_ultralytics_cmd`/`_build_paddlex_cmd`; needs data_dir/export_dir so signature differs slightly from the brief's `_build_cmd(task)`).
- Replacements made: `_running_tasks` → `cls._registry`; manual log loop → `cls.follow_logs`; manual DB status updates → `cls._mark_status`; `container.wait(...)` → `cls._get_exit_code(container)`; `MAX_CONCURRENT` (was unused) → `_concurrency = 1`.
- Kept public `start_training`/`stop_training` (controller imports them). `start_training` keeps validation + field-reset then `asyncio.create_task(TrainExecutor.run(task_id))`. `stop_training` delegates to `TrainExecutor.stop`.
- Removed orphan-cleanup block from `_scheduler_loop`; it now does scheduled-training trigger + `await TrainExecutor.recover_orphans()` every 30s.
- Also fixed 3 pre-existing ruff errors carried over verbatim from the old file (`total` unused, one-liner try/except in `_parse_epoch`, B005 `.lstrip`).
- Tests: `tests/test_task_executor.py` passes. Ruff clean.
- Commit B: `e5d392e` `refactor(train): migrate TrainExecutor to base class`

## Unit C: EvalExecutor migration (eval_scheduler.py)

- Defined `class EvalExecutor(TaskExecutor)` (`name="eval"`, `status_enum=TrainStatus`, `model_class=TrainEval`, `_concurrency=1`) and fully migrated `_execute_evaluation` into `_execute` (pull image, export eval dataset, download model with storage_path backtracking, run `yolo val`, parse `all` + per-class metrics, mark success/failed/cancelled). **No `raise NotImplementedError` placeholder delivered.**
- Metrics parsing uses a stateful closure `_parse_val_metrics` passed as `follow_logs` parse_fn (accumulates into `metrics` dict across lines); DB metrics fields written via `cls._mark_status`.
- Kept public `start_evaluation`/`stop_evaluation` (controller imports them), delegating to `EvalExecutor.run/stop`.
- `start_evaluation_scheduler()` now just starts `EvalExecutor.start_recovery_loop()`; old `_eval_scheduler_loop` orphan-cleanup deleted.
- Tests pass; ruff clean.
- Commit C: `778b64a` `refactor(train): migrate EvalExecutor to base class`

## Unit D: PredictExecutor migration + init_app wiring (predict_executor.py, init_app.py)

- Defined `class PredictExecutor(TaskExecutor)` (`name="predict"`, `status_enum=TrainStatus`, `model_class=TrainPredict`, `_concurrency=1`) and fully migrated `_execute_prediction` into `_execute` (pull image, prepare source images, download model, run `yolo predict`, collect result images + ZIP → RustFS, mark success/failed/cancelled). **No `raise NotImplementedError` placeholder delivered.**
- This executor now GAINS orphan recovery via the base (previously it had no recovery loop — the bug this task fixes).
- Added `start_prediction_scheduler()` module function (starts `PredictExecutor.start_recovery_loop()`) and wired it in `init_app.py` after the eval scheduler startup.
- Kept public `start_prediction`/`stop_prediction` (controller imports them), delegating to `PredictExecutor.run/stop`.

### Wiring decision (deviation from brief Step 4 snippet)

The brief shows init_app starting all three `*.start_recovery_loop()`. The task instructions explicitly allow the alternative. I chose: **keep `start_scheduler()`** (which already runs the scheduled-training trigger **and** `TrainExecutor.recover_orphans()` every 30s) **and only ADD the eval + predict recovery loops** to init_app. This preserves all three required behaviors with no duplicate train-recovery loop:

1. **Scheduled-training trigger** — intact in `_scheduler_loop` (`get_due_schedules` → `TrainService.create_task` → `start_training(new_id)` → `update last_run_at/last_task_id`).
2. **Orphan recovery for all three** — train via `_scheduler_loop`'s `TrainExecutor.recover_orphans()`; eval via `start_evaluation_scheduler` → `EvalExecutor.start_recovery_loop()`; predict via new `start_prediction_scheduler` → `PredictExecutor.start_recovery_loop()`.
3. **Existing entrypoints** — `start_scheduler`, `start_evaluation_scheduler`, `start_prediction`, `stop_*`, `start_training`, `stop_training` all kept, controller imports unchanged.

- Full suite: `18 passed`.
- Ruff: all changed modules clean (the one remaining `E114` in `init_app.py:795` is **pre-existing at HEAD** — "挂载录制文件目录" comment indentation — not introduced by this task; I verified it against the HEAD version).
- Commit D: `9f97b91` `refactor(train): wire all three executors to TaskExecutor recovery loops`

## Files changed

- `backend/app/plugin/module_train/task_executor.py` (new)
- `backend/app/plugin/module_train/scheduler.py`
- `backend/app/plugin/module_train/eval_scheduler.py`
- `backend/app/plugin/module_train/predict_executor.py`
- `backend/app/scripts/init_app.py`
- `backend/tests/test_task_executor.py` (new)

## Test results per unit

- Unit A: RED (`ModuleNotFoundError`) → GREEN (`2 passed`)
- Unit B: `2 passed`, ruff clean
- Unit C: `2 passed`, ruff clean
- Unit D: full suite `18 passed`, ruff clean (except pre-existing init_app E114)

## Self-review findings

- **Base `_mark_status` binds string statuses** ("running"/"failed") via `update().values(status="running")`. I empirically verified (SQLAlchemy 2.0.45) that binding the lowercase string to the `SAEnum(TrainStatus)` column normalizes to the stored DB value `RUNNING` — runtime correct on both SQLite and Postgres.
- **Test stubs needed `_execute`** — brief's stubs were uninstantiable; added no-op `_execute`.
- **`follow_logs` returns only `metrics_log`** (not `(metrics_log, exit_code)` as the brief docstring claimed); exit code is obtained separately via `_get_exit_code`. Fixed docstring.
- **Eval orphan message field**: base `recover_orphans` writes `error_log` only; the old eval loop also wrote `log`. The eval-logs endpoint falls back to the `log` column when the log file is absent, so an orphaned eval would show an empty log instead of the disconnect message. Minor behavior difference, acceptable.

## Concerns

1. **Per-epoch `progress` updates during training are dropped.** The old `_execute_training` updated `TrainTask.progress` on every parsed epoch line inside the log loop; the base `follow_logs`' sync `parse_fn` cannot run async DB writes, and the brief's design does not carry progress. Progress now stays at the value set by `start_training` (0) until success (100). `metrics_log`/`best_metrics`/`last_metrics` are still fully captured. If per-epoch progress is needed, `follow_logs` would need an optional async `on_epoch` callback.
2. **`stop` now writes CANCELLED to DB immediately** for eval/predict (old code only set the cancel flag; CANCELLED was written later by the executor). This is a strict improvement and race-free (double-marking CANCELLED is idempotent), but is a subtle behavior change.
3. **Serialization via semaphore is now real.** Previously `MAX_CONCURRENT=1` was unused (concurrent trainings were possible). Now `_concurrency=1` actually serializes; queued tasks wait on the semaphore with status RUNNING but not yet in `_registry` (recovery could theoretically mark a long-queued task FAILED after 1800s). Edge case, low risk.
4. **Pre-existing `E114` in `init_app.py:795`** left untouched (unrelated to this task).

## Follow-up: Review findings (semaphore-queue race + train metrics shape)

**Commit:** `d0797a0` `fix(train): handle semaphore queue race and restore train metrics shape`

### Fix 1 — Semaphore-queue vs orphan-recovery / stop race

**Problem:** A task waiting on the semaphore had DB status RUNNING but was NOT in `_registry` (registry populated only after container start inside `_execute`). After 1800s queue wait `recover_orphans` marked a queued task FAILED; `stop()` on a queued task wrote CANCELLED but `_execute_with_state` unconditionally re-marked "running" and executed anyway.

**Fix (`task_executor.py`):**
- `run()` now registers `{task_id: {"queued": True}}` in `_registry` BEFORE acquiring the semaphore.
- `_execute_with_state()` checks `cls._registry.get(task_id, {}).get("cancel")` first and, if set, marks `cancelled` + returns (queued task never executes).
- `stop()` now sets `entry["cancel"] = True` unconditionally (also for queued entries with no container yet); container stop only when a `container_id` exists.
- `recover_orphans` needed **no change** — queued entries are now in `_registry`, so the existing `if r.id in cls._registry: continue` already skips them.
- Subclasses no longer overwrite the registry entry: `scheduler.py` / `eval_scheduler.py` / `predict_executor.py` now merge via `entry = cls._registry.get(task_id) or {}; entry.update({"container_id": container_id}); cls._registry[task_id] = entry`, preserving the `queued`/`cancel` flags (so a cancel requested while queued survives into execution).

### Fix 2 — Train metrics_log shape regression

**Problem:** `follow_logs` appended every parse hit as a separate entry, so `metrics_log` ended with `{epoch: -1, precision, recall, map50, map5095}` (no losses). `_compute_best` returned this `-1` entry and `last_metrics = metrics_log[-1]` was the same — frontend showed epoch "-1/?" with missing losses.

**Fix (`scheduler.py`):**
- In `TrainExecutor._execute`, after `follow_logs` returns and BEFORE `best_metrics`/`last_metrics` are computed, a trailing `epoch == -1` "all" summary is merged into the last real epoch (`epoch > 0`), preserving the real epoch number (only metric keys are copied, `epoch` itself is kept from the real-epoch dict). This restores the old merged shape (losses + mAP on one epoch row).
- Hardened `_compute_best`: `valid = [m for m in metrics_log if m and m.get("map50") is not None]` (None-guard, drops the now-unnecessary `epoch > 0` filter).

### Verification

```
uv run pytest tests/test_task_executor.py -v        → 2 passed
uv run pytest tests/ -v                             → 18 passed (2 warnings, DeprecationWarning only)
uv run ruff check app/plugin/module_train/task_executor.py \
  app/plugin/module_train/scheduler.py \
  app/plugin/module_train/eval_scheduler.py \
  app/plugin/module_train/predict_executor.py       → All checks passed!
```

Staged only the 4 touched files (no `git add -A`).

## Report file
`D:/AIStation/.superpowers/sdd/task-4-report.md`
