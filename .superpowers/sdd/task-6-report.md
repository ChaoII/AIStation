# Task 6 Report: 打通 paddlex 执行链路（训练→评估→预测→部署）

## Status
DONE_WITH_CONCERNS

## What I implemented

### 1. `_export_paddlex` — full PaddleX detection export (`exporter.py`)
Replaced the mkdir+log stub with a complete async implementation:

- **Signature** (adapted from brief): `async def _export_paddlex(dataset_id, task_id, images, output_dir, annotation_task_id=None, train_ratio=0.8, class_names=None)`.
- Downloads each image from RustFS (`s3_client.download_fileobj`) into `images/`.
- Fetches latest annotation record per image (filtered by `annotation_task_id`, `order_by version desc`), consistent with `_export_yolo`.
- Writes Pascal-VOC XML into `annotations/{stem}.xml` — `<size>` from `img.width/height`, `<bndbox>` coords scaled by `img.width/height` (normalized → pixels).
- Writes `train.txt` / `val.txt` (`images/{name}\tannotations/{name}.xml`) with a train/val split (default ratio 0.8, `random.shuffle` first — brief uses 0.8 hardcoded; I made it use the `train_ratio` param that `_export_core` already carries, preserving the brief's default).
- Writes `labels.txt` with sorted unique class names.

**Improvement over the brief** (task instruction #2): brief used `class_{class_id}` names. I resolve real class names from `annotation_task_id`'s `classes` mapping (same pattern as `_export_yolo`), falling back to `class_{id}` when unavailable. `class_names` is passed in from `_export_core` (already computed there) to avoid a duplicate DB query; if not provided the function loads it itself from the annotation task.

### 2. `_export_core` wiring
The `else: _export_paddlex(images, output_dir)` branch now calls
`await _export_paddlex(dataset_id, task_id, images, output_dir, annotation_task_id, train_ratio=train_ratio, class_names=class_names)`.
All args were already in scope. `task_id` is accepted per the brief's signature (not used inside — no ruff issue since it's a param).

### 3. PaddleX training command (`scheduler.py`)
`_build_paddlex_cmd` now emits `paddlex --train --model ... --data /data --epochs ... --batch ... --lr ... --output /output` (added the missing `--train`). `_build_cmd` already dispatches the PADDLEX branch to `_build_paddlex_cmd`; ultralytics path unchanged.

### 4. PaddleX artifact search (`exporter.py:export_model`)
For `framework == "paddlex"`, prepend candidates:
- `{export_dir}/output/best_model/model.pdparams`
- `{export_dir}/best_model/model.pdparams`
- `{export_dir}/exp/best_model/model.pdparams`
- `{export_dir}/output/exp/best_model/model.pdparams`

The existing `best.pdparams` recursive fallback (excluding `.models_cache`) remains as last resort.

### 5. PaddleX eval / predict command branches
`eval_scheduler.py` and `predict_executor.py`:
- **Effective framework resolution**: `TrainEval.framework` / `TrainPredict.framework` are NOT persisted at create time (both `create_eval`/`create_predict` in `service.py` omit the field → default `ULTRALYTICS`). So I infer the real framework from the model version row (`TrainModel.framework`), falling back to the record field. This is a deliberate adaptation of brief Step 5, which branched only on `eval_rec.framework` (would always be ULTRALYTICS in practice and never work for paddlex).
- Eval dataset / predict source dataset export now uses `framework.value` so paddlex gets the PaddleX layout.
- **Command**: paddlex branch → `paddlex --eval --model=/model/{file} --data /data --device {dev}` / `paddlex --predict --model=... --source /data --save_dir /output --device {dev}`. Ultralytics branches byte-identical to before.
- **Docker image**: paddlex → `paddlecloud/paddlex:3.0` (matches `service.py:303` train default); ultralytics → existing `ultralytics/ultralytics:latest`.
- **Predict result collection**: paddlex has no fixed `exp/` subdir, so for paddlex I recursively walk the output dir for images and zip them (relpath from output root). Ultralytics path is unchanged (top-level `exp/`, same files & zip layout).

## TDD evidence
- Wrote `tests/test_paddlex_export.py` first (brief Step 1) with 2 tests:
  - `test_export_paddlex_is_implemented` — inspect-source assert "yaml"/"label"/"json" present.
  - `test_export_paddlex_signature` — asserts `dataset_id`, `task_id`, `output_dir` params exist.
- Ran against the stub → **both FAILED** (only `mkdir`/`log`, no label/json; no new params).
- After implementation → both PASS; full suite **24 passed, 2 warnings**.

## What's tested vs verified-by-inspection
**Tested (unit-level):**
- Test file (2 tests) proving `_export_paddlex` is no longer a stub and has the new signature.
- Full existing suite (24 passed) — confirms no regression in train/eval/predict module imports, task_executor, service/repo logic, type conversion.

**Verified-by-inspection only (honest):**
- The actual runtime behavior of `_export_paddlex` (S3 download + XML writing + train/val files) — **NOT run**: requires a live Postgres + RustFS/S3 + annotated images. This is a known limitation per the task instructions.
- `paddlex --train/--eval/--predict` CLI argument shapes — PaddleX 3.0's exact CLI contract is not confirmed against the real `paddlecloud/paddlex:3.0` image. Commands follow the brief's shapes; flagging as the biggest real-world risk.
- Eval metrics parsing (`_parse_val_metrics`) is YOLO-specific; paddlex eval output will not parse into `precision/map50/...`, so eval metrics will be sparse for paddlex. Eval still completes SUCCESS/FAILED based on exit code.
- Docker image selection for eval/predict (`paddlecloud/paddlex:3.0`) mirrors the train path's default but was not verified to exist/pull.

## Files changed
- `backend/app/plugin/module_train/exporter.py` — `_export_paddlex` full impl, `_export_core` wiring, `export_model` paddlex candidates.
- `backend/app/plugin/module_train/scheduler.py` — `_build_paddlex_cmd` adds `--train`.
- `backend/app/plugin/module_train/eval_scheduler.py` — framework inference + command/docker-image branches.
- `backend/app/plugin/module_train/predict_executor.py` — framework inference + command/docker-image branches + paddlex result collection.
- `backend/tests/test_paddlex_export.py` — new.

## Self-review findings
- Kept all ultralytics code paths byte-identical (diff confirms).
- Result-collection refactor preserves previous ultralytics behavior exactly (same files, same zip relpaths).
- `class_names` resolution matches `_export_yolo`'s pattern; duplicate DB query avoided by passing from `_export_core`.
- Ruff: `scheduler.py`, `eval_scheduler.py`, `predict_executor.py`, `tests/test_paddlex_export.py` — **all pass**. `exporter.py` still has 2 pre-existing errors (F841 at old line 127, B007 at old line 289) — confirmed pre-existing via `git stash` check, untouched, unrelated to this task.

## Concerns
1. **PaddleX CLI contract unverified** — `paddlex --train/--eval/--predict` arg shapes are best-effort per the brief; must be validated against the real image when Docker infra is available.
2. **Framework inference relies on `TrainModel.framework`** — since `create_eval`/`create_predict` never set the record's `framework` field. If a user evaluates/predicts a paddlex model, inference works; but a follow-up should persist `framework` at create time (frontend + schema + service) to remove the reliance.
3. **Paddlex eval metrics won't parse** with the YOLO-only `_parse_val_metrics`.
4. `_export_paddlex`'s `task_id`/`dataset_id` params are unused inside (kept for signature parity with the brief); harmless but noted.

## Fix note (review finding, commit `8a3a63c`)

**Issue**: `eval_scheduler.py` / `predict_executor.py` called `pull_image(DOCKER_IMAGE)` (ultralytics) BEFORE framework inference, then passed the resolved `paddlecloud/paddlex:3.0` image to `run_container` (which uses `pull=False`) without ever pulling it → `ImageNotFound` on hosts without a cached paddlex image.

**Fix**: In both executors, framework resolution now happens FIRST; `docker_image` is derived from the resolved framework (paddlex → `paddlecloud/paddlex:3.0`, else `DOCKER_IMAGE`); THAT image is pulled; and the same `docker_image` is passed to `run_container`. Ultralytics output remains byte-identical. `scheduler.py` `TrainExecutor._execute` already pulls `task.docker_image` (set to the paddlex image at create time by `service.py`) — verified correct, no change. Verified: `24 passed, 2 warnings`; ruff clean.
