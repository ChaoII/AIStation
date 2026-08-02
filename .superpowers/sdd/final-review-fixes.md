# Final Review Fixes — model-train architecture repair

Resolves the 6 Important findings from the whole-branch review of
`249755f..db1966f`. Committed as one fix commit.

## Fix 1: Eval no longer re-marks RUNNING after the container finishes
`eval_scheduler.py` — removed the intermediate `status=RUNNING` + metrics write
after `_get_exit_code`. Metrics (`metrics` / `metrics_log` / `best_metrics` /
`last_metrics`) are now persisted only in the terminal SUCCESS branch, matching
`TrainExecutor._execute`. A crash between exit-code collection and the terminal
transition can no longer leave an eval stuck RUNNING.

## Fix 2: Blocking `container.logs` calls moved off the event loop
Added `get_container_error_tail(container_id, tail=50)` in `docker_utils.py`
(runs `client.containers.get(...).logs(stdout=False, stderr=True, tail=...)` in
an executor; returns `""` on any exception). Replaced the four inline blocking
`container.logs(...)` try/except blocks in `scheduler.py`, `eval_scheduler.py`,
`predict_executor.py`, and `deploy_executor.py` with
`(await get_container_error_tail(container_id)).strip()`, preserving the same
error-message behavior.

## Fix 3: `model_id or model_repo_id` fallback removed
`TrainEvalCreateSchema.model_id` is now required (`model_id: int`), matching
`TrainPredictCreateSchema`. `eval_scheduler.py` and `predict_executor.py` now
pass `model_id` directly to `TrainService._resolve_model_storage` (version id),
never a repo id. `create_eval` already persisted `model_id`; the frontend eval
form requires and always sends it. No callers/tests relied on optional `model_id`.

## Fix 4: PaddleX CLI shapes documented as best-effort
Added `# TODO(paddlex): verify CLI flags against paddlecloud/paddlex:3.0 ...`
at each paddlex command construction site (`_build_paddlex_cmd` in
`scheduler.py`, eval branch in `eval_scheduler.py`, predict branch in
`predict_executor.py`). Noted `_parse_val_metrics` is YOLO-specific and PaddleX
eval metrics will be empty until a PaddleX parser is added; eval still marks
SUCCESS/FAILED by exit code. No attempt to run the real image.

## Fix 5: `recover_orphan_deploys` no longer conflates daemon-down with container-absent
`_container_exists` in `deploy_executor.py` now returns `False` only for
`docker.errors.NotFound` (container genuinely absent); any other exception
(daemon unreachable) returns `True` ("can't prove absent"), so recovery skips
the deploy instead of marking it failed. `recover_orphan_deploys` therefore
marks failed only when absence is definitive.

## Fix 6: Deploy port reservation TOCTOU hardened
In `deploy_executor.py`, `run_container` is wrapped in a
`docker.errors.APIError` handler: on a port-conflict error (`port is already
allocated` / `address already in use`, via `_is_port_conflict_error`) the port
is re-selected with `_find_available_port(excluded={host_port})`, the DB row is
updated, and the container is launched once more (single retry).

## Verification
- Backend: `uv run pytest tests/` → 36 passed
- Ruff: touched files (`eval_scheduler.py`, `scheduler.py`,
  `predict_executor.py`, `deploy_executor.py`, `docker_utils.py`, `schema.py`,
  `tests/`) → clean; remaining FAST002 findings are pre-existing in untouched
  `controller.py`
- Frontend: `pnpm run type-check` → 0 errors
