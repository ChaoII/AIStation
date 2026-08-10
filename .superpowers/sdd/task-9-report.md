# Task 9 Report — 部署功能修正（端口竞态 + 容器存活探活 + 回收）

## What was implemented

### 1. Port-race fix (`deploy_executor.py`)
- Extracted two testable pure helpers:
  - `_is_host_port_used(port)` — 127.0.0.1 socket probe.
  - `_docker_published_host_ports()` — collects Docker `HostConfig.PortBindings` host ports for **all** containers (incl. stopped), wrapped in try/except so a missing/unreachable daemon degrades to an empty set.
- `_find_available_port(start, end, excluded=None)` now excludes three sources: caller-provided reserved set (DB), Docker-published ports, and live socket bindings. This closes the main race where two deploys pick the same free 127.0.0.1 port while a container already publishes it.
- In `_execute_deployment`, when auto-selecting a port, the function now loads all DB-reserved `host_port` rows and passes them as `excluded`, then **immediately persists** the chosen port to DB before container start. This is the "reservation lock" from the brief.

### 2. Health probe + container anomaly detection
- New `_wait_server_healthy(container, host_port, timeout=60, interval=2.0)`: polls `/health` every 2s up to 60s; also polls `container.status` each cycle and fails fast if the container is `exited`/`dead`. Returns "" on healthy, else a reason string.
- Integrated into `_execute_deployment` after marking `running`: on failure it removes the container and marks the deploy `failed` with `error_log="deploy health check timeout"` (or the container-exit reason), then returns. Existing log-follow + `container.wait` flow preserved after a successful probe.
- `stop_deployment` now sets `entry["cancel"] = True` (previously the flag existed but was never set), so a user-initiated stop during the health window no longer gets clobbered to `failed` by the probe-failure path.

### 3. Orphan-deploy recovery
- New `recover_orphan_deploys()`: queries `TrainDeploy` where `status IN ('running','deploying')`; if the `container_id` doesn't exist in Docker (or is null), marks it `failed` with `error_log="deploy 会话已断开（容器丢失）"`.
  - Note: `deploying` was added beyond the brief's `running`-only scope because `_deploy_running` is in-memory — a `deploying` row surviving a backend restart is provably orphaned.
- New `start_deploy_recovery()` wrapper (try/except + log) wired into `init_app.py` lifespan via `asyncio.create_task(...)`, following the `start_prediction_scheduler` pattern.

### 4. Idempotent `start_deployment`
- Now skips if the deploy row is missing or already `deploying`/`running` — satisfies the brief's "start_deployment 幂等" Produces contract and prevents double-spawned deploy tasks.

## TDD evidence
- Test file `tests/test_deploy_fixes.py` written **before** implementation. First run failed at collection (`ImportError: cannot import name '_docker_published_host_ports'`) — red phase confirmed.
- After implementation: `uv run pytest tests/test_deploy_fixes.py -v` → **5 passed** (bounds, in-range, excluded-reservation, socket-detect, docker-set smoke).
- Full suite: `uv run pytest tests/ -v` → **36 passed, 2 pre-existing warnings**.

## Tested vs verified-by-inspection
- **Tested (pure logic):** port bounds/in-range selection, excluded-set reservation, `_is_host_port_used` socket detection, `_docker_published_host_ports` returns a set even with a live daemon.
- **Verified-by-inspection only (require a real container/daemon):**
  - Health probe success/timeout path in `_execute_deployment` (60s polling, fail → mark failed + remove container).
  - Container `status` anomaly detection during probe.
  - `recover_orphan_deploys` DB transition for a running-but-container-less deploy.
  - Docker daemon is actually live in the test env (`GET /version 200` seen in logs), but no inference containers were started per constraint.

## Files changed
- `backend/app/plugin/module_train/deploy_executor.py` — helpers + port race + health probe + orphan recovery + idempotent start + cancel flag.
- `backend/app/scripts/init_app.py` — wire `start_deploy_recovery()` at startup; also fixed a pre-existing E114 indentation lint on line 799 so the task's ruff target passes.
- `backend/tests/test_deploy_fixes.py` — new (5 tests).

## Self-review findings
- `container.status` property access is an API call, correctly wrapped in `run_in_executor` so it doesn't block the loop.
- Double `remove_container` in the probe-failure path (explicit + `finally`) is safe — `remove_container` swallows `NotFound`.
- Detached `deploy` attribute access (host_port/api_key/device) after the first session block relies on the object never having been committed/expired; this matches the pre-existing pattern (api_key/device already read this way).
- `select(TrainDeploy.host_port).where(host_port > 0)` includes all statuses — intentional: `host_port` is sticky (failed/stopped deploys keep their port reserved), matching the brief's "acceptable" note.
- Port remains reserved in DB after a failed deploy (host_port sticky) — confirmed acceptable per task instructions.

## Concerns
- **Residual micro-race:** two concurrent first-time deploys could theoretically pick the same port before either persists it (sync `_find_available_port` then awaited DB write). The DB+Docker+socket exclusion set makes the practical window negligible; one container would fail to bind and be marked failed. Not eliminated with a true lock (would require serialization), but within accepted risk.
- `recover_orphan_deploys` won't catch a deploy whose container exists but whose `/health` is dead — out of brief scope (brief only covers "no container").
- Live-daemon Docker API calls during tests add ~20s to the deploy test file run time; harmless without a daemon (empty set fallback).

## Review fix (post-review, commit `62d30fe` follow-up)

### Finding: Docker API calls blocked the event loop
- `_docker_published_host_ports()` called `docker_client.containers.list(all=True)` synchronously from async `_execute_deployment`.
- `_container_exists()` called `docker_client.containers.get` synchronously from async `recover_orphan_deploys`.
- Both blocked the loop for tens of ms, violating the `run_in_executor` convention used elsewhere in `docker_utils.py`.

### Fix
- `_docker_published_host_ports` → `async def`; the Docker listing moved into an inner `_sync()` run via `asyncio.get_event_loop().run_in_executor(None, _sync)`. Graceful degradation (empty set on daemon failure) preserved.
- `_container_exists` → `async def`; the `containers.get` moved into an inner `_sync()` via `run_in_executor`, swallowing all exceptions → `False` (behavior unchanged).
- `_find_available_port` stays **sync** and pure: added a `docker_used: set[int] = frozenset()` param so port-selection logic remains unit-testable. Caller `_execute_deployment` now `await`s `_docker_published_host_ports()` first and passes the result in.
- Call sites updated: `_execute_deployment` uses `await _docker_published_host_ports()`; `recover_orphan_deploys` uses `await _container_exists(...)`.
- Tests updated only where the async signature required it: `_docker_published_host_ports()` calls wrapped in `asyncio.run(...)` in `tests/test_deploy_fixes.py`. `_find_available_port` test calls unchanged.

### Verification
- `uv run pytest tests/test_deploy_fixes.py -v` → **5 passed**.
- Full `uv run pytest tests/ -v` → **36 passed, 2 pre-existing warnings**.
- `uv run ruff check app/plugin/module_train/deploy_executor.py tests/test_deploy_fixes.py` → all checks passed.
- No remaining synchronous Docker calls on the event loop in `deploy_executor.py` (Docker API access in `docker_utils.py`/`export_service.py` already uses `run_in_executor`).
