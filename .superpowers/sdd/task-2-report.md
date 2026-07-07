# Task 2 Report: Schema Changes

## Changes Made
- **`backend/app/plugin/module_train/schema.py`**:
  1. Replaced `TrainEvalCreateSchema`: added `model_id: int | None = None` and `hyperparams: dict = Field(default_factory=dict)`
  2. Replaced `TrainEvalOutSchema`: added `model_id`, `framework`, `hyperparams`, `started_at`, `finished_at`, `created_id` fields
  3. Added `TrainPredictCreateSchema` — supports `source_type` (dataset|upload), `source_dataset_id`, `source_images`, `hyperparams`
  4. Added `TrainPredictOutSchema` — full output schema with framework, source info, result info, timestamps, audit fields

## Git Commit Hash
`a6e7426`

## Verification
Import check `from app.plugin.module_train.schema import TrainEvalCreateSchema, TrainEvalOutSchema, TrainPredictCreateSchema, TrainPredictOutSchema` — **OK**
