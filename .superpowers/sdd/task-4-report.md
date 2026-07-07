# Task 4 Report: Controller — Predict Endpoints + Enhanced Eval Endpoints

## Changes Applied

**File:** `backend/app/plugin/module_train/controller.py`

1. **Updated imports** (lines 1, 5-8, 10-12):
   - Added `UploadFile, File` to fastapi import
   - Added `TrainPredictCreateSchema` to schema imports
   - Added `start_evaluation, stop_evaluation` from `.eval_scheduler`
   - Added `start_prediction, stop_prediction` from `.predict_executor`

2. **Enhanced eval endpoints** (lines 83-98):
   - `GET /eval/{eval_id}/detail` — get eval detail
   - `POST /eval/{eval_id}/start` — start evaluation via `start_evaluation()`
   - `POST /eval/{eval_id}/stop` — stop evaluation via `stop_evaluation()`

3. **Added predict endpoints** (lines 130-169):
   - `POST /predict/create` — create prediction task
   - `GET /predict/list` — list prediction tasks
   - `GET /predict/{predict_id}/detail` — get prediction detail
   - `POST /predict/{predict_id}/start` — start prediction via `start_prediction()`
   - `POST /predict/{predict_id}/stop` — stop prediction via `stop_prediction()`
   - `DELETE /predict/delete` — delete prediction tasks
   - `POST /predict/upload` — upload prediction images (multipart file upload)

## Verification

- Python syntax: OK (`py_compile` passes)
- Circular import (`app.core.dependencies` <-> `auth.controller`) is pre-existing and documented in AGENTS.md — does not block normal runtime
